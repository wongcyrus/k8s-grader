const APP_CONFIG = window.__K8S_PORTAL_CONFIG__ || {};
const setupOutput = document.getElementById("setupOutput");
const exerciseOutput = document.getElementById("exerciseOutput");
const exerciseConnectionStatus = document.getElementById("exerciseConnectionStatus");
const exerciseGameSelect = document.getElementById("exerciseGame");
const exerciseClientSelect = document.getElementById("exerciseClient");
const exerciseCompletedTasksLabel = document.getElementById("exerciseCompletedTasksLabel");
const exerciseSkippedTasksLabel = document.getElementById("exerciseSkippedTasksLabel");
const exerciseScoreLabel = document.getElementById("exerciseScoreLabel");
const resetStateButton = document.getElementById("resetState");
const buttons = document.querySelectorAll("button[data-action]");
const authMethodInputs = document.querySelectorAll('input[name="exerciseAuthMethod"]');
const kubeconfigPanel = document.getElementById("kubeconfigPanel");
const manualPanel = document.getElementById("manualPanel");

const BASE_URL = APP_CONFIG.baseUrl || "";
const GAME_WS_URL = APP_CONFIG.gameWsUrl || "";
const PORTAL_RPG_PATH = "./game/index.html";
const PORTAL_DOOM_PATH = "./doom/";
const STORAGE_KEY = "k8s-student-portal-state-v1";
const DEFAULT_EXERCISE_GAMES = Array.isArray(APP_CONFIG.exerciseGames) ? APP_CONFIG.exerciseGames : [];

let k8sAccountReady = false;
let exerciseSocket = null;
let exerciseSocketReady = false;
let pendingExerciseAction = null;

function exerciseActionStatusText(action, phase = "active") {
  const actionText = {
    status: phase === "connecting" ? "Connecting to score service ..." : "Checking total score ...",
    reset: phase === "connecting" ? "Connecting to reset current task ..." : "Resetting current task ...",
    "reset-all": phase === "connecting" ? "Connecting to reset whole exercise ..." : "Resetting whole exercise ...",
    skip: phase === "connecting" ? "Connecting to skip task ..." : "Skipping current task ...",
  };
  return actionText[action] || (phase === "connecting" ? "Connecting to exercise service ..." : "Updating exercise status ...");
}

function readInputs() {
  const selectedAuthMethod = document.querySelector('input[name="exerciseAuthMethod"]:checked');
  return {
    apiKey: document.getElementById("apiKey").value.trim(),
    authMethod: selectedAuthMethod ? selectedAuthMethod.value : "kubeconfig",
    kubeconfig: document.getElementById("kubeconfig").value,
    kubeconfigFile: document.getElementById("kubeconfigFile").files[0],
    endpoint: document.getElementById("endpoint").value.trim(),
    clientCertificate: document.getElementById("clientCertificate").files[0],
    clientKey: document.getElementById("clientKey").files[0],
    exerciseGame: exerciseGameSelect.value.trim(),
    exerciseClient: exerciseClientSelect.value.trim(),
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

function write(data, target = setupOutput) {
  target.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function formatSaveAccountResponse(json, endpoint = "") {
  if (!json || typeof json !== "object") {
    return "";
  }

  const status = String(json.status || "").trim() || "Unknown";
  const message = String(json.message || "").trim();
  const lines = [`Status: ${status}`];

  if (message) {
    lines.push(`Message: ${message}`);
  }

  if (endpoint && status.toUpperCase() === "OK") {
    lines.push(`Endpoint: ${endpoint}`);
  }
  if (json.authType) {
    lines.push(`Auth Type: ${json.authType}`);
  }
  if (json.context) {
    lines.push(`Context: ${json.context}`);
  }
  if (json.cluster) {
    lines.push(`Cluster: ${json.cluster}`);
  }

  return lines.join("\n");
}

function getExerciseGamesFromDom() {
  return Array.from(exerciseGameSelect.querySelectorAll("option"))
    .map((option) => option.value.trim())
    .filter(Boolean);
}

function normalizeExerciseGames(games) {
  const seen = new Set();
  const normalized = [];
  for (const game of Array.isArray(games) ? games : []) {
    const value = String(game || "").trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    normalized.push(value);
  }
  return normalized;
}

function setExerciseGameOptions(games, preferredGame = "") {
  const normalizedGames = normalizeExerciseGames(games);
  exerciseGameSelect.innerHTML = "";

  if (normalizedGames.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No games available";
    option.disabled = true;
    option.selected = true;
    exerciseGameSelect.appendChild(option);
    return;
  }

  for (const game of normalizedGames) {
    const option = document.createElement("option");
    option.value = game;
    option.textContent = game;
    exerciseGameSelect.appendChild(option);
  }

  if (preferredGame && normalizedGames.includes(preferredGame)) {
    exerciseGameSelect.value = preferredGame;
    return;
  }

  exerciseGameSelect.value = normalizedGames[0];
}

async function loadExerciseGames(preferredGame = "") {
  const fallbackGames = normalizeExerciseGames([
    ...DEFAULT_EXERCISE_GAMES,
    ...getExerciseGamesFromDom(),
  ]);

  if (!BASE_URL) {
    setExerciseGameOptions(fallbackGames, preferredGame);
    return;
  }

  try {
    const res = await fetch(`${BASE_URL}/portal/games`);
    const json = await res.json();
    if (json?.status !== "OK" || !Array.isArray(json.games)) {
      throw new Error("Invalid portal games response");
    }
    setExerciseGameOptions(json.games, preferredGame);
  } catch (error) {
    setExerciseGameOptions(fallbackGames, preferredGame);
    if (fallbackGames.length === 0) {
      write(`Failed to load available games: ${error.message}`, setupOutput);
    }
  }
}

function setBusy(isBusy) {
  buttons.forEach((btn) => {
    btn.disabled = isBusy;
  });
}

function saveState(partial = {}) {
  const current = loadState();
  const next = { ...current, ...partial };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function clearState() {
  localStorage.removeItem(STORAGE_KEY);
}

function exerciseClientUrl(game, client) {
  const path = client === "rpg" ? PORTAL_RPG_PATH : PORTAL_DOOM_PATH;
  const url = new URL(path, window.location.href);
  if (game) {
    url.searchParams.set("game", game);
  }
  if (client === "doom") {
    url.searchParams.set("wsUrl", GAME_WS_URL);
  }
  return url.toString();
}

function setExerciseConnectionStatus(text) {
  exerciseConnectionStatus.textContent = text;
}

function resetExerciseSummary() {
  exerciseCompletedTasksLabel.textContent = "-";
  exerciseSkippedTasksLabel.textContent = "-";
  exerciseScoreLabel.textContent = "0";
}

function buildExerciseStatusSummary(json) {
  const status = String(json?.status || "").toUpperCase();
  const points =
    typeof json?.total_score !== "undefined"
      ? String(json.total_score)
      : typeof json?.total_points !== "undefined"
        ? String(json.total_points)
        : "0";
  const completedTasks = Array.isArray(json?.completed_tasks) ? json.completed_tasks : [];
  const skippedTasks = Array.isArray(json?.skipped_tasks) ? json.skipped_tasks : [];
  const completedTaskLines =
    completedTasks.length > 0
      ? completedTasks.map((taskId) => `- ${taskId}`).join("\n")
      : "- None yet";
  const skippedTaskLines =
    skippedTasks.length > 0
      ? skippedTasks.map((taskId) => `- ${taskId} (skipped)`).join("\n")
      : "- None";

  if (status === "ERROR") {
    return json?.message || "Exercise score is unavailable right now.";
  }

  const lines = [];
  if (json?.message) {
    lines.push(String(json.message));
  }
  if (json?.task_id) {
    lines.push(`Current task: ${json.task_id}`);
  }
  if (json?.phase_name) {
    lines.push(`Current phase: ${json.phase_name}`);
  }
  if (lines.length > 0) {
    lines.push("");
  }

  lines.push(`Total score: ${points}`);
  lines.push(`Completed tasks (${completedTasks.length}):`);
  lines.push(completedTaskLines);
  lines.push(`Skipped tasks (${skippedTasks.length}):`);
  lines.push(skippedTaskLines);
  return lines.join("\n");
}

function updateExerciseSummary(json) {
  if (!json || typeof json !== "object") {
    return;
  }

  const completedTasks = Array.isArray(json.completed_tasks) ? json.completed_tasks : [];
  const skippedTasks = Array.isArray(json.skipped_tasks) ? json.skipped_tasks : [];

  exerciseCompletedTasksLabel.textContent = completedTasks.length > 0 ? `${completedTasks.length} tasks` : "0 tasks";
  exerciseSkippedTasksLabel.textContent = skippedTasks.length > 0 ? `${skippedTasks.length} tasks` : "0 tasks";
  exerciseScoreLabel.textContent =
    typeof json.total_score !== "undefined"
      ? String(json.total_score)
      : typeof json.total_points !== "undefined"
        ? String(json.total_points)
        : "0";

  write(buildExerciseStatusSummary(json), exerciseOutput);
}

function closeExerciseSocket() {
  pendingExerciseAction = null;
  if (exerciseSocket) {
    exerciseSocket.close();
  }
  exerciseSocket = null;
  exerciseSocketReady = false;
  setExerciseConnectionStatus("Disconnected");
}

function sendExerciseAction(action) {
  const { apiKey, exerciseGame } = readInputs();
  if (!exerciseSocket || !exerciseSocketReady || exerciseSocket.readyState !== WebSocket.OPEN) {
    write("Exercise WebSocket is not connected yet.", exerciseOutput);
    return;
  }
  pendingExerciseAction = null;
  exerciseSocket.send(
    JSON.stringify({
      action,
      apiKey,
      game: exerciseGame,
    })
  );
  write(exerciseActionStatusText(action), exerciseOutput);
}

function connectExerciseSocket(action = "status") {
  const { apiKey, exerciseGame } = readInputs();
  if (!apiKey) {
    write("API Key is required before opening or checking the exercise game.", exerciseOutput);
    return false;
  }
  if (!exerciseGame) {
    write("Choose an exercise game first.", exerciseOutput);
    return false;
  }

  if (exerciseSocket && exerciseSocket.readyState === WebSocket.OPEN && exerciseSocketReady) {
    sendExerciseAction(action);
    return true;
  }

  if (exerciseSocket && exerciseSocket.readyState === WebSocket.CONNECTING) {
    pendingExerciseAction = action;
    write(exerciseActionStatusText(action, "connecting"), exerciseOutput);
    return true;
  }

  closeExerciseSocket();
  pendingExerciseAction = action;
  setExerciseConnectionStatus("Connecting");
  write(exerciseActionStatusText(action, "connecting"), exerciseOutput);

  const socket = new WebSocket(GAME_WS_URL);
  exerciseSocket = socket;

  socket.addEventListener("open", () => {
    if (exerciseSocket !== socket) {
      return;
    }
    setExerciseConnectionStatus("Connected");
    exerciseSocketReady = true;
    socket.send(
      JSON.stringify({
        action: "subscribe",
        apiKey,
        game: exerciseGame,
      })
    );
    if (pendingExerciseAction) {
      sendExerciseAction(pendingExerciseAction);
    }
  });

  socket.addEventListener("message", (event) => {
    if (exerciseSocket !== socket) {
      return;
    }
    try {
      const payload = JSON.parse(event.data);
      const gamePayload = payload?.type === "game_status" ? payload.data : payload;
      if (!gamePayload || gamePayload.status === "SUBSCRIBED") {
        return;
      }
      updateExerciseSummary(gamePayload);
    } catch (error) {
      write(`Failed to read exercise status: ${error.message}`, exerciseOutput);
    }
  });

  socket.addEventListener("error", () => {
    if (exerciseSocket !== socket) {
      return;
    }
    exerciseSocketReady = false;
    setExerciseConnectionStatus("Error");
    write("Exercise WebSocket failed to connect.", exerciseOutput);
  });

  socket.addEventListener("close", () => {
    if (exerciseSocket !== socket) {
      return;
    }
    exerciseSocket = null;
    exerciseSocketReady = false;
    setExerciseConnectionStatus("Disconnected");
  });

  return true;
}

function skipExerciseTask() {
  const ok = window.confirm(
    "Skip the current exercise task?\n\nThis will mark it as completed with 0 points and move to the next task.\nThis cannot be undone from the exercise portal."
  );
  if (!ok) {
    write("Skip cancelled.", exerciseOutput);
    return;
  }
  connectExerciseSocket("skip");
}

function resetExerciseTask() {
  const ok = window.confirm(
    "Reset the current exercise task?\n\nThis clears the task progress so you can start that task again, but it keeps the saved attempt history."
  );
  if (!ok) {
    write("Reset cancelled.", exerciseOutput);
    return;
  }
  connectExerciseSocket("reset");
}

function resetWholeExercise() {
  const { exerciseGame } = readInputs();
  if (!exerciseGame) {
    write("Choose an exercise game first.", exerciseOutput);
    return;
  }

  const firstConfirm = window.confirm(
    `Reset the whole exercise for ${exerciseGame}?\n\nThis will delete all saved progress for this game, including completed, skipped, and current task state.\nTrial records will still be visible to teachers.\nThis cannot be undone from the portal.`
  );
  if (!firstConfirm) {
    write("Whole exercise reset cancelled.", exerciseOutput);
    return;
  }

  const confirmationText = `RESET ${exerciseGame}`;
  const typed = window.prompt(
    `Type "${confirmationText}" to confirm deleting all saved exercise progress for ${exerciseGame}.`,
    ""
  );
  if (typed !== confirmationText) {
    write("Whole exercise reset cancelled. Confirmation text did not match.", exerciseOutput);
    return;
  }

  connectExerciseSocket("reset-all");
}

function openExerciseGame() {
  const { apiKey, exerciseClient, exerciseGame } = readInputs();
  if (!apiKey) {
    write("Save or paste your API key before launching the exercise client.", exerciseOutput);
    return;
  }
  if (!k8sAccountReady) {
    write("Submit Kubernetes Login first so the exercise client can use your saved account.", exerciseOutput);
    return;
  }

  const launchUrl = exerciseClientUrl(exerciseGame, exerciseClient);
  saveState({
    apiKey,
    exerciseClient,
    exerciseGame,
    gameWsUrl: GAME_WS_URL,
    portalGameUrl: launchUrl,
    accountReady: true,
  });
  window.open(launchUrl, "_blank");
  write(`Opened ${exerciseClient} for ${exerciseGame} in a new tab.`, exerciseOutput);
}

async function callApi(action) {
  const { apiKey, authMethod, kubeconfig, kubeconfigFile, endpoint, clientCertificate, clientKey, exerciseGame } = readInputs();
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
      let json = null;
      try {
        json = JSON.parse(text);
      } catch {
        // Fall back to raw output below.
      }
      if (json && json.status === "OK") {
        k8sAccountReady = true;
        saveState({ apiKey, endpoint, exerciseGame, authMethod, accountReady: true });
      }
      write(formatSaveAccountResponse(json, endpoint) || text, setupOutput);
    } catch (err) {
      write(`Request failed: ${err.message}`, setupOutput);
    } finally {
      setBusy(false);
    }
    return;
  }

  if (action === "open-game") {
    openExerciseGame();
    return;
  }

  if (action === "exercise-status") {
    if (!exerciseGame) {
      write("Choose an exercise game first.", exerciseOutput);
      return;
    }
    connectExerciseSocket("status");
    return;
  }

  if (action === "exercise-skip") {
    if (!exerciseGame) {
      write("Choose an exercise game first.", exerciseOutput);
      return;
    }
    skipExerciseTask();
    return;
  }

  if (action === "exercise-reset") {
    if (!exerciseGame) {
      write("Choose an exercise game first.", exerciseOutput);
      return;
    }
    resetExerciseTask();
    return;
  }

  if (action === "exercise-reset-all") {
    resetWholeExercise();
  }
}

buttons.forEach((btn) => {
  btn.addEventListener("click", () => callApi(btn.dataset.action));
});

document.getElementById("apiKey").addEventListener("input", (e) => {
  saveState({ apiKey: e.target.value });
});

document.getElementById("endpoint").addEventListener("input", (e) => {
  k8sAccountReady = false;
  saveState({ endpoint: e.target.value, accountReady: false });
});

document.getElementById("kubeconfig").addEventListener("input", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
});

document.getElementById("kubeconfigFile").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
});

document.getElementById("clientCertificate").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
});

document.getElementById("clientKey").addEventListener("change", () => {
  k8sAccountReady = false;
  saveState({ accountReady: false });
});

authMethodInputs.forEach((input) => {
  input.addEventListener("change", () => {
    k8sAccountReady = false;
    setAuthMethod(input.value);
  });
});

exerciseGameSelect.addEventListener("change", (e) => {
  saveState({ exerciseGame: e.target.value, gameWsUrl: GAME_WS_URL });
  closeExerciseSocket();
  resetExerciseSummary();
  write("Choose a game, open it from the portal, then use Check Total Score.", exerciseOutput);
});

exerciseClientSelect.addEventListener("change", (e) => {
  saveState({ exerciseClient: e.target.value });
});

resetStateButton.addEventListener("click", () => {
  const ok = window.confirm(
    "Reset saved exercise form data?\n\nThis clears the API key, kubeconfig input, endpoint, exercise selection, and cached exercise portal state from this browser."
  );
  if (!ok) {
    return;
  }

  clearState();
  closeExerciseSocket();
  k8sAccountReady = false;
  document.getElementById("apiKey").value = "";
  document.getElementById("kubeconfig").value = "";
  document.getElementById("kubeconfigFile").value = "";
  document.getElementById("endpoint").value = "";
  document.getElementById("clientCertificate").value = "";
  document.getElementById("clientKey").value = "";
  setAuthMethod("kubeconfig", { persist: false });
  setExerciseGameOptions(getExerciseGamesFromDom());
  exerciseClientSelect.value = "doom";
  resetExerciseSummary();
  write("Ready.", setupOutput);
  write("Choose a game, open it from the portal, then use Check Total Score.", exerciseOutput);
});

setExerciseConnectionStatus("Disconnected");
resetExerciseSummary();

const restored = loadState();
setAuthMethod(restored.authMethod || (restored.endpoint ? "manual" : "kubeconfig"), { persist: false });
if (restored.apiKey) {
  document.getElementById("apiKey").value = restored.apiKey;
}
if (restored.endpoint) {
  document.getElementById("endpoint").value = restored.endpoint;
}
if (restored.exerciseClient) {
  exerciseClientSelect.value = restored.exerciseClient;
}
if (restored.accountReady) {
  k8sAccountReady = true;
}

loadExerciseGames(restored.exerciseGame || exerciseGameSelect.value);
