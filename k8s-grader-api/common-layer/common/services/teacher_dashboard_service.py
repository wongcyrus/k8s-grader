"""Teacher dashboard aggregation service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
class TeacherStudentSummary:
    email: str
    endpoint: str
    last_activity: str
    current_mode: str
    current_task: str
    current_phase: str
    total_score: int
    exercise_score: int
    exam_score: int
    completed_tasks: int
    skipped_tasks: int
    status: str
    latest_result: str
    latest_report_url: str
    active_exam_code: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email": self.email,
            "endpoint": self.endpoint,
            "last_activity": self.last_activity,
            "current_mode": self.current_mode,
            "current_task": self.current_task,
            "current_phase": self.current_phase,
            "total_score": self.total_score,
            "exercise_score": self.exercise_score,
            "exam_score": self.exam_score,
            "completed_tasks": self.completed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "status": self.status,
            "latest_result": self.latest_result,
            "latest_report_url": self.latest_report_url,
            "active_exam_code": self.active_exam_code,
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
        accounts = sorted(self.account_repo.list_all(), key=lambda item: item.get("email", ""))
        return [self._build_student_summary(account).to_dict() for account in accounts]

    def get_student_detail(self, student_email: str) -> Dict[str, Any]:
        account = self.account_repo.get(student_email)
        if not account:
            raise ValueError("Student account not found")

        summary = self._build_student_summary(account)
        states = self.task_repo.list_by_email(student_email)
        sessions = sorted(
            self.exam_session_repo.list_by_email(student_email),
            key=lambda item: item.get("verifiedAt", ""),
            reverse=True,
        )
        records = sorted(
            self.test_record_repo.list_by_email(student_email),
            key=lambda item: item.get("time", ""),
            reverse=True,
        )

        task_states = []
        for state in sorted(states, key=lambda item: (item.game, item.task_id)):
            task_states.append(
                {
                    "game": state.game,
                    "task_id": state.task_id,
                    "mode": state.mode,
                    "status": state.status.value,
                    "current_phase": state.current_phase_id or "",
                    "total_points": state.total_points,
                    "skipped": bool(getattr(state, "skipped", False)),
                    "updated_at": state.updated_at,
                }
            )

        exam_sessions = []
        for session in sessions:
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
        for item in records[:50]:
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

    def _build_student_summary(self, account: Dict[str, Any]) -> TeacherStudentSummary:
        email = account.get("email", "")
        states = self.task_repo.list_by_email(email)
        sessions = self.exam_session_repo.list_by_email(email)
        records = sorted(
            self.test_record_repo.list_by_email(email),
            key=lambda item: item.get("time", ""),
            reverse=True,
        )

        exercise_states = [state for state in states if getattr(state, "mode", "exercise") != "exam"]
        exam_states = [state for state in states if getattr(state, "mode", "exercise") == "exam"]
        exercise_score = sum(_safe_int(getattr(state, "total_points", 0)) for state in exercise_states)
        exam_score = sum(_safe_int(getattr(state, "total_points", 0)) for state in exam_states)

        completed_tasks = sum(
            1 for state in exercise_states
            if state.status == TaskStatus.COMPLETED and not getattr(state, "skipped", False)
        )
        skipped_tasks = sum(1 for state in exercise_states if getattr(state, "skipped", False))

        active_states = [state for state in states if state.status == TaskStatus.IN_PROGRESS]
        current_state = max(active_states, key=lambda item: item.updated_at, default=None)
        latest_state = max(states, key=lambda item: item.updated_at, default=None)

        active_sessions = [session for session in sessions if session.get("active")]
        latest_session = max(active_sessions, key=lambda item: item.get("verifiedAt", ""), default=None)
        latest_record = records[0] if records else {}

        current_mode = ""
        current_task = ""
        current_phase = ""
        status = "READY"
        if current_state:
            current_mode = getattr(current_state, "mode", "exercise")
            current_task = current_state.task_id
            current_phase = current_state.current_phase_id or ""
            status = "ACTIVE"
        elif latest_session:
            current_mode = "exam"
            status = "VERIFIED"
        elif latest_state:
            current_mode = getattr(latest_state, "mode", "exercise")
            current_task = latest_state.task_id
            current_phase = latest_state.current_phase_id or ""
            status = "FINISHED" if latest_state.status == TaskStatus.COMPLETED else latest_state.status.value.upper()

        if current_mode == "exam" and not current_task and latest_session:
            current_task = latest_session.get("allowedTasks", [""])[0] if latest_session.get("allowedTasks") else ""

        last_activity = _last_value(
            [
                getattr(latest_state, "updated_at", ""),
                latest_session.get("verifiedAt", "") if latest_session else "",
                latest_record.get("time", ""),
                str(account.get("time", "")),
            ]
        )

        return TeacherStudentSummary(
            email=email,
            endpoint=account.get("endpoint", ""),
            last_activity=last_activity,
            current_mode=current_mode,
            current_task=current_task,
            current_phase=current_phase,
            total_score=exercise_score + exam_score,
            exercise_score=exercise_score,
            exam_score=exam_score,
            completed_tasks=completed_tasks,
            skipped_tasks=skipped_tasks,
            status=status,
            latest_result=latest_record.get("testResult", ""),
            latest_report_url=latest_record.get("reportUrl", ""),
            active_exam_code=latest_session.get("examCode", "") if latest_session else "",
        )
