"""Tests for the durable exam command handler."""
import importlib.util
import json
import logging
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest


MODULE_NAME = "exam_durable_app"
HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "exam-durable-handler", "app.py")


@pytest.fixture(autouse=True)
def exam_aws_tables(dynamodb_tables):
    return dynamodb_tables


def load_module():
    fake_sdk = types.ModuleType("aws_durable_execution_sdk_python")

    class DurableContext:
        pass

    def durable_execution(fn):
        return fn

    def durable_step(fn):
        return fn

    fake_sdk.DurableContext = DurableContext
    fake_sdk.durable_execution = durable_execution
    fake_sdk.durable_step = durable_step

    sys.modules["aws_durable_execution_sdk_python"] = fake_sdk
    spec = importlib.util.spec_from_file_location(MODULE_NAME, HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


class StubContext:
    def __init__(self):
        self.calls = []

    def step(self, value):
        self.calls.append(value)
        return {"wrapped": value}


def test_execute_exam_command_dispatches_start():
    module = load_module()

    with patch.object(module, "handle_exam_start", return_value={"statusCode": 200}) as mock_start:
        result = module.execute_exam_command(
            "start",
            "student@example.com",
            "EXAM-001",
            "game02",
            "087_task",
        )

    mock_start.assert_called_once_with("student@example.com", "EXAM-001", "game02", "087_task")
    assert result == {"statusCode": 200}


def test_execute_exam_command_step_wraps_plain_helper():
    module = load_module()

    with patch.object(module, "execute_exam_command", return_value={"statusCode": 200}) as mock_execute:
        result = module.execute_exam_command_step(None, "status", "student@example.com", "EXAM-001", "game02", "087_task")

    mock_execute.assert_called_once_with("status", "student@example.com", "EXAM-001", "game02", "087_task")
    assert result == {"statusCode": 200}


def test_execute_exam_command_rejects_invalid_payload():
    module = load_module()

    result = module.execute_exam_command("run", "", "", None, None)

    body = json.loads(result["body"])
    assert body["status"] == "ERROR"
    assert "Invalid exam command payload" in body["message"]


def test_lambda_handler_routes_through_context_step():
    module = load_module()
    context = StubContext()
    event = {
        "action": "records",
        "email": "student@example.com",
        "exam_code": "EXAM-001",
        "game": "game02",
        "task_id": "087_task",
    }

    with patch.object(module, "records_exam_command_step", return_value={"statusCode": 200}) as mock_step:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once_with(
        "student@example.com",
        "EXAM-001",
        "game02",
        "087_task",
    )
    assert context.calls == [{"statusCode": 200}]
    assert result == {"wrapped": {"statusCode": 200}}


def test_lambda_handler_routes_mutations_through_guarded_step():
    module = load_module()
    context = StubContext()
    event = {
        "action": "run",
        "email": "student@example.com",
        "exam_code": "EXAM-001",
        "game": "game02",
        "task_id": "087_task",
        "execution_id": "execution-1",
    }

    with patch.object(module, "guarded_exam_command_step", return_value={"statusCode": 200}) as mock_step:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once_with("run", "student@example.com", "EXAM-001", "game02", "087_task", "execution-1")
    assert result == {"wrapped": {"statusCode": 200}}


def test_invalid_action_cannot_release_an_unrelated_execution_guard():
    module = load_module()
    context = StubContext()
    event = {
        "action": "unknown",
        "email": "student@example.com",
        "exam_code": "EXAM-001",
        "game": "game02",
        "task_id": "087_task",
        "execution_guard_key": "exam#student@example.com#EXAM-001#game02#087_task#run",
    }

    with patch.object(module.execution_guard_repo, "release", return_value=True) as mock_release:
        result = module.lambda_handler(event, context)

    mock_release.assert_not_called()
    body = json.loads(result["body"])
    assert body["status"] == "ERROR"


def test_handle_exam_records_broadcasts_only_with_scope():
    module = load_module()
    exam_service = module.get_exam_service()

    with patch.object(exam_service, "list_records", return_value=[{"task_id": "087_task", "phase": "check", "test_result": "OK"}]) as mock_list_records, \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_records("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "OK"
    assert body["records"] == [{"task_id": "087_task", "phase": "check", "test_result": "OK"}]
    mock_list_records.assert_called_once_with("student@example.com", "EXAM-001", task_id="087_task")
    mock_broadcast.assert_called_once()


@pytest.fixture
def lifecycle_exam(monkeypatch, dynamodb_tables):
    from common.database import TaskStateRepository
    from common.models.phase_config import PhaseConfig
    from common.models.task_manifest import TaskManifest
    from common.services.exam_service import ExamService
    from common.services.task_service import TaskService
    from common.status import TestResult

    module = load_module()
    phases = [
        PhaseConfig(
            id=name, name=name.title(), description=name, test_file=f"{name}.py",
            auto_run=name == "cleanup", required=name != "cleanup",
            count_attempts=name in ("ready", "challenge", "check"),
            points=100 if name == "check" else 0,
        )
        for name in ("setup", "ready", "answer", "challenge", "check", "cleanup")
    ]
    manifest = TaskManifest(
        task_id="task_a", title="Question", description="Solve {{ namespace }}",
        difficulty="beginner", estimated_minutes=5, phases=phases,
        prerequisites=[], tags=[], hints=[],
    )
    repository = TaskStateRepository()
    calls = []
    resources = set()
    failures = {}

    def run_phase(game, task, phase, session):
        assert module.execution_guard_repo.get_active("student", game)
        assert module.execution_guard_repo.get_environment("student", game)["task_id"] == task
        calls.append((task, phase.id))
        if failures.get(phase.id, 0):
            failures[phase.id] -= 1
            return TestResult.TESTS_FAILED, f"{phase.id}-failed"
        if phase.id == "setup":
            resources.add(task)
        elif phase.id == "cleanup":
            resources.discard(task)
        assert phase.id != "answer"
        return TestResult.OK, f"{phase.id}-report"

    service = TaskService(task_repo=repository, test_runner=SimpleNamespace(run_phase=run_phase))
    exam = ExamService(task_repo=repository, task_service=service)
    monkeypatch.setattr(exam, "authorize", lambda *args: (True, "", {}))
    monkeypatch.setattr(module, "get_exam_service", lambda: exam)
    monkeypatch.setattr(module, "get_task_service", lambda: service)
    monkeypatch.setattr(module.TaskManifest, "load", lambda *args: manifest)
    monkeypatch.setattr("common.services.task_service.generate_session", lambda email, game, task: {"namespace": task})
    monkeypatch.setattr(module, "get_user_data", lambda email: {"endpoint": "https://example"})
    monkeypatch.setattr(module, "extract_k8s_access_config", lambda user: {
        "endpoint": "https://example", "kubeconfig": "apiVersion: v1",
    })
    monkeypatch.setattr(module, "clear_tmp_directory", lambda: None)
    monkeypatch.setattr(module, "write_k8s_access_files", lambda config: None)
    monkeypatch.setattr(module, "with_exam_overview", lambda response, *args: response)
    monkeypatch.setattr(module, "broadcast_exam_response", lambda *args: None)
    monkeypatch.setattr(module, "broadcast_exam_update", lambda *args: None)
    monkeypatch.setattr(module, "save_exam_test_record", lambda *args: None)
    monkeypatch.setattr(module.task_phase_estimate_service, "get_estimate_payload", lambda *args, **kwargs: {})

    def command(action, task="task_a"):
        response = module.execution_guard_repo.execute(
            action, "student", "EXAM-001", "game02", task,
            lambda: module.execute_exam_command(action, "student", "EXAM-001", "game02", task),
        )
        return json.loads(response["body"])

    return SimpleNamespace(
        module=module, command=command, calls=calls, resources=resources,
        failures=failures, repository=repository, manifest=manifest,
    )


def test_preparation_owns_environment_during_student_work_and_reset_retries_cleanup(lifecycle_exam):
    exam = lifecycle_exam
    started = exam.command("start")
    assert started["status"] == "OK"
    assert started["lifecycle"]["stage"] == "working"
    assert started["current_phase"] == "challenge"
    assert exam.calls == [("task_a", "setup"), ("task_a", "ready")]
    assert exam.resources == {"task_a"}
    assert started["active_execution"] is None
    assert started["active_environment"]["task_id"] == "task_a"

    rejected = exam.command("start", "task_b")
    assert rejected["status"] == "ERROR"
    assert rejected["active_environment"]["task_id"] == "task_a"
    assert exam.resources == {"task_a"}
    exam.failures["cleanup"] = 1
    failed = exam.command("reset")
    assert failed["cleanup_failed"]
    assert failed["lifecycle"]["stage"] == "cleanup"
    assert failed["active_environment"]["task_id"] == "task_a"
    assert exam.repository.get("student", "game02", "task_a") is not None
    assert exam.command("run")["status"] == "RESET"
    assert exam.resources == set()
    assert exam.repository.get("student", "game02", "task_a") is None
    assert exam.command("start", "task_b")["lifecycle"]["stage"] == "working"


def test_assessment_is_paired_and_cleanup_retry_does_not_repeat_or_reaward_grading(lifecycle_exam):
    exam = lifecycle_exam
    exam.command("start")
    exam.failures.update(check=1, cleanup=1)
    failed = exam.command("run")
    assert failed["status"] == "FAILED"
    assert failed["current_phase"] == "check"
    assert failed["attempts"] == 1
    assert failed["lifecycle"]["stage"] == "working"
    assert [phase["phase_id"] for phase in failed["executed_phases"]] == ["challenge", "check"]
    cleaning = exam.command("run")
    assert cleaning["cleanup_failed"]
    assert cleaning["active_environment"]["task_id"] == "task_a"
    assert exam.repository.get("student", "game02", "task_a").total_points == 100
    completed = exam.command("run")
    assert completed["status"] == "COMPLETED"
    assert completed["total_points"] == 100
    assert completed["active_environment"] is None
    assert [phase for _, phase in exam.calls] == [
        "setup", "ready", "challenge", "check", "challenge", "check", "cleanup", "cleanup",
    ]
    assert exam.resources == set()


def test_ready_retry_stops_for_student_work_and_exhaustion_cleans_before_abandoning(lifecycle_exam):
    exam = lifecycle_exam
    exam.failures["ready"] = 1
    failed = exam.command("start")
    assert failed["current_phase"] == "ready"
    assert failed["lifecycle"]["stage"] == "preparation"
    assert exam.command("run")["lifecycle"]["stage"] == "working"
    exam.manifest.get_phase("check").max_attempts = 1
    exam.failures.update(check=1, cleanup=1)
    failed_cleanup = exam.command("run")
    assert failed_cleanup["cleanup_failed"]
    assert failed_cleanup["active_environment"]["task_id"] == "task_a"
    abandoned = exam.command("run")
    assert abandoned["status"] == "ABANDONED"
    assert abandoned["active_environment"] is None
    assert "Maximum attempts" in abandoned["reason"]
    assert exam.resources == set()


def test_optional_rule_phases_do_not_require_extra_student_actions(lifecycle_exam):
    exam = lifecycle_exam
    exam.manifest.phases = [exam.manifest.get_phase("check")]
    started = exam.command("start")
    assert started["lifecycle"]["stage"] == "working"
    assert exam.calls == []
    assert exam.command("run")["status"] == "COMPLETED"
    assert exam.calls == [("task_a", "check")]


def test_reset_can_release_a_reservation_if_start_failed_before_state_creation(lifecycle_exam):
    exam = lifecycle_exam
    assert exam.module.execution_guard_repo.claim_environment("student", "game02", "EXAM-001", "task_a")
    reset = exam.command("reset")
    assert reset["status"] == "RESET"
    assert reset["active_environment"] is None
    assert exam.calls == []


def test_reset_state_deletion_failure_keeps_environment_reserved(lifecycle_exam, monkeypatch):
    exam = lifecycle_exam
    exam.command("start")
    monkeypatch.setattr(exam.repository, "delete", lambda *args: False)
    failed = exam.command("reset")
    assert failed["status"] == "ERROR"
    assert failed["active_environment"]["task_id"] == "task_a"
    assert exam.command("start", "task_b")["status"] == "ERROR"


def test_guarded_command_releases_before_terminal_broadcast(dynamodb_tables):
    module = load_module()
    guard = module.execution_guard_repo
    guard._table = dynamodb_tables["ws_execution_guard_table"]
    lease = guard.acquire("student@example.com", "game02", "EXAM-001", "087_task", "run")

    def execute(*args):
        assert guard.get_active("student@example.com", "game02")
        return {"statusCode": 200, "body": '{"status":"OK"}'}

    def broadcast(*args):
        assert guard.get_active("student@example.com", "game02") is None
        assert json.loads(args[-1]["body"])["command_finished"] is True

    with patch.object(module, "execute_exam_command", side_effect=execute), \
         patch.object(module, "broadcast_exam_response", side_effect=broadcast) as mock_broadcast:
        module.guarded_exam_command_step(
            None, "run", "student@example.com", "EXAM-001", "game02", "087_task", lease["execution_id"]
        )
    mock_broadcast.assert_called_once()


def test_status_sync_reports_the_lease_and_echoes_the_browser_request_id(dynamodb_tables):
    module = load_module()
    guard = module.execution_guard_repo
    guard._table = dynamodb_tables["ws_execution_guard_table"]
    lease = guard.acquire("student", "game02", "EXAM-001", "task_a", "run")
    guard.set_phase(lease, "cleanup")
    with patch.object(module, "get_exam_service") as service, \
         patch.object(module, "broadcast_exam_response") as broadcast:
        response = module.synchronized_exam_status_step(None, "student", "EXAM-001", "game02", "task_b", "browser-1")
    payload = json.loads(response["body"])
    assert payload["status_request_id"] == "browser-1"
    assert payload["active_execution"]["phase"] == "cleanup"
    service.assert_not_called()
    broadcast.assert_called_once()


def test_exam_cleanup_keeps_the_lease_until_resources_are_removed(dynamodb_tables):
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    guard = module.execution_guard_repo
    guard._table = dynamodb_tables["ws_execution_guard_table"]
    manifest = FakeManifest([
        FakePhase("check", "Check", "Check solution"),
        FakePhase("cleanup", "Cleanup", "Remove resources", auto_run=True, required=False),
    ])
    state = TaskState(
        email="student", game="game02", task_id="task_a", npc="exam",
        status=TaskStatus.IN_PROGRESS, current_phase_id=None, mode="exam",
    )
    state.get_or_create_phase_state("check").mark_passed("", 100)

    def cleanup(*args):
        assert guard.get_active("student", "game02")["phase"] == "cleanup"
        assert guard.acquire("student", "game02", "EXAM-001", "task_b", "run") is None
        assert state.status == TaskStatus.IN_PROGRESS
        return module.TestResult.OK, "cleanup-report"

    service = SimpleNamespace(test_runner=SimpleNamespace(run_phase=cleanup))
    exam_service = SimpleNamespace(task_repo=SimpleNamespace(save=lambda value: None))
    with patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_task_service", return_value=service), \
         patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "broadcast_exam_update"):
        response = guard.execute(
            "run", "student", "EXAM-001", "game02", "task_a",
            lambda: module.task_completed_response(module.finish_exam_task("student", "EXAM-001", "game02", "task_a", state), ""),
        )
    assert json.loads(response["body"])["status"] == "COMPLETED"
    assert guard.get_active("student", "game02") is None


@pytest.mark.parametrize("reason", ["", "Maximum attempts reached"])
def test_exam_cleanup_failure_is_retryable_and_does_not_finish_the_task(reason):
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    manifest = FakeManifest([
        FakePhase("check", "Check", "Check solution"),
        FakePhase("cleanup", "Cleanup", "Remove resources", auto_run=True, required=False),
    ])
    state = TaskState(
        email="student", game="game02", task_id="task_a", npc="exam",
        status=TaskStatus.IN_PROGRESS, current_phase_id=None, mode="exam",
    )
    state.get_or_create_phase_state("check").mark_passed("", 100)
    runner_results = [(module.TestResult.TESTS_FAILED, "failed-report"), (module.TestResult.OK, "cleanup-report")]
    service = SimpleNamespace(test_runner=SimpleNamespace(run_phase=lambda *args: runner_results.pop(0)))
    saved = []
    exam_service = SimpleNamespace(task_repo=SimpleNamespace(save=lambda value: saved.append(value.status)))
    with patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_task_service", return_value=service), \
         patch.object(module, "get_exam_service", return_value=exam_service):
        failed = module.finish_exam_task("student", "EXAM-001", "game02", "task_a", state, reason)
        assert failed["cleanup_failed"] is True
        assert state.status == TaskStatus.IN_PROGRESS
        assert state.current_phase_id == "cleanup"
        payload = json.loads(module.task_completed_response(failed, "")["body"])
        assert payload["status"] == "FAILED"
        assert payload["cleanup_failed"] is True

        finished = module.finish_exam_task("student", "EXAM-001", "game02", "task_a", state)
    assert not runner_results
    assert state.status == (TaskStatus.ABANDONED if reason else TaskStatus.COMPLETED)
    assert state.get_phase_state("cleanup").status.value == "passed"
    assert finished["reason"] == reason
    assert saved[0] == TaskStatus.IN_PROGRESS


def test_execute_exam_command_surfaces_unhandled_action_errors():
    module = load_module()

    with patch.object(module, "handle_exam_run", side_effect=RuntimeError("boom")), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        result = module.execute_exam_command(
            "run",
            "student@example.com",
            "EXAM-001",
            "game02",
            "087_task",
        )

    body = json.loads(result["body"])
    assert body["status"] == "ERROR"
    assert "Exam action 'run' failed: boom" in body["message"]
    mock_broadcast.assert_called_once()


def test_module_resets_log_record_factory():
    original_factory = logging.getLogRecordFactory()

    class FakeLogRecord(logging.LogRecord):
        pass

    logging.setLogRecordFactory(FakeLogRecord)
    try:
        module = load_module()
        assert module.logging.getLogRecordFactory() is logging.LogRecord
    finally:
        logging.setLogRecordFactory(original_factory)


def test_phase_failed_response_uses_updated_result_state():
    module = load_module()

    stale_state = SimpleNamespace(
        current_phase_id="check",
        session_data={},
        get_phase_state=lambda phase_id: None,
    )
    updated_phase_state = SimpleNamespace(attempts=1)
    updated_state = SimpleNamespace(
        current_phase_id="check",
        session_data={},
        get_phase_state=lambda phase_id: updated_phase_state,
    )
    current_phase = SimpleNamespace(description="Check the pod", name="Check", max_attempts=3)
    manifest = SimpleNamespace(get_phase=lambda phase_id: current_phase, description="Task description")

    response = module.phase_failed_response(
        {
            "state": updated_state,
            "test_result": module.TestResult.TIME_OUT,
            "report_url": "",
        },
        stale_state,
        manifest,
    )

    body = json.loads(response["body"])
    assert body["attempts"] == 1
    assert body["current_phase"] == "check"
    assert body["test_result"] == "TIME_OUT"


def test_task_started_response_includes_exact_estimates_when_present():
    module = load_module()
    state = SimpleNamespace(
        game="game02",
        task_id="087_task",
        current_phase_id="challenge",
        session_data={},
    )
    manifest = SimpleNamespace(
        description="Task description",
        get_phase=lambda phase_id: SimpleNamespace(name="Challenge", description="Do it"),
    )

    with patch.object(module.task_phase_estimate_service, "get_estimate_payload", return_value={
        "estimated_phase_seconds": 45.0,
        "estimated_remaining_task_seconds": 90.0,
        "estimated_task_seconds": 120.0,
    }):
        response = module.task_started_response(state, manifest)

    body = json.loads(response["body"])
    assert body["estimated_phase_seconds"] == 45.0
    assert body["estimated_remaining_task_seconds"] == 90.0
    assert body["estimated_task_seconds"] == 120.0


class FakePhase:
    def __init__(self, phase_id, name, description, *, required=True, auto_run=False, count_attempts=False, max_attempts=3, points=0):
        self.id = phase_id
        self.name = name
        self.description = description
        self.required = required
        self.auto_run = auto_run
        self.count_attempts = count_attempts
        self.max_attempts = max_attempts
        self.points = points


class FakeManifest:
    def __init__(self, phases):
        self.phases = phases
        self.description = "Task description"

    def get_phase(self, phase_id):
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        return None

    def get_next_phase(self, phase_id):
        if not phase_id:
            return None
        ids = [phase.id for phase in self.phases]
        index = ids.index(phase_id)
        for phase in self.phases[index + 1:]:
            if not phase.auto_run:
                return phase
        return None


def test_handle_exam_run_auto_chains_setup_to_ready():
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    manifest = FakeManifest(
        [
            FakePhase("setup", "Setup", "Prepare cluster"),
            FakePhase("ready", "Ready", "Validate baseline", count_attempts=True),
            FakePhase("challenge", "Challenge", "Solve the task"),
            FakePhase("check", "Check", "Verify solution", count_attempts=True, points=100),
            FakePhase("cleanup", "Cleanup", "Cleanup resources", auto_run=True, required=False),
        ]
    )
    state = TaskState(
        email="student@example.com",
        game="game02",
        task_id="087_task",
        npc="npc01",
        status=TaskStatus.IN_PROGRESS,
        current_phase_id="setup",
        mode="exam",
        session_data={},
    )
    exam_service = SimpleNamespace(
        authorize=lambda *args, **kwargs: (True, "", {}),
        task_repo=SimpleNamespace(get=lambda *args, **kwargs: state, save=lambda s: True),
    )
    mock_task_service = SimpleNamespace(complete_task=lambda *args, **kwargs: {"state": state})
    run_results = [
        {"success": True, "state": state, "manifest": manifest, "test_result": module.TestResult.OK, "report_url": ""},
        {"success": True, "state": state, "manifest": manifest, "test_result": module.TestResult.OK, "report_url": ""},
    ]

    def run_phase(*args, **kwargs):
        current_phase = state.current_phase_id
        phase_state = state.get_or_create_phase_state(current_phase)
        phase_state.mark_passed("", 0)
        if current_phase == "setup":
            state.current_phase_id = "ready"
        elif current_phase == "ready":
            state.current_phase_id = "challenge"
        return run_results.pop(0)

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "get_task_service", return_value=mock_task_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module, "save_exam_test_record") as mock_save_record, \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "OK"
    assert body["current_phase"] == "challenge"
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["setup", "ready"]
    assert "Setup passed." in body["message"]
    assert "Ready passed." in body["message"]
    assert mock_save_record.call_count == 2
    mock_broadcast.assert_called_once()


def test_handle_exam_run_reports_ready_failure_after_setup_pass():
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    manifest = FakeManifest(
        [
            FakePhase("setup", "Setup", "Prepare cluster"),
            FakePhase("ready", "Ready", "Validate baseline", count_attempts=True),
            FakePhase("challenge", "Challenge", "Solve the task"),
            FakePhase("cleanup", "Cleanup", "Cleanup resources", auto_run=True, required=False),
        ]
    )
    state = TaskState(
        email="student@example.com",
        game="game02",
        task_id="087_task",
        npc="npc01",
        status=TaskStatus.IN_PROGRESS,
        current_phase_id="setup",
        mode="exam",
        session_data={},
    )
    exam_service = SimpleNamespace(
        authorize=lambda *args, **kwargs: (True, "", {}),
        task_repo=SimpleNamespace(get=lambda *args, **kwargs: state, save=lambda s: True),
    )
    mock_task_service = SimpleNamespace()

    def run_phase(*args, **kwargs):
        current_phase = state.current_phase_id
        phase_state = state.get_or_create_phase_state(current_phase)
        if current_phase == "setup":
            phase_state.mark_passed("", 0)
            state.current_phase_id = "ready"
            return {"success": True, "state": state, "manifest": manifest, "test_result": module.TestResult.OK, "report_url": ""}
        phase_state.mark_failed(module.TestResult.TESTS_FAILED.name, "", count_attempts=True)
        state.current_phase_id = "ready"
        return {"success": False, "state": state, "manifest": manifest, "test_result": module.TestResult.TESTS_FAILED, "report_url": ""}

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "get_task_service", return_value=mock_task_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module, "save_exam_test_record"), \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response"):
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "FAILED"
    assert body["current_phase"] == "ready"
    assert body["attempts"] == 1
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["setup", "ready"]
    assert "Setup passed." in body["message"]
    assert "Ready failed (TESTS_FAILED)." in body["message"]


def test_handle_exam_run_skips_answer_and_runs_challenge_first():
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    manifest = FakeManifest(
        [
            FakePhase("setup", "Setup", "Prepare cluster"),
            FakePhase("ready", "Ready", "Validate baseline", count_attempts=True),
            FakePhase("answer", "Answer", "Student works on the task"),
            FakePhase("challenge", "Challenge", "Solve the task"),
            FakePhase("check", "Check", "Verify solution", count_attempts=True, points=100),
            FakePhase("cleanup", "Cleanup", "Cleanup resources", auto_run=True, required=False),
        ]
    )
    state = TaskState(
        email="student@example.com",
        game="game02",
        task_id="087_task",
        npc="npc01",
        status=TaskStatus.IN_PROGRESS,
        current_phase_id="answer",
        mode="exam",
        session_data={},
    )
    exam_service = SimpleNamespace(
        authorize=lambda *args, **kwargs: (True, "", {}),
        task_repo=SimpleNamespace(get=lambda *args, **kwargs: state, save=lambda s: True),
    )
    mock_task_service = SimpleNamespace()

    def run_phase(*args, **kwargs):
        phase_id = state.current_phase_id
        assert phase_id in ("challenge", "check")
        phase_state = state.get_or_create_phase_state(phase_id)
        if phase_id == "challenge":
            phase_state.mark_passed("", 0)
            state.current_phase_id = "check"
        else:
            phase_state.mark_failed("TESTS_FAILED", "")
        return {
            "success": phase_id == "challenge",
            "state": state,
            "manifest": manifest,
            "test_result": module.TestResult.OK if phase_id == "challenge" else module.TestResult.TESTS_FAILED,
            "report_url": "",
        }

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "get_task_service", return_value=mock_task_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module, "save_exam_test_record") as mock_save_record, \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "FAILED"
    assert body["current_phase"] == "check"
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["challenge", "check"]
    assert "Answer skipped." not in body["message"]
    assert mock_save_record.call_count == 2
    assert mock_save_record.call_args_list[0].args[4] == "challenge"
    assert state.phase_states["answer"].points_earned == 0
    mock_broadcast.assert_called_once()


def test_handle_exam_run_redirects_stale_check_back_to_challenge():
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    manifest = FakeManifest(
        [
            FakePhase("setup", "Setup", "Prepare cluster"),
            FakePhase("answer", "Answer", "Student works on the task"),
            FakePhase("challenge", "Challenge", "Solve the task"),
            FakePhase("check", "Check", "Verify solution", count_attempts=True, points=100),
        ]
    )
    state = TaskState(
        email="student@example.com",
        game="game02",
        task_id="087_task",
        npc="npc01",
        status=TaskStatus.IN_PROGRESS,
        current_phase_id="check",
        mode="exam",
        session_data={},
    )
    state.get_or_create_phase_state("setup").mark_passed("", 0)
    state.get_or_create_phase_state("answer").mark_passed("", 0)
    exam_service = SimpleNamespace(
        authorize=lambda *args, **kwargs: (True, "", {}),
        task_repo=SimpleNamespace(get=lambda *args, **kwargs: state, save=lambda s: True),
    )

    def run_phase(*args, **kwargs):
        phase_id = state.current_phase_id
        assert phase_id in ("challenge", "check")
        phase_state = state.get_or_create_phase_state(phase_id)
        if phase_id == "challenge":
            phase_state.mark_passed("", 0)
            state.current_phase_id = "check"
        else:
            phase_state.mark_failed("TESTS_FAILED", "")
        return {
            "success": phase_id == "challenge",
            "state": state,
            "manifest": manifest,
            "test_result": module.TestResult.OK if phase_id == "challenge" else module.TestResult.TESTS_FAILED,
            "report_url": "",
        }

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module, "save_exam_test_record"), \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response"):
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "FAILED"
    assert body["current_phase"] == "check"
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["challenge", "check"]


def test_handle_exam_reset_deletes_state_and_requires_start():
    module = load_module()
    from common.models.task_state import TaskState, TaskStatus

    state = TaskState(
        email="student@example.com",
        game="game02",
        task_id="087_task",
        npc="exam",
        status=TaskStatus.IN_PROGRESS,
        current_phase_id="check",
        mode="exam",
        session_data={},
        total_points=5,
    )
    deleted = []
    exam_service = SimpleNamespace(
        authorize=lambda *args, **kwargs: (True, "", {}),
        task_repo=SimpleNamespace(
            get=lambda *args, **kwargs: state,
            save=lambda state: True,
            delete=lambda *args, **kwargs: (deleted.append(args), True)[1],
        ),
        get_exam_overview=lambda *args, **kwargs: {"task_summaries": [], "finished_tasks": [], "remaining_tasks": ["087_task"], "exam_score": 0},
        exam_session_repo=SimpleNamespace(get=lambda *args, **kwargs: {"allowedTasks": ["087_task"]}),
    )

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "get_user_data", return_value={}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://example", "kubeconfig": "apiVersion: v1"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=FakeManifest([])), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_reset("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "RESET"
    assert "after cleanup" in body["message"]
    assert body["total_points"] == 0
    assert body["exam_score"] == 0
    assert deleted == [("student@example.com", "game02", "087_task")]
    mock_broadcast.assert_called_once()
