import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../../exam-web/exam.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../../exam-web/exam.js", import.meta.url), "utf8");
const tasks = ["task_01", "task_02", "task_03"];

function createHarness() {
  function createElement() {
    const classes = new Set();
    return {
      value: "", textContent: "", disabled: false, listeners: {}, files: [], dataset: {},
      classList: {
        add(name) { classes.add(name); },
        remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
        toggle(name, force) {
          const enabled = force ?? !classes.has(name);
          if (enabled) classes.add(name);
          else classes.delete(name);
          return enabled;
        },
      },
      addEventListener(name, callback) { this.listeners[name] = callback; },
      appendChild() {},
    };
  }
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, createElement()]));
  const buttons = new Map([...html.matchAll(/<button\b[^>]*data-action="([^"]+)"[^>]*>([^<]+)<\/button>/g)]
    .map(([, action, label]) => {
      const button = createElement();
      button.dataset.action = action;
      button.textContent = label;
      return [action, button];
    }));
  const authInputs = ["kubeconfig", "manual"].map((value) => ({ ...createElement(), value }));
  authInputs[0].checked = true;
  const connections = [];
  const storage = new Map();
  const timers = new Map();
  let nextTimer = 0;
  class FakeWebSocket {
    static OPEN = 1;
    constructor(url) {
      this.url = new URL(url);
      this.readyState = 0;
      this.sent = [];
      connections.push(this);
    }
    send(message) { this.sent.push(JSON.parse(message)); }
    close() { this.readyState = 3; }
    open() { this.readyState = FakeWebSocket.OPEN; this.onopen(); }
    receive(data, action = "status") {
      this.onmessage({ data: JSON.stringify({ type: "exam_status", source_action: action, data }) });
    }
  }
  const context = vm.createContext({
    window: { confirm() { return true; } },
    document: {
      getElementById(id) {
        assert.ok(elements.has(id), `Missing HTML element: ${id}`);
        return elements.get(id);
      },
      createElement,
      querySelector(selector) {
        if (selector.includes("examAuthMethod")) return authInputs.find((input) => input.checked);
        return buttons.get(selector.match(/data-action="([^"]+)"/)?.[1]);
      },
      querySelectorAll(selector) {
        if (selector.includes("examAuthMethod")) return authInputs;
        if (selector === ".exam-action") {
          return [...buttons.values()].filter((button) => !["save-account", "verify"].includes(button.dataset.action));
        }
        return [...buttons.values()];
      },
    },
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    WebSocket: FakeWebSocket,
    URL, URLSearchParams,
    setTimeout(callback) { const id = ++nextTimer; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); },
    console: { log() {} },
  });
  vm.runInContext(script, context);
  elements.get("apiKey").value = "test-key";
  elements.get("examCode").value = "EXAM-001";
  vm.runInContext("k8sAccountReady = true", context);
  context.verified = {
    status: "VERIFIED", game: "game02", allowed_tasks: tasks, remaining_tasks: tasks,
    websocket_url: "wss://example.test/exam", exam_score: 0,
  };
  vm.runInContext('showResponse(JSON.stringify(verified), output, "verify")', context);
  const harness = {
    elements, buttons, connections, timers, context,
    get connection() { return connections.at(-1); },
    select(task) {
      elements.get("task").value = task;
      elements.get("task").listeners.change({ target: elements.get("task") });
    },
    status(status = "NOT_STARTED") {
      this.connection.receive({
        status, task_id: this.connection.url.searchParams.get("task"),
        active_execution: null,
        status_request_id: this.connection.sent.findLast((message) => message.action === "status")?.status_request_id,
      });
    },
    start() {
      this.connection.receive({
        status: "STARTED", current_phase: "setup", task_description: "Current question",
      }, "start");
    },
    begin(action = "run") {
      vm.runInContext(`sendExamActionViaSocket("${action}")`, context);
    },
    running(phase = "setup", executionId = "execution-1") {
      this.connection.receive({
        status: "RUNNING",
        active_execution: {
          execution_id: executionId, task_id: this.connection.url.searchParams.get("task"),
          action: "run", phase,
          command_request_id: this.connection.sent.findLast((message) => message.command_request_id)?.command_request_id,
        },
      }, "run");
    },
    poll() {
      const [id, callback] = timers.entries().next().value;
      timers.delete(id);
      callback();
    },
  };
  harness.connection.open();
  harness.status();
  return harness;
}

function assertReadyToStart(harness) {
  assert.equal(harness.elements.get("taskStatusLabel").textContent, "NOT_STARTED");
  assert.equal(harness.buttons.get("start").classList.contains("hidden"), false);
  assert.equal(harness.buttons.get("start").disabled, false);
  assert.equal(harness.buttons.get("run").classList.contains("hidden"), true);
}

test("automatic advancement restores each next task and allows all exam questions to run", () => {
  const harness = createHarness();
  for (let index = 0; index < tasks.length; index++) {
    assert.equal(harness.elements.get("task").value, tasks[index]);
    assertReadyToStart(harness);
    harness.start();
    vm.runInContext('sendExamActionViaSocket("run")', harness.context);
    assert.equal(harness.connection.sent.at(-1).action, "run");
    assert.equal(harness.connection.url.searchParams.get("task"), tasks[index]);
    harness.connection.receive({
      status: "COMPLETED", task_id: tasks[index], total_points: 10,
      command_finished: true, execution_id: `execution-${index}`,
      command_request_id: harness.connection.sent.at(-1).command_request_id,
      remaining_tasks: tasks.slice(index + 1), exam_score: (index + 1) * 10,
      finished_tasks: tasks.slice(0, index + 1),
      task_summaries: tasks.map((task_id, taskIndex) => ({
        task_id, status: taskIndex <= index ? "COMPLETED" : "NOT_STARTED",
        total_points: taskIndex <= index ? 10 : 0,
      })),
    }, "run");
    if (index < tasks.length - 1) {
      assert.equal(harness.buttons.get("start").classList.contains("hidden"), false);
      assert.equal(harness.buttons.get("start").disabled, true);
      assert.equal(harness.elements.get("taskStatusLabel").textContent, "NOT_STARTED");
      assert.equal(harness.elements.get("markOutput").textContent, "0");
      assert.equal(harness.timers.size, 0);
      harness.connection.open();
      harness.status();
      harness.connection.receive({ status: "OK", state: null, remaining_tasks: tasks.slice(index + 1) });
    }
  }
  assert.equal(harness.elements.get("task").value, "");
  assert.equal(harness.elements.get("examScoreOutput").textContent, "30");
  assert.match(harness.elements.get("questionOutput").innerHTML, /Exam completed/);
  assert.equal(harness.buttons.get("start").classList.contains("hidden"), true);
  assert.equal(harness.buttons.get("run").classList.contains("hidden"), true);
});

test("a full backend status with no saved state leaves a new task unstarted", () => {
  const harness = createHarness();
  harness.connection.receive({ status: "OK", state: null, remaining_tasks: tasks });
  assertReadyToStart(harness);
});

test("a NOT_STARTED snapshot clears a previously started state", () => {
  const harness = createHarness();
  harness.start();
  harness.status();
  assertReadyToStart(harness);
});

test("manual switching during a run preserves the running task and its lock", () => {
  const harness = createHarness();
  harness.start();
  vm.runInContext('sendExamActionViaSocket("run")', harness.context);
  assert.equal(harness.timers.size, 1);
  harness.select(tasks[1]);
  assert.equal(harness.timers.size, 1);
  assert.equal(harness.elements.get("task").value, tasks[0]);
  assert.equal(harness.connection.url.searchParams.get("task"), tasks[0]);
  assert.equal(harness.buttons.get("run").disabled, true);
  assert.equal(harness.elements.get("task").disabled, true);
});

test("late messages from the previous socket cannot change the selected task", () => {
  const harness = createHarness();
  const previous = harness.connection;
  harness.select(tasks[1]);
  harness.connection.open();
  harness.status();
  previous.receive({
    status: "COMPLETED", task_id: tasks[0], remaining_tasks: tasks.slice(1), total_points: 10,
  }, "run");
  previous.receive({ status: "OK", state: null, remaining_tasks: [tasks[0]] });
  assert.equal(harness.elements.get("task").value, tasks[1]);
  assertReadyToStart(harness);
  assert.equal(harness.elements.get("markOutput").textContent, "0");
});

test("switching back to an in-progress task restores Run rather than Start", () => {
  const harness = createHarness();
  harness.select(tasks[1]);
  harness.connection.open();
  harness.connection.receive({
    status: "OK",
    state: { status: "IN_PROGRESS", current_phase_id: "challenge", total_points: 0 },
    task_description: "Solve the saved task",
    remaining_tasks: tasks,
  });
  assert.equal(harness.buttons.get("start").classList.contains("hidden"), true);
  assert.equal(harness.buttons.get("run").disabled, false);
  assert.equal(harness.elements.get("phaseStateLabel").textContent, "Your turn");
  assert.equal(harness.elements.get("questionOutput").innerHTML, "Solve the saved task");
});

test("Start, Run, and Reset block duplicate and conflicting submissions immediately", () => {
  for (const action of ["start", "run", "reset"]) {
    const harness = createHarness();
    if (action !== "start") harness.start();
    harness.begin(action);
    const sent = harness.connection.sent.length;
    for (const conflicting of ["start", "run", "reset"]) harness.begin(conflicting);
    assert.equal(harness.connection.sent.length, sent);
    for (const button of ["start", "run", "reset", "verify", "save-account"]) {
      assert.equal(harness.buttons.get(button).disabled, true, `${action}: ${button}`);
    }
    assert.equal(harness.elements.get("resetState").disabled, true);
    assert.equal(harness.elements.get("apiKey").disabled, true);
  }
});

test("duplicate errors and unrelated messages cannot unlock a running command", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.running("check");
  harness.connection.receive({ status: "ERROR", message: "Please wait a moment." }, "run");
  harness.connection.receive({ status: "OK", records: [] }, "records");
  harness.connection.receive({
    status: "FAILED", task_id: tasks[0], command_finished: true, execution_id: "older-execution",
  }, "run");
  assert.equal(harness.buttons.get("run").disabled, true);
  assert.equal(harness.elements.get("task").disabled, true);
});

test("cleanup progress stays locked until a matching terminal result", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  for (const phase of ["setup", "ready", "check", "cleanup"]) {
    harness.running(phase);
    const label = phase === "cleanup" ? "Cleaning up" : phase === "check" ? "Assessing your work" : "Preparing environment";
    assert.equal(harness.elements.get("phaseStateLabel").textContent, label);
    assert.equal(harness.elements.get("task").disabled, true);
    assert.equal(harness.buttons.get("reset").disabled, true);
  }
  harness.connection.receive({
    status: "OK", current_phase: "challenge", task_id: tasks[0],
    command_finished: true, execution_id: "execution-1", active_execution: null,
  }, "run");
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("run").disabled, false);
  harness.select(tasks[1]);
  assert.equal(harness.connection.url.searchParams.get("task"), tasks[0]);
});

test("polling reconciles a lost response without blindly unlocking on a timer", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.poll();
  assert.equal(harness.connection.sent.at(-1).action, "status");
  assert.equal(harness.buttons.get("run").disabled, true);
  harness.status("IN_PROGRESS");
  assert.equal(harness.buttons.get("run").disabled, false);
  assert.equal(harness.elements.get("task").disabled, true);
});

test("disconnect and reconnect preserve the lock until the server confirms idle", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.running("cleanup");
  harness.connection.onclose({ code: 1006 });
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("reconnect").disabled, false);
  vm.runInContext('connectExamSocket()', harness.context);
  harness.connection.open();
  harness.connection.receive({
    status: "RUNNING", active_execution: {
      task_id: tasks[0], action: "run", phase: "cleanup", execution_id: "execution-1",
    },
    status_request_id: harness.connection.sent.at(-1).status_request_id,
  });
  assert.equal(harness.elements.get("task").disabled, true);
  harness.poll();
  harness.status("IN_PROGRESS");
  assert.equal(harness.buttons.get("run").disabled, false);
});

test("stale idle snapshots cannot clear a newer execution", () => {
  const harness = createHarness();
  const staleRequestId = harness.connection.sent.at(-1).status_request_id;
  harness.start();
  harness.begin();
  harness.connection.receive({
    status: "OK", state: null, active_execution: null, status_request_id: staleRequestId,
  });
  harness.connection.receive({ status: "IN_PROGRESS", active_execution: null });
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("run").disabled, true);
});

test("a server-side lease for another question locks this page without starting a second task", () => {
  const harness = createHarness();
  harness.connection.receive({
    status: "RUNNING", active_execution: {
      task_id: tasks[1], action: "run", phase: "setup", execution_id: "another-tab",
    },
  });
  const sent = harness.connection.sent.length;
  harness.begin("start");
  harness.select(tasks[2]);
  assert.equal(harness.connection.sent.length, sent);
  assert.equal(harness.elements.get("task").value, tasks[0]);
  assert.equal(harness.buttons.get("start").disabled, true);
});

test("a rejected Start or Reset does not advance the task state", () => {
  const harness = createHarness();
  harness.begin("start");
  harness.connection.receive({
    status: "ERROR", task_id: tasks[0], message: "Start failed",
    command_finished: true, execution_id: "start-1", active_execution: null,
    command_request_id: harness.connection.sent.at(-1).command_request_id,
  }, "start");
  assertReadyToStart(harness);
  harness.start();
  harness.begin("reset");
  harness.connection.receive({
    status: "ERROR", task_id: tasks[0], message: "Reset failed",
    command_finished: true, execution_id: "reset-1", active_execution: null,
    command_request_id: harness.connection.sent.at(-1).command_request_id,
  }, "reset");
  assert.equal(harness.buttons.get("run").disabled, false);
  assert.equal(harness.elements.get("taskStatusLabel").textContent, "IN_PROGRESS");
});

test("delayed progress and completion from an older request cannot unlock a new submission", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.connection.receive({
    status: "RUNNING", active_execution: {
      task_id: tasks[0], action: "run", phase: "cleanup",
      execution_id: "old-execution", command_request_id: "old-command",
    },
  }, "run");
  harness.connection.receive({
    status: "OK", task_id: tasks[0], command_finished: true,
    execution_id: "old-execution", command_request_id: "old-command",
  }, "run");
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("run").disabled, true);
  harness.running("setup", "new-execution");
  assert.equal(harness.elements.get("phaseStateLabel").textContent, "Preparing environment");
});

test("slow status requests are not replaced every polling tick", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.poll();
  const sent = harness.connection.sent.length;
  harness.poll();
  assert.equal(harness.connection.sent.length, sent);
  assert.equal(harness.elements.get("task").disabled, true);
});

test("a status response timeout retries reconciliation without unlocking the task", () => {
  const harness = createHarness();
  harness.start();
  harness.begin();
  harness.poll();
  const firstRequestId = harness.connection.sent.at(-1).status_request_id;
  vm.runInContext("Date.now = () => Number.MAX_SAFE_INTEGER", harness.context);
  harness.poll();
  assert.notEqual(harness.connection.sent.at(-1).status_request_id, firstRequestId);
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("run").disabled, true);
});

test("completed execution messages cannot regress a later settled result", () => {
  const harness = createHarness();
  harness.start();
  for (const [execution_id, current_phase] of [["first", "challenge"], ["second", "check"]]) {
    harness.begin();
    harness.connection.receive({
      status: "OK", task_id: tasks[0], command_finished: true, execution_id, current_phase,
      command_request_id: harness.connection.sent.at(-1).command_request_id, active_execution: null,
    }, "run");
  }
  harness.connection.receive({
    status: "OK", task_id: tasks[0], command_finished: true,
    execution_id: "first", current_phase: "challenge", active_execution: null,
  }, "run");
  assert.equal(harness.elements.get("phaseStateLabel").textContent, "Your turn");
});

test("the student working stage keeps environment ownership without locking submission", () => {
  const harness = createHarness();
  harness.connection.receive({
    status: "OK", current_phase: "check", task_description: "Keep these instructions",
    active_environment: { task_id: tasks[0], exam_code: "EXAM-001" },
    lifecycle: { stage: "working", label: "Your turn", message: "Complete the question.", run_label: "Submit answer" },
  }, "start");
  assert.equal(harness.elements.get("phaseStateLabel").textContent, "Your turn");
  assert.equal(harness.buttons.get("run").textContent, "Submit answer");
  assert.equal(harness.buttons.get("run").disabled, false);
  assert.equal(harness.elements.get("task").disabled, true);
  harness.select(tasks[1]);
  assert.equal(harness.elements.get("task").value, tasks[0]);
  assert.equal(harness.elements.get("apiKey").disabled, true);
});

test("preparation and cleanup failures show the actual retry action and preserve the question", () => {
  const harness = createHarness();
  harness.connection.receive({
    status: "OK", current_phase: "check", task_description: "Original question",
    active_environment: { task_id: tasks[0], exam_code: "EXAM-001" },
  }, "start");
  for (const [phase, label, action] of [
    ["ready", "Preparation needed", "Retry preparation"],
    ["cleanup", "Cleanup needs attention", "Retry cleanup"],
  ]) {
    harness.connection.receive({
      status: "FAILED", current_phase: phase, message: "This is a status message, not a new question.",
      active_environment: { task_id: tasks[0], exam_code: "EXAM-001" },
      lifecycle: { stage: phase === "ready" ? "preparation" : "cleanup", label, message: "Retry the failed stage.", run_label: action },
    }, "run");
    assert.equal(harness.elements.get("phaseStateLabel").textContent, label);
    assert.equal(harness.buttons.get("run").textContent, action);
    assert.equal(harness.elements.get("questionOutput").innerHTML, "Original question");
    assert.equal(harness.elements.get("task").disabled, true);
  }
});

test("cleanup-first leave unlocks selection only after a successful server result", () => {
  const harness = createHarness();
  harness.start();
  harness.begin("reset");
  harness.running("cleanup");
  assert.equal(harness.elements.get("task").disabled, true);
  harness.connection.receive({
    status: "RESET", task_id: tasks[0], command_finished: true, execution_id: "execution-1",
    command_request_id: harness.connection.sent.at(-1).command_request_id,
    active_execution: null, active_environment: null,
    lifecycle: { stage: "not_started", label: "Not started", message: "Choose a question." },
  }, "reset");
  assert.equal(harness.elements.get("task").disabled, false);
  harness.select(tasks[1]);
  assert.equal(harness.connection.url.searchParams.get("task"), tasks[1]);
});

test("reconnecting to another question restores the environment owner even while no command runs", () => {
  const harness = createHarness();
  harness.connection.receive({
    status: "OK", state: null, active_execution: null,
    active_environment: { task_id: tasks[1], exam_code: "EXAM-001" },
  });
  assert.equal(harness.elements.get("task").value, tasks[1]);
  assert.equal(harness.connection.url.searchParams.get("task"), tasks[1]);
  assert.equal(harness.buttons.get("start").disabled, true);
  harness.connection.open();
  harness.connection.receive({
    status: "OK", state: { status: "IN_PROGRESS", current_phase_id: "check" },
    active_environment: { task_id: tasks[1], exam_code: "EXAM-001" },
    lifecycle: { stage: "working", label: "Your turn", message: "Resume your work.", run_label: "Submit answer" },
  });
  assert.equal(harness.elements.get("task").disabled, true);
  assert.equal(harness.buttons.get("run").disabled, false);
});
