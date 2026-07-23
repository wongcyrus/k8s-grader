"""Tests for the exam WebSocket handler."""
import importlib.util
import json
import os
import sys
from unittest.mock import patch

HANDLER_PATH = os.path.join(os.path.dirname(__file__), '..', 'exam-ws-handler', 'app.py')
SPEC = importlib.util.spec_from_file_location("exam_ws_app", HANDLER_PATH)
exam_ws_app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exam_ws_app
SPEC.loader.exec_module(exam_ws_app)

lambda_handler = exam_ws_app.lambda_handler


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
             patch.object(exam_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "attach_request_id", return_value=True), \
             patch('exam_ws_app.invoke_durable_function', return_value='request-2') as mock_start:
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_start.assert_called_once()
        args, _ = mock_start.call_args
        payload = args[1]
        assert payload["action"] == "run"
        assert payload["execution_guard_key"] == "exam#student@example.com#EXAM-001#game02#087_kustomize_configuration#run"
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
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "An exam run is already in progress. Please wait for it to finish.",
        }

    @patch('exam_ws_app._get_connection')
    def test_run_action_releases_guard_when_queue_fails(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch.object(exam_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(exam_ws_app.execution_guard_repo, "release", return_value=True) as mock_release, \
             patch('exam_ws_app.invoke_durable_function', side_effect=ValueError("queue failed")):
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_release.assert_called_once_with(
            "exam#student@example.com#EXAM-001#game02#087_kustomize_configuration#run"
        )
        assert response["statusCode"] == 500
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "queue failed",
        }
