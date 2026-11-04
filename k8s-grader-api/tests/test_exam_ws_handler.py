"""Tests for the exam WebSocket handler."""
import importlib.util
import json
import os
import sys
from unittest.mock import patch

import pytest

HANDLER_PATH = os.path.join(os.path.dirname(__file__), '..', 'exam-ws-handler', 'app.py')
SPEC = importlib.util.spec_from_file_location("exam_ws_app", HANDLER_PATH)
exam_ws_app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exam_ws_app
SPEC.loader.exec_module(exam_ws_app)

lambda_handler = exam_ws_app.lambda_handler
LEASE = {
    "scope_key": "exam#student@example.com#game02#mutation",
    "execution_id": "execution-1",
}


@pytest.fixture(autouse=True)
def exam_guard_table(dynamodb_tables):
    with patch.object(exam_ws_app.execution_guard_repo, "_table", dynamodb_tables["ws_execution_guard_table"]), \
         patch.object(exam_ws_app, "_push_inline_exam_status"):
        yield


def _ws_event(body):
    return {
        "requestContext": {
            "routeKey": "$default",
            "connectionId": "conn-1",
        },
        "body": json.dumps(body),
    }


class TestExamWebSocketHandler:
    @patch('exam_ws_app._get_connection')
    def test_default_action_start_queues_durable_function(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch('exam_ws_app.invoke_durable_function', return_value='request-1') as mock_start:
            response = lambda_handler(_ws_event({"action": "start"}), None)

        mock_start.assert_called_once()
        args, _ = mock_start.call_args
        assert args[0] == exam_ws_app.EXAM_COMMAND_DURABLE_FUNCTION_ARN
        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "start", "request_id": "request-1"}

    @patch('exam_ws_app._get_connection')
    def test_default_action_run_uses_durable_payload(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "acquire", return_value=LEASE), \
             patch('exam_ws_app.invoke_durable_function', return_value='request-2') as mock_start:
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_start.assert_called_once()
        args, _ = mock_start.call_args
        payload = args[1]
        assert payload["action"] == "run"
        assert payload["execution_id"] == "execution-1"
        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "run", "request_id": "request-2"}

    @patch('exam_ws_app._get_connection')
    def test_run_action_is_throttled_server_side(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=False), \
             patch('exam_ws_app.invoke_durable_function') as mock_start:
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_start.assert_not_called()
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "Please wait a moment before trying again.",
        }

    @patch('exam_ws_app._get_connection')
    def test_run_action_respects_active_execution_guard(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "acquire", return_value=False), \
             patch('exam_ws_app.invoke_durable_function') as mock_start:
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_start.assert_not_called()
        assert json.loads(response["body"])["status"] == "BUSY"

    @patch('exam_ws_app._get_connection')
    def test_run_action_releases_guard_when_queue_fails(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "acquire", return_value=LEASE), \
             patch.object(exam_ws_app.execution_guard_repo, "release", return_value=True) as mock_release, \
             patch('exam_ws_app.invoke_durable_function', side_effect=ValueError("queue failed")):
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_release.assert_called_once_with(LEASE["scope_key"], LEASE["execution_id"])
        assert response["statusCode"] == 500
        payload = json.loads(response["body"])
        assert payload["status"] == "ERROR"
        assert payload["message"] == "queue failed"
        assert payload["command_finished"] is True


@pytest.mark.parametrize("first_action", ["start", "run", "reset"])
@pytest.mark.parametrize("second_action", ["start", "run", "reset"])
def test_mutations_share_one_lease_across_questions_and_exam_codes(first_action, second_action):
    first = {
        "email": "student@example.com", "exam_code": "EXAM-001",
        "game": "game02", "task": "task_a",
    }
    second = {**first, "exam_code": "EXAM-002", "task": "task_b"}
    with patch.object(exam_ws_app, "_get_connection", side_effect=[first, second]), \
         patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
         patch.object(exam_ws_app, "invoke_durable_function", return_value="request-1") as invoke:
        initial = lambda_handler(_ws_event({"action": first_action}), None)
        rejected = lambda_handler(_ws_event({"action": second_action}), None)
    assert json.loads(initial["body"])["status"] == "QUEUED"
    payload = json.loads(rejected["body"])
    assert payload["status"] == "BUSY"
    assert payload["active_execution"]["task_id"] == "task_a"
    assert payload["active_execution"]["action"] == first_action
    invoke.assert_called_once()


def test_status_and_reconnect_expose_active_execution_without_running_another_command():
    guard = exam_ws_app.execution_guard_repo
    lease = guard.acquire("student@example.com", "game02", "EXAM-001", "task_a", "run")
    guard.set_phase(lease, "cleanup")
    connection = {
        "email": "student@example.com", "exam_code": "EXAM-001",
        "game": "game02", "task": "task_b",
    }
    with patch.object(exam_ws_app, "_get_connection", return_value=connection), \
         patch.object(exam_ws_app, "invoke_durable_function") as invoke:
        response = lambda_handler(_ws_event({"action": "status", "status_request_id": "sync-1"}), None)
        exam_ws_app._send_state_snapshot({}, "connection-2", "student@example.com", "EXAM-001", "game02", "task_b")
    payload = json.loads(response["body"])
    assert payload["active_execution"]["phase"] == "cleanup"
    assert payload["status_request_id"] == "sync-1"
    invoke.assert_not_called()
    assert exam_ws_app._push_inline_exam_status.call_args.args[2]["active_execution"]["task_id"] == "task_a"
