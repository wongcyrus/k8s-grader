"""Teacher dashboard aggregation service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from common.database.repositories import (
    AccountRepository,
    ExamSessionRepository,
    TaskStateRepository,
    TestRecordRepository,
)
from common.models.task_state import TaskStatus


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _last_value(values: List[Optional[str]]) -> str:
    normalized = [value for value in values if value]
    if not normalized:
        return ""
    return max(normalized)


@dataclass
class TeacherScopeSummary:
    email: str
    endpoint: str
    game: str
    scope_mode: str
    exam_code: str
    last_activity: str
    current_task: str
    current_phase: str
    total_score: int
    completed_tasks: int
    skipped_tasks: int
    status: str
    latest_result: str
    latest_report_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email": self.email,
            "endpoint": self.endpoint,
            "game": self.game,
            "scope_mode": self.scope_mode,
            "exam_code": self.exam_code,
            "last_activity": self.last_activity,
            "current_task": self.current_task,
            "current_phase": self.current_phase,
            "total_score": self.total_score,
            "completed_tasks": self.completed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "status": self.status,
            "latest_result": self.latest_result,
            "latest_report_url": self.latest_report_url,
        }


class TeacherDashboardService:
    """Aggregates progress, score, and report data for teacher dashboards."""

    def __init__(
        self,
        account_repo: Optional[AccountRepository] = None,
        task_repo: Optional[TaskStateRepository] = None,
        exam_session_repo: Optional[ExamSessionRepository] = None,
        test_record_repo: Optional[TestRecordRepository] = None,
    ):
        self.account_repo = account_repo or AccountRepository()
        self.task_repo = task_repo or TaskStateRepository()
        self.exam_session_repo = exam_session_repo or ExamSessionRepository()
        self.test_record_repo = test_record_repo or TestRecordRepository()

    def list_students(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        accounts = sorted(self.account_repo.list_all(), key=lambda item: item.get("email", ""))

        for account in accounts:
            email = account.get("email", "")
            states = self.task_repo.list_by_email(email)
            sessions = self.exam_session_repo.list_by_email(email)
            records = self.test_record_repo.list_by_email(email)
            rows.extend(self._build_scope_summaries(account, states, sessions, records))

        return rows

    def get_student_detail(
        self,
        student_email: str,
        game: Optional[str] = None,
        mode: Optional[str] = None,
        exam_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self.account_repo.get(student_email)
        if not account:
            raise ValueError("Student account not found")

        states = self.task_repo.list_by_email(student_email)
        sessions = self.exam_session_repo.list_by_email(student_email)
        records = self.test_record_repo.list_by_email(student_email)

        filtered_states, filtered_sessions, filtered_records = self._filter_scope_items(
            states,
            sessions,
            records,
            game,
            mode,
            exam_code,
        )

        summary = self._build_scope_summary(
            account,
            filtered_states,
            filtered_sessions,
            filtered_records,
            game or self._resolve_game(filtered_states, filtered_sessions, filtered_records),
            mode or self._resolve_mode(filtered_states, filtered_sessions, filtered_records),
            exam_code or self._resolve_exam_code(filtered_states, filtered_sessions, filtered_records),
        )

        task_states = []
        for state in sorted(filtered_states, key=lambda item: (item.game, item.task_id, item.updated_at)):
            task_states.append(
                {
                    "game": state.game,
                    "task_id": state.task_id,
                    "mode": state.mode,
                    "exam_code": getattr(state, "exam_code", "") or "",
                    "status": state.status.value,
                    "current_phase": state.current_phase_id or "",
                    "total_points": state.total_points,
                    "skipped": bool(getattr(state, "skipped", False)),
                    "updated_at": state.updated_at,
                }
            )

        exam_sessions = []
        for session in sorted(
            filtered_sessions,
            key=lambda item: item.get("verifiedAt", ""),
            reverse=True,
        ):
            exam_sessions.append(
                {
                    "exam_code": session.get("examCode", ""),
                    "game": session.get("game", ""),
                    "active": bool(session.get("active", False)),
                    "verified_at": session.get("verifiedAt", ""),
                    "expires_at": session.get("expiresAt", ""),
                }
            )

        report_items = []
        for item in sorted(filtered_records, key=lambda entry: entry.get("time", ""), reverse=True)[:50]:
            report_items.append(
                {
                    "game": item.get("gameTime", "").split("#", 1)[0],
                    "task_id": item.get("task", ""),
                    "phase": item.get("gamePhase", ""),
                    "test_result": item.get("testResult", ""),
                    "time": item.get("time", ""),
                    "report_url": item.get("reportUrl", ""),
                    "mode": item.get("mode", ""),
                    "exam_code": item.get("examCode", ""),
                }
            )

        return {
            "student": summary.to_dict(),
            "task_states": task_states,
            "exam_sessions": exam_sessions,
            "reports": report_items,
        }

    def _build_scope_summaries(
        self,
        account: Dict[str, Any],
        states: List[Any],
        sessions: List[Dict[str, Any]],
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        scope_keys: set[Tuple[str, str, str]] = set()

        for state in states:
            scope_keys.add(
                (
                    state.game,
                    getattr(state, "mode", "exercise"),
                    getattr(state, "exam_code", "") or "",
                )
            )

        for session in sessions:
            scope_keys.add(
                (
                    session.get("game", ""),
                    "exam",
                    session.get("examCode", ""),
                )
            )

        for record in records:
            scope_keys.add(
                (
                    record.get("gameTime", "").split("#", 1)[0],
                    record.get("mode", "exercise") or "exercise",
                    record.get("examCode", "") or "",
                )
            )

        rows: List[Dict[str, Any]] = []
        for game, mode, exam_code in sorted(scope_keys):
            if not game:
                continue
            filtered_states, filtered_sessions, filtered_records = self._filter_scope_items(
                states,
                sessions,
                records,
                game,
                mode,
                exam_code,
            )
            rows.append(
                self._build_scope_summary(
                    account,
                    filtered_states,
                    filtered_sessions,
                    filtered_records,
                    game,
                    mode,
                    exam_code,
                ).to_dict()
            )
        return rows

    def _build_scope_summary(
        self,
        account: Dict[str, Any],
        states: List[Any],
        sessions: List[Dict[str, Any]],
        records: List[Dict[str, Any]],
        game: Optional[str],
        mode: Optional[str],
        exam_code: Optional[str],
    ) -> TeacherScopeSummary:
        scope_mode = mode or "exercise"
        scope_exam_code = exam_code or ""
        active_states = [state for state in states if state.status == TaskStatus.IN_PROGRESS]
        current_state = max(active_states, key=lambda item: item.updated_at, default=None)
        latest_state = max(states, key=lambda item: item.updated_at, default=None)
        latest_session = max(sessions, key=lambda item: item.get("verifiedAt", ""), default=None)
        latest_record = max(records, key=lambda item: item.get("time", ""), default={}) if records else {}

        total_score = sum(_safe_int(getattr(state, "total_points", 0)) for state in states)
        completed_tasks = sum(
            1 for state in states
            if state.status == TaskStatus.COMPLETED and not getattr(state, "skipped", False)
        )
        skipped_tasks = sum(1 for state in states if getattr(state, "skipped", False))

        current_task = ""
        current_phase = ""
        status = "READY"
        if current_state:
            current_task = current_state.task_id
            current_phase = current_state.current_phase_id or ""
            status = "ACTIVE"
        elif latest_state:
            current_task = latest_state.task_id
            current_phase = latest_state.current_phase_id or ""
            status = "FINISHED" if latest_state.status == TaskStatus.COMPLETED else latest_state.status.value.upper()
        elif latest_session:
            allowed_tasks = latest_session.get("allowedTasks") or []
            current_task = allowed_tasks[0] if allowed_tasks else ""
            status = "VERIFIED"

        last_activity = _last_value(
            [
                getattr(latest_state, "updated_at", ""),
                latest_session.get("verifiedAt", "") if latest_session else "",
                latest_record.get("time", ""),
                str(account.get("time", "")),
            ]
        )

        return TeacherScopeSummary(
            email=account.get("email", ""),
            endpoint=account.get("endpoint", ""),
            game=game or "",
            scope_mode=scope_mode,
            exam_code=scope_exam_code,
            last_activity=last_activity,
            current_task=current_task,
            current_phase=current_phase,
            total_score=total_score,
            completed_tasks=completed_tasks,
            skipped_tasks=skipped_tasks,
            status=status,
            latest_result=latest_record.get("testResult", ""),
            latest_report_url=latest_record.get("reportUrl", ""),
        )

    def _filter_scope_items(
        self,
        states: List[Any],
        sessions: List[Dict[str, Any]],
        records: List[Dict[str, Any]],
        game: Optional[str],
        mode: Optional[str],
        exam_code: Optional[str],
    ) -> Tuple[List[Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        filtered_states = states
        filtered_sessions = sessions
        filtered_records = records

        if game:
            filtered_states = [state for state in filtered_states if state.game == game]
            filtered_sessions = [session for session in filtered_sessions if session.get("game", "") == game]
            filtered_records = [
                record
                for record in filtered_records
                if record.get("gameTime", "").split("#", 1)[0] == game
            ]

        if mode:
            filtered_states = [state for state in filtered_states if getattr(state, "mode", "exercise") == mode]
            filtered_records = [record for record in filtered_records if (record.get("mode", "exercise") or "exercise") == mode]
            if mode != "exam":
                filtered_sessions = []

        if exam_code:
            filtered_states = [state for state in filtered_states if (getattr(state, "exam_code", "") or "") == exam_code]
            filtered_sessions = [session for session in filtered_sessions if (session.get("examCode", "") or "") == exam_code]
            filtered_records = [record for record in filtered_records if (record.get("examCode", "") or "") == exam_code]
        elif mode == "exam":
            filtered_states = [state for state in filtered_states if getattr(state, "mode", "exercise") == "exam"]

        return filtered_states, filtered_sessions, filtered_records

    def _resolve_game(self, states: List[Any], sessions: List[Dict[str, Any]], records: List[Dict[str, Any]]) -> str:
        if states:
            return states[0].game
        if sessions:
            return sessions[0].get("game", "")
        if records:
            return records[0].get("gameTime", "").split("#", 1)[0]
        return ""

    def _resolve_mode(self, states: List[Any], sessions: List[Dict[str, Any]], records: List[Dict[str, Any]]) -> str:
        if states:
            return getattr(states[0], "mode", "exercise")
        if sessions:
            return "exam"
        if records:
            return records[0].get("mode", "exercise") or "exercise"
        return "exercise"

    def _resolve_exam_code(self, states: List[Any], sessions: List[Dict[str, Any]], records: List[Dict[str, Any]]) -> str:
        for state in states:
            value = getattr(state, "exam_code", "") or ""
            if value:
                return value
        for session in sessions:
            value = session.get("examCode", "") or ""
            if value:
                return value
        for record in records:
            value = record.get("examCode", "") or ""
            if value:
                return value
        return ""
