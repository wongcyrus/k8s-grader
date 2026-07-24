const APP_CONFIG = window.__K8S_PORTAL_CONFIG__ || {};
const BASE_URL = APP_CONFIG.baseUrl || "";
const STORAGE_KEY = "k8s-teacher-dashboard-state-v1";

const apiKeyInput = document.getElementById("apiKey");
const loadOverviewButton = document.getElementById("loadOverview");
const resetStateButton = document.getElementById("resetState");
const overviewSummary = document.getElementById("overviewSummary");
const overviewBody = document.getElementById("overviewBody");
const studentDetail = document.getElementById("studentDetail");

let overviewRows = [];

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

function saveState(partial = {}) {
  const next = { ...loadState(), ...partial };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function clearState() {
  localStorage.removeItem(STORAGE_KEY);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function readApiKey() {
  return apiKeyInput.value.trim();
}

async function apiGet(path, params = {}) {
  const apiKey = readApiKey();
  if (!apiKey) {
    throw new Error("Teacher API key is required.");
  }

  const url = new URL(`${BASE_URL}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    }
  });

  const response = await fetch(url.toString(), {
    headers: {
      "x-api-key": apiKey,
    },
  });
  const payload = await response.json();
  if (payload.status !== "OK") {
    throw new Error(payload.message || "Teacher request failed.");
  }
  saveState({ apiKey });
  return payload;
}

function renderOverviewRows(students) {
  if (!students.length) {
    overviewBody.innerHTML = '<tr><td colspan="10">No student accounts found.</td></tr>';
    return;
  }

  overviewBody.innerHTML = students
    .map(
      (student) => `
        <tr data-student-email="${escapeHtml(student.email)}">
          <td>${escapeHtml(student.email)}</td>
          <td>${escapeHtml(student.status || "-")}</td>
          <td>${escapeHtml(student.current_mode || "-")}</td>
          <td>${escapeHtml(student.total_score)}</td>
          <td>${escapeHtml(student.exercise_score)}</td>
          <td>${escapeHtml(student.exam_score)}</td>
          <td>${escapeHtml(student.completed_tasks)}</td>
          <td>${escapeHtml(student.skipped_tasks)}</td>
          <td>${escapeHtml(student.current_task || "-")}</td>
          <td>${student.latest_report_url ? `<a href="${escapeHtml(student.latest_report_url)}" target="_blank" rel="noreferrer">Open</a>` : "-"}</td>
        </tr>
      `
    )
    .join("");
}

function renderDetail(detail) {
  const student = detail.student || {};
  const taskStates = Array.isArray(detail.task_states) ? detail.task_states : [];
  const examSessions = Array.isArray(detail.exam_sessions) ? detail.exam_sessions : [];
  const reports = Array.isArray(detail.reports) ? detail.reports : [];

  const taskRows =
    taskStates.length > 0
      ? taskStates
          .map(
            (task) => `
              <tr>
                <td>${escapeHtml(task.game)}</td>
                <td>${escapeHtml(task.task_id)}</td>
                <td>${escapeHtml(task.mode)}</td>
                <td>${escapeHtml(task.status)}</td>
                <td>${escapeHtml(task.current_phase || "-")}</td>
                <td>${escapeHtml(task.total_points)}</td>
                <td>${task.skipped ? "Yes" : "No"}</td>
                <td>${escapeHtml(task.updated_at || "-")}</td>
              </tr>
            `
          )
          .join("")
      : '<tr><td colspan="8">No task state found.</td></tr>';

  const examRows =
    examSessions.length > 0
      ? examSessions
          .map(
            (session) => `
              <tr>
                <td>${escapeHtml(session.exam_code)}</td>
                <td>${escapeHtml(session.game)}</td>
                <td>${session.active ? "Yes" : "No"}</td>
                <td>${escapeHtml(session.verified_at || "-")}</td>
                <td>${escapeHtml(session.expires_at || "-")}</td>
              </tr>
            `
          )
          .join("")
      : '<tr><td colspan="5">No exam sessions found.</td></tr>';

  const reportRows =
    reports.length > 0
      ? reports
          .map(
            (report) => `
              <tr>
                <td>${escapeHtml(report.time || "-")}</td>
                <td>${escapeHtml(report.game || "-")}</td>
                <td>${escapeHtml(report.task_id || "-")}</td>
                <td>${escapeHtml(report.phase || "-")}</td>
                <td>${escapeHtml(report.mode || "-")}</td>
                <td>${escapeHtml(report.test_result || "-")}</td>
                <td>${report.report_url ? `<a href="${escapeHtml(report.report_url)}" target="_blank" rel="noreferrer">Open</a>` : "-"}</td>
              </tr>
            `
          )
          .join("")
      : '<tr><td colspan="7">No reports found.</td></tr>';

  studentDetail.innerHTML = `
    <div class="teacher-summary-grid">
      <div class="teacher-summary-item"><strong>Student</strong><span>${escapeHtml(student.email || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Status</strong><span>${escapeHtml(student.status || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Total score</strong><span>${escapeHtml(student.total_score || 0)}</span></div>
      <div class="teacher-summary-item"><strong>Exercise score</strong><span>${escapeHtml(student.exercise_score || 0)}</span></div>
      <div class="teacher-summary-item"><strong>Exam score</strong><span>${escapeHtml(student.exam_score || 0)}</span></div>
      <div class="teacher-summary-item"><strong>Current task</strong><span>${escapeHtml(student.current_task || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Current phase</strong><span>${escapeHtml(student.current_phase || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Last activity</strong><span>${escapeHtml(student.last_activity || "-")}</span></div>
    </div>
    <h3>Task States</h3>
    <div class="table-wrap">
      <table class="dashboard-table">
        <thead>
          <tr>
            <th>Game</th>
            <th>Task</th>
            <th>Mode</th>
            <th>Status</th>
            <th>Phase</th>
            <th>Points</th>
            <th>Skipped</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>${taskRows}</tbody>
      </table>
    </div>
    <h3>Exam Sessions</h3>
    <div class="table-wrap">
      <table class="dashboard-table">
        <thead>
          <tr>
            <th>Exam Code</th>
            <th>Game</th>
            <th>Active</th>
            <th>Verified</th>
            <th>Expires</th>
          </tr>
        </thead>
        <tbody>${examRows}</tbody>
      </table>
    </div>
    <h3>Recent Reports</h3>
    <div class="table-wrap">
      <table class="dashboard-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Game</th>
            <th>Task</th>
            <th>Phase</th>
            <th>Mode</th>
            <th>Result</th>
            <th>Report</th>
          </tr>
        </thead>
        <tbody>${reportRows}</tbody>
      </table>
    </div>
  `;
}

async function loadOverview() {
  overviewSummary.textContent = "Loading class overview ...";
  studentDetail.textContent = "Select a student row to load detail.";

  try {
    const payload = await apiGet("/teacher/overview");
    overviewRows = Array.isArray(payload.students) ? payload.students : [];
    renderOverviewRows(overviewRows);
    overviewSummary.textContent = `${overviewRows.length} student account(s) loaded. Click a row for detail.`;
  } catch (error) {
    overviewBody.innerHTML = '<tr><td colspan="10">Overview failed to load.</td></tr>';
    overviewSummary.textContent = error.message;
  }
}

async function loadStudentDetail(studentEmail) {
  studentDetail.textContent = `Loading ${studentEmail} ...`;
  try {
    const payload = await apiGet("/teacher/student", { studentEmail });
    renderDetail(payload);
  } catch (error) {
    studentDetail.textContent = error.message;
  }
}

overviewBody.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-student-email]");
  if (!row) {
    return;
  }
  loadStudentDetail(row.dataset.studentEmail || "");
});

loadOverviewButton.addEventListener("click", () => {
  loadOverview();
});

resetStateButton.addEventListener("click", () => {
  clearState();
  apiKeyInput.value = "";
  overviewRows = [];
  overviewBody.innerHTML = '<tr><td colspan="10">No data loaded yet.</td></tr>';
  overviewSummary.textContent = "Saved teacher key cleared.";
  studentDetail.textContent = "Select a student row to load detail.";
});

const savedState = loadState();
if (savedState.apiKey) {
  apiKeyInput.value = savedState.apiKey;
}
