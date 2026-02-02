"""Unified task handler - replaces game-task and grader endpoints"""
# DEPLOYMENT: 2026-02-02 - Bug fixes for task completion
import json
import logging
import random
from decimal import Decimal
from typing import Dict, Any, Optional
from jinja2 import Environment

from common.handler import (
    get_email_game_and_npc_from_event,
    extract_k8s_credentials,
    setup_paths
)
from common.database import get_user_data, get_npc_background, get_ai_random_chat
from common.services.task_service import TaskService
from common.file import clear_tmp_directory, write_user_files
from common.google_spreadsheet import get_easter_egg_link
from common.status import TestResult
from common.models.task_state import TaskStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Unified task handler - replaces /game-task and /grader"""
    
    try:
        # Extract parameters
        email, game, npc = get_email_game_and_npc_from_event(event)
        if not email or not game or not npc:
            return error_response("Missing required parameters: email, game, or npc")
        
        # Validate game format
        if not game.isalnum():
            return error_response("Game parameter must be alphanumeric")
        
        # Get NPC background
        npc_background = get_npc_background(npc)
        if not npc_background:
            return error_response(f"NPC '{npc}' not found")
        
        # Random chat (30% chance)
        if random.random() < 0.3:
            message = get_ai_random_chat(npc)
            return ok_response(message or "...")
        
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
    
    # Render template variables with session data
    phase_message = render_template(phase_message, state.session_data)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'STARTED',
            'task_id': state.task_id,
            'current_phase': state.current_phase_id,
            'phase_name': current_phase.name if current_phase else '',
            'message': phase_message,
            'progress': 0.0
        }, cls=DecimalEncoder)
    }


def phase_passed_response(result, state, manifest) -> Dict[str, Any]:
    """Return response for passed phase"""
    # Use updated state from result consistently
    updated_state = result['state']
    progress = updated_state.calculate_progress(manifest)
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
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'OK',
            'current_phase': updated_state.current_phase_id,
            'phase_name': next_phase.name if next_phase else '',
            'next_phase': next_phase.id if next_phase else None,
            'message': next_phase_message,
            'report_url': result['report_url'],
            'progress': progress,
            'points': updated_state.total_points
        }, cls=DecimalEncoder)
    }


def phase_failed_response(result, state, manifest) -> Dict[str, Any]:
    """Return response for failed phase"""
    phase_state = state.get_phase_state(state.current_phase_id)
    
    # Get current phase info
    current_phase = manifest.get_phase(state.current_phase_id)
    phase_message = current_phase.description if current_phase else 'Tests failed. Check the report.'
    
    # Render template variables with session data
    phase_message = render_template(phase_message, state.session_data)
    
    # Get encouragement easter egg for failure
    test_result = result.get('test_result', TestResult.TESTS_FAILED)
    easter_egg = get_easter_egg_link(test_result)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'FAILED',
            'current_phase': state.current_phase_id,
            'phase_name': current_phase.name if current_phase else '',
            'next_phase': state.current_phase_id,  # Retry same phase
            'message': phase_message,
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
    
    # Get encouragement easter egg for abandonment (use TESTS_FAILED as the result type)
    easter_egg = get_easter_egg_link(TestResult.TESTS_FAILED)
    
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps({
            'status': 'ABANDONED',
            'task_id': state.task_id,
            'message': f'❌ Task abandoned: {reason}. You can try again with the same NPC.',
            'reason': reason,
            'report_url': report_url,
            'easter_egg_url': easter_egg or '',
            'progress': 0.0,
            'total_points': state.total_points
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
