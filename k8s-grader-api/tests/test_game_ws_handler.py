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
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "attach_request_id", return_value=True):
            response = lambda_handler(
                _ws_event({"action": "talk", "apiKey": "k", "game": "game01", "npc": "Aiden"}),
                None,
            )

        mock_queue.assert_called_once()
        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "talk"
        assert queued_payload["npc"] == "Aiden"
        assert queued_payload["execution_guard_key"] == "game#student@example.com#game01#mutation"

        body = json.loads(response["body"])
        assert body["status"] == "QUEUED"
        assert body["action"] == "talk"

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-2")
    def test_status_action_queues_game_command(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True):
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
    @patch("game_ws_app._queue_game_command", return_value="request-3")
    def test_skip_action_queues_game_command(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "attach_request_id", return_value=True):
            response = lambda_handler(
                _ws_event({"action": "skip", "apiKey": "k", "game": "game01"}),
                None,
            )

        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "skip"
        assert queued_payload["npc"] == ""
        assert queued_payload["execution_guard_key"] == "game#student@example.com#game01#mutation"

        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "skip", "request_id": "request-3"}

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-4")
    def test_reset_action_queues_game_command(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "attach_request_id", return_value=True):
            response = lambda_handler(
                _ws_event({"action": "reset", "apiKey": "k", "game": "game01"}),
                None,
            )

        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "reset"
        assert queued_payload["npc"] == ""
        assert queued_payload["execution_guard_key"] == "game#student@example.com#game01#mutation"

        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "reset", "request_id": "request-4"}

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-5")
    def test_reset_all_action_queues_game_command(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "attach_request_id", return_value=True):
            response = lambda_handler(
                _ws_event({"action": "reset-all", "apiKey": "k", "game": "game01"}),
                None,
            )

        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["action"] == "reset-all"
        assert queued_payload["npc"] == ""
        assert queued_payload["execution_guard_key"] == "game#student@example.com#game01#mutation"

        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "reset-all", "request_id": "request-5"}

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", return_value="request-6")
    def test_skip_action_uses_shared_mutation_guard(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "attach_request_id", return_value=True):
            response = lambda_handler(
                _ws_event({"action": "skip", "apiKey": "k", "game": "game01"}),
                None,
            )

        queued_payload = mock_queue.call_args.args[0]
        assert queued_payload["execution_guard_key"] == "game#student@example.com#game01#mutation"
        body = json.loads(response["body"])
        assert body == {"status": "QUEUED", "action": "skip", "request_id": "request-6"}

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

    @patch("game_ws_app.get_email_from_api_key", side_effect=ValueError("Invalid or expired API key: InvalidToken"))
    def test_invalid_api_key_returns_player_facing_message(self, _mock_email):
        response = lambda_handler(
            _ws_event({"action": "talk", "apiKey": "bad", "game": "game01", "npc": "Aiden"}),
            None,
        )

        assert response["statusCode"] == 401
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "Your game link is invalid or expired. Please open a fresh game link.",
        }

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command")
    def test_talk_action_is_throttled_server_side(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=False):
            response = lambda_handler(
                _ws_event({"action": "talk", "apiKey": "k", "game": "game01", "npc": "Aiden"}),
                None,
            )

        mock_queue.assert_not_called()
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "Please wait a moment before trying again.",
        }

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command")
    def test_talk_action_respects_active_execution_guard(self, mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=False):
            response = lambda_handler(
                _ws_event({"action": "talk", "apiKey": "k", "game": "game01", "npc": "Aiden"}),
                None,
            )

        mock_queue.assert_not_called()
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "A game task is already running for you. Please wait for it to finish.",
        }

    @patch("game_ws_app.get_email_from_api_key", return_value="student@example.com")
    @patch("game_ws_app._queue_game_command", side_effect=ValueError("queue failed"))
    def test_talk_action_releases_guard_when_queue_fails(self, _mock_queue, _mock_email):
        with patch.object(game_ws_app.request_throttle_repo, "claim_request", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "acquire", return_value=True), \
             patch.object(game_ws_app.execution_guard_repo, "release", return_value=True) as mock_release:
            response = lambda_handler(
                _ws_event({"action": "talk", "apiKey": "k", "game": "game01", "npc": "Aiden"}),
                None,
            )

        mock_release.assert_called_once_with("game#student@example.com#game01#mutation")
        assert response["statusCode"] == 500
        assert json.loads(response["body"]) == {
            "status": "ERROR",
            "message": "queue failed",
        }
