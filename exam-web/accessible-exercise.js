const APP_CONFIG = window.__K8S_PORTAL_CONFIG__ || {};
const BASE_URL = APP_CONFIG.baseUrl || "";
const GAME_WS_URL = APP_CONFIG.gameWsUrl || "";
const PORTAL_STORAGE_KEY = "k8s-student-portal-state-v1";

const apiKeyInput = document.getElementById("apiKey");
const unlockButton = document.getElementById("unlockView");
const accessStatus = document.getElementById("accessStatus");
const exerciseView = document.getElementById("exerciseView");
const connectionStatus = document.getElementById("connectionStatus");
const triggerGradingButton = document.getElementById("triggerGrading");
const checkScoreButton = document.getElementById("checkScore");
const resetTaskButton = document.getElementById("resetTask");
const resetExerciseButton = document.getElementById("resetExercise");
const skipTaskButton = document.getElementById("skipTask");
const exerciseOutput = document.getElementById("exerciseOutput");
const currentTask = document.getElementById("currentTask");
const taskInstructions = document.getElementById("taskInstructions");
const currentStep = document.getElementById("currentStep");
const contrastToggle = document.getElementById("contrastToggle");
const textSizeInput = document.getElementById("textSize");
const textSizeLabel = document.getElementById("textSizeLabel");
const saveLoginButton = document.getElementById("saveLogin");
const setupOutput = document.getElementById("setupOutput");
const kubernetesStatus = document.getElementById("kubernetesStatus");
const kubeconfigMethod = document.getElementById("kubeconfigMethod");
const manualMethod = document.getElementById("manualMethod");
const loginInputIds = ["kubeconfig", "kubeconfigFile", "endpoint", "clientCertificate", "clientKey"];
const actionButtons = [
  triggerGradingButton, checkScoreButton, resetTaskButton, resetExerciseButton, skipTaskButton,
];

let allowedGame = "";
let socket = null;
let socketReady = false;
let pendingAction = null;
let actionInFlight = false;
let displayedTaskId = "";
let loginInFlight = false;
let verifiedApiKey = "";

function writeOutput(text) {
  exerciseOutput.textContent = text;
}

function writeTaskInstructions(text) {
  if (window.marked && window.DOMPurify) {
    taskInstructions.innerHTML = window.DOMPurify.sanitize(
      window.marked.parse(text, { breaks: true, gfm: true }),
    );
  } else {
    taskInstructions.textContent = text;
  }
}

function setActionBusy(busy) {
  actionInFlight = busy;
  for (const button of actionButtons) {
    button.disabled = busy || loginInFlight || !allowedGame;
  }
  triggerGradingButton.disabled ||= verifiedApiKey !== apiKeyInput.value.trim();
  saveLoginButton.disabled = busy || loginInFlight;
  apiKeyInput.disabled = busy || loginInFlight;
  for (const id of [...loginInputIds, "kubeconfigMethod", "manualMethod"]) {
    document.getElementById(id).disabled = busy || loginInFlight;
  }
}

function invalidateLogin() {
  verifiedApiKey = "";
  kubernetesStatus.textContent = "Not verified - submit Kubernetes Login";
  setActionBusy(actionInFlight);
}

function selectLoginMethod(manual) {
  manualMethod.checked = manual;
  kubeconfigMethod.checked = !manual;
  document.getElementById("kubeconfigPanel").classList.toggle("hidden", manual);
  document.getElementById("manualPanel").classList.toggle("hidden", !manual);
  invalidateLogin();
}

async function submitKubernetesLogin() {
  if (loginInFlight || actionInFlight) return;
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey || !BASE_URL) {
    setupOutput.textContent = !apiKey ? "API Key is required." : "The exercise service is not configured.";
    return;
  }
  const get = (id) => document.getElementById(id);
  const formData = new FormData();
  if (!manualMethod.checked) {
    const yaml = get("kubeconfig").value.trim();
    const file = get("kubeconfigFile").files[0];
    if (!yaml && !file) {
      setupOutput.textContent = "Paste kubeconfig YAML or choose a kubeconfig file.";
      return;
    }
    if (yaml) formData.append("kubeconfig", yaml);
    if (file) formData.append("kubeconfig-file", file);
  } else {
    const endpoint = get("endpoint").value.trim();
    const certificate = get("clientCertificate").files[0];
    const key = get("clientKey").files[0];
    if (!endpoint || Boolean(certificate) !== Boolean(key)) {
      setupOutput.textContent = !endpoint
        ? "Endpoint is required for manual mode."
        : "Client certificate and client key must be provided together.";
      return;
    }
    formData.append("endpoint", endpoint);
    if (certificate && key) {
      formData.append("client-certificate", certificate);
      formData.append("client-key", key);
    }
  }
  verifiedApiKey = "";
  loginInFlight = true;
  setActionBusy(actionInFlight);
  kubernetesStatus.textContent = "Checking from AWS Lambda...";
  setupOutput.textContent = "Submitting Kubernetes login...";
  try {
    const response = await fetch(`${BASE_URL}/save-k8s-account`, {
      method: "POST", headers: { "x-api-key": apiKey, Authorization: apiKey }, body: formData,
    });
    const text = await response.text();
    let result;
    try {
      result = JSON.parse(text);
    } catch {
      throw new Error(text || "The login service returned an empty response.");
    }
    if (!response.ok || result?.status !== "OK") {
      throw new Error(result?.message || text || "Kubernetes login verification failed.");
    }
    verifiedApiKey = apiKey;
    kubernetesStatus.textContent = "Verified by AWS Lambda on last submission";
    setupOutput.textContent = [
      result.message,
      result.authType ? `Auth Type: ${result.authType}` : "",
      result.context ? `Context: ${result.context}` : "",
      result.cluster ? `Cluster: ${result.cluster}` : "",
    ].filter(Boolean).join("\n");
  } catch (error) {
    kubernetesStatus.textContent = "Verification failed";
    setupOutput.textContent = `Could not save Kubernetes login: ${error.message}`;
  } finally {
    loginInFlight = false;
    setActionBusy(actionInFlight);
  }
}

function closeSocket() {
  const previous = socket;
  socket = null;
  socketReady = false;
  pendingAction = null;
  if (previous) previous.close();
  connectionStatus.textContent = "Disconnected";
}

function renderGameStatus(payload) {
  renderTaskInstructions(payload);
  const lines = [];
  const message = payload.message || payload.progress_message;
  if (message && (!payload.task_description || String(message).trim() !== String(payload.task_description).trim())) {
    lines.push(String(message));
  }
  if (payload.task_id) lines.push(`Task: ${payload.task_id}`);
  if (payload.phase_name || payload.current_phase) {
    lines.push(`Current step: ${payload.phase_name || payload.current_phase}`);
  }
  if (typeof payload.total_score !== "undefined") {
    lines.push(`Total exercise score: ${payload.total_score}`);
  }
  if (typeof payload.total_points !== "undefined") {
    lines.push(`Task points: ${payload.total_points}`);
  }
  if (Array.isArray(payload.completed_tasks)) {
    lines.push(`Completed tasks (${payload.completed_tasks.length}):\n${payload.completed_tasks.join("\n") || "None"}`);
  }
  if (Array.isArray(payload.skipped_tasks)) {
    lines.push(`Skipped tasks (${payload.skipped_tasks.length}):\n${payload.skipped_tasks.join("\n") || "None"}`);
  }
  if (payload.report_url) lines.push(`Report: ${payload.report_url}`);
  writeOutput(lines.join("\n\n") || `Status: ${payload.status || "Updated"}`);
}

function renderTaskInstructions(payload) {
  if (payload.status === "COMPLETED" && !payload.task_id) {
    displayedTaskId = "";
    currentTask.textContent = "All exercise tasks completed.";
    taskInstructions.textContent = "There are no remaining tasks.";
    currentStep.textContent = "";
    return;
  }
  if (!payload.task_id) return;
  if (payload.task_id !== displayedTaskId) {
    displayedTaskId = payload.task_id;
    taskInstructions.textContent = "";
    currentStep.textContent = "";
  }
  currentTask.textContent = `Task: ${payload.task_id}`;
  if (payload.task_description) {
    writeTaskInstructions(String(payload.task_description));
  }
  const phase = payload.next_game_phrase || payload.current_phase;
  if (payload.phase_name || phase) {
    currentStep.textContent = `Current step: ${payload.phase_name || String(phase).toUpperCase()}`;
  }
  const status = String(payload.status || "").toUpperCase();
  if (!payload.task_description && status === "NOT_STARTED" && !payload.skipped_task && payload.message) {
    writeTaskInstructions(String(payload.message));
  }
}

function handleGameMessage(rawMessage) {
  let envelope;
  try {
    envelope = JSON.parse(rawMessage);
  } catch (error) {
    writeOutput(`Could not read the game response: ${error.message}`);
    setActionBusy(false);
    return;
  }
  const payload = envelope?.type === "game_status" ? envelope.data : envelope;
  if (!payload || typeof payload !== "object" || payload.status === "SUBSCRIBED") return;
  if (payload.status === "QUEUED") {
    writeOutput("Your request was received. Waiting for the game service...");
    return;
  }
  renderGameStatus(payload);
  setActionBusy(String(payload.status || "").toUpperCase() === "RUNNING");
}

function connectAndSend(action) {
  if (!allowedGame) {
    accessStatus.textContent = "Check access before using the exercise controls.";
    return;
  }
  if (!GAME_WS_URL) {
    writeOutput("The game service is not configured. Please contact your teacher.");
    return;
  }
  if (actionInFlight) {
    writeOutput("A game request is already running. Please wait for its response.");
    return;
  }
  if (loginInFlight || (action === "talk" && verifiedApiKey !== apiKeyInput.value.trim())) {
    writeOutput("Submit Kubernetes Login and verify cluster access before triggering grading.");
    return;
  }
  const payload = { action, apiKey: apiKeyInput.value.trim(), game: allowedGame };
  // Match hkzero's enemy-defeat event and the shared interactive game flow.
  if (action === "talk") payload.npc = "hkzero";
  pendingAction = payload;
  setActionBusy(true);
  const messages = {
    talk: "Triggering game grading...",
    status: "Checking total score and current exercise progress...",
    reset: "Resetting current task...",
    "reset-all": "Resetting whole exercise...",
    skip: "Skipping current task...",
  };
  writeOutput(messages[action]);
  if (socket && socket.readyState === WebSocket.OPEN && socketReady) {
    socket.send(JSON.stringify(payload));
    pendingAction = null;
    return;
  }
  if (socket && socket.readyState === WebSocket.CONNECTING) return;
  try {
    socket = new WebSocket(GAME_WS_URL);
  } catch (error) {
    socket = null;
    setActionBusy(false);
    connectionStatus.textContent = "Connection failed";
    writeOutput(`Could not connect to the game service: ${error.message}`);
    return;
  }
  const activeSocket = socket;
  connectionStatus.textContent = "Connecting";
  activeSocket.addEventListener("open", () => {
    if (socket !== activeSocket) return;
    socketReady = true;
    connectionStatus.textContent = "Connected";
    activeSocket.send(JSON.stringify({
      action: "subscribe", apiKey: apiKeyInput.value.trim(), game: allowedGame,
    }));
    if (pendingAction) {
      activeSocket.send(JSON.stringify(pendingAction));
      pendingAction = null;
    }
  });
  activeSocket.addEventListener("message", (event) => {
    if (socket === activeSocket) handleGameMessage(event.data);
  });
  activeSocket.addEventListener("error", () => {
    if (socket !== activeSocket) return;
    socketReady = false;
    connectionStatus.textContent = "Connection error";
    setActionBusy(false);
    writeOutput("The game service connection failed. Check your connection and try again.");
  });
  activeSocket.addEventListener("close", () => {
    if (socket !== activeSocket) return;
    closeSocket();
    if (actionInFlight) {
      setActionBusy(false);
      writeOutput("The game service disconnected before sending a result. Check Total Score before retrying.");
    }
  });
}

async function unlockAccessibleView() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    accessStatus.textContent = "Enter your student API key.";
    apiKeyInput.focus();
    return;
  }
  if (!BASE_URL) {
    accessStatus.textContent = "The exercise service is not configured.";
    return;
  }
  closeSocket();
  allowedGame = "";
  displayedTaskId = "";
  currentTask.textContent = "Checking current task...";
  taskInstructions.textContent = "";
  currentStep.textContent = "";
  setActionBusy(false);
  exerciseView.classList.add("hidden");
  unlockButton.disabled = true;
  accessStatus.textContent = "Checking account access...";
  try {
    const response = await fetch(`${BASE_URL}/portal/accessible-exercise`, {
      headers: { "x-api-key": apiKey },
    });
    const result = await response.json();
    if (!response.ok || result?.status !== "OK" || result?.game !== "game02") {
      accessStatus.textContent = result?.message || "This account is not enabled for the accessible exercise view.";
      return;
    }
    allowedGame = result.game;
    exerciseView.classList.remove("hidden");
    accessStatus.textContent = "Access confirmed for game02 exercise mode.";
    setActionBusy(false);
    connectAndSend("status");
  } catch (error) {
    accessStatus.textContent = `Could not check account access: ${error.message}`;
  } finally {
    unlockButton.disabled = false;
  }
}

unlockButton.addEventListener("click", unlockAccessibleView);
saveLoginButton.addEventListener("click", submitKubernetesLogin);
kubeconfigMethod.addEventListener("change", () => selectLoginMethod(false));
manualMethod.addEventListener("change", () => selectLoginMethod(true));
for (const id of loginInputIds) {
  document.getElementById(id).addEventListener(id === "kubeconfig" || id === "endpoint" ? "input" : "change", invalidateLogin);
}
apiKeyInput.addEventListener("input", () => {
  closeSocket();
  allowedGame = "";
  exerciseView.classList.add("hidden");
  accessStatus.textContent = "API key changed. Check access again.";
  invalidateLogin();
});
triggerGradingButton.addEventListener("click", () => connectAndSend("talk"));
checkScoreButton.addEventListener("click", () => connectAndSend("status"));
resetTaskButton.addEventListener("click", () => {
  if (window.confirm("Reset the current exercise task?\n\nThis clears task progress but keeps the saved attempt history.")) {
    connectAndSend("reset");
  }
});
skipTaskButton.addEventListener("click", () => {
  if (window.confirm("Skip the current exercise task?\n\nThis marks it as completed with 0 points and moves to the next task. This cannot be undone from the exercise portal.")) {
    connectAndSend("skip");
  }
});
resetExerciseButton.addEventListener("click", () => {
  if (!window.confirm(`Reset the whole exercise for ${allowedGame}?\n\nThis deletes all saved progress, including completed, skipped, and current task state. Trial records remain visible to teachers. This cannot be undone from the portal.`)) return;
  if (window.prompt(`Type "RESET ${allowedGame}" to confirm deleting all saved exercise progress.`, "") !== `RESET ${allowedGame}`) {
    writeOutput("Whole exercise reset cancelled. Confirmation text did not match.");
    return;
  }
  connectAndSend("reset-all");
});
contrastToggle.addEventListener("click", () => {
  const highContrast = document.body.classList.toggle("accessible-high-contrast");
  contrastToggle.setAttribute("aria-pressed", String(highContrast));
  contrastToggle.textContent = highContrast ? "Use standard contrast" : "Use high contrast";
});
textSizeInput.addEventListener("input", () => {
  const percent = Number(textSizeInput.value);
  for (const element of [taskInstructions, exerciseOutput]) {
    element.style.setProperty("--accessible-text-size", `${percent / 100}rem`);
  }
  textSizeLabel.textContent = `${percent}%`;
});

setActionBusy(false);
try {
  const portalState = JSON.parse(localStorage.getItem(PORTAL_STORAGE_KEY) || "{}");
  if (typeof portalState.apiKey === "string") apiKeyInput.value = portalState.apiKey;
} catch (error) {
  console.warn("Could not read saved student portal settings", error);
}
