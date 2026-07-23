import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3
from common.database import ExecutionGuardRepository, RequestThrottleRepository
from common.handler import get_email_from_api_key
from common.durable_invoker import invoke_durable_function


TABLE_NAME = os.getenv("ExamWsConnectionTable", "")
TASK_STATE_TABLE = os.getenv("TaskStateTable", "")
EXAM_COMMAND_DURABLE_FUNCTION_ARN = os.getenv("ExamCommandDurableFunctionArn", "")
EXAM_ACTION_COOLDOWN_SECONDS = {
    "start": 2,
    "reset": 5,
    "run": 2,
    "status": 2,
    "records": 2,
}
EXAM_ACTION_GUARD_TTL_SECONDS = {
    "run": 600,
}
dynamodb = boto3.resource("dynamodb")
request_throttle_repo = RequestThrottleRepository()
execution_guard_repo = ExecutionGuardRepository()


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


def _push_inline_exam_status(event: Dict[str, Any], source_action: str, payload: Dict[str, Any]) -> None:
    connection_id = event.get("requestContext", {}).get("connectionId")
    if not connection_id:
        return
    try:
        _send_ws_message(
            event,
            connection_id,
            {
                "type": "exam_status",
                "source_action": source_action,
                "data": payload,
            },
        )
    except Exception:
        # Inline feedback is best-effort only; the guard remains enforced even if push fails.
        return


def _exam_throttle_scope(email: str, exam_code: str, game: str, task: str, action: str) -> str:
    return f"exam#{email}#{exam_code}#{game}#{task}#{action}"


def _exam_execution_guard_scope(email: str, exam_code: str, game: str, task: str, action: str) -> str:
    return f"exam#{email}#{exam_code}#{game}#{task}#{action}"


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
        email = connection.get("email") or ""
        exam_code = connection.get("exam_code") or ""
        game = connection.get("game") or ""
        task = connection.get("task") or ""
        cooldown_seconds = EXAM_ACTION_COOLDOWN_SECONDS.get(action, 0)
        if cooldown_seconds > 0:
            throttle_scope = _exam_throttle_scope(email, exam_code, game, task, action)
            if not request_throttle_repo.claim_request(
                throttle_scope,
                email=email,
                channel="exam_ws",
                action=action,
                cooldown_seconds=cooldown_seconds,
            ):
                payload = {"status": "ERROR", "message": "Please wait a moment before trying again."}
                _push_inline_exam_status(event, action, payload)
                return _response(200, payload)

        execution_guard_key = ""
        guard_ttl_seconds = EXAM_ACTION_GUARD_TTL_SECONDS.get(action, 0)
        if guard_ttl_seconds > 0:
            execution_guard_key = _exam_execution_guard_scope(email, exam_code, game, task, action)
            if not execution_guard_repo.acquire(
                execution_guard_key,
                email=email,
                channel="exam_ws",
                action=action,
                ttl_seconds=guard_ttl_seconds,
            ):
                payload = {"status": "ERROR", "message": "An exam run is already in progress. Please wait for it to finish."}
                _push_inline_exam_status(event, action, payload)
                return _response(200, payload)
        try:
            request_id = invoke_durable_function(
                EXAM_COMMAND_DURABLE_FUNCTION_ARN,
                {
                    "action": action,
                    "email": email,
                    "exam_code": exam_code,
                    "game": game,
                    "task_id": task,
                    "execution_guard_key": execution_guard_key,
                },
            )
            if execution_guard_key:
                execution_guard_repo.attach_request_id(execution_guard_key, request_id)
        except Exception as err:
            if execution_guard_key:
                execution_guard_repo.release(execution_guard_key)
            return _response(500, {"status": "ERROR", "message": str(err)})
        return _response(200, {"status": "QUEUED", "action": action, "request_id": request_id})

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
