import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from aws_durable_execution_sdk_python import DurableContext, durable_execution, durable_step
from jinja2 import Environment

from common.database import ExecutionGuardRepository
from common.database import get_npc_background, get_user_data
from common.file import clear_tmp_directory, write_user_files
from common.google_spreadsheet import get_easter_egg_link
from common.handler import extract_k8s_credentials, setup_paths, to_player_safe_game_message
from common.models.task_manifest import TaskManifest
from common.models.task_state import TaskStatus
from common.services.task_service import TaskService
from common.state_machine.task_state_machine import TaskStateMachine
from common.status import TestResult


logging.setLogRecordFactory(logging.LogRecord)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

setup_paths()

task_service = TaskService()
execution_guard_repo = ExecutionGuardRepository()


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _send_ws_message(endpoint: str, connection_id: str, payload: Dict[str, Any]) -> None:
    client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)
    message = json.dumps(payload, cls=DecimalEncoder).encode("utf-8")
    try:
        client.post_to_connection(ConnectionId=connection_id, Data=message)
    except client.exceptions.GoneException:
        logger.info("Game websocket connection %s is gone", connection_id)


def _push_game_update(endpoint: str, connection_id: str, source_action: str, data: Dict[str, Any]) -> None:
    _send_ws_message(
        endpoint,
        connection_id,
        {
            "type": "game_status",
            "source_action": source_action,
            "data": data,
        },
    )


def _render_template(template: Optional[str], session_data: Dict[str, Any]) -> str:
    if not template:
        return ""
    try:
        env = Environment()
        return env.from_string(template).render(session_data)
    except Exception as err:
        logger.warning("Failed to render template: %s", err)
        return template


def _phase_hint(phase_id: Optional[str]) -> str:
    return phase_id.upper() if phase_id else ""


def _error_payload(message: str) -> Dict[str, Any]:
    return {"status": "ERROR", "message": to_player_safe_game_message(message)}


def _advance_game_answer_phase(state, manifest) -> bool:
    if not state or state.current_phase_id != "answer" or not manifest:
        return False

    challenge_phase = manifest.get_phase("challenge")
    challenge_state = state.get_phase_state("challenge") if challenge_phase else None
    challenge_status = getattr(getattr(challenge_state, "status", None), "value", getattr(challenge_state, "status", None))
    next_phase = manifest.get_next_phase("answer")
    phase_state = state.get_or_create_phase_state("answer")
    phase_status = getattr(getattr(phase_state, "status", None), "value", getattr(phase_state, "status", None))
    if phase_status != "passed":
        phase_state.mark_passed("", 0)
    if challenge_phase and challenge_status != "passed":
        state.current_phase_id = challenge_phase.id
    else:
        state.current_phase_id = next_phase.id if next_phase else None
    task_service.task_repo.save(state)
    logger.info(
        "Advanced game answer phase for %s/%s to %s without running test_03_answer.py",
        state.game,
        state.task_id,
        state.current_phase_id,
    )
    return True


def _ensure_game_challenge_before_check(state, manifest) -> bool:
    if not state or state.current_phase_id != "check" or not manifest:
        return False

    challenge_phase = manifest.get_phase("challenge")
    if not challenge_phase:
        return False

    challenge_state = state.get_phase_state("challenge")
    challenge_status = getattr(getattr(challenge_state, "status", None), "value", getattr(challenge_state, "status", None))
    if challenge_status == "passed":
        return False

    state.current_phase_id = challenge_phase.id
    task_service.task_repo.save(state)
    logger.info(
        "Redirected game flow for %s/%s back to challenge before check",
        state.game,
        state.task_id,
    )
    return True


def _base_task_payload(state, manifest, *, status: str, message: str, report_url: str = "") -> Dict[str, Any]:
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    manifest_description = getattr(manifest, "description", None)
    task_description_src = manifest_description if isinstance(manifest_description, str) and manifest_description else message
    payload = {
        "status": status,
        "task_id": state.task_id,
        "current_phase": state.current_phase_id,
        "phase_name": current_phase.name if current_phase else "",
        "message": _render_template(message, state.session_data),
        "task_description": _render_template(task_description_src, state.session_data),
        "progress": state.calculate_progress(manifest),
        "total_points": state.total_points,
        "next_game_phrase": _phase_hint(state.current_phase_id),
    }
    if report_url:
        payload["report_url"] = report_url
    return payload


def _running_payload(state, manifest) -> Dict[str, Any]:
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    phase_message = current_phase.description if current_phase else "Working on the task."
    payload = _base_task_payload(
        state,
        manifest,
        status="RUNNING",
        message=phase_message,
    )
    payload["progress_message"] = f"Running {current_phase.name if current_phase else state.current_phase_id or 'task'}"
    return payload


def _task_started_payload(state, manifest) -> Dict[str, Any]:
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    phase_message = current_phase.description if current_phase else "Task started!"
    payload = _base_task_payload(
        state,
        manifest,
        status="STARTED",
        message=phase_message,
    )
    payload["progress"] = 0.0
    return payload


def _phase_passed_payload(result: Dict[str, Any], manifest) -> Dict[str, Any]:
    state = result["state"]
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    next_phase = manifest.get_next_phase(state.current_phase_id) if state.current_phase_id else None
    next_phase_message = next_phase.description if next_phase else "Continue to next phase"
    payload = _base_task_payload(
        state,
        manifest,
        status="OK",
        message=next_phase_message,
        report_url=result.get("report_url", ""),
    )
    payload["next_phase"] = next_phase.id if next_phase else None
    payload["phase_name"] = current_phase.name if current_phase else ""
    payload["points"] = state.total_points
    payload["next_game_phrase"] = _phase_hint(payload["next_phase"])
    return payload


def _phase_failed_payload(result: Dict[str, Any], manifest) -> Dict[str, Any]:
    state = result["state"]
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    phase_state = state.get_phase_state(state.current_phase_id)
    test_result = result.get("test_result", TestResult.TESTS_FAILED)
    payload = _base_task_payload(
        state,
        manifest,
        status="FAILED",
        message=current_phase.description if current_phase else "Tests failed. Check the report.",
        report_url=result.get("report_url", ""),
    )
    payload["attempts"] = phase_state.attempts if phase_state else 0
    payload["max_attempts"] = current_phase.max_attempts if current_phase else 3
    payload["test_result"] = test_result.name if test_result else "UNKNOWN"
    payload["easter_egg_url"] = get_easter_egg_link(test_result) or ""
    return payload


def _task_completed_payload(completion_result: Dict[str, Any], report_url: str) -> Dict[str, Any]:
    state = completion_result["state"]
    return {
        "status": "COMPLETED",
        "task_id": state.task_id,
        "message": f"🎉 Task completed! You earned {state.total_points} points!",
        "report_url": report_url,
        "easter_egg_url": get_easter_egg_link(TestResult.OK) or "",
        "progress": 1.0,
        "total_points": state.total_points,
        "next_game_phrase": "",
    }


def _task_abandoned_payload(abandon_result: Dict[str, Any], report_url: str) -> Dict[str, Any]:
    state = abandon_result["state"]
    reason = abandon_result["reason"]
    return {
        "status": "ABANDONED",
        "task_id": state.task_id,
        "message": f"❌ Task abandoned: {reason}. You can try again with the same NPC.",
        "reason": reason,
        "report_url": report_url,
        "easter_egg_url": get_easter_egg_link(TestResult.TESTS_FAILED) or "",
        "progress": 0.0,
        "total_points": state.total_points,
        "next_game_phrase": "",
    }


def _handle_game_skip(email: str, game: str) -> Dict[str, Any]:
    current_task = task_service.get_current_task(email, game)
    if not current_task:
        return _build_game_status_payload(email, game)

    task_service.skip_task(email, game, current_task)
    payload = _build_game_status_payload(email, game)
    payload["message"] = f"Skipped {current_task}."
    payload["skipped_task"] = current_task
    return payload


def _build_game_status_payload(email: str, game: str) -> Dict[str, Any]:
    total_score = task_service.get_total_score(email, game)
    completed_tasks = task_service.get_completed_tasks(email, game)
    skipped_tasks = task_service.get_skipped_tasks(email, game)
    current_task = task_service.get_current_task(email, game)
    if not current_task:
        return {
            "status": "COMPLETED",
            "message": "🎉 Congratulations! You've completed all tasks!",
            "progress": 1.0,
            "total_score": total_score,
            "completed_tasks": completed_tasks,
            "skipped_tasks": skipped_tasks,
            "next_game_phrase": "",
        }

    state = task_service.task_repo.get(email, game, current_task)
    if not state:
        manifest = TaskManifest.load(game, current_task)
        task_description = manifest.description or "Talk to the NPC to begin."
        rendered_description = _render_template(task_description, {})
        first_phase = manifest.get_first_phase()
        return {
            "status": "NOT_STARTED",
            "task_id": current_task,
            "message": rendered_description,
            "task_description": rendered_description,
            "total_score": total_score,
            "completed_tasks": completed_tasks,
            "skipped_tasks": skipped_tasks,
            "next_game_phrase": _phase_hint(first_phase.id if first_phase else None),
        }

    manifest = TaskManifest.load(game, current_task)
    _advance_game_answer_phase(state, manifest)
    _ensure_game_challenge_before_check(state, manifest)
    challenge_phase = manifest.get_phase("challenge") if manifest else None
    challenge_state = state.get_phase_state("challenge") if challenge_phase else None
    challenge_status = getattr(getattr(challenge_state, "status", None), "value", getattr(challenge_state, "status", None))
    if state.current_phase_id == "check" and challenge_phase and challenge_status != "passed":
        state.current_phase_id = "challenge"
        task_service.task_repo.save(state)
    current_phase = manifest.get_phase(state.current_phase_id) if state.current_phase_id else None
    phase_message = (
        current_phase.description
        if current_phase and getattr(current_phase, "description", "")
        else manifest.description or "Continue the task."
    )
    task_description_source = manifest.description or phase_message or "Continue the task."
    return {
        "status": state.status.value.upper() if isinstance(state.status, TaskStatus) else str(state.status).upper(),
        "task_id": current_task,
        "current_phase": state.current_phase_id,
        "phase_name": current_phase.name if current_phase else "",
        "message": _render_template(phase_message, state.session_data),
        "task_description": _render_template(task_description_source, state.session_data),
        "total_points": state.total_points,
        "total_score": total_score,
        "completed_tasks": completed_tasks,
        "skipped_tasks": skipped_tasks,
        "progress": state.calculate_progress(manifest),
        "next_game_phrase": _phase_hint(state.current_phase_id),
    }


def _handle_game_talk(email: str, game: str, npc: str, endpoint: str, connection_id: str) -> Dict[str, Any]:
    if not email or not game or not npc:
        return _error_payload("Missing required websocket parameters")
    if not game.isalnum():
        return _error_payload("Game parameter must be alphanumeric")
    if not get_npc_background(npc):
        return _error_payload(f"NPC '{npc}' not found")

    can_access, error = task_service.validate_npc_access(email, game, npc)
    if not can_access:
        return _error_payload(error)

    user_data = get_user_data(email)
    if not user_data:
        return _error_payload("User account not found")

    client_certificate, client_key, endpoint_url = extract_k8s_credentials(user_data)
    if not all([client_certificate, client_key, endpoint_url]):
        return _error_payload("K8s credentials missing or incomplete")

    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    current_task = task_service.get_current_task(email, game)
    if not current_task:
        return {
            "status": "COMPLETED",
            "message": "🎉 Congratulations! You've completed all tasks!",
            "progress": 1.0,
            "next_game_phrase": "",
        }

    manifest = TaskManifest.load(game, current_task)
    state = task_service.task_repo.get(email, game, current_task)

    if state and state.status == TaskStatus.ABANDONED:
        task_service.task_repo.delete(email, game, current_task)
        state = None

    if not state:
        state = task_service.start_task(email, game, current_task, npc)
        manifest = TaskManifest.load(game, current_task)
        _push_game_update(endpoint, connection_id, "talk", _running_payload(state, manifest))

    state.session_data["$endpoint"] = endpoint_url
    state.session_data["$client_certificate"] = client_certificate
    state.session_data["$client_key"] = client_key
    state.session_data["$email"] = email
    task_service.task_repo.save(state)

    if state.status == TaskStatus.COMPLETED:
        return _task_completed_payload({"state": state}, state.get_phase_state(state.current_phase_id).report_url if state.current_phase_id else "")

    while True:
        _advance_game_answer_phase(state, manifest)
        _ensure_game_challenge_before_check(state, manifest)

        if not state.current_phase_id:
            completion_result = task_service.complete_task(email, game, current_task, state)
            return _task_completed_payload(completion_result, "")

        _push_game_update(endpoint, connection_id, "talk", _running_payload(state, manifest))
        result = task_service.execute_phase(email, game, current_task)
        manifest = result["manifest"]
        state = result["state"]

        if not result["success"]:
            return _phase_failed_payload(result, manifest)

        can_complete, _ = TaskStateMachine(manifest, state).can_complete_task()
        if can_complete:
            completion_result = task_service.complete_task(email, game, current_task, state)
            return _task_completed_payload(completion_result, result.get("report_url", ""))


def execute_game_command(
    action: str,
    email: str,
    game: str,
    npc: str,
    endpoint: str,
    connection_id: str,
) -> Dict[str, Any]:
    if action == "talk":
        return _handle_game_talk(email, game, npc, endpoint, connection_id)
    if action == "status":
        return _build_game_status_payload(email, game)
    if action == "skip":
        return _handle_game_skip(email, game)
    return _error_payload(f"Unsupported game action: {action}")


@durable_step
def execute_game_command_step(step_context, action: str, email: str, game: str, npc: str, endpoint: str, connection_id: str) -> Dict[str, Any]:
    del step_context
    return execute_game_command(action, email, game, npc, endpoint, connection_id)


@durable_execution
def lambda_handler(event: Dict[str, Any], context: DurableContext) -> Dict[str, Any]:
    connection_id = event.get("connection_id")
    endpoint = event.get("connection_endpoint")
    action = event.get("action")
    email = event.get("email", "")
    game = event.get("game", "")
    npc = event.get("npc", "")
    execution_guard_key = event.get("execution_guard_key", "")

    if not connection_id or not endpoint:
        return {
            "statusCode": 400,
            "body": json.dumps(_error_payload("Missing websocket connection details"), cls=DecimalEncoder),
        }

    try:
        payload = context.step(execute_game_command_step(action, email, game, npc, endpoint, connection_id))
    except Exception as err:
        logger.exception("Game command failed")
        payload = _error_payload(str(err))
    finally:
        if execution_guard_key:
            execution_guard_repo.release(execution_guard_key)

    _push_game_update(endpoint, connection_id, action or "error", payload)
    return {"statusCode": 200, "body": json.dumps({"status": "OK"}, cls=DecimalEncoder)}
