"""Unified task handler - replaces game-task and grader endpoints"""
# DEPLOYMENT: 2026-02-02 - Bug fixes for task completion
import json
import logging
import os
from decimal import Decimal
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from jinja2 import Environment

from common.handler import (
    get_email_game_and_npc_from_event,
    get_email_from_event,
    extract_k8s_credentials,
    setup_paths
)
from common.database import get_user_data, get_npc_background
from common.services.task_service import TaskService
from common.services.exam_service import ExamService
from common.database.repositories import GameAccessRepository
from common.models.task_manifest import TaskManifest
from common.file import clear_tmp_directory, write_user_files
from common.google_spreadsheet import get_easter_egg_link
from common.status import TestResult
from common.models.task_state import TaskStatus
from common.durable_invoker import invoke_durable_function

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
AUTO_CHAIN_EXAM_PHASES = {"setup": "ready"}

setup_paths()


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


def render_template(template: str, session_data: Dict[str, Any]) -> str:
    """Render Jinja2 template with session variables"""
    try:
        env = Environment()
        jinja_template = env.from_string(template)
        return jinja_template.render(session_data)
    except Exception as e:
        logger.warning(f"Failed to render template: {e}")
        return template  # Return original if rendering fails


# Initialize service
task_service = TaskService()
exam_service = ExamService()
game_access_repo = GameAccessRepository()

_dynamodb_resource = boto3.resource('dynamodb')


def broadcast_exam_update(email: str, exam_code: str, game: str, task_id: str, source_action: str, payload: Dict[str, Any]) -> None:
    table_name = os.getenv('ExamWsConnectionTable')
    endpoint = os.getenv('ExamWebSocketManagementEndpoint')
    if not table_name or not endpoint:
        return

    table = _dynamodb_resource.Table(table_name)
    scope = f"{exam_code}#{game}#{task_id}"
    result = table.query(
        IndexName='EmailScopeIndex',
        KeyConditionExpression=Key('email').eq(email) & Key('scope').eq(scope),
    )
    items = result.get('Items', [])
    if not items:
        return

    api_client = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint)
    message = json.dumps({
        'type': 'exam_status',
        'source_action': source_action,
        'data': payload,
    }, cls=DecimalEncoder).encode('utf-8')

    for item in items:
        connection_id = item.get('connection_id')
        if not connection_id:
            continue
        try:
            api_client.post_to_connection(ConnectionId=connection_id, Data=message)
        except api_client.exceptions.GoneException:
            table.delete_item(Key={'connection_id': connection_id})
        except ClientError as err:
            code = err.response.get('Error', {}).get('Code')
            if code == 'GoneException':
                table.delete_item(Key={'connection_id': connection_id})
            else:
                logger.warning(f"WebSocket push failed for {connection_id}: {err}")


def broadcast_exam_response(email: str, exam_code: str, game: Optional[str], task_id: Optional[str], source_action: str, response: Dict[str, Any]) -> None:
    if not game or not task_id:
        return

    body = response.get('body')
    if not isinstance(body, str):
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return

    broadcast_exam_update(email, exam_code, game, task_id, source_action, payload)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Unified task handler - replaces /game-task and /grader"""
    try:
        path = (event.get('path') or event.get('resource') or '/task').rstrip('/')
        if path.startswith('/exam'):
            return exam_lambda_handler(event, context)
        return handle_task_request(event, context)
    except ValueError as e:
        # Handle API key validation errors
        error_msg = str(e)
        if "Invalid API key" in error_msg or "decrypt" in error_msg.lower():
            logger.error(f"API key validation error: {e}")
            return error_response("Invalid or expired API key. Please generate a new one.")
        logger.error(f"Validation error: {e}", exc_info=True)
        return error_response(f"Validation error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return error_response(f"Internal error: {str(e)}")


def handle_task_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle the legacy RPG task flow."""
    # Extract parameters
    email, game, npc = get_email_game_and_npc_from_event(event)
    if not email or not game or not npc:
        return error_response("Missing required parameters: email, game, or npc")

    # Validate game format
    if not game.isalnum():
        return error_response("Game parameter must be alphanumeric")

    # Exam-mode games must be accessed through /exam endpoints
    if game_access_repo.get_mode(game) == "exam":
        return error_response("This game is configured for exam mode. Use /exam endpoints.")

    # Get NPC background
    npc_background = get_npc_background(npc)
    if not npc_background:
        return error_response(f"NPC '{npc}' not found")

    # Validate NPC access
    can_access, error = task_service.validate_npc_access(email, game, npc)
    if not can_access:
        return error_response(error)

    # Get user K8s credentials
    user_data = get_user_data(email)
    if not user_data:
        return error_response("User account not found")

    client_certificate, client_key, endpoint = extract_k8s_credentials(user_data)
    if not all([client_certificate, client_key, endpoint]):
        return error_response("K8s credentials missing or incomplete")

    # Setup environment
    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    # Get current task
    current_task = task_service.get_current_task(email, game)
    if not current_task:
        return ok_response("🎉 Congratulations! You've completed all tasks!")

    # Check if task already started
    from common.database.repositories import TaskStateRepository
    from common.models.task_state import TaskStatus
    task_repo = TaskStateRepository()
    state = task_repo.get(email, game, current_task)

    is_new_task = state is None

    # If task is already completed, return completion message
    if state and state.status == TaskStatus.COMPLETED:
        logger.info(f"Task {current_task} already completed for {email}")
        from common.models.task_manifest import TaskManifest
        manifest = TaskManifest.load(game, current_task)
        return task_completed_response(
            {'state': state, 'manifest': manifest},
            state.get_phase_state(state.current_phase_id).report_url if state.current_phase_id else ''
        )

    # If task was abandoned, allow restart
    if state and state.status == TaskStatus.ABANDONED:
        logger.info(f"Restarting abandoned task {current_task} for {email}")
        # Delete old state and start fresh
        task_repo.delete(email, game, current_task)
        state = None
        is_new_task = True

    if not state:
        # Start new task
        state = task_service.start_task(email, game, current_task, npc)

    # Always add/update credentials to session (may have changed)
    state.session_data['$endpoint'] = endpoint
    state.session_data['$client_certificate'] = client_certificate
    state.session_data['$client_key'] = client_key
    state.session_data['$email'] = email

    # Save state with updated credentials
    task_repo.save(state)

    # If this was a new task, return started response
    if is_new_task:
        from common.models.task_manifest import TaskManifest
        manifest = TaskManifest.load(game, current_task)
        return task_started_response(state, manifest)

    # Execute current phase
    result = task_service.execute_phase(email, game, current_task)

    # Log test execution to TestRecordTable for analytics
    if result.get('test_result'):
        from common.database.repositories import TestRecordRepository
        from datetime import datetime, timezone

        test_record_repo = TestRecordRepository()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

        # Extract S3 bucket and key from report URL if available
        report_url = result.get('report_url', '')
        bucket = ""
        key = ""
        if report_url:
            # Parse S3 info from presigned URL or use environment variable
            import os
            bucket = os.getenv('TestResultBucket', '')
            # Extract key from report URL if needed
            if bucket and report_url:
                # Key format: game/email/task/test_report_phase_timestamp.html
                key = f"{game}/{email}/{current_task}/test_report_{state.current_phase_id}_{now_str}.html"

        test_record_repo.save(
            email=email,
            game=game,
            current_task=current_task,
            game_phase=state.current_phase_id or 'unknown',
            test_result=result['test_result'].name,
            bucket=bucket,
            key=key,
            report_url=report_url,
            now_str=now_str
        )

    if not result['success']:
        # Check if max attempts reached
        from common.state_machine.task_state_machine import TaskStateMachine
        manifest = result['manifest']
        sm = TaskStateMachine(manifest, result['state'])
        next_action = sm.get_next_action()

        if next_action['action'] == 'max_attempts_reached':
            # Abandon the task
            abandon_result = task_service.abandon_task(
                email, game, current_task,
                f"Maximum attempts reached for phase '{next_action['phase_id']}'"
            )
            return task_abandoned_response(abandon_result, result.get('report_url', ''))

        return phase_failed_response(result, state, manifest)

    # Check if task is complete
    from common.state_machine.task_state_machine import TaskStateMachine
    manifest = result['manifest']
    state = result['state']  # Use updated state from result
    sm = TaskStateMachine(manifest, state)

    can_complete, _ = sm.can_complete_task()
    if can_complete:
        completion_result = task_service.complete_task(email, game, current_task, state)
        return task_completed_response(completion_result, result['report_url'])

    # Phase passed, continue to next
    return phase_passed_response(result, state, manifest)
    


def error_response(message: str) -> Dict[str, Any]:
    """Return error response"""
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'ERROR',
            'message': message
        }, cls=DecimalEncoder)
    }


def ok_response(message: str) -> Dict[str, Any]:
    """Return OK response"""
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'OK',
            'message': message
        }, cls=DecimalEncoder)
    }


def task_started_response(state, manifest) -> Dict[str, Any]:
    """Return response for task start"""
    # Get current phase description
    current_phase = manifest.get_phase(state.current_phase_id)
    phase_message = current_phase.description if current_phase else 'Task started!'
    manifest_description = getattr(manifest, 'description', None)
    task_description = manifest_description if isinstance(manifest_description, str) and manifest_description else phase_message
    
    # Render template variables with session data
    phase_message = render_template(phase_message, state.session_data)
    task_description = render_template(task_description, state.session_data)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'STARTED',
            'task_id': state.task_id,
            'current_phase': state.current_phase_id,
            'phase_name': current_phase.name if current_phase else '',
            'message': phase_message,
            'task_description': task_description,
            'progress': 0.0
        }, cls=DecimalEncoder)
    }


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
    from datetime import datetime, timezone

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
        mode="exam"
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
    """Return response for passed phase"""
    # Use updated state from result consistently
    updated_state = result['state']
    progress = updated_state.calculate_progress(manifest)
    current_phase = manifest.get_phase(updated_state.current_phase_id) if updated_state.current_phase_id else None
    next_phase = manifest.get_next_phase(updated_state.current_phase_id) if updated_state.current_phase_id else None
    
    # Get next phase description
    # Only show "All phases completed!" if we can actually complete the task
    if next_phase:
        next_phase_message = next_phase.description
    else:
        # No next phase - check if task can be completed
        from common.state_machine.task_state_machine import TaskStateMachine
        sm = TaskStateMachine(manifest, updated_state)
        can_complete, _ = sm.can_complete_task()
        next_phase_message = 'All phases completed!' if can_complete else 'Continue to next phase'
    
    # Render template variables with session data
    next_phase_message = render_template(next_phase_message, updated_state.session_data)
    manifest_description = getattr(manifest, 'description', None)
    task_description_src = manifest_description if isinstance(manifest_description, str) and manifest_description else next_phase_message
    task_description = render_template(task_description_src, updated_state.session_data)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'OK',
            'current_phase': updated_state.current_phase_id,
            'phase_name': current_phase.name if current_phase else '',
            'next_phase': next_phase.id if next_phase else None,
            'message': next_phase_message,
            'task_description': task_description,
            'report_url': result['report_url'],
            'progress': progress,
            'points': updated_state.total_points
        }, cls=DecimalEncoder)
    }


def phase_failed_response(result, state, manifest) -> Dict[str, Any]:
    """Return response for failed phase"""
    updated_state = result.get("state") or state
    phase_state = updated_state.get_phase_state(updated_state.current_phase_id)
    
    # Get current phase info
    current_phase = manifest.get_phase(updated_state.current_phase_id)
    phase_message = current_phase.description if current_phase else 'Tests failed. Check the report.'
    
    # Render template variables with session data
    phase_message = render_template(phase_message, updated_state.session_data)
    manifest_description = getattr(manifest, 'description', None)
    task_description_src = manifest_description if isinstance(manifest_description, str) and manifest_description else phase_message
    task_description = render_template(task_description_src, updated_state.session_data)
    
    # Get encouragement easter egg for failure
    test_result = result.get('test_result', TestResult.TESTS_FAILED)
    easter_egg = get_easter_egg_link(test_result)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'FAILED',
            'current_phase': updated_state.current_phase_id,
            'phase_name': current_phase.name if current_phase else '',
            'next_phase': updated_state.current_phase_id,  # Retry same phase
            'message': phase_message,
            'task_description': task_description,
            'report_url': result.get('report_url', ''),
            'easter_egg_url': easter_egg or '',
            'attempts': phase_state.attempts if phase_state else 0,
            'max_attempts': current_phase.max_attempts if current_phase else 3,
            'test_result': result.get('test_result').name if result.get('test_result') else 'UNKNOWN'
        }, cls=DecimalEncoder)
    }


def task_completed_response(completion_result, report_url) -> Dict[str, Any]:
    """Return response for completed task"""
    state = completion_result['state']
    easter_egg = get_easter_egg_link(TestResult.OK)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'COMPLETED',
            'task_id': state.task_id,
            'message': f'🎉 Task completed! You earned {state.total_points} points!',
            'report_url': report_url,
            'easter_egg_url': easter_egg or '',
            'progress': 1.0,
            'total_points': state.total_points
        }, cls=DecimalEncoder)
    }


def task_abandoned_response(abandon_result, report_url) -> Dict[str, Any]:
    """Return response for abandoned task"""
    state = abandon_result['state']
    reason = abandon_result['reason']
    retry_hint = 'You can try again with the same NPC.'
    if getattr(state, 'mode', 'exercise') == 'exam':
        retry_hint = 'You can retry from the exam UI.'
    
    # Get encouragement easter egg for abandonment (use TESTS_FAILED as the result type)
    easter_egg = get_easter_egg_link(TestResult.TESTS_FAILED)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'ABANDONED',
            'task_id': state.task_id,
            'message': f'❌ Task abandoned: {reason}. {retry_hint}',
            'reason': reason,
            'report_url': report_url,
            'easter_egg_url': easter_egg or '',
            'progress': 0.0,
            'total_points': state.total_points
        }, cls=DecimalEncoder)
    }


def exam_lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle exam routes."""
    path = (event.get('path') or event.get('resource') or '').rstrip('/')
    params = event.get('queryStringParameters') or {}
    email = get_email_from_event(event)
    exam_code = params.get('examCode')
    game = params.get('game')
    task_id = params.get('task')

    if not email:
        return error_response("Missing required parameters: email")

    if path.endswith('/verify-code'):
        if not exam_code:
            return error_response("Missing required parameters: examCode")
        try:
            result = exam_service.verify_code(email, exam_code)
            websocket_url = os.getenv('ExamWebSocketUrl', '')
            return {
                'statusCode': 200,
                'headers': cors_headers(),
                'body': json.dumps({
                    'status': 'VERIFIED',
                    'websocket_url': websocket_url,
                    **result
                }, cls=DecimalEncoder)
            }
        except ValueError as e:
            return error_response(str(e))

    if not exam_code:
        return error_response("Missing required parameters: examCode")

    if path.endswith('/start'):
        return handle_exam_start(email, exam_code, game, task_id)
    if path.endswith('/reset'):
        return handle_exam_reset(email, exam_code, game, task_id)
    if path.endswith('/run'):
        run_async = str(params.get('async', '')).lower() in ('1', 'true', 'yes')
        if run_async:
            return handle_exam_run_async(email, exam_code, game, task_id)
        return handle_exam_run(email, exam_code, game, task_id)
    if path.endswith('/status'):
        return handle_exam_status(email, exam_code, game, task_id)
    if path.endswith('/records'):
        return handle_exam_records(email, exam_code, task_id)

    return error_response("Unknown exam endpoint")


def handle_exam_run_async(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    state = exam_service.task_repo.get(email, game, task_id)
    if not state:
        return error_response("Task is not started. Click Start first.")

    current_phase = state.current_phase_id
    current_phase_name = ''
    if current_phase:
        manifest = TaskManifest.load(game, task_id)
        phase_cfg = manifest.get_phase(current_phase)
        current_phase_name = phase_cfg.name if phase_cfg else ''

    try:
        request_id = invoke_durable_function(
            os.getenv('ExamCommandDurableFunctionArn', ''),
            {
                'action': 'run',
                'email': email,
                'exam_code': exam_code,
                'game': game,
                'task_id': task_id,
            },
        )
    except ValueError as err:
        return error_response(str(err))

    queued_payload = {
        'status': 'QUEUED',
        'task_id': task_id,
        'current_phase': current_phase,
        'phase_name': current_phase_name,
        'message': 'Run accepted. Processing in background. Wait for WebSocket update.',
        'request_id': request_id,
    }
    broadcast_exam_update(email, exam_code, game, task_id, 'run', queued_payload)

    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps(queued_payload, cls=DecimalEncoder),
    }


def handle_exam_start(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    user_data = get_user_data(email)
    if not user_data:
        return error_response("User account not found")

    client_certificate, client_key, endpoint = extract_k8s_credentials(user_data)
    if not all([client_certificate, client_key, endpoint]):
        return error_response("K8s credentials missing or incomplete")

    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    manifest = TaskManifest.load(game, task_id)
    state = exam_service.ensure_state(email, exam_code, game, task_id)
    if state.status == TaskStatus.ABANDONED:
        # Student retry path: reset abandoned exam state and start from phase 1.
        exam_service.task_repo.delete(email, game, task_id)
        state = exam_service.task_service.start_exam_task(email, game, task_id, exam_code)

    state.session_data['$endpoint'] = endpoint
    state.session_data['$client_certificate'] = client_certificate
    state.session_data['$client_key'] = client_key
    state.session_data['$email'] = email
    state.session_data['$exam_code'] = exam_code
    exam_service.task_repo.save(state)

    if state.status == TaskStatus.COMPLETED:
        response = task_completed_response({'state': state}, state.get_phase_state(state.current_phase_id).report_url if state.current_phase_id else '')
        broadcast_exam_response(email, exam_code, game, task_id, 'start', response)
        return response

    response = task_started_response(state, manifest)
    broadcast_exam_response(email, exam_code, game, task_id, 'start', response)
    return response


def handle_exam_reset(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    existing = exam_service.task_repo.get(email, game, task_id)
    if not existing:
        return error_response("Task is not started yet. Click Start first.")
    if existing.status == TaskStatus.COMPLETED:
        return error_response("Reset is not allowed after task completion.")
    if existing.status not in (TaskStatus.IN_PROGRESS, TaskStatus.ABANDONED):
        return error_response(f"Reset is not allowed for status '{existing.status.value}'.")

    exam_service.task_repo.delete(email, game, task_id)
    response = {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'RESET',
            'task_id': task_id,
            'current_phase': None,
            'phase_name': '',
            'message': 'Task reset. Click Start to begin again. Attempt history remains in Records.',
            'total_points': 0,
            'progress': 0.0,
        }, cls=DecimalEncoder)
    }
    broadcast_exam_response(email, exam_code, game, task_id, 'reset', response)
    return response


def handle_exam_run(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")

    ok, error, _ = exam_service.authorize(email, exam_code, game, task_id)
    if not ok:
        return error_response(error)

    # Server-side flow enforcement: exam run must follow persisted state-machine state
    state = exam_service.task_repo.get(email, game, task_id)
    if not state:
        return error_response("Task is not started. Click Start first.")

    manifest = TaskManifest.load(game, task_id)
    advance_exam_answer_phase(state, manifest, exam_service.task_repo)
    ensure_exam_challenge_before_check(state, manifest, exam_service.task_repo)
    from common.state_machine.task_state_machine import TaskStateMachine

    sm = TaskStateMachine(manifest, state)
    next_action = sm.get_next_action()

    if next_action['action'] == 'complete_task':
        completion_result = task_service.complete_task(email, game, task_id, state)
        response = task_completed_response(completion_result, '')
        broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
        return response

    if next_action['action'] == 'max_attempts_reached':
        abandon_result = task_service.abandon_task(
            email, game, task_id,
            f"Maximum attempts reached for phase '{next_action['phase_id']}'"
        )
        response = task_abandoned_response(abandon_result, '')
        broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
        return response

    if next_action['action'] not in ('execute_phase', 'retry_phase'):
        return error_response(f"Invalid next action for run: {next_action['action']}. Click Start/Status.")

    user_data = get_user_data(email)
    if not user_data:
        return error_response("User account not found")

    client_certificate, client_key, endpoint = extract_k8s_credentials(user_data)
    if not all([client_certificate, client_key, endpoint]):
        return error_response("K8s credentials missing or incomplete")

    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    # Keep session data refreshed with latest account credentials before each run
    state.session_data['$endpoint'] = endpoint
    state.session_data['$client_certificate'] = client_certificate
    state.session_data['$client_key'] = client_key
    state.session_data['$email'] = email
    state.session_data['$exam_code'] = exam_code
    exam_service.task_repo.save(state)

    if state.status == TaskStatus.COMPLETED:
        response = task_completed_response({'state': state}, state.get_phase_state(state.current_phase_id).report_url if state.current_phase_id else '')
        broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
        return response

    executed_phases = []

    while True:
        executed_phase_id = state.current_phase_id
        result = exam_service.run_phase(email, exam_code, game, task_id)
        manifest = result['manifest'] or manifest
        state = result['state']

        append_exam_phase_execution(executed_phases, executed_phase_id, manifest, result)
        if executed_phase_id:
            save_exam_test_record(email, exam_code, game, task_id, executed_phase_id, result)

        if not result['success']:
            from common.state_machine.task_state_machine import TaskStateMachine
            sm = TaskStateMachine(manifest, state)
            next_action = sm.get_next_action()
            if next_action['action'] == 'max_attempts_reached':
                abandon_result = task_service.abandon_task(email, game, task_id, f"Maximum attempts reached for phase '{next_action['phase_id']}'")
                response = task_abandoned_response(abandon_result, result.get('report_url', ''))
                response = attach_exam_run_details(response, executed_phases, cleanup_triggered=cleanup_triggered_for_manifest(manifest))
                broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
                return response
            response = phase_failed_response(result, state, manifest)
            response = attach_exam_run_details(response, executed_phases)
            broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
            return response

        sm = __import__('common.state_machine.task_state_machine', fromlist=['TaskStateMachine']).TaskStateMachine(manifest, state)
        can_complete, _ = sm.can_complete_task()
        if can_complete:
            completion_result = task_service.complete_task(email, game, task_id, state)
            response = task_completed_response(completion_result, result['report_url'])
            response = attach_exam_run_details(response, executed_phases, cleanup_triggered=cleanup_triggered_for_manifest(manifest))
            broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
            return response

        if should_auto_chain_exam_phase(executed_phase_id, state.current_phase_id):
            continue

        response = phase_passed_response(result, state, manifest)
        response = attach_exam_run_details(response, executed_phases)
        broadcast_exam_response(email, exam_code, game, task_id, 'run', response)
        return response


def handle_exam_status(email: str, exam_code: str, game: Optional[str], task_id: Optional[str]) -> Dict[str, Any]:
    if not game or not task_id:
        return error_response("Missing required parameters: game or task")
    try:
        payload = exam_service.get_status(email, exam_code, game, task_id)
        state = payload['state']
        manifest = payload['manifest']
        next_action = None
        task_description = ''
        if state:
            from common.state_machine.task_state_machine import TaskStateMachine

            ensure_exam_challenge_before_check(state, manifest, exam_service.task_repo)
            next_action = TaskStateMachine(manifest, state).get_next_action()
            if state.current_phase_id == 'answer':
                next_phase = manifest.get_phase('challenge') or manifest.get_next_phase('answer')
                next_action = {
                    'action': 'execute_phase',
                    'phase_id': next_phase.id if next_phase else None,
                    'message': 'Solve the task, then click Run to continue.'
                }
            task_description = render_template(manifest.description or '', state.session_data)
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({
                'status': 'OK',
                'state': state.to_dict() if state else None,
                'manifest': manifest.to_dict(),
                'task_description': task_description,
                'next_action': next_action,
                'allowed_tasks': payload.get('allowed_tasks', []),
            }, cls=DecimalEncoder)
        }
    except ValueError as e:
        return error_response(str(e))


def handle_exam_records(email: str, exam_code: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    records = exam_service.list_records(email, exam_code, task_id=task_id)
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'OK',
            'records': records
        }, cls=DecimalEncoder)
    }


def cors_headers() -> Dict[str, str]:
    """Return CORS headers"""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': '*',
        'Access-Control-Allow-Headers': '*'
    }
