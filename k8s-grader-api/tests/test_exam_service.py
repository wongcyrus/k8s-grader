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

    def test_list_records_normalizes_and_sorts_exam_history(self, exam_service):
        with patch("common.database.repositories.TestRecordRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.list_by_email.return_value = [
                {
                    "task": "087_task",
                    "gamePhase": "setup",
                    "testResult": "OK",
                    "time": "2026-07-22_03-10-00",
                    "reportUrl": "",
                    "mode": "exam",
                },
                {
                    "task": "087_task",
                    "gamePhase": "check",
                    "testResult": "TESTS_FAILED",
                    "time": "2026-07-22_03-12-00",
                    "reportUrl": "https://example.com/report.html",
                    "mode": "exam",
                },
            ]

            records = exam_service.list_records("student@example.com", "EXAM-001", task_id="087_task")

        assert records == [
            {
                "task_id": "087_task",
                "phase": "check",
                "test_result": "TESTS_FAILED",
                "time": "2026-07-22_03-12-00",
                "report_url": "https://example.com/report.html",
                "mode": "exam",
            },
            {
                "task_id": "087_task",
                "phase": "setup",
                "test_result": "OK",
                "time": "2026-07-22_03-10-00",
                "report_url": "",
                "mode": "exam",
            },
        ]
        mock_repo.list_by_email.assert_called_once_with("student@example.com", exam_code="EXAM-001", task_id="087_task")

    def test_get_exam_overview_normalizes_stale_non_check_points(self, exam_service, exam_manifest, exam_task_state):
        exam_task_state.status = TaskStatus.IN_PROGRESS
        exam_task_state.current_phase_id = "check"
        exam_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED, points_earned=0)
        exam_task_state.phase_states["challenge"] = PhaseState("challenge", PhaseStatus.PASSED, points_earned=5)
        exam_task_state.total_points = 5
        exam_service.task_repo.save(exam_task_state)

        with patch("common.services.exam_service.TaskManifest.load", return_value=exam_manifest):
            overview = exam_service.get_exam_overview("student@example.com", "exam01", ["exam_task_01"])

        assert overview["exam_score"] == 0
        assert overview["task_summaries"][0]["total_points"] == 0
        saved_state = exam_service.task_repo.get("student@example.com", "exam01", "exam_task_01")
        assert saved_state.total_points == 0
        assert saved_state.get_phase_state("challenge").points_earned == 0

    def test_get_status_normalizes_state_points_for_exam_mode(self, exam_service, exam_manifest, exam_task_state):
        exam_service.exam_code_repo.save(
            exam_code="EXAM-005",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            starts_at="2026-01-01T00:00:00+00:00",
            ends_at="2026-12-31T23:59:59+00:00",
            max_attempts=3,
            status="active",
        )
        exam_service.exam_session_repo.save(
            email="student@example.com",
            exam_code="EXAM-005",
            game="exam01",
            allowed_tasks=["exam_task_01"],
            expires_at="2026-12-31T23:59:59+00:00",
        )
        exam_service.game_access_repo.save("exam01", mode="exam", allowed_tasks=["exam_task_01"])

        exam_task_state.status = TaskStatus.IN_PROGRESS
        exam_task_state.current_phase_id = "check"
        exam_task_state.phase_states["challenge"] = PhaseState("challenge", PhaseStatus.PASSED, points_earned=5)
        exam_task_state.total_points = 5
        exam_service.task_repo.save(exam_task_state)

        with patch("common.services.exam_service.TaskManifest.load", return_value=exam_manifest):
            result = exam_service.get_status("student@example.com", "EXAM-005", "exam01", "exam_task_01")

        assert result["state"].total_points == 0
        assert result["exam_score"] == 0
