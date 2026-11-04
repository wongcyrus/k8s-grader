"""Durable exam command handler."""
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from aws_durable_execution_sdk_python import DurableContext, durable_execution, durable_step
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from jinja2 import Environment

from common.database import get_user_data
from common.exam_execution import EXAM_MUTATIONS, ExamExecutionGuard, current_exam_execution
from common.exam_lifecycle import AUTO_CHAIN_EXAM_PHASES, lifecycle_payload
from common.file import clear_tmp_directory, write_k8s_access_files
from common.google_spreadsheet import get_easter_egg_link
from common.handler import extract_k8s_access_config, setup_paths
from common.kubeconfig import session_data_from_access_config
from common.models.task_manifest import TaskManifest
from common.models.task_state import TaskStatus, PhaseStatus
from common.services.exam_service import ExamService
from common.services.task_phase_estimate_service import TaskPhaseEstimateService
from common.services.task_service import TaskService
from common.status import TestResult

logging.setLogRecordFactory(logging.LogRecord)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
DURABLE_HANDLER_REVISION = "2026-07-22-7"

setup_paths()

_task_service: Optional[TaskService] = None
_exam_service: Optional[ExamService] = None
_dynamodb_resource = None
execution_guard_repo = ExamExecutionGuard()
task_phase_estimate_service = TaskPhaseEstimateService()


def get_task_service() -> TaskService:
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service


def get_exam_service() -> ExamService:
    global _exam_service
    if _exam_service is None:
        _exam_service = ExamService()
    return _exam_service


def get_dynamodb_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
    return _dynamodb_resource


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def cors_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


def error_response(message: str) -> Dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps({"status": "ERROR", "message": message}, cls=DecimalEncoder),
    }


def render_template(template: str, session_data: Dict[str, Any]) -> str:
    try:
        env = Environment()
        jinja_template = env.from_string(template)
        return jinja_template.render(session_data)
    except Exception as err:
        logger.warning(f"Failed to render template: {err}")
        return template


def attach_exact_estimates(
    response: Dict[str, Any],
    game: Optional[str],
    task_id: Optional[str],
    current_phase_id: Optional[str],
    manifest: Optional[TaskManifest],
) -> Dict[str, Any]:
    if not game or not task_id or manifest is None:
        return response
    body = response.get("body")
    if not isinstance(body, str):
        return response
    payload = json.loads(body)
    payload.update(
        task_phase_estimate_service.get_estimate_payload(
            game,
            task_id,
            current_phase_id=current_phase_id,
            manifest=manifest,
        )
    )
    response["body"] = json.dumps(payload, cls=DecimalEncoder)
    return response


def broadcast_exam_update(email: str, exam_code: str, game: str, task_id: str, source_action: str, payload: Dict[str, Any]) -> None:
    table_name = os.getenv("ExamWsConnectionTable")
    endpoint = os.getenv("ExamWebSocketManagementEndpoint")
    if not table_name or not endpoint:
        return

    table = get_dynamodb_resource().Table(table_name)
    scope = f"{exam_code}#{game}#{task_id}"
    result = table.query(
        IndexName="EmailScopeIndex",
        KeyConditionExpression=Key("email").eq(email) & Key("scope").eq(scope),
    )
    items = result.get("Items", [])
    if not items:
        return

    api_client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)
    message = json.dumps(
        {"type": "exam_status", "source_action": source_action, "data": payload},
        cls=DecimalEncoder,
    ).encode("utf-8")

    for item in items:
        connection_id = item.get("connection_id")
        if not connection_id:
            continue
        try:
            api_client.post_to_connection(ConnectionId=connection_id, Data=message)
        except api_client.exceptions.GoneException:
            table.delete_item(Key={"connection_id": connection_id})
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code == "GoneException":
                table.delete_item(Key={"connection_id": connection_id})
            else:
                logger.warning(f"WebSocket push failed for {connection_id}: {err}")


def broadcast_exam_response(email: str, exam_code: str, game: Optional[str], task_id: Optional[str], source_action: str, response: Dict[str, Any]) -> None:
    if current_exam_execution.get():
        return
    if not game or not task_id:
        return
    body = response.get("body")
    if not isinstance(body, str):
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return
    broadcast_exam_update(email, exam_code, game, task_id, source_action, payload)


def with_exam_overview(response: Dict[str, Any], email: str, exam_code: str, game: Optional[str]) -> Dict[str, Any]:
    if not game:
        return response
    body = response.get("body")
    if not isinstance(body, str):
        return response
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return response
    exam_service = get_exam_service()
    session = exam_service.exam_session_repo.get(email, exam_code) or {}
    allowed_tasks = payload.get("allowed_tasks") or session.get("allowedTasks", [])
    overview = exam_service.get_exam_overview(email, game, allowed_tasks, persist_points=False)
    payload.update(overview)
    response["body"] = json.dumps(payload, cls=DecimalEncoder)
    return response


def task_started_response(state, manifest) -> Dict[str, Any]:
    current_phase = manifest.get_phase(state.current_phase_id)
    phase_message = current_phase.description if current_phase else "Task started!"
    manifest_description = getattr(manifest, "description", None)
    task_description = manifest_description if isinstance(manifest_description, str) and manifest_description else phase_message
    phase_message = render_template(phase_message, state.session_data)
    task_description = render_template(task_description, state.session_data)
    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(
            {
                "status": "STARTED",
                "task_id": state.task_id,
                "current_phase": state.current_phase_id,
                "phase_name": current_phase.name if current_phase else "",
                "message": phase_message,
                "task_description": task_description,
                "progress": 0.0,
                "lifecycle": lifecycle_payload(state),
            },
            cls=DecimalEncoder,
        ),
    }
    return attach_exact_estimates(
        response,
        getattr(state, "game", None),
        getattr(state, "task_id", None),
        getattr(state, "current_phase_id", None),
        manifest,
    )


def should_auto_chain_exam_phase(phase_id: Optional[str], next_phase_id: Optional[str]) -> bool:
    if not phase_id or not next_phase_id:
        return False
    return AUTO_CHAIN_EXAM_PHASES.get(phase_id) == next_phase_id


def cleanup_triggered_for_manifest(manifest) -> bool:
    cleanup_phase = manifest.get_phase("cleanup") if manifest else None
    return bool(cleanup_phase and cleanup_phase.auto_run)


def advance_exam_answer_phase(state, manifest, task_repo) -> bool:
    if not state or state.current_phase_id != "answer":
        return False

    challenge_phase = manifest.get_phase("challenge") if manifest else None
    challenge_state = state.get_phase_state("challenge") if challenge_phase else None
    challenge_status = getattr(getattr(challenge_state, "status", None), "value", getattr(challenge_state, "status", None))
    next_phase = manifest.get_next_phase("answer") if manifest else None
    phase_state = state.get_or_create_phase_state("answer")
    phase_status = getattr(phase_state.status, "value", phase_state.status)
    if phase_status != "passed":
        phase_state.mark_passed("", 0)
    if challenge_phase and challenge_status != "passed":
        state.current_phase_id = challenge_phase.id
    else:
        state.current_phase_id = next_phase.id if next_phase else None
    task_repo.save(state)
    logger.info(
        "Advanced exam answer phase for %s/%s to %s without running test_03_answer.py",
        state.game,
        state.task_id,
        state.current_phase_id,
    )
    return True


def ensure_exam_challenge_before_check(state, manifest, task_repo) -> bool:
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
    task_repo.save(state)
    logger.info(
        "Redirected exam flow for %s/%s back to challenge before check",
        state.game,
        state.task_id,
    )
    return True


def append_exam_phase_execution(executed_phases, phase_id, manifest, result) -> None:
    phase = manifest.get_phase(phase_id) if manifest and phase_id else None
    test_result = result.get("test_result")
    executed_phases.append(
        {
            "phase_id": phase_id,
            "phase_name": phase.name if phase else phase_id or "",
            "success": bool(result.get("success")),
            "test_result": test_result.name if test_result else "UNKNOWN",
            "report_url": result.get("report_url", ""),
        }
    )


def save_exam_test_record(email: str, exam_code: str, game: str, task_id: str, phase_id: str, result: Dict[str, Any]) -> None:
    test_result = result.get("test_result")
    if not test_result:
        return

    from common.database.repositories import TestRecordRepository

    test_record_repo = TestRecordRepository()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    report_url = result.get("report_url", "")
    bucket = os.getenv("TestResultBucket", "") if report_url else ""
    key = f"{game}/{email}/{task_id}/test_report_{phase_id}_{now_str}.html" if bucket and report_url else ""
    test_record_repo.save(
        email=email,
        game=game,
        current_task=task_id,
        game_phase=phase_id or "unknown",
        test_result=test_result.name,
        bucket=bucket,
        key=key,
        report_url=report_url,
        now_str=now_str,
        exam_code=exam_code,
        mode="exam",
    )


def _phase_execution_message(executed_phase: Dict[str, Any]) -> str:
    phase_label = executed_phase.get("phase_name") or executed_phase.get("phase_id") or "Phase"
    test_result = executed_phase.get("test_result", "UNKNOWN")
    if executed_phase.get("success"):
        if test_result == "NO_TESTS_COLLECTED":
            return f"{phase_label} skipped."
        return f"{phase_label} passed."
    return f"{phase_label} failed ({test_result})."


def attach_exam_run_details(response: Dict[str, Any], executed_phases, cleanup_triggered: bool = False) -> Dict[str, Any]:
    body = response.get("body")
    if not isinstance(body, str):
        return response

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return response

    if executed_phases:
        payload["executed_phases"] = executed_phases

    if cleanup_triggered:
        payload["cleanup_triggered"] = True

    summary_lines = [_phase_execution_message(phase) for phase in executed_phases]
    if cleanup_triggered:
        summary_lines.append("Cleanup ran automatically.")
    summary = "\n".join(summary_lines).strip()
    if summary:
        message = payload.get("message", "").strip()
        payload["message"] = f"{summary}\n\n{message}".strip() if message else summary

    response["body"] = json.dumps(payload, cls=DecimalEncoder)
    return response


def phase_passed_response(result, state, manifest) -> Dict[str, Any]:
    updated_state = result["state"]
    progress = updated_state.calculate_progress(manifest)
    current_phase = manifest.get_phase(updated_state.current_phase_id) if updated_state.current_phase_id else None
    next_phase = manifest.get_next_phase(updated_state.current_phase_id) if updated_state.current_phase_id else None

    if current_phase:
        next_phase_message = current_phase.description
    else:
        from common.state_machine.task_state_machine import TaskStateMachine

        sm = TaskStateMachine(manifest, updated_state)
        can_complete, _ = sm.can_complete_task()
        next_phase_message = "All phases completed!" if can_complete else "Continue to next phase"

    next_phase_message = render_template(next_phase_message, updated_state.session_data)
    manifest_description = getattr(manifest, "description", None)
    task_description_src = manifest_description if isinstance(manifest_description, str) and manifest_description else next_phase_message
    task_description = render_template(task_description_src, updated_state.session_data)

    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(
            {
                "status": "OK",
                "current_phase": updated_state.current_phase_id,
                "phase_name": current_phase.name if current_phase else "",
                "next_phase": next_phase.id if next_phase else None,
                "message": next_phase_message,
                "task_description": task_description,
                "report_url": result["report_url"],
                "progress": progress,
                "points": updated_state.total_points,
                "lifecycle": lifecycle_payload(updated_state),
            },
            cls=DecimalEncoder,
        ),
    }
    return attach_exact_estimates(
        response,
        getattr(updated_state, "game", None),
        getattr(updated_state, "task_id", None),
        getattr(updated_state, "current_phase_id", None),
        manifest,
    )


def phase_failed_response(result, state, manifest) -> Dict[str, Any]:
    updated_state = result.get("state") or state
    phase_state = updated_state.get_phase_state(updated_state.current_phase_id)
    current_phase = manifest.get_phase(updated_state.current_phase_id)
    phase_message = current_phase.description if current_phase else "Tests failed. Check the report."
    phase_message = render_template(phase_message, updated_state.session_data)
    manifest_description = getattr(manifest, "description", None)
    task_description_src = manifest_description if isinstance(manifest_description, str) and manifest_description else phase_message
    task_description = render_template(task_description_src, updated_state.session_data)
    test_result = result.get("test_result", TestResult.TESTS_FAILED)
    easter_egg = get_easter_egg_link(test_result)

    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(
            {
                "status": "FAILED",
                "lifecycle": lifecycle_payload(updated_state),
                "current_phase": updated_state.current_phase_id,
                "phase_name": current_phase.name if current_phase else "",
                "next_phase": updated_state.current_phase_id,
                "message": phase_message,
                "task_description": task_description,
                "report_url": result.get("report_url", ""),
                "easter_egg_url": easter_egg or "",
                "attempts": phase_state.attempts if phase_state else 0,
                "max_attempts": current_phase.max_attempts if current_phase else 3,
                "test_result": result.get("test_result").name if result.get("test_result") else "UNKNOWN",
            },
            cls=DecimalEncoder,
        ),
    }
    return attach_exact_estimates(
        response,
        getattr(updated_state, "game", None),
        getattr(updated_state, "task_id", None),
        getattr(updated_state, "current_phase_id", None),
        manifest,
    )


def task_completed_response(completion_result, report_url) -> Dict[str, Any]:
    if completion_result.get("cleanup_failed"):
        return cleanup_failed_response(completion_result)
    if completion_result.get("reason"):
        return task_abandoned_response(completion_result, report_url)
    state = completion_result["state"]
    easter_egg = get_easter_egg_link(TestResult.OK)
    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(
            {
                "status": "COMPLETED",
                "task_id": state.task_id,
                "message": f"🎉 Task completed! You earned {state.total_points} points!",
                "report_url": report_url,
                "easter_egg_url": easter_egg or "",
                "progress": 1.0,
                "lifecycle": lifecycle_payload(state),
                "total_points": state.total_points,
            },
            cls=DecimalEncoder,
        ),
    }
    return response


def task_abandoned_response(abandon_result, report_url) -> Dict[str, Any]:
    if abandon_result.get("cleanup_failed"):
        return cleanup_failed_response(abandon_result)
    state = abandon_result["state"]
    reason = abandon_result["reason"]
    easter_egg = get_easter_egg_link(TestResult.TESTS_FAILED)
    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(
            {
                "status": "ABANDONED",
                "task_id": state.task_id,
                "message": f"❌ Task abandoned: {reason}. You can retry from the exam UI.",
                "reason": reason,
                "report_url": report_url,
                "easter_egg_url": easter_egg or "",
                "progress": 0.0,
                "lifecycle": lifecycle_payload(state),
                "total_points": state.total_points,
            },
            cls=DecimalEncoder,
        ),
    }
    return response


def publish_exam_progress(email, exam_code, game, task_id, phase):
    execution = current_exam_execution.get()
    if not execution:
        return
    execution_guard_repo.set_phase(execution, phase)
    broadcast_exam_update(email, exam_code, game, task_id, execution["action"], {
        "status": "RUNNING",
        "task_id": task_id,
        "current_phase": phase,
        "active_execution": execution,
        "lifecycle": lifecycle_payload(phase=phase, running=True),
    })


def cleanup_failed_response(result):
    return {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps({
            "status": "FAILED",
            "current_phase": "cleanup",
            "cleanup_failed": True,
            "lifecycle": lifecycle_payload(result["state"]),
            "message": "Cleanup failed. Use Retry cleanup before continuing.",
            "report_url": result.get("report_url", ""),
        }),
    }


def cleanup_exam_environment(email, exam_code, game, task_id, state, manifest):
    cleanup = manifest.get_phase("cleanup")
    if cleanup:
        state.current_phase_id = "cleanup"
        if get_exam_service().task_repo.save(state) is False:
            raise RuntimeError("Could not save cleanup state; environment remains reserved.")
        publish_exam_progress(email, exam_code, game, task_id, "cleanup")
        phase_state = state.get_or_create_phase_state("cleanup")
        try:
            test_result, report_url = get_task_service().test_runner.run_phase(
                game, task_id, cleanup, state.session_data
            )
        except Exception:
            logger.exception("Exam cleanup failed for %s/%s", game, task_id)
            test_result, report_url = TestResult.TESTS_FAILED, ""
        if test_result not in (TestResult.OK, TestResult.NO_TESTS_COLLECTED):
            phase_state.mark_failed(test_result.name, report_url, count_attempts=False)
            state.current_phase_id = "cleanup"
            get_exam_service().task_repo.save(state)
            return {"state": state, "cleanup_failed": True, "report_url": report_url}
        phase_state.mark_passed(report_url, 0)
        state.current_phase_id = None
    return {"state": state}


def finish_exam_task(email, exam_code, game, task_id, state, reason=""):
    from common.state_machine.task_state_machine import TaskStateMachine

    manifest = TaskManifest.load(game, task_id)
    reason = reason or state.session_data.get("$exam_cleanup_abandon_reason", "")
    if reason:
        state.session_data["$exam_cleanup_abandon_reason"] = reason
    if state.session_data.get("$exam_cleanup_action") == "reset":
        return finish_exam_reset(email, exam_code, game, task_id, state, manifest)
    cleanup = manifest.get_phase("cleanup")
    if cleanup and cleanup.auto_run:
        result = cleanup_exam_environment(email, exam_code, game, task_id, state, manifest)
        if result.get("cleanup_failed"):
            return result

    sm = TaskStateMachine(manifest, state)
    success, error = sm.fail_task(reason) if reason else sm.complete_task()
    if not success:
        raise ValueError(error)
    state.session_data.pop("$exam_cleanup_abandon_reason", None)
    if get_exam_service().task_repo.save(state) is False:
        raise RuntimeError("Could not save the finished question; environment remains reserved.")
    execution_guard_repo.release_environment(email, game, exam_code, task_id)
    return {"state": state, "total_points": state.total_points, "reason": reason}


def finish_exam_reset(email, exam_code, game, task_id, state, manifest):
    state.status = TaskStatus.IN_PROGRESS
    state.session_data["$exam_cleanup_action"] = "reset"
    get_exam_service().task_repo.save(state)
    result = cleanup_exam_environment(email, exam_code, game, task_id, state, manifest)
    if result.get("cleanup_failed"):
        return result
    if not get_exam_service().task_repo.delete(email, game, task_id):
        raise RuntimeError("Could not reset the question; environment remains reserved.")
    execution_guard_repo.release_environment(email, game, exam_code, task_id)
    return {"state": state, "reset": True}


def reset_response():
    return {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps({
            "status": "RESET", "current_phase": None, "total_points": 0,
            "message": "Question left after cleanup. Choose a question to start again. Attempt history is preserved.",
            "lifecycle": lifecycle_payload(),
        }),
    }


def require_exam_environment(email, exam_code, game, task_id):
    if execution_guard_repo.claim_environment(email, game, exam_code, task_id):
        return None
    response = error_response("Another question owns your environment. Return to it and finish or leave it with cleanup first.")
    payload = json.loads(response["body"])
    payload["active_environment"] = execution_guard_repo.get_environment(email, game)
    response["body"] = json.dumps(payload)
    return response


def handle_exam_start(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    exam_service = get_exam_service()
    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    user_data = get_user_data(email)
    if not user_data:
        return error_response("User account not found")

    access_config = extract_k8s_access_config(user_data)
    endpoint = access_config.get("endpoint")
    if not endpoint or not access_config.get("kubeconfig"):
        return error_response("K8s credentials missing or incomplete")

    blocked = require_exam_environment(email, exam_code, game, task_id)
    if blocked:
        return blocked
    clear_tmp_directory()
    write_k8s_access_files(access_config)

    manifest = TaskManifest.load(game, task_id)
    exam_service = get_exam_service()
    state = exam_service.ensure_state(email, exam_code, game, task_id)
    if state.status == TaskStatus.ABANDONED:
        exam_service.task_repo.delete(email, game, task_id)
        state = exam_service.task_service.start_exam_task(email, game, task_id, exam_code)

    state.session_data.update(session_data_from_access_config(access_config))
    state.session_data["$email"] = email
    state.session_data["$exam_code"] = exam_code
    exam_service.task_repo.save(state)

    if state.status == TaskStatus.COMPLETED:
        execution_guard_repo.release_environment(email, game, exam_code, task_id)
        response = task_completed_response({"state": state}, state.get_phase_state(state.current_phase_id).report_url if state.current_phase_id else "")
    else:
        return handle_exam_run(email, exam_code, game, task_id, prepare_only=True)
    response = with_exam_overview(response, email, exam_code, game)
    broadcast_exam_response(email, exam_code, game, task_id, "start", response)
    return response


def handle_exam_reset(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    exam_service = get_exam_service()
    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    existing = exam_service.task_repo.get(email, game, task_id, consistent=True)
    if not existing:
        if execution_guard_repo.get_environment(email, game) == {"task_id": task_id, "exam_code": exam_code}:
            execution_guard_repo.release_environment(email, game, exam_code, task_id)
            return with_exam_overview(reset_response(), email, exam_code, game)
        return error_response("Task is not started yet. Click Start first.")
    if existing.status == TaskStatus.COMPLETED:
        return error_response("Reset is not allowed after task completion.")
    if existing.status not in (TaskStatus.IN_PROGRESS, TaskStatus.ABANDONED):
        return error_response(f"Reset is not allowed for status '{existing.status.value}'.")

    blocked = require_exam_environment(email, exam_code, game, task_id)
    if blocked:
        return blocked
    access_config = extract_k8s_access_config(get_user_data(email) or {})
    if not access_config.get("endpoint") or not access_config.get("kubeconfig"):
        return error_response("K8s credentials missing or incomplete")
    clear_tmp_directory()
    write_k8s_access_files(access_config)
    existing.session_data.update(session_data_from_access_config(access_config))
    manifest = TaskManifest.load(game, task_id)
    result = finish_exam_reset(email, exam_code, game, task_id, existing, manifest)
    response = cleanup_failed_response(result) if result.get("cleanup_failed") else reset_response()
    response = with_exam_overview(response, email, exam_code, game)
    broadcast_exam_response(email, exam_code, game, task_id, "reset", response)
    return response


def handle_exam_run(email: str, exam_code: str, game: Optional[str], task_id: Optional[str], *, prepare_only=False) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    exam_service = get_exam_service()
    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    state = exam_service.task_repo.get(email, game, task_id, consistent=True)
    if not state:
        return error_response("Task is not started. Click Start first.")

    if state.status in (TaskStatus.COMPLETED, TaskStatus.ABANDONED):
        return error_response("This question has finished. Refresh its status before continuing.")
    blocked = require_exam_environment(email, exam_code, game, task_id)
    if blocked:
        return blocked
    user_data = get_user_data(email)
    if not user_data:
        return error_response("User account not found")
    access_config = extract_k8s_access_config(user_data)
    if not access_config.get("endpoint") or not access_config.get("kubeconfig"):
        return error_response("K8s credentials missing or incomplete")
    clear_tmp_directory()
    write_k8s_access_files(access_config)
    state.session_data.update(session_data_from_access_config(access_config))
    state.session_data["$email"] = email
    state.session_data["$exam_code"] = exam_code
    exam_service.task_repo.save(state)

    manifest = TaskManifest.load(game, task_id)
    if state.current_phase_id == "cleanup":
        completion_result = finish_exam_task(email, exam_code, game, task_id, state)
        if completion_result.get("reset"):
            return with_exam_overview(reset_response(), email, exam_code, game)
        return with_exam_overview(
            task_completed_response(completion_result, ""), email, exam_code, game
        )
    advance_exam_answer_phase(state, manifest, exam_service.task_repo)
    ensure_exam_challenge_before_check(state, manifest, exam_service.task_repo)
    from common.state_machine.task_state_machine import TaskStateMachine

    sm = TaskStateMachine(manifest, state)
    next_action = sm.get_next_action()

    if next_action["action"] == "complete_task":
        completion_result = finish_exam_task(email, exam_code, game, task_id, state)
        response = task_completed_response(completion_result, "")
        response = with_exam_overview(response, email, exam_code, game)
        broadcast_exam_response(email, exam_code, game, task_id, "run", response)
        return response

    if next_action["action"] == "max_attempts_reached":
        abandon_result = finish_exam_task(email, exam_code, game, task_id, state, f"Maximum attempts reached for phase '{next_action['phase_id']}'")
        response = task_abandoned_response(abandon_result, "")
        response = with_exam_overview(response, email, exam_code, game)
        broadcast_exam_response(email, exam_code, game, task_id, "run", response)
        return response

    if next_action["action"] not in ("execute_phase", "retry_phase"):
        return error_response(f"Invalid next action for run: {next_action['action']}. Click Start/Status.")

    if prepare_only and state.current_phase_id not in ("setup", "ready"):
        return with_exam_overview(task_started_response(state, manifest), email, exam_code, game)

    check_state = state.get_phase_state("check")
    challenge = manifest.get_phase("challenge")
    if state.current_phase_id == "check" and check_state and check_state.status == PhaseStatus.FAILED and challenge:
        state.get_or_create_phase_state("challenge").status = PhaseStatus.PENDING
        state.current_phase_id = "challenge"
        exam_service.task_repo.save(state)

    executed_phases = []
    exam_service = get_exam_service()

    while True:
        executed_phase_id = state.current_phase_id
        publish_exam_progress(email, exam_code, game, task_id, executed_phase_id)
        result = exam_service.run_phase(email, exam_code, game, task_id)
        manifest = result["manifest"] or manifest
        state = result["state"]

        append_exam_phase_execution(executed_phases, executed_phase_id, manifest, result)
        if executed_phase_id:
            save_exam_test_record(email, exam_code, game, task_id, executed_phase_id, result)

        if not result["success"]:
            from common.state_machine.task_state_machine import TaskStateMachine

            sm = TaskStateMachine(manifest, state)
            next_action = sm.get_next_action()
            if next_action["action"] == "max_attempts_reached":
                abandon_result = finish_exam_task(email, exam_code, game, task_id, state, f"Maximum attempts reached for phase '{next_action['phase_id']}'")
                response = task_abandoned_response(abandon_result, result.get("report_url", ""))
                response = attach_exam_run_details(response, executed_phases, cleanup_triggered=cleanup_triggered_for_manifest(manifest))
                response = with_exam_overview(response, email, exam_code, game)
                broadcast_exam_response(email, exam_code, game, task_id, "run", response)
                return response
            response = phase_failed_response(result, state, manifest)
            response = attach_exam_run_details(response, executed_phases)
            response = with_exam_overview(response, email, exam_code, game)
            broadcast_exam_response(email, exam_code, game, task_id, "run", response)
            return response

        advance_exam_answer_phase(state, manifest, exam_service.task_repo)
        from common.state_machine.task_state_machine import TaskStateMachine

        sm = TaskStateMachine(manifest, state)
        can_complete, _ = sm.can_complete_task()
        if can_complete:
            completion_result = finish_exam_task(email, exam_code, game, task_id, state)
            response = task_completed_response(completion_result, result["report_url"])
            response = attach_exam_run_details(response, executed_phases, cleanup_triggered=cleanup_triggered_for_manifest(manifest))
            response = with_exam_overview(response, email, exam_code, game)
            broadcast_exam_response(email, exam_code, game, task_id, "run", response)
            return response

        if should_auto_chain_exam_phase(executed_phase_id, state.current_phase_id):
            continue

        response = phase_passed_response(result, state, manifest)
        response = attach_exam_run_details(response, executed_phases)
        response = with_exam_overview(response, email, exam_code, game)
        broadcast_exam_response(email, exam_code, game, task_id, "run", response)
        return response


def handle_exam_status(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")
    try:
        active_execution = execution_guard_repo.get_active(email, game)
        if active_execution:
            return {
                "statusCode": 200,
                "headers": cors_headers(),
                "body": json.dumps({
                    "status": "RUNNING", "task_id": task_id,
                    "active_execution": active_execution,
                }, cls=DecimalEncoder),
            }
        payload = get_exam_service().get_status(email, exam_code, game, task_id, persist_points=False)
        state = payload["state"]
        manifest = payload["manifest"]
        next_action = None
        task_description = ""
        if state:
            from common.state_machine.task_state_machine import TaskStateMachine

            next_action = TaskStateMachine(manifest, state).get_next_action()
            if state.current_phase_id == "answer":
                next_phase = manifest.get_phase("challenge") or manifest.get_next_phase("answer")
                next_action = {
                    "action": "execute_phase",
                    "phase_id": next_phase.id if next_phase else None,
                    "message": "Solve the task, then click Run to continue.",
                }
            task_description = render_template(manifest.description or "", state.session_data)
        response = {
            "statusCode": 200,
            "headers": cors_headers(),
            "body": json.dumps(
                {
                    "status": "OK",
                    "state": state.to_dict() if state else None,
                    "manifest": manifest.to_dict(),
                    "task_description": task_description,
                    "next_action": next_action,
                    "allowed_tasks": payload.get("allowed_tasks", []),
                    "active_execution": None,
                    "active_environment": execution_guard_repo.get_environment(email, game),
                    "lifecycle": lifecycle_payload(state),
                },
                cls=DecimalEncoder,
            ),
        }
        if manifest:
            current_phase_id = state.current_phase_id if state else None
            if not current_phase_id:
                first_phase = manifest.get_first_phase()
                current_phase_id = first_phase.id if first_phase else None
            response = attach_exact_estimates(response, game, task_id, current_phase_id, manifest)
        response = with_exam_overview(response, email, exam_code, game)
        return response
    except ValueError as err:
        return error_response(str(err))


def handle_exam_records(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    records = get_exam_service().list_records(email, exam_code, task_id=task_id)
    response = {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps({"status": "OK", "records": records}, cls=DecimalEncoder),
    }
    if game and task_id:
        response = with_exam_overview(response, email, exam_code, game)
        broadcast_exam_response(email, exam_code, game, task_id, "records", response)
    return response


def execute_exam_command(action: str, email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not email or not exam_code or not action:
        return error_response("Invalid exam command payload")
    try:
        if action == "start":
            return handle_exam_start(email, exam_code, game, task_id)
        if action == "reset":
            return handle_exam_reset(email, exam_code, game, task_id)
        if action == "run":
            return handle_exam_run(email, exam_code, game, task_id)
        if action == "status":
            return handle_exam_status(email, exam_code, game, task_id)
        if action == "records":
            return handle_exam_records(email, exam_code, game, task_id)
        return error_response(f"Unsupported exam action: {action}")
    except Exception as err:
        logger.exception("Durable exam action '%s' failed", action)
        response = error_response(f"Exam action '{action}' failed: {err}")
        broadcast_exam_response(email, exam_code, game, task_id, action, response)
        return response


@durable_step
def execute_exam_command_step(step_context, action: str, email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    del step_context
    return execute_exam_command(action, email, exam_code, game, task_id)


def start_exam_command_step(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]):
    return execute_exam_command_step("start", email, exam_code, game, task_id)


def reset_exam_command_step(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]):
    return execute_exam_command_step("reset", email, exam_code, game, task_id)


def run_exam_command_step(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]):
    return execute_exam_command_step("run", email, exam_code, game, task_id)


def status_exam_command_step(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]):
    return execute_exam_command_step("status", email, exam_code, game, task_id)


def records_exam_command_step(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]):
    return execute_exam_command_step("records", email, exam_code, game, task_id)


@durable_step
def guarded_exam_command_step(step_context, action, email, exam_code, game, task_id, execution_id):
    del step_context
    response = execution_guard_repo.execute(
        action, email, exam_code, game, task_id,
        lambda: execute_exam_command(action, email, exam_code, game, task_id),
        execution_id=execution_id,
    )
    broadcast_exam_response(email, exam_code, game, task_id, action, response)
    return response


@durable_step
def synchronized_exam_status_step(step_context, email, exam_code, game, task_id, status_request_id):
    del step_context
    response = execute_exam_command("status", email, exam_code, game, task_id)
    payload = json.loads(response["body"])
    payload["status_request_id"] = status_request_id
    response["body"] = json.dumps(payload, cls=DecimalEncoder)
    broadcast_exam_response(email, exam_code, game, task_id, "status", response)
    return response


@durable_execution
def lambda_handler(event: Dict[str, Any], context: DurableContext) -> Dict[str, Any]:
    action = event.get("action")
    email = event.get("email")
    exam_code = event.get("exam_code")
    game = event.get("game")
    task_id = event.get("task_id")
    if not email or not exam_code or not game or not task_id:
        return error_response("Invalid exam command payload")
    if action in EXAM_MUTATIONS:
        return context.step(guarded_exam_command_step(
            action, email, exam_code, game, task_id, event.get("execution_id", "")
        ))
    if action == "status":
        return context.step(synchronized_exam_status_step(
            email, exam_code, game, task_id, event.get("status_request_id", "")
        ))
    if action == "records":
        return context.step(records_exam_command_step(email, exam_code, game, task_id))
    return error_response("Invalid exam command payload")
