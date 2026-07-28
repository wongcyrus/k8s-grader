const APP_CONFIG = window.__K8S_PORTAL_CONFIG__ || {};
const BASE_URL = APP_CONFIG.baseUrl || "";
const STORAGE_KEY = "k8s-teacher-dashboard-state-v1";

const apiKeyInput = document.getElementById("apiKey");
const loadOverviewButton = document.getElementById("loadOverview");
const resetStateButton = document.getElementById("resetState");
const exportOverviewButton = document.getElementById("exportOverview");
const overviewSummary = document.getElementById("overviewSummary");
const summaryBody = document.getElementById("summaryBody");
const overviewBody = document.getElementById("overviewBody");
const studentDetail = document.getElementById("studentDetail");
const filterGameSelect = document.getElementById("filterGame");
const filterScopeSelect = document.getElementById("filterScope");
const filterExamCodeSelect = document.getElementById("filterExamCode");
const sortBySelect = document.getElementById("sortBy");
const sortDirectionSelect = document.getElementById("sortDirection");

let overviewRows = [];
let visibleOverviewRows = [];

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

function sortValue(value) {
  if (typeof value === "number") {
    return value;
  }
  return String(value ?? "").trim().toLowerCase();
}

function compareOverviewRows(left, right, primaryField, direction) {
  const numericFields = new Set(["total_score", "completed_tasks", "skipped_tasks"]);
  const fallbackFields = ["game", "scope_mode", "exam_code", "email", "current_task"];
  const fields = [primaryField, ...fallbackFields.filter((field) => field !== primaryField)];

  for (const field of fields) {
    const leftValue = numericFields.has(field) ? Number(left[field] ?? 0) : sortValue(left[field]);
    const rightValue = numericFields.has(field) ? Number(right[field] ?? 0) : sortValue(right[field]);
    if (leftValue < rightValue) {
      return direction === "desc" ? 1 : -1;
    }
    if (leftValue > rightValue) {
      return direction === "desc" ? -1 : 1;
    }
  }
  return 0;
}

function currentOverviewFilters() {
  return {
    game: filterGameSelect.value,
    scope: filterScopeSelect.value,
    examCode: filterExamCodeSelect.value,
    sortBy: sortBySelect.value || "game",
    sortDirection: sortDirectionSelect.value || "asc",
  };
}

function saveOverviewControls() {
  saveState({ teacherOverview: currentOverviewFilters() });
}

function setSelectOptions(select, values, placeholder) {
  const currentValue = select.value;
  const options = [`<option value="">${placeholder}</option>`];
  values.forEach((value) => {
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join("");
  if (currentValue && values.includes(currentValue)) {
    select.value = currentValue;
  }
}

function setFilterControl(select, values, allLabel, emptyLabel) {
  const normalized = [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))].sort();

  if (normalized.length === 0) {
    select.innerHTML = `<option value="">${emptyLabel}</option>`;
    select.value = "";
    select.disabled = true;
    return;
  }

  if (normalized.length === 1) {
    select.innerHTML = `<option value="${escapeHtml(normalized[0])}">${escapeHtml(normalized[0])}</option>`;
    select.value = normalized[0];
    select.disabled = true;
    return;
  }

  setSelectOptions(select, normalized, allLabel);
  select.disabled = false;
}

function renderSummaryRows(rows) {
  if (!rows.length) {
    summaryBody.innerHTML = '<tr><td colspan="8">No summary available.</td></tr>';
    return;
  }

  const grouped = new Map();
  rows.forEach((row) => {
    const key = [row.game || "", row.scope_mode || "", row.exam_code || ""].join("::");
    if (!grouped.has(key)) {
      grouped.set(key, {
        game: row.game || "-",
        scope_mode: row.scope_mode || "-",
        exam_code: row.exam_code || "-",
        accounts: 0,
        total_score: 0,
        completed_tasks: 0,
        skipped_tasks: 0,
        active_accounts: 0,
      });
    }
    const item = grouped.get(key);
    item.accounts += 1;
    item.total_score += Number(row.total_score ?? 0);
    item.completed_tasks += Number(row.completed_tasks ?? 0);
    item.skipped_tasks += Number(row.skipped_tasks ?? 0);
    if (String(row.status || "").toUpperCase() === "ACTIVE") {
      item.active_accounts += 1;
    }
  });

  const summaryRows = [...grouped.values()].sort((left, right) => (
    compareOverviewRows(left, right, "game", "asc")
    || compareOverviewRows(left, right, "scope_mode", "asc")
    || compareOverviewRows(left, right, "exam_code", "asc")
  ));

  summaryBody.innerHTML = summaryRows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.game)}</td>
          <td>${escapeHtml(row.scope_mode)}</td>
          <td>${escapeHtml(row.exam_code)}</td>
          <td>${escapeHtml(row.accounts)}</td>
          <td>${escapeHtml(row.total_score)}</td>
          <td>${escapeHtml(row.completed_tasks)}</td>
          <td>${escapeHtml(row.skipped_tasks)}</td>
          <td>${escapeHtml(row.active_accounts)}</td>
        </tr>
      `
    )
    .join("");
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

function saveState(partial = {}) {
  const next = { ...loadState(), ...partial };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function clearState() {
  localStorage.removeItem(STORAGE_KEY);
}

function refreshOverviewFilters() {
  const games = overviewRows.map((row) => row.game || "");
  const scopes = overviewRows.map((row) => row.scope_mode || "");
  const examCodes = overviewRows.map((row) => row.exam_code || "");

  setFilterControl(filterGameSelect, games, "All games", "No games");
  setFilterControl(filterScopeSelect, scopes, "All scopes", "No scopes");
  setFilterControl(filterExamCodeSelect, examCodes, "All exam codes", "No exam codes");
}

function filteredAndSortedOverviewRows() {
  const { game, scope, examCode, sortBy, sortDirection } = currentOverviewFilters();
  return overviewRows
    .filter((row) => !game || row.game === game)
    .filter((row) => !scope || row.scope_mode === scope)
    .filter((row) => !examCode || row.exam_code === examCode)
    .slice()
    .sort((left, right) => compareOverviewRows(left, right, sortBy, sortDirection));
}

function updateOverviewTable() {
  visibleOverviewRows = filteredAndSortedOverviewRows();
  renderSummaryRows(visibleOverviewRows);
  renderOverviewRows(visibleOverviewRows);
  const { game, scope, examCode } = currentOverviewFilters();
  const filterSummary = [
    game ? `game=${game}` : null,
    scope ? `scope=${scope}` : null,
    examCode ? `exam=${examCode}` : null,
  ].filter(Boolean);
  overviewSummary.textContent = filterSummary.length > 0
    ? `${visibleOverviewRows.length} of ${overviewRows.length} account scope(s) shown (${filterSummary.join(", ")}). Click a row for detail.`
    : `${visibleOverviewRows.length} account scope(s) loaded. Click a row for detail.`;
}

function exportVisibleOverviewRows() {
  if (!visibleOverviewRows.length) {
    overviewSummary.textContent = "No visible rows to export.";
    return;
  }

  const header = [
    "Account",
    "Game",
    "Scope",
    "Exam Code",
    "Status",
    "Score",
    "Completed",
    "Skipped",
    "Current Task",
    "Current Phase",
    "Last Activity",
    "Latest Result",
    "Latest Report URL",
  ];
  const csvRows = [
    header,
    ...visibleOverviewRows.map((row) => [
      row.email || "",
      row.game || "",
      row.scope_mode || "",
      row.exam_code || "",
      row.status || "",
      row.total_score ?? 0,
      row.completed_tasks ?? 0,
      row.skipped_tasks ?? 0,
      row.current_task || "",
      row.current_phase || "",
      row.last_activity || "",
      row.latest_result || "",
      row.latest_report_url || "",
    ]),
  ];
  const csvContent = csvRows
    .map((row) => row.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const now = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  link.href = url;
  link.download = `teacher-dashboard-${now}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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
    overviewBody.innerHTML = '<tr><td colspan="10">No account scopes found.</td></tr>';
    return;
  }

  overviewBody.innerHTML = students
    .map(
      (student) => `
        <tr
          data-student-email="${escapeHtml(student.email)}"
          data-game="${escapeHtml(student.game || "")}"
          data-mode="${escapeHtml(student.scope_mode || "")}"
          data-exam-code="${escapeHtml(student.exam_code || "")}"
        >
          <td>${escapeHtml(student.email)}</td>
          <td>${escapeHtml(student.game || "-")}</td>
          <td>${escapeHtml(student.scope_mode || "-")}</td>
          <td>${escapeHtml(student.exam_code || "-")}</td>
          <td>${escapeHtml(student.status || "-")}</td>
          <td>${escapeHtml(student.total_score)}</td>
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
      <div class="teacher-summary-item"><strong>Account</strong><span>${escapeHtml(student.email || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Game</strong><span>${escapeHtml(student.game || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Scope</strong><span>${escapeHtml(student.scope_mode || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Exam code</strong><span>${escapeHtml(student.exam_code || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Status</strong><span>${escapeHtml(student.status || "-")}</span></div>
      <div class="teacher-summary-item"><strong>Scope score</strong><span>${escapeHtml(student.total_score || 0)}</span></div>
      <div class="teacher-summary-item"><strong>Completed tasks</strong><span>${escapeHtml(student.completed_tasks || 0)}</span></div>
      <div class="teacher-summary-item"><strong>Skipped tasks</strong><span>${escapeHtml(student.skipped_tasks || 0)}</span></div>
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
  studentDetail.textContent = "Select an account row to load detail.";

  try {
    const payload = await apiGet("/teacher/overview");
    overviewRows = Array.isArray(payload.students) ? payload.students : [];
    refreshOverviewFilters();
    const savedFilters = loadState().teacherOverview || {};
    if (savedFilters.game) {
      filterGameSelect.value = savedFilters.game;
    }
    if (savedFilters.examCode) {
      filterExamCodeSelect.value = savedFilters.examCode;
    }
    updateOverviewTable();
  } catch (error) {
    summaryBody.innerHTML = '<tr><td colspan="8">Summary failed to load.</td></tr>';
    overviewBody.innerHTML = '<tr><td colspan="10">Overview failed to load.</td></tr>';
    overviewSummary.textContent = error.message;
  }
}

async function loadStudentDetail(studentEmail, game, mode, examCode) {
  studentDetail.textContent = `Loading ${studentEmail} ${game ? `(${game}/${mode || "-"})` : ""} ...`;
  try {
    const payload = await apiGet("/teacher/student", { studentEmail, game, mode, examCode });
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
  loadStudentDetail(
    row.dataset.studentEmail || "",
    row.dataset.game || "",
    row.dataset.mode || "",
    row.dataset.examCode || "",
  );
});

loadOverviewButton.addEventListener("click", () => {
  loadOverview();
});

[filterGameSelect, filterScopeSelect, filterExamCodeSelect, sortBySelect, sortDirectionSelect].forEach((control) => {
  control.addEventListener("change", () => {
    saveOverviewControls();
    updateOverviewTable();
  });
});

exportOverviewButton.addEventListener("click", () => {
  exportVisibleOverviewRows();
});

resetStateButton.addEventListener("click", () => {
  clearState();
  apiKeyInput.value = "";
  overviewRows = [];
  visibleOverviewRows = [];
  filterGameSelect.value = "";
  filterScopeSelect.innerHTML = '<option value="">All scopes</option><option value="exercise">exercise</option><option value="exam">exam</option>';
  filterScopeSelect.value = "";
  filterExamCodeSelect.innerHTML = '<option value="">All exam codes</option>';
  filterGameSelect.innerHTML = '<option value="">All games</option>';
  filterGameSelect.disabled = false;
  filterScopeSelect.disabled = false;
  filterExamCodeSelect.disabled = false;
  sortBySelect.value = "game";
  sortDirectionSelect.value = "asc";
  summaryBody.innerHTML = '<tr><td colspan="8">No summary loaded yet.</td></tr>';
  overviewBody.innerHTML = '<tr><td colspan="10">No data loaded yet.</td></tr>';
  overviewSummary.textContent = "Saved teacher key cleared.";
  studentDetail.textContent = "Select an account row to load detail.";
});

const savedState = loadState();
if (savedState.apiKey) {
  apiKeyInput.value = savedState.apiKey;
}
if (savedState.teacherOverview) {
  const teacherOverview = savedState.teacherOverview;
  filterScopeSelect.value = teacherOverview.scope || "";
  sortBySelect.value = teacherOverview.sortBy || "game";
  sortDirectionSelect.value = teacherOverview.sortDirection || "asc";
}
