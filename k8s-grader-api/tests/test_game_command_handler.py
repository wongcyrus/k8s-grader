"""Tests for the durable game command handler."""
import importlib.util
import os
import sys
import types
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from common.models.task_state import TaskStatus


MODULE_NAME = "game_command_app"
HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "game-command-handler", "app.py")


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
        return value


class FakeManifest:
    def __init__(self):
        self.description = "Solve {{ target }}"
        self.phases = {
            "setup": SimpleNamespace(id="setup", name="Setup", description="Set up {{ target }}", max_attempts=3),
            "answer": SimpleNamespace(id="answer", name="Answer", description="Answer {{ target }}", max_attempts=3),
            "challenge": SimpleNamespace(id="challenge", name="Challenge", description="Solve {{ target }}", max_attempts=3),
            "check": SimpleNamespace(id="check", name="Check", description="Check {{ target }}", max_attempts=3),
        }

    def get_phase(self, phase_id):
        return self.phases.get(phase_id)

    def get_next_phase(self, phase_id):
        if phase_id == "setup":
            return self.phases["answer"]
        if phase_id == "answer":
            return self.phases["challenge"]
        if phase_id == "challenge":
            return self.phases["check"]
        return None

    def get_first_phase(self):
        return self.phases["setup"]


class FakeDoomManifest:
    def __init__(self):
        self.description = "Solve {{ target }}"
        self.phases = {
            "setup": SimpleNamespace(id="setup", name="Setup", description="Set up {{ target }}", max_attempts=3),
            "ready": SimpleNamespace(id="ready", name="Ready", description="Ready {{ target }}", max_attempts=3),
            "answer": SimpleNamespace(id="answer", name="Answer", description="Answer {{ target }}", max_attempts=3),
            "challenge": SimpleNamespace(id="challenge", name="Challenge", description="Solve {{ target }}", max_attempts=3),
            "check": SimpleNamespace(id="check", name="Check", description="Check {{ target }}", max_attempts=3),
        }

    def get_phase(self, phase_id):
        return self.phases.get(phase_id)

    def get_next_phase(self, phase_id):
        if phase_id == "setup":
            return self.phases["ready"]
        if phase_id == "ready":
            return self.phases["answer"]
        if phase_id == "answer":
            return self.phases["challenge"]
        if phase_id == "challenge":
            return self.phases["check"]
        return None

    def get_first_phase(self):
        return self.phases["setup"]


class FakeSimpleDoomManifest:
    def __init__(self):
        self.description = "Solve {{ target }}"
        self.phases = {
            "setup": SimpleNamespace(id="setup", name="Setup", description="Set up {{ target }}", max_attempts=3),
            "answer": SimpleNamespace(id="answer", name="Answer", description="Answer {{ target }}", max_attempts=3),
            "check": SimpleNamespace(id="check", name="Check", description="Check {{ target }}", max_attempts=3),
        }

    def get_phase(self, phase_id):
        return self.phases.get(phase_id)

    def get_next_phase(self, phase_id):
        if phase_id == "setup":
            return self.phases["answer"]
        if phase_id == "answer":
            return self.phases["check"]
        return None

    def get_first_phase(self):
        return self.phases["setup"]


def _state(task_id: str, current_phase: str | None, total_points: int = 0):
    state = Mock()
    state.task_id = task_id
    state.current_phase_id = current_phase
    state.total_points = total_points
    state.session_data = {"target": "namespace"}
    state.status = TaskStatus.IN_PROGRESS
    state.calculate_progress.return_value = 0.0 if current_phase == "setup" else 0.5 if current_phase == "check" else 1.0
    failed_phase = Mock()
    failed_phase.attempts = 1
    failed_phase.report_url = "https://report.example"
    state.get_phase_state.return_value = failed_phase
    return state


def test_execute_game_command_dispatches_status():
    module = load_module()

    with patch.object(module, "_build_game_status_payload", return_value={"status": "NOT_STARTED"}) as mock_status:
        result = module.execute_game_command("status", "student@example.com", "game01", "", "https://example", "conn-1")

    mock_status.assert_called_once_with("student@example.com", "game01")
    assert result == {"status": "NOT_STARTED"}


def test_lambda_handler_routes_through_context_and_broadcasts():
    module = load_module()
    context = StubContext()
    event = {
        "action": "status",
        "email": "student@example.com",
        "game": "game01",
        "connection_id": "conn-1",
        "connection_endpoint": "https://example.execute-api.us-east-1.amazonaws.com/Prod",
    }

    with patch.object(module, "execute_game_command_step", return_value={"status": "NOT_STARTED"}) as mock_step, \
         patch.object(module, "_push_game_update") as mock_push:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once_with(
        "status",
        "student@example.com",
        "game01",
        "",
        "https://example.execute-api.us-east-1.amazonaws.com/Prod",
        "conn-1",
    )
    assert context.calls == [{"status": "NOT_STARTED"}]
    mock_push.assert_called_once_with(
        "https://example.execute-api.us-east-1.amazonaws.com/Prod",
        "conn-1",
        "status",
        {"status": "NOT_STARTED"},
    )
    assert result["statusCode"] == 200


def test_lambda_handler_releases_execution_guard():
    module = load_module()
    context = StubContext()
    event = {
        "action": "talk",
        "email": "student@example.com",
        "game": "game01",
        "npc": "Aiden",
        "connection_id": "conn-1",
        "connection_endpoint": "https://example.execute-api.us-east-1.amazonaws.com/Prod",
        "execution_guard_key": "game#student@example.com#game01#talk",
    }

    with patch.object(module, "execute_game_command_step", return_value={"status": "OK"}) as mock_step, \
         patch.object(module, "_push_game_update") as mock_push, \
         patch.object(module.execution_guard_repo, "release", return_value=True) as mock_release:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once()
    mock_push.assert_called_once()
    mock_release.assert_called_once_with("game#student@example.com#game01#talk")
    assert result["statusCode"] == 200


def test_lambda_handler_releases_execution_guard_on_exception():
    module = load_module()
    context = StubContext()
    event = {
        "action": "talk",
        "email": "student@example.com",
        "game": "game01",
        "npc": "Aiden",
        "connection_id": "conn-1",
        "connection_endpoint": "https://example.execute-api.us-east-1.amazonaws.com/Prod",
        "execution_guard_key": "game#student@example.com#game01#talk",
    }

    with patch.object(module, "execute_game_command_step", side_effect=RuntimeError("boom")), \
         patch.object(module, "_push_game_update") as mock_push, \
         patch.object(module.execution_guard_repo, "release", return_value=True) as mock_release:
        result = module.lambda_handler(event, context)

    mock_release.assert_called_once_with("game#student@example.com#game01#talk")
    pushed_payload = mock_push.call_args.args[3]
    assert pushed_payload == {"status": "ERROR", "message": "boom"}
    assert result["statusCode"] == 200


def test_send_ws_message_serializes_decimal_payloads():
    module = load_module()
    client = Mock()

    with patch.object(module.boto3, "client", return_value=client):
        module._send_ws_message(
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
            {"status": "RUNNING", "progress": Decimal("0.5"), "total_points": Decimal("2")},
        )

    sent_bytes = client.post_to_connection.call_args.kwargs["Data"]
    assert b'"progress": 0.5' in sent_bytes
    assert b'"total_points": 2' in sent_bytes


def test_status_action_returns_completed_when_all_tasks_finished():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service:
        mock_task_service.get_total_score.return_value = 12
        mock_task_service.get_completed_tasks.return_value = ["01_task", "02_task"]
        mock_task_service.get_skipped_tasks.return_value = ["03_task"]
        mock_task_service.get_current_task.return_value = None
        payload = module._build_game_status_payload("student@example.com", "game01")

    mock_task_service.get_total_score.assert_called_once_with("student@example.com", "game01", mode="exercise")
    mock_task_service.get_completed_tasks.assert_called_once_with("student@example.com", "game01", mode="exercise")
    mock_task_service.get_skipped_tasks.assert_called_once_with("student@example.com", "game01", mode="exercise")
    mock_task_service.get_current_task.assert_called_once_with("student@example.com", "game01", mode="exercise")
    assert payload["status"] == "COMPLETED"
    assert payload["progress"] == 1.0
    assert payload["total_score"] == 12
    assert payload["completed_tasks"] == ["01_task", "02_task"]
    assert payload["skipped_tasks"] == ["03_task"]


def test_status_action_renders_not_started_manifest_with_generated_session():
    module = load_module()
    manifest = FakeManifest()
    manifest.description = "Create namespace {{ namespace }}"

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "generate_session", return_value={"namespace": "student-ns"}):
        mock_task_service.get_total_score.return_value = 0
        mock_task_service.get_completed_tasks.return_value = []
        mock_task_service.get_skipped_tasks.return_value = []
        mock_task_service.get_current_task.return_value = "02_create_namespace"
        mock_task_service.task_repo.get.return_value = None
        payload = module._build_game_status_payload("student@example.com", "game01")

    assert payload["status"] == "NOT_STARTED"
    assert payload["message"] == "Create namespace student-ns"
    assert payload["task_description"] == "Create namespace student-ns"


def test_status_action_redirects_stale_check_snapshot_back_to_challenge():
    module = load_module()
    manifest = FakeManifest()
    state = _state("01_task", "check", total_points=3)

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module.TaskManifest, "load", return_value=manifest):
        mock_task_service.get_total_score.return_value = 9
        mock_task_service.get_completed_tasks.return_value = ["01_task", "02_task"]
        mock_task_service.get_skipped_tasks.return_value = ["03_task"]
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = state
        payload = module._build_game_status_payload("student@example.com", "game01")

    assert payload["status"] == "IN_PROGRESS"
    assert payload["current_phase"] == "challenge"
    assert payload["message"] == "Solve namespace"
    assert payload["task_description"] == "Solve namespace"
    assert payload["next_game_phrase"] == "CHALLENGE"
    assert payload["total_score"] == 9
    assert payload["completed_tasks"] == ["01_task", "02_task"]
    assert payload["skipped_tasks"] == ["03_task"]


def test_status_action_skips_answer_phase_to_challenge():
    module = load_module()
    manifest = FakeManifest()
    state = _state("01_task", "answer", total_points=0)
    answer_phase_state = Mock()
    answer_phase_state.status = "pending"
    answer_phase_state.mark_passed = Mock()
    challenge_phase_state = Mock()
    challenge_phase_state.status = "pending"
    state.get_or_create_phase_state.return_value = answer_phase_state
    state.get_phase_state.side_effect = lambda phase_id: challenge_phase_state if phase_id == "challenge" else None

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module.TaskManifest, "load", return_value=manifest):
        mock_task_service.get_total_score.return_value = 4
        mock_task_service.get_completed_tasks.return_value = ["01_task"]
        mock_task_service.get_skipped_tasks.return_value = ["02_task"]
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = state
        payload = module._build_game_status_payload("student@example.com", "game01")

    answer_phase_state.mark_passed.assert_called_once_with("", 0)
    assert state.current_phase_id == "challenge"
    assert payload["current_phase"] == "challenge"
    assert payload["next_game_phrase"] == "CHALLENGE"
    assert payload["total_score"] == 4
    assert payload["completed_tasks"] == ["01_task"]
    assert payload["skipped_tasks"] == ["02_task"]


def test_talk_action_maps_npc_access_errors_to_player_message():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}):
        mock_task_service.validate_npc_access.return_value = (False, "Aiden does not have any task for you!")

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert result == {"status": "ERROR", "message": "Aiden has no task for you right now."}


def test_talk_action_maps_missing_account_to_player_message():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value=None):
        mock_task_service.validate_npc_access.return_value = (True, None)

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert result == {"status": "ERROR", "message": "Please save your Kubernetes account first."}


def test_talk_action_accepts_doom_without_npc_background():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_user_data", return_value=None), \
         patch.object(module, "get_npc_background") as mock_get_npc_background:
        mock_task_service.validate_npc_access.return_value = (True, None)

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            module.DOOM_TASK_SOURCE,
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_get_npc_background.assert_not_called()
    assert result == {"status": "ERROR", "message": "Please save your Kubernetes account first."}
    mock_task_service.validate_npc_access.assert_not_called()


def test_doom_talk_runs_setup_then_ready_before_waiting_for_challenge():
    module = load_module()
    manifest = FakeDoomManifest()
    started_state = _state("01_task", "setup", total_points=0)
    after_setup_state = _state("01_task", "ready", total_points=0)
    after_ready_state = _state("01_task", "answer", total_points=1)

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = None
        mock_task_service.start_task.return_value = started_state
        mock_task_service.execute_phase.side_effect = [
            {
                "success": True,
                "report_url": "",
                "test_result": module.TestResult.OK,
                "state": after_setup_state,
                "manifest": manifest,
            },
            {
                "success": True,
                "report_url": "https://report.example/ready",
                "test_result": module.TestResult.OK,
                "state": after_ready_state,
                "manifest": manifest,
            },
        ]

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            module.DOOM_TASK_SOURCE,
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert mock_task_service.execute_phase.call_count == 2
    assert after_ready_state.current_phase_id == "challenge"
    assert result["status"] == "OK"
    assert result["current_phase"] == "challenge"
    assert result["next_game_phrase"] == "CHALLENGE"


def test_doom_talk_retries_challenge_when_check_fails():
    module = load_module()
    manifest = FakeDoomManifest()
    challenge_state = _state("01_task", "challenge", total_points=1)
    after_challenge_state = _state("01_task", "check", total_points=2)
    failed_check_state = _state("01_task", "check", total_points=2)

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = challenge_state
        mock_task_service.execute_phase.side_effect = [
            {
                "success": True,
                "report_url": "",
                "test_result": module.TestResult.OK,
                "state": after_challenge_state,
                "manifest": manifest,
            },
            {
                "success": False,
                "report_url": "https://report.example/check",
                "test_result": module.TestResult.TESTS_FAILED,
                "state": failed_check_state,
                "manifest": manifest,
                "error": "Tests failed: TESTS_FAILED",
            },
        ]

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            module.DOOM_TASK_SOURCE,
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert mock_task_service.execute_phase.call_count == 2
    assert failed_check_state.current_phase_id == "challenge"
    assert result["status"] == "FAILED"
    assert result["current_phase"] == "challenge"
    assert result["next_game_phrase"] == "CHALLENGE"


def test_doom_talk_completes_after_check_passes():
    module = load_module()
    manifest = FakeDoomManifest()
    challenge_state = _state("01_task", "challenge", total_points=1)
    after_challenge_state = _state("01_task", "check", total_points=2)
    after_check_state = _state("01_task", None, total_points=5)
    completion_state = _state("01_task", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    sm = Mock()
    sm.can_complete_task.return_value = (True, None)

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = challenge_state
        mock_task_service.execute_phase.side_effect = [
            {
                "success": True,
                "report_url": "",
                "test_result": module.TestResult.OK,
                "state": after_challenge_state,
                "manifest": manifest,
            },
            {
                "success": True,
                "report_url": "https://report.example/check",
                "test_result": module.TestResult.OK,
                "state": after_check_state,
                "manifest": manifest,
            },
        ]
        mock_task_service.complete_task.return_value = {"state": completion_state}

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            module.DOOM_TASK_SOURCE,
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert mock_task_service.execute_phase.call_count == 2
    mock_task_service.complete_task.assert_called_once_with("student@example.com", "game01", "01_task", after_check_state)
    assert result["status"] == "COMPLETED"
    assert result["report_url"] == "https://report.example/check"


def test_doom_talk_executes_check_when_task_has_no_challenge_phase():
    module = load_module()
    manifest = FakeSimpleDoomManifest()
    check_state = _state("03_create_pod_port_80", "check", total_points=1)
    after_check_state = _state("03_create_pod_port_80", None, total_points=5)
    completion_state = _state("03_create_pod_port_80", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    sm = Mock()
    sm.can_complete_task.return_value = (True, None)

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.get_current_task.return_value = "03_create_pod_port_80"
        mock_task_service.task_repo.get.return_value = check_state
        mock_task_service.execute_phase.return_value = {
            "success": True,
            "report_url": "https://report.example/check",
            "test_result": module.TestResult.OK,
            "state": after_check_state,
            "manifest": manifest,
        }
        mock_task_service.complete_task.return_value = {"state": completion_state}

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            module.DOOM_TASK_SOURCE,
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_task_service.execute_phase.assert_called_once_with("student@example.com", "game01", "03_create_pod_port_80")
    mock_task_service.complete_task.assert_called_once_with("student@example.com", "game01", "03_create_pod_port_80", after_check_state)
    assert result["status"] == "COMPLETED"


def test_skip_action_marks_task_skipped_and_returns_updated_status():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "_build_game_status_payload", return_value={"status": "NOT_STARTED", "total_score": 5, "completed_tasks": ["01_task"], "skipped_tasks": ["02_task"]}) as mock_status:
        mock_task_service.get_current_task.return_value = "01_task"

        result = module.execute_game_command(
            "skip",
            "student@example.com",
            "game01",
            "",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_task_service.get_current_task.assert_called_once_with("student@example.com", "game01", mode="exercise")
    mock_task_service.skip_task.assert_called_once_with("student@example.com", "game01", "01_task")
    mock_status.assert_called_once_with("student@example.com", "game01")
    assert result["skipped_task"] == "01_task"
    assert result["message"] == "Skipped 01_task."


def test_reset_action_resets_current_task_and_returns_not_started_payload():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "_build_game_status_payload", return_value={"status": "NOT_STARTED", "task_id": "01_task", "task_description": "Do task"}) as mock_status:
        mock_task_service.get_current_task.return_value = "01_task"

        result = module.execute_game_command(
            "reset",
            "student@example.com",
            "game01",
            "",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_task_service.get_current_task.assert_called_once_with("student@example.com", "game01", mode="exercise")
    mock_task_service.reset_task.assert_called_once_with("student@example.com", "game01", "01_task")
    mock_status.assert_called_once_with("student@example.com", "game01")
    assert result["status"] == "RESET"
    assert result["reset_task"] == "01_task"


def test_reset_action_returns_player_facing_error_when_task_cannot_be_reset():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service:
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.reset_task.side_effect = ValueError("Task is not started yet. Open the exercise client and start the task first.")

        result = module.execute_game_command(
            "reset",
            "student@example.com",
            "game01",
            "",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert result == {
        "status": "ERROR",
        "message": "Task is not started yet. Open the exercise client and start the task first.",
    }


def test_reset_all_action_clears_whole_exercise_and_returns_not_started_payload():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "_build_game_status_payload", return_value={"status": "NOT_STARTED", "task_id": "01_task", "task_description": "Do task"}) as mock_status:
        mock_task_service.reset_game_progress.return_value = {
            "success": True,
            "deleted_task_count": 3,
            "deleted_task_ids": ["01_task", "02_task", "03_task"],
        }

        result = module.execute_game_command(
            "reset-all",
            "student@example.com",
            "game01",
            "",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_task_service.reset_game_progress.assert_called_once_with("student@example.com", "game01")
    mock_status.assert_called_once_with("student@example.com", "game01")
    assert result["status"] == "RESET_ALL"
    assert result["deleted_task_count"] == 3
    assert result["deleted_task_ids"] == ["01_task", "02_task", "03_task"]


def test_reset_all_action_returns_player_facing_error_when_whole_exercise_cannot_be_reset():
    module = load_module()

    with patch.object(module, "task_service") as mock_task_service:
        mock_task_service.reset_game_progress.side_effect = ValueError("No saved exercise progress was found for this game.")

        result = module.execute_game_command(
            "reset-all",
            "student@example.com",
            "game01",
            "",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert result == {
        "status": "ERROR",
        "message": "No saved exercise progress was found for this game.",
    }


def test_talk_action_saves_exercise_test_records():
    module = load_module()
    manifest = FakeManifest()
    started_state = _state("01_task", "setup", total_points=0)
    failed_state = _state("01_task", "setup", total_points=0)
    failed_result = {
        "success": False,
        "report_url": "https://report.example",
        "test_result": module.TestResult.TESTS_FAILED,
        "state": failed_state,
        "manifest": manifest,
    }

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "save_game_test_record") as mock_save_record, \
         patch.object(module, "_send_ws_message"):
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = None
        mock_task_service.start_task.return_value = started_state
        mock_task_service.execute_phase.return_value = failed_result

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_save_record.assert_called_once_with("student@example.com", "game01", "01_task", "setup", failed_result)
    assert result["status"] == "FAILED"


def test_talk_action_runs_multi_phase_flow_until_completion():
    module = load_module()
    manifest = FakeManifest()
    started_state = _state("01_task", "setup", total_points=0)
    after_setup_state = _state("01_task", "challenge", total_points=2)
    after_challenge_state = _state("01_task", "check", total_points=2)
    after_check_state = _state("01_task", None, total_points=5)
    completion_state = _state("01_task", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    ok_result_1 = {
        "success": True,
        "report_url": "",
        "test_result": module.TestResult.OK,
        "state": after_setup_state,
        "manifest": manifest,
    }
    ok_result_2 = {
        "success": True,
        "report_url": "",
        "test_result": module.TestResult.OK,
        "state": after_challenge_state,
        "manifest": manifest,
    }
    ok_result_3 = {
        "success": True,
        "report_url": "https://report.example",
        "test_result": module.TestResult.OK,
        "state": after_check_state,
        "manifest": manifest,
    }

    sm = Mock()
    sm.can_complete_task.side_effect = [(False, None), (False, None), (True, None)]

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message") as mock_send:
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = None
        mock_task_service.start_task.return_value = started_state
        mock_task_service.execute_phase.side_effect = [ok_result_1, ok_result_2, ok_result_3]
        mock_task_service.complete_task.return_value = {"state": completion_state}

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    statuses = [call.args[2]["data"]["status"] for call in mock_send.call_args_list]
    assert statuses == ["RUNNING", "RUNNING", "RUNNING", "RUNNING"]
    assert result["status"] == "COMPLETED"
    assert result["report_url"] == "https://report.example"


def test_talk_action_skips_answer_phase_before_running_tests():
    module = load_module()
    manifest = FakeManifest()
    answer_state = _state("01_task", "answer", total_points=0)
    after_challenge_state = _state("01_task", "check", total_points=2)
    completion_state = _state("01_task", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    answer_phase_state = Mock()
    answer_phase_state.status = "pending"
    answer_phase_state.mark_passed = Mock()
    challenge_phase_state = Mock()
    challenge_phase_state.status = "pending"
    answer_state.get_or_create_phase_state.return_value = answer_phase_state
    answer_state.get_phase_state.side_effect = lambda phase_id: challenge_phase_state if phase_id == "challenge" else None

    ok_result = {
        "success": True,
        "report_url": "https://report.example",
        "test_result": module.TestResult.OK,
        "state": after_challenge_state,
        "manifest": manifest,
    }

    sm = Mock()
    sm.can_complete_task.side_effect = [(True, None)]

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = answer_state
        mock_task_service.execute_phase.return_value = ok_result
        mock_task_service.complete_task.return_value = {"state": completion_state}

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    answer_phase_state.mark_passed.assert_called_once_with("", 0)
    mock_task_service.execute_phase.assert_called_once_with("student@example.com", "game01", "01_task")
    assert answer_state.current_phase_id == "challenge"
    assert result["status"] == "COMPLETED"


def test_talk_action_redirects_stale_check_back_to_challenge():
    module = load_module()
    manifest = FakeManifest()
    stale_check_state = _state("01_task", "check", total_points=2)
    after_challenge_state = _state("01_task", "check", total_points=2)
    completion_state = _state("01_task", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    ok_result = {
        "success": True,
        "report_url": "https://report.example",
        "test_result": module.TestResult.OK,
        "state": after_challenge_state,
        "manifest": manifest,
    }

    sm = Mock()
    sm.can_complete_task.side_effect = [(False, None), (True, None)]

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = stale_check_state
        mock_task_service.execute_phase.return_value = ok_result
        mock_task_service.complete_task.return_value = {"state": completion_state}

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert stale_check_state.current_phase_id == "challenge"
    assert result["status"] == "COMPLETED"


def test_talk_action_prioritizes_task_flow_over_flavor_chat():
    module = load_module()
    manifest = FakeManifest()
    started_state = _state("01_task", "setup", total_points=0)
    after_setup_state = _state("01_task", "answer", total_points=0)
    after_challenge_state = _state("01_task", "check", total_points=2)
    after_check_state = _state("01_task", None, total_points=5)
    completion_state = _state("01_task", None, total_points=5)
    completion_state.status = TaskStatus.COMPLETED

    sm = Mock()
    sm.can_complete_task.side_effect = [(False, None), (False, None), (True, None)]

    with patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"), \
         patch.object(module, "task_service") as mock_task_service:
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = None
        mock_task_service.start_task.return_value = started_state
        mock_task_service.execute_phase.side_effect = [
            {
                "success": True,
                "report_url": "",
                "test_result": module.TestResult.OK,
                "state": after_setup_state,
                "manifest": manifest,
            },
            {
                "success": True,
                "report_url": "https://report.example",
                "test_result": module.TestResult.OK,
                "state": after_challenge_state,
                "manifest": manifest,
            },
            {
                "success": True,
                "report_url": "https://report.example",
                "test_result": module.TestResult.OK,
                "state": after_check_state,
                "manifest": manifest,
            },
        ]
        mock_task_service.complete_task.return_value = {"state": completion_state}
        payload = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    assert payload["status"] == "COMPLETED"
    mock_task_service.validate_npc_access.assert_called_once_with("student@example.com", "game01", "Aiden")


def test_talk_action_does_not_abandon_when_max_attempts_are_reached():
    module = load_module()
    manifest = FakeManifest()
    started_state = _state("01_task", "check", total_points=0)
    failed_result = {
        "success": False,
        "report_url": "https://report.example",
        "test_result": module.TestResult.TESTS_FAILED,
        "state": started_state,
        "manifest": manifest,
    }

    sm = Mock()
    sm.get_next_action.return_value = {
        "action": "max_attempts_reached",
        "phase_id": "check",
        "message": "Maximum attempts reached.",
    }

    with patch.object(module, "task_service") as mock_task_service, \
         patch.object(module, "get_npc_background", return_value={"name": "Aiden"}), \
         patch.object(module, "get_user_data", return_value={"client_certificate": "cert", "client_key": "key", "endpoint": "https://k8s"}), \
         patch.object(module, "extract_k8s_access_config", return_value={"endpoint": "https://k8s", "client_certificate": "cert", "client_key": "key", "kubeconfig": "apiVersion: v1", "auth_type": "client_certificate"}), \
         patch.object(module, "clear_tmp_directory"), \
         patch.object(module, "write_k8s_access_files"), \
         patch.object(module.TaskManifest, "load", return_value=manifest), \
         patch.object(module, "TaskStateMachine", return_value=sm), \
         patch.object(module, "_send_ws_message"):
        mock_task_service.validate_npc_access.return_value = (True, None)
        mock_task_service.get_current_task.return_value = "01_task"
        mock_task_service.task_repo.get.return_value = started_state
        mock_task_service.execute_phase.return_value = failed_result

        result = module.execute_game_command(
            "talk",
            "student@example.com",
            "game01",
            "Aiden",
            "https://example.execute-api.us-east-1.amazonaws.com/Prod",
            "conn-1",
        )

    mock_task_service.abandon_task.assert_not_called()
    assert result["status"] == "FAILED"
    assert result["current_phase"] == "challenge"


def test_lambda_handler_maps_invalid_api_key_error_for_player():
    module = load_module()
    context = StubContext()
    event = {
        "action": "talk",
        "email": "student@example.com",
        "game": "game01",
        "npc": "Aiden",
        "connection_id": "conn-1",
        "connection_endpoint": "https://example.execute-api.us-east-1.amazonaws.com/Prod",
    }

    with patch.object(module, "execute_game_command_step", side_effect=ValueError("Invalid or expired API key: InvalidToken")), \
         patch.object(module, "_push_game_update") as mock_push:
        result = module.lambda_handler(event, context)

    mock_push.assert_called_once_with(
        "https://example.execute-api.us-east-1.amazonaws.com/Prod",
        "conn-1",
        "talk",
        {"status": "ERROR", "message": "Your game link is invalid or expired. Please open a fresh game link."},
    )
    assert result["statusCode"] == 200
