import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3
from common.handler import get_email_from_api_key
from common.durable_invoker import invoke_durable_function


TABLE_NAME = os.getenv("ExamWsConnectionTable", "")
TASK_STATE_TABLE = os.getenv("TaskStateTable", "")
EXAM_COMMAND_DURABLE_FUNCTION_ARN = os.getenv("ExamCommandDurableFunctionArn", "")
dynamodb = boto3.resource("dynamodb")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(body),
    }


def _get_table():
    if not TABLE_NAME:
        raise ValueError("ExamWsConnectionTable is not configured")
    return dynamodb.Table(TABLE_NAME)


def _get_connection(connection_id: str) -> Dict[str, Any]:
    table = _get_table()
    response = table.get_item(Key={"connection_id": connection_id})
    return response.get("Item") or {}


def _get_query_params(event: Dict[str, Any]) -> Dict[str, str]:
    params = event.get("queryStringParameters")
    if isinstance(params, dict):
        return params
    return {}


def _save_connection(connection_id: str, api_key: str, exam_code: str, game: str, task: str) -> Dict[str, Any]:
    email = get_email_from_api_key(api_key)
    scope = f"{exam_code}#{game}#{task}"
    now_iso = datetime.now(timezone.utc).isoformat()
    table = _get_table()
    table.put_item(
        Item={
            "connection_id": connection_id,
            "email": email,
            "scope": scope,
            "exam_code": exam_code,
            "game": game,
            "task": task,
            "connected_at": now_iso,
        }
    )
    return {"email": email, "scope": scope}


def _ws_endpoint(event: Dict[str, Any]) -> str:
    ctx = event.get("requestContext", {})
    domain = ctx.get("domainName", "")
    stage = ctx.get("stage", "")
    return f"https://{domain}/{stage}"


def _send_ws_message(event: Dict[str, Any], connection_id: str, payload: Dict[str, Any]) -> None:
    endpoint = _ws_endpoint(event)
    client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)
    message = json.dumps(payload, cls=DecimalEncoder).encode("utf-8")
    client.post_to_connection(ConnectionId=connection_id, Data=message)


def _send_state_snapshot(event: Dict[str, Any], connection_id: str, email: str, exam_code: str, game: str, task: str) -> None:
    if not TASK_STATE_TABLE:
        return

    table = dynamodb.Table(TASK_STATE_TABLE)
    response = table.get_item(Key={"email": email, "gameTask": f"{game}#{task}"})
    item = response.get("Item")
    if not item:
        _send_ws_message(event, connection_id, {
            "type": "exam_status",
            "source_action": "status",
            "data": {"status": "NOT_STARTED", "game": game, "task_id": task},
        })
        return

    current_phase = item.get("current_phase_id")
    snapshot = {
        "status": item.get("status", "UNKNOWN"),
        "task_id": task,
        "current_phase": current_phase,
        "total_points": item.get("total_points", 0),
    }
    _send_ws_message(event, connection_id, {
        "type": "exam_status",
        "source_action": "status",
        "data": snapshot,
    })


def _handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return _response(400, {"status": "ERROR", "message": "Missing connection ID"})

    params = _get_query_params(event)
    api_key = params.get("apiKey", "")
    exam_code = params.get("examCode", "")
    game = params.get("game", "")
    task = params.get("task", "")
    if not api_key or not exam_code or not game or not task:
        return _response(401, {"status": "ERROR", "message": "Missing required websocket parameters"})

    try:
        connection = _save_connection(connection_id, api_key, exam_code, game, task)
    except ValueError as err:
        return _response(401, {"status": "ERROR", "message": str(err)})

    return _response(200, {"status": "CONNECTED"})


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return _response(200, {"status": "DISCONNECTED"})

    table = _get_table()
    table.delete_item(Key={"connection_id": connection_id})
    return _response(200, {"status": "DISCONNECTED"})


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return _response(400, {"status": "ERROR", "message": "Missing connection ID"})

    raw = event.get("body") or "{}"
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return _response(400, {"status": "ERROR", "message": "Invalid JSON body"})

    action = body.get("action")
    if action in {"start", "reset", "run", "status", "records"}:
        connection = _get_connection(connection_id)
        if not connection:
            return _response(400, {"status": "ERROR", "message": "Connection is not registered. Reconnect websocket."})
        try:
            invoke_durable_function(
                EXAM_COMMAND_DURABLE_FUNCTION_ARN,
                {
                    "action": action,
                    "email": connection.get("email"),
                    "exam_code": connection.get("exam_code"),
                    "game": connection.get("game"),
                    "task_id": connection.get("task"),
                },
            )
        except ValueError as err:
            return _response(500, {"status": "ERROR", "message": str(err)})
        return _response(200, {"status": "QUEUED", "action": action})

    if action != "subscribe":
        return _response(200, {"status": "OK"})

    api_key = body.get("apiKey", "")
    exam_code = body.get("examCode", "")
    game = body.get("game", "")
    task = body.get("task", "")
    if not api_key or not exam_code or not game or not task:
        return _response(400, {"status": "ERROR", "message": "Missing subscribe parameters"})

    try:
        conn = _save_connection(connection_id, api_key, exam_code, game, task)
        _send_state_snapshot(event, connection_id, conn["email"], exam_code, game, task)
    except ValueError as err:
        return _response(401, {"status": "ERROR", "message": str(err)})

    return _response(200, {"status": "SUBSCRIBED", **conn})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    route_key = event.get("requestContext", {}).get("routeKey", "")

    if route_key == "$connect":
        return _handle_connect(event)
    if route_key == "$disconnect":
        return _handle_disconnect(event)
    return _handle_default(event)
