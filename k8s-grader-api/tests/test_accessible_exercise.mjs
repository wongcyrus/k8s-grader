import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../../exam-web/accessible-exercise.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../../exam-web/accessible-exercise.js", import.meta.url), "utf8");

function createHarness({ confirm = true, prompt = "RESET game02", access = true, loginOk = true, loginError = false } = {}) {
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [
    id,
    {
      value: "", textContent: "", disabled: false, listeners: {}, files: [], checked: false,
      classList: { add() {}, remove() {}, toggle() {} },
      style: { setProperty() {} },
      addEventListener(name, callback) { this.listeners[name] = callback; },
    },
  ]));
  const sent = [];
  const connections = [];
  const confirmations = [];
  const requests = [];
  class FakeWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    constructor() {
      this.readyState = FakeWebSocket.CONNECTING;
      this.listeners = {};
      connections.push(this);
    }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    send(message) { sent.push(JSON.parse(message)); }
    close() {
      this.readyState = 3;
      this.listeners.close?.();
    }
    open() {
      this.readyState = FakeWebSocket.OPEN;
      this.listeners.open();
    }
    receive(payload) {
      this.listeners.message({ data: JSON.stringify({ type: "game_status", data: payload }) });
    }
  }
  const context = vm.createContext({
    window: {
      __K8S_PORTAL_CONFIG__: { baseUrl: "https://example.test", gameWsUrl: "wss://example.test" },
      confirm(message) { confirmations.push(message); return confirm; },
      prompt: () => prompt,
    },
    document: {
      getElementById(id) {
        assert.ok(elements.has(id), `Missing HTML element: ${id}`);
        return elements.get(id);
      },
    },
    localStorage: { getItem: () => null },
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url.endsWith("/save-k8s-account")) {
        if (loginError) throw new Error("Network unavailable");
        return {
          ok: loginOk,
          text: async () => JSON.stringify(loginOk
            ? { status: "OK", message: "Kubernetes endpoint verified and data saved successfully" }
            : { status: "ERROR", message: "Endpoint probe failed" }),
        };
      }
      return {
        ok: access,
        json: async () => access ? { status: "OK", game: "game02" } : { status: "ERROR", message: "Access denied." },
      };
    },
    FormData,
    WebSocket: FakeWebSocket,
    console,
  });
  vm.runInContext(script, context);
  elements.get("apiKey").value = "test-key";
  return {
    elements, context, sent, connections, confirmations, requests,
    click(id) { elements.get(id).listeners.click(); },
    async unlock() { await vm.runInContext("unlockAccessibleView()", context); },
    get connection() { return connections.at(-1); },
    ready() {
      vm.runInContext('verifiedApiKey = "test-key"; setActionBusy(false)', context);
      this.connection.open();
      this.connection.receive({ status: "NOT_STARTED", task_id: "task_01", total_score: 0 });
    },
  };
}

test("page has versioned assets and game-event controls, not task selection", () => {
  assert.match(html, /src="\.\/accessible-exercise\.js\?v=[^"]+"/);
  assert.doesNotMatch(html, /id="(?:taskSelection|refreshTasks|startTask|runTask)"/);
  assert.doesNotMatch(script, /accessible-(?:list|start|run)|task_list_chunk/);
});

test("login and gateway status are explicitly distinct", () => {
  assert.match(html, /Game gateway \(WebSocket\)/);
  assert.match(html, /Kubernetes login check/);
  assert.match(html, /does not verify Kubernetes access/);
  assert.match(html, /Step 1: Save Kubernetes Login/);
  assert.match(html, /Submit Kubernetes Login/);
});

test("grading requires a verified login, not just an open WebSocket", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.connection.open();
  harness.connection.receive({ status: "NOT_STARTED", task_id: "task_01" });
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  harness.click("triggerGrading");
  assert.equal(harness.sent.at(-1).action, "status");
  assert.match(harness.elements.get("exerciseOutput").textContent, /Submit Kubernetes Login/);
});

test("kubeconfig login uses the existing endpoint and enables grading only on success", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.connection.open();
  harness.connection.receive({ status: "OK" });
  harness.elements.get("kubeconfig").value = "apiVersion: v1";
  await vm.runInContext("submitKubernetesLogin()", harness.context);
  const request = harness.requests.at(-1);
  assert.equal(request.url, "https://example.test/save-k8s-account");
  assert.equal(request.options.method, "POST");
  assert.deepEqual(request.options.headers["x-api-key"], "test-key");
  assert.equal(request.options.headers.Authorization, "test-key");
  assert.equal(request.options.body.get("kubeconfig"), "apiVersion: v1");
  assert.equal(harness.elements.get("triggerGrading").disabled, false);
  assert.match(harness.elements.get("kubernetesStatus").textContent, /Verified by AWS Lambda on last submission/);
  harness.elements.get("kubeconfig").listeners.input();
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  assert.match(harness.elements.get("kubernetesStatus").textContent, /Not verified/);
});

test("file upload and manual credentials use the same multipart fields as the portal", async () => {
  const harness = createHarness();
  harness.elements.get("kubeconfigFile").files = [new Blob(["apiVersion: v1"])];
  await vm.runInContext("submitKubernetesLogin()", harness.context);
  assert.ok(harness.requests.at(-1).options.body.get("kubeconfig-file"));
  harness.elements.get("manualMethod").listeners.change();
  harness.elements.get("endpoint").value = "https://cluster.test:6443";
  harness.elements.get("clientCertificate").files = [new Blob(["certificate"])];
  harness.elements.get("clientKey").files = [new Blob(["key"])];
  await vm.runInContext("submitKubernetesLogin()", harness.context);
  const body = harness.requests.at(-1).options.body;
  assert.equal(body.get("endpoint"), "https://cluster.test:6443");
  assert.ok(body.get("client-certificate"));
  assert.ok(body.get("client-key"));
  assert.equal(body.has("kubeconfig"), false);
});

test("missing login inputs and failed verification never claim Kubernetes is connected", async () => {
  for (const options of [{ loginOk: false }, { loginError: true }]) {
    const harness = createHarness(options);
    await vm.runInContext("submitKubernetesLogin()", harness.context);
    assert.equal(harness.requests.length, 0);
    harness.elements.get("kubeconfig").value = "apiVersion: v1";
    await vm.runInContext("submitKubernetesLogin()", harness.context);
    assert.equal(harness.elements.get("kubernetesStatus").textContent, "Verification failed");
    assert.equal(harness.elements.get("triggerGrading").disabled, true);
    assert.match(harness.elements.get("setupOutput").textContent, /Could not save/);
  }
});

test("manual login validates endpoint and paired certificate files before submitting", async () => {
  const harness = createHarness();
  harness.elements.get("manualMethod").listeners.change();
  await vm.runInContext("submitKubernetesLogin()", harness.context);
  assert.match(harness.elements.get("setupOutput").textContent, /Endpoint is required/);
  harness.elements.get("endpoint").value = "https://cluster.test:6443";
  harness.elements.get("clientCertificate").files = [new Blob(["certificate"])];
  await vm.runInContext("submitKubernetesLogin()", harness.context);
  assert.match(harness.elements.get("setupOutput").textContent, /must be provided together/);
  assert.equal(harness.requests.length, 0);
});

test("changing API key closes the gateway and requires new access and login checks", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.elements.get("apiKey").value = "different-key";
  harness.elements.get("apiKey").listeners.input();
  assert.equal(harness.connection.readyState, 3);
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  assert.match(harness.elements.get("accessStatus").textContent, /Check access again/);
  assert.match(harness.elements.get("kubernetesStatus").textContent, /Not verified/);
  const count = harness.sent.length;
  harness.click("triggerGrading");
  assert.equal(harness.sent.length, count);
});

test("changing login method invalidates previous verification without claiming gateway failure", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  assert.equal(harness.elements.get("triggerGrading").disabled, false);
  harness.elements.get("manualMethod").listeners.change();
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  assert.equal(harness.elements.get("connectionStatus").textContent, "Connected");
  assert.match(harness.elements.get("kubernetesStatus").textContent, /Not verified/);
});

test("unlock checks current progress without fetching the task catalog", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.connection.open();
  assert.deepEqual(harness.sent, [
    { action: "subscribe", apiKey: "test-key", game: "game02" },
    { action: "status", apiKey: "test-key", game: "game02" },
  ]);
});

test("grading sends exactly the hkzero enemy-defeat event without a task ID", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.click("triggerGrading");
  assert.deepEqual(harness.sent.at(-1), {
    action: "talk", apiKey: "test-key", game: "game02", npc: "hkzero",
  });
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  harness.connection.receive({ status: "RUNNING", message: "Checking cluster..." });
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
  const count = harness.sent.length;
  harness.click("triggerGrading");
  assert.equal(harness.sent.length, count);
  harness.connection.receive({ status: "PHASE_PASSED", task_id: "task_01", message: "Continue the task." });
  assert.equal(harness.elements.get("triggerGrading").disabled, false);
  harness.click("triggerGrading");
  assert.equal(harness.sent.at(-1).action, "talk");
});

test("portal controls send the existing score, reset and skip actions", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  for (const [id, action] of [
    ["checkScore", "status"], ["resetTask", "reset"], ["resetExercise", "reset-all"], ["skipTask", "skip"],
  ]) {
    harness.click(id);
    assert.deepEqual(harness.sent.at(-1), { action, apiKey: "test-key", game: "game02" });
    harness.connection.receive({ status: "OK" });
  }
  assert.equal(harness.confirmations.length, 3);
});

test("cancelled destructive actions and incorrect whole-reset confirmation send nothing", async () => {
  for (const options of [{ confirm: false }, { prompt: "wrong" }]) {
    const harness = createHarness(options);
    await harness.unlock();
    harness.ready();
    const count = harness.sent.length;
    if (options.confirm === false) {
      harness.click("resetTask");
      harness.click("skipTask");
    }
    harness.click("resetExercise");
    assert.equal(harness.sent.length, count);
  }
});

test("current instructions, score, completed and skipped tasks are readable", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.connection.receive({
    status: "IN_PROGRESS", task_id: "task_02", current_phase: "challenge",
    message: "Create a deployment.", total_score: 10,
    completed_tasks: ["task_01"], skipped_tasks: [],
    report_url: "https://example.test/report",
  });
  const output = harness.elements.get("exerciseOutput").textContent;
  for (const text of [
    "Create a deployment.", "Task: task_02", "Current step: challenge",
    "Total exercise score: 10", "Completed tasks (1):\ntask_01", "Skipped tasks (0):\nNone",
    "Report: https://example.test/report",
  ]) assert.ok(output.includes(text), text);
});

test("failed access cannot send game events", async () => {
  const harness = createHarness({ access: false });
  await harness.unlock();
  harness.click("triggerGrading");
  assert.equal(harness.connections.length, 0);
  assert.equal(harness.sent.length, 0);
  assert.equal(harness.elements.get("triggerGrading").disabled, true);
});

test("disconnect and game errors re-enable controls without automatically repeating grading", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.click("triggerGrading");
  harness.connection.receive({ status: "ERROR", message: "Please wait a moment before trying again." });
  assert.equal(harness.elements.get("triggerGrading").disabled, false);
  harness.click("triggerGrading");
  const count = harness.sent.length;
  harness.connection.close();
  assert.equal(harness.elements.get("triggerGrading").disabled, false);
  assert.match(harness.elements.get("exerciseOutput").textContent, /Check Total Score before retrying/);
  assert.equal(harness.sent.length, count);
});

test("game task instructions load on entry and persist through grading results", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.connection.receive({
    status: "IN_PROGRESS", task_id: "task_01", phase_name: "Challenge",
    task_description: "Create a deployment in namespace student-ns.",
    message: "Deploy three replicas.",
  });
  const instructions = harness.elements.get("taskInstructions");
  assert.equal(instructions.textContent, "Create a deployment in namespace student-ns.");
  assert.equal(harness.elements.get("currentTask").textContent, "Task: task_01");
  harness.click("triggerGrading");
  assert.equal(instructions.textContent, "Create a deployment in namespace student-ns.");
  harness.connection.receive({ status: "QUEUED" });
  harness.connection.receive({ status: "RUNNING", task_id: "task_01", message: "Running tests..." });
  harness.connection.receive({ status: "FAILED", task_id: "task_01", message: "Check failed." });
  assert.equal(instructions.textContent, "Create a deployment in namespace student-ns.");
  assert.match(harness.elements.get("exerciseOutput").textContent, /Check failed/);
  harness.connection.receive({ status: "COMPLETED", task_id: "task_01", message: "Task completed!" });
  assert.equal(instructions.textContent, "Create a deployment in namespace student-ns.");
});

test("skip and reset show actual instructions, not their result message", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.connection.receive({
    status: "NOT_STARTED", task_id: "task_02", skipped_task: "task_01",
    task_description: "Configure a service.",
    message: "Skipped task_01.",
  });
  assert.equal(harness.elements.get("taskInstructions").textContent, "Configure a service.");
  assert.match(harness.elements.get("exerciseOutput").textContent, /Skipped task_01/);
  harness.connection.receive({
    status: "RESET", task_id: "task_02", task_description: "Configure a service.",
    message: "Task reset.",
  });
  assert.equal(harness.elements.get("taskInstructions").textContent, "Configure a service.");
});

test("task changes clear stale instructions and finishing all tasks clears the task panel", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  harness.connection.receive({
    status: "IN_PROGRESS", task_id: "task_01", task_description: "First task.",
    current_phase: "challenge",
  });
  harness.connection.receive({ status: "RUNNING", task_id: "task_02" });
  assert.equal(harness.elements.get("taskInstructions").textContent, "");
  assert.equal(harness.elements.get("currentStep").textContent, "");
  harness.connection.receive({ status: "COMPLETED", message: "All tasks completed!" });
  assert.equal(harness.elements.get("currentTask").textContent, "All exercise tasks completed.");
  assert.equal(harness.elements.get("taskInstructions").textContent, "There are no remaining tasks.");
});

test("text size control applies to task instructions and results", () => {
  const harness = createHarness();
  const sizes = new Map();
  for (const id of ["taskInstructions", "exerciseOutput"]) {
    harness.elements.get(id).style.setProperty = (name, value) => sizes.set(id, [name, value]);
  }
  harness.elements.get("textSize").value = "180";
  harness.elements.get("textSize").listeners.input();
  assert.equal(sizes.size, 2);
  for (const value of sizes.values()) assert.deepEqual(value, ["--accessible-text-size", "1.8rem"]);
});

test("same game payload displays task instruction separately and deduplicates the message", async () => {
  const harness = createHarness();
  await harness.unlock();
  harness.ready();
  const instruction = "# Create resources\n\n1. Create a Pod\n2. Create a Service";
  harness.connection.receive({
    status: "OK", task_id: "task_01", phase_name: "Challenge",
    next_game_phrase: "CHALLENGE", message: instruction, task_description: instruction,
  });
  assert.equal(harness.elements.get("taskInstructions").textContent, instruction);
  assert.equal(harness.elements.get("currentStep").textContent, "Current step: Challenge");
  assert.ok(!harness.elements.get("exerciseOutput").textContent.includes(instruction));
  harness.connection.receive({
    status: "FAILED", task_id: "task_01",
    message: "Deployment has only one ready replica.",
    task_description: instruction, report_url: "https://example.test/report",
  });
  assert.equal(harness.elements.get("taskInstructions").textContent, instruction);
  assert.match(harness.elements.get("exerciseOutput").textContent, /Deployment has only one ready replica/);
});

test("Markdown goes through the same marked and DOMPurify pipeline as Doom", async () => {
  const harness = createHarness();
  const calls = [];
  vm.runInContext(`
    window.marked = { parse(text, options) {
      record("parse", text, options.breaks, options.gfm);
      return "<h1>Task</h1>";
    } };
    window.DOMPurify = { sanitize(html) {
      record("sanitize", html);
      return "<h1>Safe task</h1>";
    } };
  `, Object.assign(harness.context, { record: (...args) => calls.push(args) }));
  await harness.unlock();
  harness.ready();
  calls.length = 0;
  harness.connection.receive({ status: "OK", task_id: "task_01", task_description: "# Task", message: "# Task" });
  assert.deepEqual(calls, [["parse", "# Task", true, true], ["sanitize", "<h1>Task</h1>"]]);
  assert.equal(harness.elements.get("taskInstructions").innerHTML, "<h1>Safe task</h1>");
});
