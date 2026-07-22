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

        with patch('exam_ws_app.invoke_durable_function', return_value='request-1') as mock_start:
            response = lambda_handler(_ws_event({"action": "start"}), None)

        mock_start.assert_called_once()
        args, _ = mock_start.call_args
        assert args[0] == exam_ws_app.EXAM_COMMAND_DURABLE_FUNCTION_ARN
        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "start"}

    @patch('exam_ws_app._get_connection')
    def test_default_action_run_uses_durable_payload(self, mock_get_connection):
        mock_get_connection.return_value = {
            "email": "student@example.com",
            "exam_code": "EXAM-001",
            "game": "game02",
            "task": "087_kustomize_configuration",
        }

        with patch('exam_ws_app.invoke_durable_function', return_value='request-2') as mock_start:
            response = lambda_handler(_ws_event({"action": "run"}), None)

        mock_start.assert_called_once()
        args, _ = mock_start.call_args
        payload = args[1]
        assert payload["action"] == "run"
        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "run"}
