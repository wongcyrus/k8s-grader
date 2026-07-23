"""Tests for the game WebSocket handler."""
import importlib.util
import json
import os
import sys
from unittest.mock import patch

HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "game-ws-handler", "app.py")
SPEC = importlib.util.spec_from_file_location("game_ws_app", HANDLER_PATH)
game_ws_app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = game_ws_app
SPEC.loader.exec_module(game_ws_app)

lambda_handler = game_ws_app.lambda_handler


def _ws_event(body):
    return {
        "requestContext": {
            "routeKey": "$default",
            "connectionId": "conn-1",
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "stage": "Prod",
        },
        "body": json.dumps(body),
    }


class TestGameWebSocketHandler:
    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-1")
    def test_talk_action_queues_game_command(self, mock_queue, _mock_email):
        response = lambda_handler(
            _ws_event({"action": "talk", "apiKey": "k", "game": "game01", "npc": "Aiden"}),
            None,
        )

        mock_queue.assert_called_once()
        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "talk"
        assert queued_payload["npc"] == "Aiden"

        body = json.loads(response["body"])
        assert body["status"] == "QUEUED"
        assert body["action"] == "talk"

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-2")
    def test_status_action_queues_game_command(self, mock_queue, _mock_email):
        response = lambda_handler(
            _ws_event({"action": "status", "apiKey": "k", "game": "game01"}),
            None,
        )

        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "status"
        assert queued_payload["npc"] == ""

        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "status", "request_id": "request-2"}

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    def test_subscribe_validates_api_key(self, _mock_email):
        response = lambda_handler(
            _ws_event({"action": "subscribe", "apiKey": "k", "game": "game01"}),
            None,
        )

        body = json.loads(response["body"])
        assert body == {"status": "SUBSCRIBED", "game": "game01"}

    def test_invalid_json_body_returns_error(self):
        response = lambda_handler(
            {
                "requestContext": {
                    "routeKey": "$default",
                    "connectionId": "conn-1",
                },
                "body": "{bad json",
            },
            None,
        )

        assert response["statusCode"] == 400
        assert json.loads(response["body"]) == {"status": "ERROR", "message": "Invalid JSON body"}
