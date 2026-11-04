import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../../exam-web/teacher.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../../exam-web/teacher.js", import.meta.url), "utf8");
const overview = [
  { email: "one@example.com", game: "game01", scope_mode: "exercise", completed_tasks: 1 },
  { email: "one@example.com", game: "game01", scope_mode: "exam", exam_code: "EXAM-001", completed_tasks: 1 },
  { email: "two@example.com", game: "game01", scope_mode: "exercise", completed_tasks: 1 },
  { email: "other@example.com", game: "game02", scope_mode: "exercise", completed_tasks: 1 },
];

function passedTask(overrides = {}) {
  return {
    game: "game01", task_id: "task01", mode: "exercise", exam_code: "",
    status: "completed", skipped: false, total_points: 5, current_phase: "cleanup",
    created_at: "2026-01-01T10:00:00Z", completed_at: "2026-01-01T11:00:00Z",
    updated_at: "2026-01-01T11:00:00Z", ...overrides,
  };
}

function report(overrides = {}) {
  return {
    game: "game01", task_id: "task01", mode: "exercise", exam_code: "",
    phase: "check", test_result: "OK", time: "2026-01-01_10-59-00",
    report_url: "https://reports.example.com/pass.html", ...overrides,
  };
}

function defaultDetail(email) {
  return email === "one@example.com"
    ? {
      completed_only: true,
      task_states: [passedTask(), passedTask({ mode: "exam", exam_code: "EXAM-001", total_points: 10 })],
      reports: [
        report({ test_result: "FAIL", report_url: "https://reports.example.com/fail.html" }),
        report(),
        report({ mode: "exam", exam_code: "EXAM-001", report_url: "https://reports.example.com/exam.html" }),
      ],
    }
    : { completed_only: true, task_states: [passedTask({ task_id: "task02", total_points: 0 })], reports: [] };
}

function createHarness(detail = defaultDetail) {
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, {
    value: "", textContent: "", disabled: false, listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
  }]));
  for (const [id, element] of elements) {
    let markup = "";
    Object.defineProperty(element, "innerHTML", {
      get() { return markup; },
      set(value) {
        markup = value;
        if (id.startsWith("filter") || id.startsWith("sort")) {
          element.value = value.match(/<option value="([^"]*)"/)?.[1] || "";
        }
      },
    });
  }
  elements.get("exportCompletedRecords").disabled = true;
  elements.get("sortBy").value = "game";
  elements.get("sortDirection").value = "asc";
  const storage = new Map();
  const requests = [];
  const blobs = new Map();
  const downloads = [];
  class BrowserURL extends URL {
    static createObjectURL(blob) {
      const url = `blob:${blobs.size}`;
      blobs.set(url, blob);
      return url;
    }
    static revokeObjectURL(url) { blobs.delete(url); }
  }
  const context = vm.createContext({
    window: { __K8S_PORTAL_CONFIG__: { baseUrl: "https://api.example.com" } },
    document: {
      getElementById(id) {
        assert.ok(elements.has(id), `Missing HTML element: ${id}`);
        return elements.get(id);
      },
      createElement(tag) {
        assert.equal(tag, "a");
        return { click() { downloads.push({ filename: this.download, blob: blobs.get(this.href) }); } };
      },
      body: { appendChild() {}, removeChild() {} },
    },
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    URL: BrowserURL, Blob,
    async fetch(input, options) {
      const url = new URL(input);
      requests.push({ url, options });
      assert.equal(options.headers["x-api-key"], "teacher-key");
      const payload = url.pathname.endsWith("/overview")
        ? { students: overview }
        : await detail(url.searchParams.get("studentEmail"), url.searchParams);
      return { json: async () => ({ status: "OK", ...payload }) };
    },
  });
  vm.runInContext(script, context);
  elements.get("apiKey").value = "teacher-key";
  return {
    elements, requests, downloads, blobs, context,
    load() { return vm.runInContext("loadOverview()", context); },
    select(id, value) {
      elements.get(id).value = value;
      elements.get(id).listeners.change();
    },
    export() { return elements.get("exportCompletedRecords").listeners.click(); },
    get detailRequests() { return requests.filter(({ url }) => url.pathname.endsWith("/student")); },
  };
}

test("passed-task export requires a loaded overview and a selected game", async () => {
  const harness = createHarness();
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, true);
  await harness.export();
  assert.equal(harness.requests.length, 0);
  await harness.load();
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, true);
  await harness.export();
  assert.equal(harness.detailRequests.length, 0);
  harness.select("filterGame", "game01");
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, false);
});

test("exports every matching account once with all attempts and tasks without reports", async () => {
  const harness = createHarness();
  await harness.load();
  harness.select("filterGame", "game01");
  assert.equal(harness.elements.get("filterExamCode").value, "");
  assert.equal(harness.elements.get("filterExamCode").disabled, false);
  await harness.export();
  assert.deepEqual(harness.detailRequests.map(({ url }) => url.searchParams.get("studentEmail")), [
    "one@example.com", "two@example.com",
  ]);
  for (const { url } of harness.detailRequests) {
    assert.equal(url.searchParams.get("game"), "game01");
    assert.equal(url.searchParams.get("completedOnly"), "true");
    assert.equal(url.searchParams.has("mode"), false);
    assert.equal(url.searchParams.has("examCode"), false);
  }
  assert.equal(harness.downloads.length, 1);
  const csv = await harness.downloads[0].blob.text();
  assert.match(harness.downloads[0].filename, /^teacher-passed-tasks-game01-.*\.csv$/);
  assert.equal(csv.split("\n").length, 5);
  assert.match(csv, /"Task Started","Task Completed","Task Updated"/);
  assert.match(csv, /"FAIL"/);
  assert.match(csv, /"exam","EXAM-001","task01"/);
  assert.match(csv, /"two@example.com","game01","exercise","","task02","completed","cleanup","0"/);
  assert.equal((csv.match(/https:\/\/reports.example.com\/exam.html/g) || []).length, 1);
  assert.match(harness.elements.get("exportStatus").textContent, /Exported 3 passed task\(s\) in 4 record row\(s\)/);
  assert.equal(harness.blobs.size, 0);
});

test("scope and exam filters are forwarded and prevent unrelated account requests", async () => {
  const harness = createHarness(() => ({
    completed_only: true,
    task_states: [passedTask({ mode: "exam", exam_code: "EXAM-001" })],
    reports: [],
  }));
  await harness.load();
  harness.select("filterGame", "game01");
  harness.select("filterScope", "exam");
  harness.select("filterExamCode", "EXAM-001");
  await harness.export();
  assert.equal(harness.detailRequests.length, 1);
  const params = harness.detailRequests[0].url.searchParams;
  assert.equal(params.get("mode"), "exam");
  assert.equal(params.get("examCode"), "EXAM-001");
  assert.equal(params.get("studentEmail"), "one@example.com");
});

test("CSV escapes multiline quoted fields and neutralizes spreadsheet formulas", async () => {
  const taskId = '=SUM(1,2)\n"quoted"';
  const harness = createHarness(() => ({
    completed_only: true,
    task_states: [passedTask({ task_id: taskId, total_points: 0 })], reports: [],
  }));
  await harness.load();
  harness.select("filterGame", "game01");
  await harness.export();
  const csv = await harness.downloads[0].blob.text();
  assert.ok(csv.includes(`"'=SUM(1,2)\n""quoted"""`));
  assert.ok(csv.includes('"cleanup","0"'));
});

test("any account error prevents a partial download and restores controls", async () => {
  const harness = createHarness((email) => {
    if (email === "two@example.com") throw new Error("Read failed");
    return defaultDetail(email);
  });
  await harness.load();
  harness.select("filterGame", "game01");
  await harness.export();
  assert.equal(harness.detailRequests.length, 2);
  assert.equal(harness.downloads.length, 0);
  assert.match(harness.elements.get("exportStatus").textContent, /No CSV was downloaded. Read failed/);
  assert.equal(harness.elements.get("apiKey").disabled, false);
  assert.equal(harness.elements.get("filterGame").disabled, false);
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, false);
});

test("an older backend cannot silently export only the 50 recent reports", async () => {
  const harness = createHarness(() => ({ task_states: [passedTask()], reports: [] }));
  await harness.load();
  harness.select("filterGame", "game01");
  await harness.export();
  assert.equal(harness.downloads.length, 0);
  assert.match(harness.elements.get("exportStatus").textContent, /updated teacher API/);
});

test("empty, unfinished, and skipped task results do not produce a CSV", async () => {
  const harness = createHarness(() => ({
    completed_only: true,
    task_states: [passedTask({ skipped: true }), passedTask({ status: "in_progress" })],
    reports: [],
  }));
  await harness.load();
  harness.select("filterGame", "game01");
  await harness.export();
  assert.equal(harness.downloads.length, 0);
  assert.match(harness.elements.get("exportStatus").textContent, /No passed tasks found/);
});

test("an active export blocks duplicates and configuration changes until it finishes", async () => {
  let release;
  const wait = new Promise((resolve) => { release = resolve; });
  const harness = createHarness(async (email) => { await wait; return defaultDetail(email); });
  await harness.load();
  harness.select("filterGame", "game01");
  const exporting = harness.export();
  await harness.export();
  assert.equal(harness.detailRequests.length, 1);
  for (const id of ["apiKey", "loadOverview", "resetState", "filterGame", "filterScope", "exportCompletedRecords"]) {
    assert.equal(harness.elements.get(id).disabled, true, id);
  }
  release();
  await exporting;
  assert.equal(harness.detailRequests.length, 2);
  assert.equal(harness.downloads.length, 1);
  assert.equal(harness.elements.get("loadOverview").disabled, false);
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, false);
});

test("summary export still works and resetting the dashboard disables record export", async () => {
  const harness = createHarness();
  await harness.load();
  harness.select("filterGame", "game01");
  harness.elements.get("exportOverview").listeners.click();
  assert.equal(harness.downloads.length, 1);
  assert.match(harness.downloads[0].filename, /^teacher-dashboard-/);
  assert.match(await harness.downloads[0].blob.text(), /"Account","Game","Scope","Exam Code","Status","Score","Completed"/);
  harness.elements.get("resetState").listeners.click();
  assert.equal(harness.elements.get("exportCompletedRecords").disabled, true);
  assert.equal(harness.elements.get("exportStatus").textContent, "");
});
