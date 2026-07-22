"""Tests for ExamService"""
import pytest
from unittest.mock import patch

from common.services.exam_service import ExamService
from common.database.repositories import ExamCodeRepository, ExamSessionRepository, GameAccessRepository, TaskStateRepository
from common.models.task_state import TaskStatus, PhaseStatus, PhaseState
from common.status import TestResult


@pytest.fixture
def exam_service(dynamodb_tables):
    return ExamService(
        exam_code_repo=ExamCodeRepository(),
        exam_session_repo=ExamSessionRepository(),
        game_access_repo=GameAccessRepository(),
        task_repo=TaskStateRepository(),
    )


class TestExamService:
    def test_verify_code_creates_session_and_game_access(self, exam_service, exam_manifest):
        exam_service.exam_code_repo.save(
            exam_code="EXAM-001",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            starts_at="2026-01-01T00:00:00+00:00",
            ends_at="2026-12-31T23:59:59+00:00",
            max_attempts=3,
            status="active",
        )

        result = exam_service.verify_code("student@example.com", "EXAM-001")

        assert result["exam_code"] == "EXAM-001"
        assert result["game"] == "exam01"
        session = exam_service.exam_session_repo.get("student@example.com", "EXAM-001")
        assert session["active"] is True
        assert exam_service.game_access_repo.get_mode("exam01") == "exam"

    def test_authorize_rejects_without_session(self, exam_service):
        exam_service.exam_code_repo.save(
            exam_code="EXAM-002",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            starts_at="2026-01-01T00:00:00+00:00",
            ends_at="2026-12-31T23:59:59+00:00",
            max_attempts=3,
            status="active",
        )
        exam_service.game_access_repo.save("exam01", mode="exam", allowed_tasks=["exam_task_01"])

        ok, error, _ = exam_service.authorize("student@example.com", "EXAM-002", "exam01", "exam_task_01")

        assert ok is False
        assert "verified" in error.lower()

    def test_start_exam_task_uses_exam_mode(self, exam_service, exam_manifest):
        exam_service.exam_code_repo.save(
            exam_code="EXAM-003",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            starts_at="2026-01-01T00:00:00+00:00",
            ends_at="2026-12-31T23:59:59+00:00",
            max_attempts=3,
            status="active",
        )
        exam_service.exam_session_repo.save(
            email="student@example.com",
            exam_code="EXAM-003",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            expires_at="2026-12-31T23:59:59+00:00",
        )
        exam_service.game_access_repo.save("exam01", mode="exam", allowed_tasks=["exam_task_01"])

        with patch('common.services.task_service.TaskManifest.load', return_value=exam_manifest), \
             patch('common.services.task_service.generate_session', return_value={'key': 'value'}):
            state = exam_service.task_service.start_exam_task("student@example.com", "exam01", "exam_task_01", "EXAM-003")

        assert state.mode == "exam"
        assert state.exam_code == "EXAM-003"
        assert state.npc == "exam"
        assert state.status == TaskStatus.IN_PROGRESS

    def test_run_phase_allows_challenge_without_counting_attempts(self, exam_service, exam_manifest, exam_task_state):
        exam_service.exam_code_repo.save(
            exam_code="EXAM-004",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            starts_at="2026-01-01T00:00:00+00:00",
            ends_at="2026-12-31T23:59:59+00:00",
            max_attempts=3,
            status="active",
        )
        exam_service.exam_session_repo.save(
            email="student@example.com",
            exam_code="EXAM-004",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            expires_at="2026-12-31T23:59:59+00:00",
        )
        exam_service.game_access_repo.save("exam01", mode="exam", allowed_tasks=["exam_task_01"])
        exam_task_state.status = TaskStatus.IN_PROGRESS
        exam_task_state.current_phase_id = "challenge"
        exam_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        exam_service.task_repo.save(exam_task_state)

        with patch('common.services.task_service.TaskManifest.load', return_value=exam_manifest), \
             patch.object(exam_service.task_service.test_runner, 'run_phase', return_value=(TestResult.TESTS_FAILED, 'https://report.url')):
            result = exam_service.run_phase("student@example.com", "EXAM-004", "exam01", "exam_task_01", "challenge")

        assert result["success"] is False
        state = exam_service.task_repo.get("student@example.com", "exam01", "exam_task_01")
        assert state.get_phase_state("challenge").attempts == 0
