"""Exam access and execution service"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging
import uuid

from common.database.repositories import (
    ExamCodeRepository,
    ExamSessionRepository,
    GameAccessRepository,
    TaskStateRepository,
)
from common.models.task_state import TaskState, TaskStatus
from common.models.task_manifest import TaskManifest
from common.state_machine.task_state_machine import TaskStateMachine
from common.services.task_service import TaskService

logger = logging.getLogger(__name__)


class ExamService:
    """Exam access, authorization, and execution."""

    def __init__(
        self,
        exam_code_repo: Optional[ExamCodeRepository] = None,
        exam_session_repo: Optional[ExamSessionRepository] = None,
        game_access_repo: Optional[GameAccessRepository] = None,
        task_repo: Optional[TaskStateRepository] = None,
        task_service: Optional[TaskService] = None,
    ):
        self.exam_code_repo = exam_code_repo or ExamCodeRepository()
        self.exam_session_repo = exam_session_repo or ExamSessionRepository()
        self.game_access_repo = game_access_repo or GameAccessRepository()
        self.task_repo = task_repo or TaskStateRepository()
        self.task_service = task_service or TaskService(task_repo=self.task_repo)

    def verify_code(self, email: str, exam_code: str) -> Dict[str, Any]:
        exam = self.exam_code_repo.get(exam_code)
        if not exam:
            raise ValueError("Invalid exam code")
        if exam.get("status", "").lower() != "active":
            raise ValueError("Exam code is disabled")

        now = datetime.now(timezone.utc)
        starts_at = exam.get("startsAt")
        ends_at = exam.get("endsAt")
        if starts_at and now.isoformat() < starts_at:
            raise ValueError("Exam has not started")
        if ends_at and now.isoformat() > ends_at:
            raise ValueError("Exam has ended")

        game = exam["game"]
        allowed_tasks = exam.get("allowedTasks", [])
        expires_at = ends_at or (now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat())
        session_id = f"{email}#{exam_code}#{uuid.uuid4().hex[:8]}"
        self.exam_session_repo.save(
            email=email,
            exam_code=exam_code,
            game=game,
            allowed_tasks=allowed_tasks,
            expires_at=expires_at,
            session_id=session_id,
        )
        self.game_access_repo.save(game=game, mode="exam", allowed_tasks=allowed_tasks)
        return {
            "email": email,
            "exam_code": exam_code,
            "session_id": session_id,
            "game": game,
            "allowed_tasks": allowed_tasks,
            "max_attempts": exam.get("maxAttempts", 3),
        }

    def authorize(self, email: str, exam_code: str, game: str, task_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        exam = self.exam_code_repo.get(exam_code)
        if not exam:
            return False, "Invalid exam code", None
        if exam.get("status", "").lower() != "active":
            return False, "Exam code is disabled", None
        if exam.get("game") != game:
            return False, "Exam scope mismatch", None

        session = self.exam_session_repo.get(email, exam_code)
        if not session or not session.get("active", False):
            return False, "Exam code not verified", None
        if session.get("game") != game:
            return False, "Exam scope mismatch", None

        allowed_tasks = session.get("allowedTasks", exam.get("allowedTasks", []))
        if allowed_tasks and task_id not in allowed_tasks:
            return False, "Task not allowed for this exam", None

        if self.game_access_repo.get_mode(game) != "exam":
            return False, "Game is not configured for exam mode", None

        return True, "", {"exam": exam, "session": session}

    def ensure_state(self, email: str, exam_code: str, game: str, task_id: str) -> TaskState:
        state = self.task_repo.get(email, game, task_id)
        if state:
            if state.exam_code != exam_code and state.mode != "exam":
                raise ValueError("Task already exists for a different mode")
            return state

        state = self.task_service.start_exam_task(email, game, task_id, exam_code)
        return state

    def run_phase(self, email: str, exam_code: str, game: str, task_id: str, phase_id: Optional[str] = None) -> Dict[str, Any]:
        state = self.ensure_state(email, exam_code, game, task_id)
        result = self.task_service.execute_phase(email, game, task_id, phase_id)
        return {
            "state": result.get("state", state),
            "manifest": result.get("manifest"),
            "success": result.get("success", False),
            "error": result.get("error"),
            "test_result": result.get("test_result"),
            "report_url": result.get("report_url", ""),
        }

    def get_status(self, email: str, exam_code: str, game: str, task_id: str) -> Dict[str, Any]:
        ok, error, context = self.authorize(email, exam_code, game, task_id)
        if not ok:
            raise ValueError(error)
        state = self.task_repo.get(email, game, task_id)
        manifest = TaskManifest.load(game, task_id)
        return {
            "state": state,
            "manifest": manifest,
            "allowed_tasks": context["session"].get("allowedTasks", []),
        }

    def list_records(self, email: str, exam_code: str) -> List[Dict[str, Any]]:
        from common.database.repositories import TestRecordRepository

        repo = TestRecordRepository()
        return repo.list_by_email(email, exam_code=exam_code)
