"""Tests for the durable exam command handler."""
import importlib.util
import json
import logging
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch


MODULE_NAME = "exam_durable_app"
HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "exam-durable-handler", "app.py")


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


def test_lambda_handler_releases_execution_guard():
    module = load_module()
    context = StubContext()
    event = {
        "action": "run",
        "email": "student@example.com",
        "exam_code": "EXAM-001",
        "game": "game02",
        "task_id": "087_task",
        "execution_guard_key": "exam#student@example.com#EXAM-001#game02#087_task#run",
    }

    with patch.object(module, "run_exam_command_step", return_value={"statusCode": 200}) as mock_step, \
         patch.object(module.execution_guard_repo, "release", return_value=True) as mock_release:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once_with("student@example.com", "EXAM-001", "game02", "087_task")
    mock_release.assert_called_once_with("exam#student@example.com#EXAM-001#game02#087_task#run")
    assert result == {"wrapped": {"statusCode": 200}}


def test_lambda_handler_releases_execution_guard_on_invalid_action():
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

    mock_release.assert_called_once_with("exam#student@example.com#EXAM-001#game02#087_task#run")
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
         patch.object(module, "extract_k8s_credentials", return_value=("cert", "key", "https://example")), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_user_files"), \
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
         patch.object(module, "extract_k8s_credentials", return_value=("cert", "key", "https://example")), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_user_files"), \
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
        assert state.current_phase_id == "challenge"
        phase_state = state.get_or_create_phase_state("challenge")
        phase_state.mark_passed("", 0)
        state.current_phase_id = "check"
        return {
            "success": True,
            "state": state,
            "manifest": manifest,
            "test_result": module.TestResult.OK,
            "report_url": "",
        }

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "get_task_service", return_value=mock_task_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_credentials", return_value=("cert", "key", "https://example")), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_user_files"), \
         patch.object(module, "save_exam_test_record") as mock_save_record, \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "OK"
    assert body["current_phase"] == "check"
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["challenge"]
    assert "Answer skipped." not in body["message"]
    assert mock_save_record.call_count == 1
    assert mock_save_record.call_args.args[4] == "challenge"
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
        assert state.current_phase_id == "challenge"
        phase_state = state.get_or_create_phase_state("challenge")
        phase_state.mark_passed("", 0)
        state.current_phase_id = "check"
        return {
            "success": True,
            "state": state,
            "manifest": manifest,
            "test_result": module.TestResult.OK,
            "report_url": "",
        }

    exam_service.run_phase = run_phase

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "get_user_data", return_value={"endpoint": "https://example", "client_certificate": "cert", "client_key": "key"}), \
         patch.object(module, "extract_k8s_credentials", return_value=("cert", "key", "https://example")), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_user_files"), \
         patch.object(module, "save_exam_test_record"), \
         patch.object(module, "with_exam_overview", side_effect=lambda response, *_args: response), \
         patch.object(module, "broadcast_exam_response"):
        response = module.handle_exam_run("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "OK"
    assert body["current_phase"] == "check"
    assert [phase["phase_id"] for phase in body["executed_phases"]] == ["challenge"]


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
            delete=lambda *args, **kwargs: deleted.append(args),
        ),
        get_exam_overview=lambda *args, **kwargs: {"task_summaries": [], "finished_tasks": [], "remaining_tasks": ["087_task"], "exam_score": 0},
        exam_session_repo=SimpleNamespace(get=lambda *args, **kwargs: {"allowedTasks": ["087_task"]}),
    )

    with patch.object(module, "get_exam_service", return_value=exam_service), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_reset("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "RESET"
    assert body["message"] == "Task reset. Click Start to begin again. Attempt history remains in Records."
    assert body["total_points"] == 0
    assert body["exam_score"] == 0
    assert deleted == [("student@example.com", "game02", "087_task")]
    mock_broadcast.assert_called_once()
