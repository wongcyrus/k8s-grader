import json
from unittest.mock import Mock, patch

import pytest

from common.database import ExecutionGuardRepository
from common.exam_execution import ExamExecutionGuard, current_exam_execution


@pytest.fixture
def guard(dynamodb_tables):
    repo = ExamExecutionGuard()
    repo._table = dynamodb_tables["ws_execution_guard_table"]
    return repo


def test_expired_owner_cannot_release_or_execute_under_a_new_lease(guard):
    with patch("common.exam_execution.time.time", return_value=100):
        first = guard.acquire("student", "game02", "exam1", "task_a", "run")
    with patch("common.exam_execution.time.time", return_value=4000):
        second = guard.acquire("student", "game02", "exam1", "task_b", "run")
        assert guard.release(first["scope_key"], first["execution_id"]) is False
        callback = Mock()
        response = guard.execute(
            "run",
            "student",
            "exam1",
            "game02",
            "task_a",
            callback,
            execution_id=first["execution_id"],
        )
        assert (
            json.loads(response["body"])["active_execution"]["execution_id"]
            == second["execution_id"]
        )
        callback.assert_not_called()


def test_guard_covers_callback_and_releases_before_exposing_completion(guard):
    lease = guard.acquire("student", "game02", "exam1", "task_a", "run")

    def callback():
        assert current_exam_execution.get()["execution_id"] == lease["execution_id"]
        guard.set_phase(current_exam_execution.get(), "cleanup")
        assert guard.acquire("student", "game02", "exam2", "task_b", "start") is None
        assert guard.get_active("student", "game02")["phase"] == "cleanup"
        return {"statusCode": 200, "body": '{"status":"COMPLETED"}'}

    response = guard.execute(
        "run",
        "student",
        "exam1",
        "game02",
        "task_a",
        callback,
        execution_id=lease["execution_id"],
    )
    payload = json.loads(response["body"])
    assert payload["command_finished"] is True
    assert payload["active_execution"] is None
    assert guard.get_active("student", "game02") is None
    assert current_exam_execution.get() is None


def test_guard_releases_on_exception_without_affecting_game_leases(guard):
    game_repo = ExecutionGuardRepository()
    game_repo._table = guard.table
    assert game_repo.acquire(
        "game#student#game02#mutation",
        email="student",
        channel="game_ws",
        action="talk",
        ttl_seconds=180,
    )
    with pytest.raises(RuntimeError, match="failed"):
        guard.execute(
            "reset",
            "student",
            "exam1",
            "game02",
            "task_a",
            Mock(side_effect=RuntimeError("failed")),
        )
    assert guard.get_active("student", "game02") is None
    assert game_repo.table.get_item(Key={"scope_key": "game#student#game02#mutation"})[
        "Item"
    ]


def test_environment_survives_execution_expiry_and_cannot_be_taken_by_another_question(guard):
    with patch("common.exam_execution.time.time", return_value=100):
        assert guard.claim_environment("student", "game02", "exam1", "task_a")
        guard.acquire("student", "game02", "exam1", "task_a", "start")
    with patch("common.exam_execution.time.time", return_value=100000):
        assert guard.get_active("student", "game02") is None
        assert guard.get_environment("student", "game02")["task_id"] == "task_a"
        assert not guard.claim_environment("student", "game02", "exam2", "task_b")
        assert not guard.release_environment("student", "game02", "exam2", "task_a")
        assert guard.get_environment("student", "game02")["task_id"] == "task_a"


def test_unfinished_legacy_question_is_adopted_before_another_can_start(guard):
    from common.database import TaskStateRepository
    from common.models.task_state import TaskState, TaskStatus

    repository = TaskStateRepository()
    repository.save(TaskState(
        email="student", game="game02", task_id="old_question", npc="exam",
        mode="exam", exam_code="exam1", status=TaskStatus.IN_PROGRESS,
        current_phase_id="check",
    ))
    assert not guard.claim_environment("student", "game02", "exam1", "new_question")
    assert guard.get_environment("student", "game02")["task_id"] == "old_question"
    assert guard.claim_environment("student", "game02", "exam1", "old_question")
