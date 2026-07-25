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

const BASE_URL = APP_CONFIG.baseUrl || "";
const GAME_WS_URL = APP_CONFIG.gameWsUrl || "";
const PORTAL_RPG_PATH = "./game/index.html";
const PORTAL_DOOM_PATH = "./doom/";
const STORAGE_KEY = "k8s-student-portal-state-v1";

let k8sAccountReady = false;
let exerciseSocket = null;
let exerciseSocketReady = false;
let pendingExerciseAction = null;

function exerciseActionStatusText(action, phase = "active") {
  const actionText = {
    status: phase === "connecting" ? "Connecting to score service ..." : "Checking total score ...",
    reset: phase === "connecting" ? "Connecting to reset current task ..." : "Resetting current task ...",
    skip: phase === "connecting" ? "Connecting to skip task ..." : "Skipping current task ...",
  };
  return actionText[action] || (phase === "connecting" ? "Connecting to exercise service ..." : "Updating exercise status ...");
}

function readInputs() {
  return {
    apiKey: document.getElementById("apiKey").value.trim(),
    endpoint: document.getElementById("endpoint").value.trim(),
    clientCertificate: document.getElementById("clientCertificate").files[0],
    clientKey: document.getElementById("clientKey").files[0],
    exerciseGame: exerciseGameSelect.value.trim(),
    exerciseClient: exerciseClientSelect.value.trim(),
  };
}

function write(data, target = setupOutput) {
  target.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
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
  if (json?.task_description) {
    lines.push(`Task instruction: ${json.task_description}`);
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
  const { apiKey, endpoint, clientCertificate, clientKey, exerciseGame } = readInputs();
  if (!apiKey) {
    write("API Key is required.", setupOutput);
    return;
  }

  if (action === "save-account") {
    if (!endpoint) {
      write("Endpoint is required.", setupOutput);
      return;
    }
    if ((clientCertificate && !clientKey) || (!clientCertificate && clientKey)) {
      write("Client certificate and client key must be provided together.", setupOutput);
      return;
    }

    const formData = new FormData();
    formData.append("endpoint", endpoint);
    if (clientCertificate && clientKey) {
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
        saveState({ apiKey, endpoint, exerciseGame, accountReady: true });
      }
      write(json || text, setupOutput);
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
    "Reset saved exercise form data?\n\nThis clears the API key, endpoint, exercise selection, and cached exercise portal state from this browser."
  );
  if (!ok) {
    return;
  }

  clearState();
  closeExerciseSocket();
  k8sAccountReady = false;
  document.getElementById("apiKey").value = "";
  document.getElementById("endpoint").value = "";
  document.getElementById("clientCertificate").value = "";
  document.getElementById("clientKey").value = "";
  exerciseGameSelect.value = "game01";
  exerciseClientSelect.value = "doom";
  resetExerciseSummary();
  write("Ready.", setupOutput);
  write("Choose a game, open it from the portal, then use Check Total Score.", exerciseOutput);
});

setExerciseConnectionStatus("Disconnected");
resetExerciseSummary();

const restored = loadState();
if (restored.apiKey) {
  document.getElementById("apiKey").value = restored.apiKey;
}
if (restored.endpoint) {
  document.getElementById("endpoint").value = restored.endpoint;
}
if (restored.exerciseGame) {
  exerciseGameSelect.value = restored.exerciseGame;
}
if (restored.exerciseClient) {
  exerciseClientSelect.value = restored.exerciseClient;
}
if (restored.accountReady) {
  k8sAccountReady = true;
}
