import json
import os
from typing import Any, Dict

import boto3
from common.durable_invoker import invoke_durable_function
from common.database import ExecutionGuardRepository, RequestThrottleRepository
from common.handler import get_email_from_api_key, to_player_safe_game_message


GAME_COMMAND_FUNCTION_ARN = os.getenv("GameCommandDurableFunctionArn", "")
GAME_ACTION_COOLDOWN_SECONDS = {
    "talk": 2,
    "status": 3,
    "reset": 5,
    "reset-all": 10,
    "skip": 5,
}
GAME_ACTION_GUARD_TTL_SECONDS = {
    "talk": 180,
    "reset": 30,
    "reset-all": 45,
    "skip": 30,
}
request_throttle_repo = RequestThrottleRepository()
execution_guard_repo = ExecutionGuardRepository()


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(body),
    }


def _error_response(status_code: int, message: str) -> Dict[str, Any]:
    return _response(status_code, {"status": "ERROR", "message": to_player_safe_game_message(message)})


def _ws_endpoint(event: Dict[str, Any]) -> str:
    ctx = event.get("requestContext", {})
    domain = ctx.get("domainName", "")
    stage = ctx.get("stage", "")
    return f"https://{domain}/{stage}"


def _queue_game_command(payload: Dict[str, Any]) -> str:
    if not GAME_COMMAND_FUNCTION_ARN:
        raise ValueError("GameCommandDurableFunctionArn is not configured")
    return invoke_durable_function(GAME_COMMAND_FUNCTION_ARN, payload)


def _send_ws_message(endpoint: str, connection_id: str, payload: Dict[str, Any]) -> None:
    client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)
    client.post_to_connection(ConnectionId=connection_id, Data=json.dumps(payload).encode("utf-8"))


def _push_inline_game_status(event: Dict[str, Any], source_action: str, payload: Dict[str, Any]) -> None:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return
    try:
        _send_ws_message(
            _ws_endpoint(event),
            connection_id,
            {
                "type": "game_status",
                "source_action": source_action,
                "data": payload,
            },
        )
    except Exception:
        # Inline feedback is best-effort only; request protection still applies without it.
        return


def _game_throttle_scope(email: str, game: str, action: str) -> str:
    return f"game#{email}#{game}#{action}"


def _game_execution_guard_scope(email: str, game: str, action: str) -> str:
    if action in {"talk", "reset", "reset-all", "skip"}:
        return f"game#{email}#{game}#mutation"
    return f"game#{email}#{game}#{action}"


def _handle_connect(_event: Dict[str, Any]) -> Dict[str, Any]:
    return _response(200, {"status": "CONNECTED"})


def _handle_disconnect(_event: Dict[str, Any]) -> Dict[str, Any]:
    return _response(200, {"status": "DISCONNECTED"})


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return _error_response(400, "Missing websocket connection details")

    raw = event.get("body") or "{}"
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return _error_response(400, "Invalid JSON body")

    action = body.get("action")
    api_key = body.get("apiKey", "")
    game = body.get("game", "")
    npc = body.get("npc", "")

    if action == "subscribe":
        if not api_key or not game:
            return _error_response(400, "Missing subscribe parameters")
        try:
            get_email_from_api_key(api_key)
        except ValueError as err:
            return _error_response(401, str(err))
        return _response(200, {"status": "SUBSCRIBED", "game": game})

    if action not in {"talk", "status", "reset", "reset-all", "skip"}:
        return _response(200, {"status": "OK"})

    if not api_key or not game:
        return _error_response(400, "Missing required websocket parameters")

    try:
        email = get_email_from_api_key(api_key)
    except ValueError as err:
        return _error_response(401, str(err))

    cooldown_seconds = GAME_ACTION_COOLDOWN_SECONDS.get(action, 0)
    if cooldown_seconds > 0:
        throttle_scope = _game_throttle_scope(email, game, action)
        if not request_throttle_repo.claim_request(
            throttle_scope,
            email=email,
            channel="game_ws",
            action=action,
            cooldown_seconds=cooldown_seconds,
        ):
            payload = {"status": "ERROR", "message": "Please wait a moment before trying again."}
            _push_inline_game_status(event, action, payload)
            return _response(200, payload)

    execution_guard_key = ""
    guard_ttl_seconds = GAME_ACTION_GUARD_TTL_SECONDS.get(action, 0)
    if guard_ttl_seconds > 0:
        execution_guard_key = _game_execution_guard_scope(email, game, action)
        if not execution_guard_repo.acquire(
            execution_guard_key,
            email=email,
            channel="game_ws",
            action=action,
            ttl_seconds=guard_ttl_seconds,
        ):
            payload = {
                "status": "ERROR",
                "message": "A game task is already running for you. Please wait for it to finish.",
            }
            _push_inline_game_status(event, action, payload)
            return _response(200, payload)

    try:
        request_id = _queue_game_command(
            {
                "action": action,
                "connection_id": connection_id,
                "connection_endpoint": _ws_endpoint(event),
                "api_key": api_key,
                "email": email,
                "game": game,
                "npc": npc,
                "execution_guard_key": execution_guard_key,
            }
        )
        if execution_guard_key:
            execution_guard_repo.attach_request_id(execution_guard_key, request_id)
    except Exception as err:
        if execution_guard_key:
            execution_guard_repo.release(execution_guard_key)
        return _error_response(500, str(err))

    return _response(200, {"status": "QUEUED", "action": action, "request_id": request_id})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    route_key = event.get("requestContext", {}).get("routeKey", "")

    if route_key == "$connect":
        return _handle_connect(event)
    if route_key == "$disconnect":
        return _handle_disconnect(event)
    return _handle_default(event)
