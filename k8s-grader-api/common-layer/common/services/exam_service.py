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
        overview = self.get_exam_overview(email, game, allowed_tasks)
        return {
            "email": email,
            "exam_code": exam_code,
            "session_id": session_id,
            "game": game,
            "allowed_tasks": allowed_tasks,
            "max_attempts": exam.get("maxAttempts", 3),
            **overview,
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
        self.normalize_exam_points(state, manifest)
        overview = self.get_exam_overview(email, game, context["session"].get("allowedTasks", []))
        return {
            "state": state,
            "manifest": manifest,
            "allowed_tasks": context["session"].get("allowedTasks", []),
            **overview,
        }

    def list_records(self, email: str, exam_code: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        from common.database.repositories import TestRecordRepository

        repo = TestRecordRepository()
        records = repo.list_by_email(email, exam_code=exam_code, task_id=task_id)
        normalized_records = []
        for item in sorted(records, key=lambda record: record.get("time", ""), reverse=True):
            normalized_records.append({
                "task_id": item.get("task", ""),
                "phase": item.get("gamePhase", ""),
                "test_result": item.get("testResult", ""),
                "time": item.get("time", ""),
                "report_url": item.get("reportUrl", ""),
                "mode": item.get("mode", ""),
            })
        return normalized_records

    def normalize_exam_points(self, state: Optional[TaskState], manifest: Optional[TaskManifest] = None) -> int:
        if not state:
            return 0
        if state.mode != "exam":
            return state.total_points

        manifest = manifest or TaskManifest.load(state.game, state.task_id)
        normalized_points = 0
        changed = False

        for phase in manifest.phases:
            phase_state = state.get_phase_state(phase.id)
            if not phase_state:
                continue

            phase_status = getattr(phase_state.status, "value", phase_state.status)
            expected_points = phase.points if phase.id == "check" and phase_status == "passed" else 0
            if phase_state.points_earned != expected_points:
                phase_state.points_earned = expected_points
                changed = True
            if phase_status == "passed":
                normalized_points += expected_points

        if state.total_points != normalized_points:
            state.total_points = normalized_points
            changed = True

        if changed:
            self.task_repo.save(state)

        return normalized_points

    def get_exam_overview(self, email: str, game: str, allowed_tasks: List[str]) -> Dict[str, Any]:
        task_summaries = []
        exam_score = 0
        finished_statuses = {TaskStatus.COMPLETED.value, TaskStatus.ABANDONED.value}

        for task_id in allowed_tasks:
            state = self.task_repo.get(email, game, task_id)
            status = state.status.value if state else TaskStatus.NOT_STARTED.value
            manifest = TaskManifest.load(game, task_id) if state else None
            total_points = self.normalize_exam_points(state, manifest) if state else 0
            exam_score += total_points
            task_summaries.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "total_points": total_points,
                    "current_phase": state.current_phase_id if state else None,
                }
            )

        finished_tasks = [item["task_id"] for item in task_summaries if item["status"] in finished_statuses]
        remaining_tasks = [task_id for task_id in allowed_tasks if task_id not in finished_tasks]

        return {
            "task_summaries": task_summaries,
            "finished_tasks": finished_tasks,
            "remaining_tasks": remaining_tasks,
            "exam_score": exam_score,
        }
