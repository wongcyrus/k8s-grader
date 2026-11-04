const APP_CONFIG = window.__K8S_PORTAL_CONFIG__ || {};
const output = document.getElementById("output");
const setupOutput = document.getElementById("setupOutput");
const questionOutput = document.getElementById("questionOutput");
const markOutput = document.getElementById("markOutput");
const examScoreOutput = document.getElementById("examScoreOutput");
const phaseOutput = document.getElementById("phaseOutput");
const connectionStatus = document.getElementById("connectionStatus");
const gameLabel = document.getElementById("gameLabel");
const nextStepOutput = document.getElementById("nextStepOutput");
const examPhaseEstimateRow = document.getElementById("examPhaseEstimateRow");
const examPhaseEstimateLabel = document.getElementById("examPhaseEstimateLabel");
const examTaskEstimateRow = document.getElementById("examTaskEstimateRow");
const examTaskEstimateTitle = document.getElementById("examTaskEstimateTitle");
const examTaskEstimateLabel = document.getElementById("examTaskEstimateLabel");
const buttons = document.querySelectorAll("button[data-action]");
const examScope = document.getElementById("examScope");
const examActionButtons = document.querySelectorAll(".exam-action");
const resetStateButton = document.getElementById("resetState");
const phaseStateLabel = document.getElementById("phaseStateLabel");
const taskStatusLabel = document.getElementById("taskStatusLabel");
const verifyButton = document.querySelector('button[data-action="verify"]');
const authMethodInputs = document.querySelectorAll('input[name="examAuthMethod"]');
const kubeconfigPanel = document.getElementById("kubeconfigPanel");
const manualPanel = document.getElementById("manualPanel");

const BASE_URL = APP_CONFIG.baseUrl || "";
const EXAM_ACTION_COOLDOWN_MS = 1500;
const EXECUTION_STATUS_POLL_MS = 3000;
const STATUS_RESPONSE_TIMEOUT_MS = 30000;
const REQUEST_ID_PREFIX = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const STORAGE_KEY = "k8s-exam-page-state-v1";
const LEGACY_STORAGE_KEYS = ["k8s-exam-web-state-v1"];
const LOCKED_EXAM_GUIDANCE = "Submit Kubernetes Login and verify an exam code to unlock the exam flow.";

let examFlowState = "unverified";
let lastExamActionAt = 0;
let examSocket = null;
let examSocketBaseUrl = "";
let examSocketReady = false;
let k8sAccountReady = false;
let currentPhaseState = "setup";
let backendTaskStatus = "NOT_STARTED";
let backendNextAction = null;
let taskStarted = false;
let runResponseTimer = null;
let statusSyncPending = false;
let examHasRemainingTasks = true;
let pendingExecution = null;
let selectedExamTask = "";
let httpBusy = false;
let statusRequestSequence = 0;
let latestStatusRequestId = "";
let statusRequestSentAt = 0;
let activeEnvironment = null;
let currentLifecycle = null;
const finishedExecutionIds = new Set();

function wsDebug(event, data = null) {
  const ts = new Date().toISOString();
  if (data === null) {
    console.log(`[ExamWS][${ts}] ${event}`);
    return;
  }
  console.log(`[ExamWS][${ts}] ${event}`, data);
}

function readInputs() {
  const selectedAuthMethod = document.querySelector('input[name="examAuthMethod"]:checked');
  return {
    apiKey: document.getElementById("apiKey").value.trim(),
    authMethod: selectedAuthMethod ? selectedAuthMethod.value : "kubeconfig",
    kubeconfig: document.getElementById("kubeconfig").value,
    kubeconfigFile: document.getElementById("kubeconfigFile").files[0],
    endpoint: document.getElementById("endpoint").value.trim(),
    clientCertificate: document.getElementById("clientCertificate").files[0],
    clientKey: document.getElementById("clientKey").files[0],
    examCode: document.getElementById("examCode").value.trim(),
    game: document.getElementById("game").value.trim(),
    task: document.getElementById("task").value.trim(),
  };
}

function setAuthMethod(method, { persist = true } = {}) {
  const selectedMethod = method === "manual" ? "manual" : "kubeconfig";
  authMethodInputs.forEach((input) => {
    input.checked = input.value === selectedMethod;
  });
  kubeconfigPanel.classList.toggle("hidden", selectedMethod !== "kubeconfig");
  manualPanel.classList.toggle("hidden", selectedMethod !== "manual");
  if (persist) {
    saveState({ authMethod: selectedMethod, accountReady: false });
  }
}

function write(data, target = output) {
  target.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function saveState(partial = {}) {
  const current = loadState();
  const next = { ...current, ...partial };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function loadState() {
  for (const key of [STORAGE_KEY, ...LEGACY_STORAGE_KEYS]) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) {
        continue;
      }
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch {
      // Ignore malformed saved state.
    }
  }
  return {};
}

function clearState() {
  [STORAGE_KEY, ...LEGACY_STORAGE_KEYS].forEach((key) => localStorage.removeItem(key));
}

function shortenUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.origin}${parsed.pathname}`;
  } catch {
    return url;
  }
}

function buildLinkHtml(url, label) {
  const href = encodeURIComponent(url);
  const text = escapeHtml(label || shortenUrl(url));
  return `<button type="button" class="response-popup-btn" data-popup-url="${href}">${text}</button>`;
}

function openPopup(url) {
  const popup = window.open(
    url,
    "exam-report-popup",
    "popup=yes,width=1200,height=800,resizable=yes,scrollbars=yes"
  );
  if (!popup) {
    write("Popup blocked by browser. Please allow popups for this site and click again.");
  }
}

function renderMarkdown(text) {
  const source = typeof text === "string" ? text : String(text ?? "");
  if (window.marked && window.DOMPurify) {
    return window.DOMPurify.sanitize(window.marked.parse(source, { breaks: true, gfm: true }));
  }
  return source;
}

function writeMarkdown(text, target = questionOutput) {
  target.innerHTML = renderMarkdown(text);
}

function formatEstimateDuration(seconds) {
  const totalSeconds = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes === 0) {
    return `${remainingSeconds} sec`;
  }
  if (remainingSeconds === 0) {
    return `${minutes} min`;
  }
  return `${minutes} min ${remainingSeconds} sec`;
}

function normalizeTaskStatus(status) {
  if (!status) {
    return "NOT_STARTED";
  }
  return String(status).replace(/_/g, " ").trim().toUpperCase().replace(/\s+/g, "_");
}

function normalizePhaseState(phase) {
  const normalized = String(phase ?? "").trim().toLowerCase().replace(/[\s_-]+/g, "_");
  if (!normalized || normalized === "not_started") {
    return "setup";
  }
  return normalized;
}

function setCurrentPhaseState(phase) {
  currentPhaseState = normalizePhaseState(phase);
  currentLifecycle = null;
  updateStateMachineUI();
}

function getLifecycle() {
  if (currentLifecycle) return currentLifecycle;
  const phase = pendingExecution?.phase || pendingExecution?.action || currentPhaseState;
  if (pendingExecution) {
    if (["setup", "ready", "start"].includes(phase)) {
      return { stage: "preparation", label: "Preparing environment", message: phase === "ready" ? "Checking that the environment is ready." : "Creating the question's Kubernetes resources." };
    }
    if (["cleanup", "reset"].includes(phase)) {
      return { stage: "cleanup", label: "Cleaning up", message: "Removing the question's Kubernetes resources. Wait for cleanup to finish." };
    }
    return { stage: "assessment", label: "Assessing your work", message: phase === "challenge" ? "Running the challenge against your work." : "Checking your answer." };
  }
  if (backendTaskStatus === "COMPLETED") return { stage: "completed", label: "Finished", message: "Cleanup finished. You may choose another question." };
  if (backendTaskStatus === "ABANDONED") return { stage: "abandoned", label: "Attempts exhausted", message: "The question has finished after cleanup." };
  if (!taskStarted) return { stage: "not_started", label: "Not started", message: "Start question to prepare your environment." };
  if (phase === "cleanup") return { stage: "cleanup", label: "Cleanup needs attention", message: "Retry cleanup before continuing.", run_label: "Retry cleanup" };
  if (["setup", "ready"].includes(phase)) return { stage: "preparation", label: "Preparation needed", message: "Retry preparation before working on this question.", run_label: "Retry preparation" };
  return { stage: "working", label: "Your turn", message: "Complete the question in Kubernetes, then submit your answer.", run_label: "Submit answer" };
}

function updateStateMachineUI() {
  const lifecycle = getLifecycle();
  phaseStateLabel.textContent = lifecycle.label;
  taskStatusLabel.textContent = backendTaskStatus;
  const lifecycleOutput = document.getElementById("lifecycleOutput");
  if (lifecycleOutput) lifecycleOutput.textContent = lifecycle.message || "";
  const activities = {
    setup: "Creating resources", ready: "Checking readiness",
    challenge: "Running challenge", check: "Checking answer", cleanup: "Removing resources",
  };
  phaseOutput.textContent = lifecycle.stage === "working" ? "Waiting for your Kubernetes changes."
    : ["completed", "abandoned"].includes(lifecycle.stage) ? "Environment released."
      : activities[lifecycle.phase || pendingExecution?.phase] || "";
  const stages = ["Prepare environment", "Your turn", "Assess your work", "Clean up"];
  const index = { preparation: 0, working: 1, assessment: 2, cleanup: 3 }[lifecycle.stage];
  const lifecycleSteps = document.getElementById("lifecycleSteps");
  if (lifecycleSteps) lifecycleSteps.textContent = stages.map((label, position) => position === index ? `[${label}]` : label).join(" / ");
}

function setBusy(isBusy) {
  httpBusy = isBusy;
  updateExamButtons();
}

function stopRunResponseWatchdog() {
  if (runResponseTimer) {
    clearTimeout(runResponseTimer);
    runResponseTimer = null;
  }
}

function startRunResponseWatchdog() {
  stopRunResponseWatchdog();
  runResponseTimer = setTimeout(() => {
    runResponseTimer = null;
    if (pendingExecution && examSocketReady) {
      if (!statusSyncPending || Date.now() - statusRequestSentAt >= STATUS_RESPONSE_TIMEOUT_MS) {
        refreshCurrentTaskStatus();
      }
      startRunResponseWatchdog();
    }
  }, EXECUTION_STATUS_POLL_MS);
}

examActionButtons.forEach((btn) => {
  if (!btn.dataset.baseLabel) {
    btn.dataset.baseLabel = btn.textContent.trim();
  }
});

function setConnectionStatus(text) {
  connectionStatus.textContent = text;
  updateStateMachineUI();
}

function setNextStep(message) {
  nextStepOutput.innerHTML = `<strong>Next step:</strong> ${message}`;
}

function closeExamSocket() {
  if (examSocket) {
    wsDebug("closeExamSocket() closing current socket");
    examSocket.close();
    examSocket = null;
  }
  stopRunResponseWatchdog();
  examSocketReady = false;
  if (examFlowState !== "unverified") {
    setConnectionStatus("Disconnected");
  }
  updateStateMachineUI();
}

function buildExamSocketUrl() {
  const { apiKey, examCode, game, task } = readInputs();
  if (!examSocketBaseUrl || !apiKey || !examCode || !game || !task) {
    return "";
  }
  const params = new URLSearchParams({ apiKey, examCode, game, task });
  return `${examSocketBaseUrl}?${params.toString()}`;
}

function connectExamSocket() {
  const socketUrl = buildExamSocketUrl();
  if (!socketUrl) {
    wsDebug("connectExamSocket() skipped: missing socket url or required fields", readInputs());
    return;
  }

  wsDebug("connectExamSocket() opening", { socketUrl });
  closeExamSocket();
  setConnectionStatus("Connecting...");

  let socket;
  try {
    socket = new WebSocket(socketUrl);
  } catch {
    wsDebug("connectExamSocket() constructor failed");
    setConnectionStatus("Disconnected");
    write("WebSocket connection failed.");
    return;
  }
  examSocket = socket;

  socket.onmessage = (event) => {
    if (examSocket !== socket) {
      return;
    }
    wsDebug("onmessage raw", event.data);
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      wsDebug("onmessage parse failed");
      return;
    }
    wsDebug("onmessage parsed", payload);
    if (payload && payload.message && payload.type !== "exam_status") {
      write(
        `WebSocket server error: ${payload.message}${payload.requestId ? ` (requestId: ${payload.requestId})` : ""}`,
        output
      );
      if (pendingExecution) {
        refreshCurrentTaskStatus();
      }
      return;
    }
    if (!payload || payload.type !== "exam_status" || !payload.data) {
      return;
    }
    const action = payload.source_action || "status";
    showResponse(JSON.stringify(payload.data), output, action);
  };

  socket.onopen = () => {
    if (examSocket !== socket) {
      return;
    }
    examSocketReady = true;
    setConnectionStatus("Connected");
    updateExamButtons();
    socket.send(
      JSON.stringify({
        action: "subscribe",
        apiKey: readInputs().apiKey,
        examCode: readInputs().examCode,
        game: readInputs().game,
        task: readInputs().task,
      })
    );
    refreshCurrentTaskStatus();
  };

  socket.onerror = (event) => {
    if (examSocket !== socket) {
      return;
    }
    wsDebug("onerror", event);
    examSocketReady = false;
    setConnectionStatus("Disconnected");
    updateExamButtons();
  };

  socket.onclose = (event) => {
    if (examSocket !== socket) {
      return;
    }
    wsDebug("onclose", { code: event.code, reason: event.reason, wasClean: event.wasClean });
    examSocket = null;
    examSocketReady = false;
    stopRunResponseWatchdog();
    setConnectionStatus("Disconnected");
    updateExamButtons();
    if (examFlowState !== "unverified") {
      setNextStep("WebSocket disconnected. Click Reconnect Exam.");
    }
  };
}

function sendExamActionViaSocket(action) {
  if (!examSocket || !examSocketReady || examSocket.readyState !== WebSocket.OPEN) {
    write("WebSocket is still connecting. Wait a moment, then try again.");
    return;
  }
  if (pendingExecution || statusSyncPending || httpBusy) {
    write("An exam task is processing or restoring. Wait for setup, testing, and cleanup to finish.");
    return;
  }

  if (["start", "run", "reset"].includes(action)) {
    currentLifecycle = null;
    pendingExecution = {
      action, task_id: readInputs().task,
      command_request_id: `${REQUEST_ID_PREFIX}-command-${++statusRequestSequence}`,
    };
    latestStatusRequestId = "";
    startRunResponseWatchdog();
    updateExamButtons();
  }
  try {
    examSocket.send(JSON.stringify({ action, command_request_id: pendingExecution?.command_request_id }));
  } catch {
    write("Unable to confirm submission. Reconnect Exam to restore the server execution state.");
    return;
  }
  write(`Sent exam/${action} via WebSocket ...`);
}

function refreshCurrentTaskStatus() {
  if (!examSocket || !examSocketReady || examSocket.readyState !== WebSocket.OPEN) {
    return;
  }
  const task = document.getElementById("task").value;
  if (!task) {
    statusSyncPending = false;
    updateExamButtons();
    return;
  }
  statusSyncPending = true;
  latestStatusRequestId = `${REQUEST_ID_PREFIX}-status-${++statusRequestSequence}`;
  statusRequestSentAt = Date.now();
  examSocket.send(JSON.stringify({ action: "status", status_request_id: latestStatusRequestId }));
  updateExamButtons();
}

function showLoadingSelectedTaskState() {
  if (pendingExecution) {
    return;
  }
  stopRunResponseWatchdog();
  examFlowState = "ready_to_start";
  backendNextAction = null;
  taskStarted = false;
  backendTaskStatus = "NOT_STARTED";
  currentLifecycle = null;
  statusSyncPending = true;
  setCurrentPhaseState("ready");
  writeMarkdown("Restoring task state...", questionOutput);
  markOutput.textContent = "0";
  examScoreOutput.textContent = "-";
  phaseOutput.textContent = "Phase: Loading...";
  setNextStep("Restoring task state from the server...");
  updateExamButtons();
  updateStateMachineUI();
}

function setExamReady(isReady) {
  examScope.classList.toggle("hidden", !isReady);
  examActionButtons.forEach((btn) => {
    btn.disabled = !isReady;
  });
  if (!isReady) {
    examFlowState = "unverified";
    setCurrentPhaseState("setup");
    taskStarted = false;
    backendNextAction = null;
    setNextStep(LOCKED_EXAM_GUIDANCE);
  }
  updateExamButtons();
  updateStateMachineUI();
}

function updateTaskOptions(tasks, preferredTask = "") {
  if (!Array.isArray(tasks)) {
    return;
  }
  examHasRemainingTasks = tasks.length > 0;
  const taskSelect = document.getElementById("task");
  const previousValue = taskSelect.value;
  const desiredValue = preferredTask || previousValue;
  taskSelect.innerHTML = "";

  if (tasks.length === 0) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "No remaining tasks";
    taskSelect.appendChild(empty);
    taskSelect.value = "";
    selectedExamTask = "";
    saveState({ allowedTasks: tasks, task: "" });
    if (previousValue !== taskSelect.value) {
      closeExamSocket();
      setConnectionStatus("Disconnected");
    }
    return;
  }

  tasks.forEach((task) => {
    const option = document.createElement("option");
    option.value = task;
    option.textContent = task;
    taskSelect.appendChild(option);
  });

  taskSelect.value = desiredValue && tasks.includes(desiredValue) ? desiredValue : tasks[0];
  selectedExamTask = taskSelect.value;
  saveState({ allowedTasks: tasks, task: taskSelect.value });
  if (previousValue !== taskSelect.value) {
    showLoadingSelectedTaskState();
    connectExamSocket();
  }
}

function setGameValue(game) {
  const value = game || "";
  document.getElementById("game").value = value;
  gameLabel.textContent = value || "-";
}

function setActionLock(button, locked, reason = "") {
  if (!button) {
    return;
  }
  const baseLabel = button.dataset.baseLabel || button.textContent.trim();
  button.disabled = locked;
  button.classList.toggle("locked", locked);
  button.title = locked ? reason : "";
  button.textContent = locked ? `🔒 ${baseLabel}` : baseLabel;
}

function setActionVisible(button, visible) {
  if (!button) {
    return;
  }
  button.classList.toggle("hidden", !visible);
}

function updateExamButtons() {
  const executing = Boolean(pendingExecution);
  const locked = executing || statusSyncPending || httpBusy;
  const ownsEnvironment = Boolean(activeEnvironment);
  document.getElementById("task").disabled = locked || ownsEnvironment;
  resetStateButton.disabled = locked || ownsEnvironment;
  ["apiKey", "examCode", "endpoint", "kubeconfig", "kubeconfigFile", "clientCertificate", "clientKey"].forEach((id) => {
    document.getElementById(id).disabled = locked || ownsEnvironment;
  });
  authMethodInputs.forEach((input) => { input.disabled = locked || ownsEnvironment; });
  const saveAccountButton = document.querySelector('button[data-action="save-account"]');
  saveAccountButton.disabled = locked || ownsEnvironment;
  if (verifyButton) {
    verifyButton.disabled = locked || ownsEnvironment || !k8sAccountReady;
  }
  updateStateMachineUI();
  if (examScope.classList.contains("hidden")) {
    examActionButtons.forEach((btn) => {
      setActionLock(btn, true, "Complete Step 1: Submit Kubernetes Login first.");
      setActionVisible(btn, false);
    });
    setNextStep(LOCKED_EXAM_GUIDANCE);
    return;
  }

  const reconnectBtn = document.querySelector('button[data-action="reconnect"]');
  const startBtn = document.querySelector('button[data-action="start"]');
  const resetBtn = document.querySelector('button[data-action="reset"]');
  const runBtn = document.querySelector('button[data-action="run"]');
  const recordsBtn = document.querySelector('button[data-action="records"]');
  startBtn.dataset.baseLabel = "Start question";
  resetBtn.dataset.baseLabel = "Leave question and clean up";
  runBtn.dataset.baseLabel = getLifecycle().run_label || "Submit answer";

  const disconnected = !examSocketReady;
  const completed = backendTaskStatus === "COMPLETED";
  const abandoned = backendTaskStatus === "ABANDONED";
  const started = taskStarted && !completed && !abandoned;
  const restoring = statusSyncPending || httpBusy;
  const busyReason = "Wait for setup, testing, and cleanup to finish.";

  setActionVisible(reconnectBtn, examHasRemainingTasks && disconnected);
  setActionVisible(startBtn, examHasRemainingTasks && !taskStarted);
  setActionVisible(resetBtn, examHasRemainingTasks && (taskStarted || ownsEnvironment) && !completed);
  setActionVisible(runBtn, examHasRemainingTasks && taskStarted && !completed && !abandoned);
  setActionVisible(recordsBtn, examHasRemainingTasks && (taskStarted || completed || abandoned));

  setActionLock(reconnectBtn, false);
  setActionLock(startBtn, executing || restoring || !examSocketReady || taskStarted, executing ? busyReason : restoring ? "Restoring task state from the server." : !examSocketReady ? "Wait until the exam session is connected." : "Task already started.");
  setActionLock(resetBtn, executing || restoring || !examSocketReady || (!taskStarted && !ownsEnvironment) || completed, executing ? busyReason : restoring ? "Restoring task state from the server." : !examSocketReady ? "Wait until the exam session is connected." : "Start the task first.");
  setActionLock(runBtn, executing || restoring || !examSocketReady || !started, executing ? busyReason : restoring ? "Restoring task state from the server." : !examSocketReady ? "Wait until the exam session is connected." : "Start the task first.");
  setActionLock(recordsBtn, executing || restoring || (!taskStarted && !completed && !abandoned), executing ? busyReason : restoring ? "Restoring task state from the server." : "Start the task first.");

  if (executing) {
    setNextStep(`Task ${escapeHtml(pendingExecution.task_id)}: ${escapeHtml(getLifecycle().message || "Processing. Please wait.")}${!examSocketReady ? " Reconnect Exam to restore progress." : ""}`);
    return;
  }
  if (!examHasRemainingTasks) {
    setNextStep("Exam completed. Review the report below.");
    return;
  }
  if (restoring) {
    setNextStep("Restoring task state from the server...");
    return;
  }
  if (!taskStarted) {
    setNextStep(examSocketReady ? "Click Start question to prepare the environment." : "Connect the exam session first.");
    return;
  }
  if (completed) {
    setNextStep("Task completed. Use Records to view attempt history.");
    return;
  }
  if (abandoned) {
    setNextStep("Attempts exhausted. Use Leave question and clean up to restart this question.");
    return;
  }
  if (!examSocketReady) {
    setNextStep("Reconnecting exam session ...");
    return;
  }
  setNextStep(escapeHtml(getLifecycle().message));
}

function renderExamResponse(json, action = "") {
  if (!json || typeof json !== "object" || Array.isArray(json)) {
    return "";
  }

  const lines = [];
  const status = json.status || (json.state && json.state.status);
  const rawPhaseId = json.current_phase || (json.state && json.state.current_phase_id);
  const phaseId = rawPhaseId === "answer" ? null : rawPhaseId;
  const phaseName = rawPhaseId === "answer" ? null : json.phase_name || (json.state && json.state.current_phase_name);
  const nextPhase = json.next_phase || (json.state && json.state.next_phase_id);
  const testResult = json.test_result;
  const attempts = json.attempts;
  const maxAttempts = json.max_attempts;
  const points = typeof json.total_points !== "undefined" ? json.total_points : json.points;

  if (status) lines.push(`<p><strong>Status:</strong> ${escapeHtml(status)}</p>`);
  if (phaseName && phaseId && String(phaseName).toLowerCase() !== String(phaseId).toLowerCase()) {
    lines.push(`<p><strong>Phase:</strong> ${escapeHtml(phaseName)} (${escapeHtml(phaseId)})</p>`);
  } else if (phaseName || phaseId) {
    lines.push(`<p><strong>Phase:</strong> ${escapeHtml(phaseName || phaseId)}</p>`);
  }
  if (nextPhase) lines.push(`<p><strong>Next phase:</strong> ${escapeHtml(nextPhase)}</p>`);
  if (typeof points !== "undefined") lines.push(`<p><strong>Points:</strong> ${escapeHtml(points)}</p>`);
  if (typeof attempts !== "undefined" || typeof maxAttempts !== "undefined") {
    const attemptText = `${typeof attempts !== "undefined" ? attempts : "-"} / ${typeof maxAttempts !== "undefined" ? maxAttempts : "-"}`;
    lines.push(`<p><strong>Attempts:</strong> ${escapeHtml(attemptText)}</p>`);
  }
  if (testResult) lines.push(`<p><strong>Test result:</strong> ${escapeHtml(testResult)}</p>`);
  if (json.task_id) lines.push(`<p><strong>Task:</strong> ${escapeHtml(json.task_id)}</p>`);

  if (Array.isArray(json.executed_phases) && json.executed_phases.length > 0) {
    const phaseLines = json.executed_phases.map((phase, index) => {
      const phaseLabel = phase.phase_name || phase.phase_id || `Phase ${index + 1}`;
      const resultLabel = phase.test_result || (phase.success ? "OK" : "UNKNOWN");
      const reportLink = phase.report_url
        ? `, Report: ${buildLinkHtml(phase.report_url, "Open report")}`
        : "";
      return `<li>#${index + 1} ${escapeHtml(phaseLabel)}: ${escapeHtml(resultLabel)}${reportLink}</li>`;
    });
    lines.push("<p><strong>Run details:</strong></p>");
    lines.push(`<ul class="response-link-list">${phaseLines.join("")}</ul>`);
  }

  if (json.cleanup_triggered) {
    lines.push("<p><strong>Cleanup:</strong> triggered automatically</p>");
  }

  const normalizedMessage = typeof json.message === "string" ? json.message.trim() : "";
  const normalizedTaskDescription = typeof json.task_description === "string" ? json.task_description.trim() : "";
  if (normalizedMessage) {
    const repeatsTaskDescription =
      normalizedTaskDescription &&
      (normalizedMessage === normalizedTaskDescription ||
        normalizedMessage.endsWith(normalizedTaskDescription));
    const messageSummary = repeatsTaskDescription
      ? normalizedMessage.slice(0, normalizedMessage.length - normalizedTaskDescription.length).trim()
      : normalizedMessage;

    if (messageSummary) {
      lines.push(`<p><strong>Message:</strong></p><div class="markdown-body">${renderMarkdown(messageSummary)}</div>`);
    }
    if (repeatsTaskDescription) {
      lines.push("<p><strong>Message:</strong> Same as the current question above.</p>");
    }
    if (!messageSummary && !repeatsTaskDescription) {
      lines.push(`<p><strong>Message:</strong></p><div class="markdown-body">${renderMarkdown(json.message)}</div>`);
    }
  }

  const links = [];
  if (json.report_url) {
    links.push(`<li>${buildLinkHtml(json.report_url, "Open test report")}</li>`);
  }
  if (json.easter_egg_url) {
    links.push(`<li>${buildLinkHtml(json.easter_egg_url, "Open bonus link")}</li>`);
  }
  if (links.length > 0) {
    lines.push(`<p><strong>Links:</strong></p><ul class="response-link-list">${links.join("")}</ul>`);
  }

  if (action === "records" && Array.isArray(json.records)) {
    if (json.records.length === 0) {
      lines.push("<p><strong>Attempt history:</strong> No recorded exam runs yet.</p>");
    } else {
      const recordLines = json.records.map((record, index) => {
        const taskId = record.task_id || record.task || "-";
        const phase = record.phase || record.current_phase || record.gamePhase || "-";
        const result = record.test_result || record.testResult || "-";
        const time = record.time || "-";
        const reportLink = record.report_url || record.reportUrl
          ? `, Report: ${buildLinkHtml(record.report_url || record.reportUrl, "Open report")}`
          : "";
        return `<li>#${index + 1} Task: ${escapeHtml(taskId)}, Phase: ${escapeHtml(phase)}, Result: ${escapeHtml(result)}, Time: ${escapeHtml(time)}${reportLink}</li>`;
      });
      lines.push("<p><strong>Attempt history:</strong> Each row is one saved grading run for this exam code.</p>");
      lines.push(`<ul class="response-link-list">${recordLines.join("")}</ul>`);
    }
  }

  if (lines.length === 0) {
    return "";
  }

  return window.DOMPurify ? window.DOMPurify.sanitize(lines.join("")) : lines.join("");
}

function writeExamResponse(json, target = output, action = "") {
  if (target !== output) {
    write(json, target);
    return;
  }
  const html = renderExamResponse(json, action);
  if (!html) {
    write(json, target);
    return;
  }
  target.innerHTML = html;
}

function renderExamCompletionReport(data = {}) {
  const taskSummaries = Array.isArray(data.task_summaries) ? data.task_summaries : [];
  const finishedTasks = Array.isArray(data.finished_tasks) ? data.finished_tasks : [];
  const examScore = typeof data.exam_score !== "undefined" ? data.exam_score : examScoreOutput.textContent;
  const lines = [
    "# Exam completed",
    "",
    `- Final exam score: **${examScore}**`,
    `- Finished tasks: **${finishedTasks.length} / ${taskSummaries.length || finishedTasks.length}**`,
  ];

  if (taskSummaries.length > 0) {
    lines.push("", "| Task | Status | Score |", "| --- | --- | ---: |");
    taskSummaries.forEach((task) => {
      lines.push(
        `| ${task.task_id || "-"} | ${task.status || "-"} | ${typeof task.total_points !== "undefined" ? task.total_points : "-"} |`
      );
    });
  }

  return lines.join("\n");
}

function showExamCompletionReport(data = {}) {
  examHasRemainingTasks = false;
  taskStarted = false;
  statusSyncPending = false;
  backendTaskStatus = "COMPLETED";
  backendNextAction = null;
  setCurrentPhaseState("cleanup");
  writeMarkdown(renderExamCompletionReport(data), questionOutput);
  markOutput.textContent = "-";
  if (typeof data.exam_score !== "undefined") {
    examScoreOutput.textContent = String(data.exam_score);
  }
  phaseOutput.textContent = "Phase: Exam completed";
  examPhaseEstimateRow.classList.add("hidden");
  examTaskEstimateRow.classList.add("hidden");
  setNextStep("Exam completed. Review the report below.");
  updateExamButtons();
  updateStateMachineUI();
}

function updateExamEstimates(json) {
  const phaseSeconds = Number.isFinite(Number(json?.estimated_phase_seconds)) ? Number(json.estimated_phase_seconds) : null;
  const remainingSeconds = Number.isFinite(Number(json?.estimated_remaining_task_seconds))
    ? Number(json.estimated_remaining_task_seconds)
    : null;
  const taskSeconds = Number.isFinite(Number(json?.estimated_task_seconds)) ? Number(json.estimated_task_seconds) : null;
  const taskStatus = String(json?.status || json?.state?.status || "").toUpperCase();

  if (phaseSeconds !== null) {
    examPhaseEstimateLabel.textContent = formatEstimateDuration(phaseSeconds);
    examPhaseEstimateRow.classList.remove("hidden");
  } else {
    examPhaseEstimateRow.classList.add("hidden");
  }

  const taskEstimate = remainingSeconds !== null ? remainingSeconds : taskStatus === "NOT_STARTED" ? taskSeconds : null;
  if (taskEstimate !== null) {
    examTaskEstimateTitle.textContent = taskStatus === "NOT_STARTED" ? "Task estimate" : "Remaining task time";
    examTaskEstimateLabel.textContent = formatEstimateDuration(taskEstimate);
    examTaskEstimateRow.classList.remove("hidden");
  } else {
    examTaskEstimateRow.classList.add("hidden");
  }
}

function updateExamSummary(json, action) {
  updateExamEstimates(json);
  if (json.task_description) {
    writeMarkdown(json.task_description, questionOutput);
  }

  if (action === "status" && json.state) {
    if (typeof json.state.total_points !== "undefined") {
      markOutput.textContent = String(json.state.total_points);
    }
  }

  if (typeof json.total_points !== "undefined") {
    markOutput.textContent = String(json.total_points);
  } else if (typeof json.points !== "undefined") {
    markOutput.textContent = String(json.points);
  }
  if (typeof json.exam_score !== "undefined") {
    examScoreOutput.textContent = String(json.exam_score);
  }

  if (Array.isArray(json.remaining_tasks)) {
    const selectedTask = document.getElementById("task").value;
    updateTaskOptions(json.remaining_tasks, selectedTask);
    if (json.remaining_tasks.length === 0) {
      showExamCompletionReport(json);
      return;
    }
    if (selectedTask !== document.getElementById("task").value) {
      return;
    }
  }

  if (action === "records" && Array.isArray(json.records)) {
    phaseOutput.textContent = `Records: ${json.records.length}`;
  }

  if (action === "status" && (json.state?.status || json.status)) {
    const status = json.state?.status || (json.status === "OK" && !json.state ? "NOT_STARTED" : json.status);
    backendTaskStatus = normalizeTaskStatus(status);
    taskStarted = backendTaskStatus !== "NOT_STARTED";
    if (!taskStarted) {
      if (!Object.hasOwn(json, "active_environment")) activeEnvironment = null;
      examFlowState = "ready_to_start";
      setCurrentPhaseState("ready");
      writeMarkdown("Press Start to load the question.", questionOutput);
      phaseOutput.textContent = "Phase: -";
      markOutput.textContent = "0";
    } else {
      examFlowState =
        backendTaskStatus === "COMPLETED"
          ? "completed"
          : backendTaskStatus === "ABANDONED"
            ? "abandoned"
            : "started";
      const phase = json.state?.current_phase_name || json.state?.current_phase_id || json.phase_name || json.current_phase;
      if (phase) {
        setCurrentPhaseState(phase);
      }
      if (backendTaskStatus === "IN_PROGRESS" && !activeEnvironment) {
        activeEnvironment = { task_id: readInputs().task, exam_code: readInputs().examCode };
      }
    }
    currentLifecycle = json.lifecycle || null;
    updateExamButtons();
  }
}

function showResponse(text, target = output, action = "") {
  try {
    const json = JSON.parse(text);
    if (action === "status" && json.status_request_id && json.status_request_id !== latestStatusRequestId) {
      return;
    }
    if (json.active_execution) {
      if (finishedExecutionIds.has(json.active_execution.execution_id)) {
        return;
      }
      if (pendingExecution?.command_request_id
        && !["status", "records"].includes(action)
        && json.status !== "BUSY"
        && json.active_execution.command_request_id !== pendingExecution.command_request_id) {
        return;
      }
      pendingExecution = json.active_execution;
      if (pendingExecution.task_id === readInputs().task && pendingExecution.phase) {
        setCurrentPhaseState(pendingExecution.phase);
      }
      currentLifecycle = json.lifecycle || null;
      if (action === "status") {
        statusSyncPending = false;
      }
      startRunResponseWatchdog();
      updateExamButtons();
      writeExamResponse(json, target, action);
      return;
    }
    if (json.command_finished) {
      if (finishedExecutionIds.has(json.execution_id)) {
        return;
      }
      if (pendingExecution && (
        (pendingExecution.execution_id && pendingExecution.execution_id !== json.execution_id)
        || (!pendingExecution.execution_id && pendingExecution.command_request_id !== json.command_request_id)
        || pendingExecution.task_id !== json.task_id
      )) {
        return;
      }
      finishedExecutionIds.add(json.execution_id);
      pendingExecution = null;
      statusSyncPending = false;
      latestStatusRequestId = "";
      stopRunResponseWatchdog();
      if (json.task_id !== readInputs().task) {
        refreshCurrentTaskStatus();
        return;
      }
    } else if (pendingExecution) {
      const authoritativeIdle = action === "status"
        && json.status_request_id === latestStatusRequestId
        && json.status_request_id
        && Object.hasOwn(json, "active_execution")
        && !["ERROR", "BUSY", "RUNNING"].includes(json.status);
      if (!authoritativeIdle) {
        if (json.message) {
          writeExamResponse(json, target, action);
        }
        return;
      }
      if (pendingExecution.execution_id) {
        finishedExecutionIds.add(pendingExecution.execution_id);
      }
      pendingExecution = null;
      stopRunResponseWatchdog();
    }
    if (["BUSY", "RUNNING", "QUEUED"].includes(json.status)) {
      updateExamButtons();
      writeExamResponse(json, target, action);
      return;
    }
    if (action === "status") {
      statusSyncPending = false;
    }
    if (Object.hasOwn(json, "active_environment")) {
      activeEnvironment = json.active_environment;
    }
    if (activeEnvironment && activeEnvironment.task_id !== readInputs().task && !pendingExecution) {
      document.getElementById("examCode").value = activeEnvironment.exam_code;
      const available = loadState().allowedTasks || [];
      updateTaskOptions([...new Set([...available, activeEnvironment.task_id])], activeEnvironment.task_id);
      write("Restoring the question that owns your environment. Finish it or leave it with cleanup before changing questions.");
      return;
    }
    if (json.status === "ERROR" && ["start", "reset", "run", "status"].includes(action)) {
      updateExamButtons();
      writeExamResponse(json, target, action);
      return;
    }
    backendNextAction = json && json.next_action ? json.next_action : null;

    if (action === "save-account") {
      k8sAccountReady = json.status === "OK";
      saveState({
        apiKey: document.getElementById("apiKey").value.trim(),
        endpoint: document.getElementById("endpoint").value.trim(),
        accountReady: k8sAccountReady,
      });
      if (k8sAccountReady) {
        setCurrentPhaseState("setup");
      }
      updateExamButtons();
      updateStateMachineUI();
    }

    if (action === "verify" && json.status === "VERIFIED") {
      if (json.game) {
        setGameValue(json.game);
      }
      updateTaskOptions(
        Array.isArray(json.remaining_tasks) ? json.remaining_tasks : json.allowed_tasks,
        document.getElementById("task").value
      );
      setExamReady(true);
      saveState({
        apiKey: document.getElementById("apiKey").value.trim(),
        endpoint: document.getElementById("endpoint").value.trim(),
        examCode: document.getElementById("examCode").value.trim(),
        game: json.game || "",
        allowedTasks: Array.isArray(json.allowed_tasks) ? json.allowed_tasks : [],
        remainingTasks: Array.isArray(json.remaining_tasks) ? json.remaining_tasks : [],
        task: document.getElementById("task").value,
        websocketUrl: json.websocket_url || "",
        examReady: true,
        accountReady: k8sAccountReady,
      });
      markOutput.textContent = "0";
      examScoreOutput.textContent = typeof json.exam_score !== "undefined" ? String(json.exam_score) : "0";
      if (json.websocket_url) {
        examSocketBaseUrl = json.websocket_url;
      }
      examFlowState = "ready_to_start";
      examSocketReady = false;
      taskStarted = false;
      statusSyncPending = false;
      backendNextAction = null;
      backendTaskStatus = "NOT_STARTED";
      setCurrentPhaseState("ready");
      updateExamButtons();
      updateStateMachineUI();
      if (Array.isArray(json.remaining_tasks) && json.remaining_tasks.length === 0) {
        showExamCompletionReport(json);
      } else {
        updateExamEstimates(json);
        connectExamSocket();
      }
    } else if (action === "verify" && json.status === "ERROR") {
      setExamReady(false);
      saveState({ examReady: false });
      statusSyncPending = false;
      markOutput.textContent = "0";
      examScoreOutput.textContent = "0";
      examPhaseEstimateRow.classList.add("hidden");
      examTaskEstimateRow.classList.add("hidden");
      closeExamSocket();
    }

    if (["start", "run", "reset"].includes(action) && json.status === "RESET") {
      taskStarted = false;
      activeEnvironment = json.active_environment || null;
      statusSyncPending = false;
      examFlowState = "ready_to_start";
      backendTaskStatus = "NOT_STARTED";
      backendNextAction = null;
      setCurrentPhaseState("ready");
      phaseOutput.textContent = "Phase: -";
      markOutput.textContent = "0";
      updateExamEstimates(json);
      writeMarkdown("Choose a question, then press Start question to prepare its environment.", questionOutput);
      updateExamButtons();
      updateStateMachineUI();
    } else if (["start", "run", "reset"].includes(action)) {
      taskStarted = true;
      statusSyncPending = false;
      if (json.status === "COMPLETED") {
        examFlowState = "completed";
        backendTaskStatus = "COMPLETED";
        activeEnvironment = json.active_environment || null;
      } else if (json.status === "ABANDONED") {
        examFlowState = "abandoned";
        backendTaskStatus = "ABANDONED";
        activeEnvironment = json.active_environment || null;
      } else if (json.status === "FAILED" || json.status === "ERROR") {
        examFlowState = "started";
        backendTaskStatus = "IN_PROGRESS";
        setCurrentPhaseState(json.current_phase || json.lifecycle?.phase || currentPhaseState);
      } else {
        examFlowState = "started";
        backendTaskStatus = "IN_PROGRESS";
        if (json.current_phase || json.phase_name) {
          setCurrentPhaseState(json.phase_name || json.current_phase);
        }
      }
      if (backendTaskStatus === "IN_PROGRESS" && !activeEnvironment) {
        activeEnvironment = { task_id: readInputs().task, exam_code: readInputs().examCode };
      }
      currentLifecycle = json.lifecycle || null;
      updateExamButtons();
      updateStateMachineUI();
    }

    if (target === output) {
      updateExamSummary(json, action);
    }
    writeExamResponse(json, target, action);
  } catch {
    write(text, target);
  }
}

async function callApi(action) {
  if ((pendingExecution || statusSyncPending || httpBusy) && !["reconnect", "status"].includes(action)) {
    write("Wait for the current exam operation to finish before changing or submitting a task.");
    return;
  }
  if (action === "status") {
    refreshCurrentTaskStatus();
    return;
  }
  const { apiKey, authMethod, kubeconfig, kubeconfigFile, endpoint, clientCertificate, clientKey, examCode } = readInputs();
  if (!apiKey) {
    write("API Key is required.", setupOutput);
    return;
  }

  if (action === "save-account") {
    const hasKubeconfig = Boolean(kubeconfig.trim()) || Boolean(kubeconfigFile);
    const useKubeconfig = authMethod === "kubeconfig";
    if (useKubeconfig) {
      if (!hasKubeconfig) {
        write("Paste kubeconfig YAML or choose a kubeconfig file.", setupOutput);
        return;
      }
    } else {
      if (!endpoint) {
        write("Endpoint is required for manual mode.", setupOutput);
        return;
      }
      if ((clientCertificate && !clientKey) || (!clientCertificate && clientKey)) {
        write("Client certificate and client key must be provided together.", setupOutput);
        return;
      }
    }

    const formData = new FormData();
    if (useKubeconfig && kubeconfig.trim()) {
      formData.append("kubeconfig", kubeconfig.trim());
    }
    if (useKubeconfig && kubeconfigFile) {
      formData.append("kubeconfig-file", kubeconfigFile);
    }
    if (!useKubeconfig && endpoint) {
      formData.append("endpoint", endpoint);
    }
    if (!useKubeconfig && clientCertificate && clientKey) {
      formData.append("client-certificate", clientCertificate);
      formData.append("client-key", clientKey);
    }

    setBusy(true);
    write("Submitting Kubernetes login ...", setupOutput);
    try {
      const res = await fetch(`${BASE_URL}/save-k8s-account`, {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          Authorization: apiKey,
        },
        body: formData,
      });
      const text = await res.text();
      showResponse(text, setupOutput, action);
    } catch (err) {
      write(`Request failed: ${err.message}`, setupOutput);
    } finally {
      setBusy(false);
    }
    return;
  }

  if (action === "reset") {
    const ok = window.confirm(
      "Leave this question and clean up its Kubernetes resources?\n\nThis clears this question's current progress after cleanup succeeds. Attempt history is preserved. You can then choose another question or restart this one."
    );
    if (!ok) {
      write("Reset cancelled.", output);
      return;
    }
  }

  if (action === "reconnect") {
    closeExamSocket();
    connectExamSocket();
    return;
  }

  if (["start", "reset", "run", "status", "records"].includes(action)) {
    const now = Date.now();
    if (now - lastExamActionAt < EXAM_ACTION_COOLDOWN_MS) {
      write("Please wait a moment before clicking again.", output);
      return;
    }
    lastExamActionAt = now;
    sendExamActionViaSocket(action);
    return;
  }

  if (action !== "verify") {
    write(`Unknown action: ${action}`, output);
    return;
  }

  setBusy(true);
  write("Calling exam/verify ...", output);
  try {
    const res = await fetch(`${BASE_URL}/exam/verify-code?examCode=${encodeURIComponent(examCode)}`, {
      method: "GET",
      headers: {
        "x-api-key": apiKey,
        Authorization: apiKey,
      },
    });
    const text = await res.text();
    showResponse(text, output, action);
  } catch (err) {
    write(`Request failed: ${err.message}`, output);
  } finally {
    setBusy(false);
  }
}

buttons.forEach((btn) => {
  btn.addEventListener("click", () => callApi(btn.dataset.action));
});

output.addEventListener("click", (event) => {
  const popupButton = event.target.closest("[data-popup-url]");
  if (!popupButton) {
    return;
  }
  const encodedUrl = popupButton.getAttribute("data-popup-url");
  if (!encodedUrl) {
    return;
  }
  openPopup(decodeURIComponent(encodedUrl));
});

document.getElementById("apiKey").addEventListener("input", (e) => {
  saveState({ apiKey: e.target.value });
});

document.getElementById("endpoint").addEventListener("input", (e) => {
  k8sAccountReady = false;
  saveState({ endpoint: e.target.value, accountReady: false });
  updateExamButtons();
});

document.getElementById("kubeconfig").addEventListener("input", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
  updateExamButtons();
});

document.getElementById("kubeconfigFile").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
  updateExamButtons();
});

document.getElementById("clientCertificate").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
  updateExamButtons();
});

document.getElementById("clientKey").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
  updateExamButtons();
});

authMethodInputs.forEach((input) => {
  input.addEventListener("change", () => {
    k8sAccountReady = false;
    setAuthMethod(input.value);
    updateExamButtons();
  });
});

document.getElementById("examCode").addEventListener("input", (e) => {
  saveState({ examCode: e.target.value });
});

document.getElementById("task").addEventListener("change", (e) => {
  if (pendingExecution || statusSyncPending || httpBusy || activeEnvironment) {
    e.target.value = selectedExamTask;
    write("This question still owns your environment. Finish it or use Leave question and clean up before changing questions.");
    return;
  }
  selectedExamTask = e.target.value;
  saveState({ task: e.target.value });
  showLoadingSelectedTaskState();
  connectExamSocket();
});

resetStateButton.addEventListener("click", () => {
  if (pendingExecution || statusSyncPending || httpBusy || activeEnvironment) {
    write("Wait for the current exam operation to finish before resetting saved data.");
    return;
  }
  const ok = window.confirm(
    "Reset saved exam form data?\n\nThis clears the API key, kubeconfig input, endpoint, exam code, task selection, and cached exam state from this browser."
  );
  if (!ok) {
    return;
  }

  closeExamSocket();
  examSocketBaseUrl = "";
  k8sAccountReady = false;
  clearState();
  document.getElementById("apiKey").value = "";
  document.getElementById("kubeconfig").value = "";
  document.getElementById("kubeconfigFile").value = "";
  document.getElementById("endpoint").value = "";
  document.getElementById("clientCertificate").value = "";
  document.getElementById("clientKey").value = "";
  setAuthMethod("kubeconfig", { persist: false });
  document.getElementById("examCode").value = "";
  setGameValue("");
  document.getElementById("task").innerHTML = "";
  writeMarkdown("Press Start to load the question.", questionOutput);
  setNextStep(LOCKED_EXAM_GUIDANCE);
  markOutput.textContent = "0";
  examScoreOutput.textContent = "0";
  phaseOutput.textContent = "Phase: -";
  examPhaseEstimateRow.classList.add("hidden");
  examTaskEstimateRow.classList.add("hidden");
  setConnectionStatus("Disconnected");
  examFlowState = "unverified";
  setCurrentPhaseState("setup");
  setExamReady(false);
  write("Ready.", setupOutput);
});

setExamReady(false);
setConnectionStatus("Disconnected");
updateExamButtons();
writeMarkdown("Press Start to load the question.", questionOutput);
examPhaseEstimateRow.classList.add("hidden");
examTaskEstimateRow.classList.add("hidden");

const restored = loadState();
setAuthMethod(restored.authMethod || (restored.endpoint ? "manual" : "kubeconfig"), { persist: false });
if (restored.endpoint) {
  document.getElementById("endpoint").value = restored.endpoint;
}
if (restored.apiKey) {
  document.getElementById("apiKey").value = restored.apiKey;
}
if (restored.examCode) {
  document.getElementById("examCode").value = restored.examCode;
}
if (restored.game) {
  setGameValue(restored.game);
}
if (restored.websocketUrl) {
  examSocketBaseUrl = restored.websocketUrl;
}
if (restored.accountReady) {
  k8sAccountReady = true;
}
if (Array.isArray(restored.allowedTasks) && restored.allowedTasks.length > 0) {
  updateTaskOptions(restored.allowedTasks);
  if (restored.task) {
    document.getElementById("task").value = restored.task;
    selectedExamTask = restored.task;
  }
}
if (restored.examReady) {
  setExamReady(true);
  examFlowState = "ready_to_start";
  examSocketReady = false;
  setConnectionStatus("Disconnected");
  if (document.getElementById("task").value) {
    showLoadingSelectedTaskState();
  }
  connectExamSocket();
}
updateStateMachineUI();
