import json
import os
from typing import Any, Dict

from common.durable_invoker import invoke_durable_function
from common.handler import get_email_from_api_key, to_player_safe_game_message


GAME_COMMAND_FUNCTION_ARN = os.getenv("GameCommandDurableFunctionArn", "")


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

    if action not in {"talk", "status"}:
        return _response(200, {"status": "OK"})

    if not api_key or not game:
        return _error_response(400, "Missing required websocket parameters")

    try:
        email = get_email_from_api_key(api_key)
    except ValueError as err:
        return _error_response(401, str(err))

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
            }
        )
    except ValueError as err:
        return _error_response(500, str(err))

    return _response(200, {"status": "QUEUED", "action": action, "request_id": request_id})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    route_key = event.get("requestContext", {}).get("routeKey", "")

    if route_key == "$connect":
        return _handle_connect(event)
    if route_key == "$disconnect":
        return _handle_disconnect(event)
    return _handle_default(event)
