"""Tests for teacher dashboard aggregation service."""
from unittest.mock import Mock

from common.models.task_state import TaskState, TaskStatus
from common.services.teacher_dashboard_service import TeacherDashboardService


def build_state(
    email,
    game,
    task_id,
    *,
    mode="exercise",
    exam_code=None,
    status=TaskStatus.IN_PROGRESS,
    phase="setup",
    points=0,
    skipped=False,
    updated_at="2026-01-01T10:00:00+00:00",
):
    return TaskState(
        email=email,
        game=game,
        task_id=task_id,
        npc="npc1",
        mode=mode,
        exam_code=exam_code,
        status=status,
        current_phase_id=phase,
        total_points=points,
        skipped=skipped,
        session_data={},
        created_at=updated_at,
        updated_at=updated_at,
    )


class TestTeacherDashboardService:
    def test_list_students_groups_rows_per_game_and_scope(self):
        account_repo = Mock()
        task_repo = Mock()
        exam_session_repo = Mock()
        test_record_repo = Mock()

        account_repo.list_all.return_value = [
            {"email": "student@example.com", "endpoint": "https://cluster.example.com", "time": 1700000000}
        ]
        task_repo.list_by_email.return_value = [
            build_state(
                "student@example.com",
                "game01",
                "task01",
                mode="exercise",
                status=TaskStatus.COMPLETED,
                phase="check",
                points=5,
                updated_at="2026-01-01T10:00:00+00:00",
            ),
            build_state(
                "student@example.com",
                "game01",
                "task02",
                mode="exercise",
                status=TaskStatus.COMPLETED,
                phase="done",
                points=0,
                skipped=True,
                updated_at="2026-01-01T09:30:00+00:00",
            ),
            build_state(
                "student@example.com",
                "game01",
                "task03",
                mode="exam",
                exam_code="EXAM-001",
                status=TaskStatus.IN_PROGRESS,
                phase="ready",
                points=3,
                updated_at="2026-01-01T11:00:00+00:00",
            ),
        ]
        exam_session_repo.list_by_email.return_value = [
            {
                "examCode": "EXAM-001",
                "game": "game01",
                "active": True,
                "verifiedAt": "2026-01-01T08:00:00+00:00",
                "allowedTasks": ["task03"],
            }
        ]
        test_record_repo.list_by_email.return_value = [
            {
                "gameTime": "game01#2026-01-01_11-05-00",
                "mode": "exam",
                "examCode": "EXAM-001",
                "testResult": "OK",
                "reportUrl": "https://report.example.com/exam.html",
                "time": "2026-01-01_11-05-00",
            },
            {
                "gameTime": "game01#2026-01-01_10-05-00",
                "mode": "exercise",
                "testResult": "OK",
                "reportUrl": "https://report.example.com/exercise.html",
                "time": "2026-01-01_10-05-00",
            },
        ]

        service = TeacherDashboardService(
            account_repo=account_repo,
            task_repo=task_repo,
            exam_session_repo=exam_session_repo,
            test_record_repo=test_record_repo,
        )

        result = service.list_students()

        assert len(result) == 2
        exercise_row = next(item for item in result if item["scope_mode"] == "exercise")
        exam_row = next(item for item in result if item["scope_mode"] == "exam")

        assert exercise_row["game"] == "game01"
        assert exercise_row["total_score"] == 5
        assert exercise_row["completed_tasks"] == 1
        assert exercise_row["skipped_tasks"] == 1
        assert exercise_row["latest_report_url"] == "https://report.example.com/exercise.html"

        assert exam_row["game"] == "game01"
        assert exam_row["exam_code"] == "EXAM-001"
        assert exam_row["status"] == "ACTIVE"
        assert exam_row["current_task"] == "task03"
        assert exam_row["current_phase"] == "ready"
        assert exam_row["total_score"] == 3
        assert exam_row["latest_report_url"] == "https://report.example.com/exam.html"

    def test_get_student_detail_filters_by_scope(self):
        account_repo = Mock()
        task_repo = Mock()
        exam_session_repo = Mock()
        test_record_repo = Mock()

        account_repo.get.return_value = {"email": "student@example.com", "endpoint": "https://cluster.example.com", "time": 1700000000}
        task_repo.list_by_email.return_value = [
            build_state(
                "student@example.com",
                "game01",
                "task01",
                mode="exercise",
                status=TaskStatus.COMPLETED,
                phase="check",
                points=5,
                updated_at="2026-01-01T10:00:00+00:00",
            ),
            build_state(
                "student@example.com",
                "game01",
                "task02",
                mode="exam",
                exam_code="EXAM-001",
                status=TaskStatus.IN_PROGRESS,
                phase="ready",
                points=3,
                updated_at="2026-01-01T11:00:00+00:00",
            ),
        ]
        exam_session_repo.list_by_email.return_value = [
            {
                "examCode": "EXAM-001",
                "game": "game01",
                "active": True,
                "verifiedAt": "2026-01-01T08:00:00+00:00",
                "expiresAt": "2026-01-01T12:00:00+00:00",
            }
        ]
        test_record_repo.list_by_email.return_value = [
            {
                "gameTime": "game01#2026-01-01_10-00-00",
                "task": "task01",
                "gamePhase": "check",
                "testResult": "OK",
                "time": "2026-01-01_10-00-00",
                "reportUrl": "https://report.example.com/exercise.html",
                "mode": "exercise",
            },
            {
                "gameTime": "game01#2026-01-01_11-00-00",
                "task": "task02",
                "gamePhase": "ready",
                "testResult": "OK",
                "time": "2026-01-01_11-00-00",
                "reportUrl": "https://report.example.com/exam.html",
                "mode": "exam",
                "examCode": "EXAM-001",
            },
        ]

        service = TeacherDashboardService(
            account_repo=account_repo,
            task_repo=task_repo,
            exam_session_repo=exam_session_repo,
            test_record_repo=test_record_repo,
        )

        result = service.get_student_detail(
            "student@example.com",
            game="game01",
            mode="exam",
            exam_code="EXAM-001",
        )

        assert result["student"]["email"] == "student@example.com"
        assert result["student"]["game"] == "game01"
        assert result["student"]["scope_mode"] == "exam"
        assert result["student"]["exam_code"] == "EXAM-001"
        assert len(result["task_states"]) == 1
        assert result["task_states"][0]["task_id"] == "task02"
        assert len(result["exam_sessions"]) == 1
        assert result["exam_sessions"][0]["exam_code"] == "EXAM-001"
        assert len(result["reports"]) == 1
        assert result["reports"][0]["report_url"] == "https://report.example.com/exam.html"

    def test_get_student_detail_rejects_unknown_student(self):
        service = TeacherDashboardService(
            account_repo=Mock(get=Mock(return_value=None)),
            task_repo=Mock(),
            exam_session_repo=Mock(),
            test_record_repo=Mock(),
        )

        try:
            service.get_student_detail("missing@example.com")
        except ValueError as err:
            assert str(err) == "Student account not found"
        else:
            raise AssertionError("Expected ValueError for missing student")
