"""Tests for unified task handler Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock

# Import the handler
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'task-handler'))

from app import (
    lambda_handler,
    error_response,
    ok_response,
    task_started_response,
    phase_passed_response,
    phase_failed_response,
    task_completed_response
)

from common.models.task_state import TaskState, TaskStatus, PhaseState, PhaseStatus
from common.status import TestResult


@pytest.fixture
def api_event():
    """Sample API Gateway event"""
    return {
        'path': '/task',
        'queryStringParameters': {
            'email': 'test@example.com',
            'game': 'game01',
            'npc': 'npc1'
        },
        'headers': {
            'x-api-key': 'test-api-key'
        }
    }


@pytest.fixture
def mock_user_data():
    """Mock user data with K8s credentials"""
    return {
        'email': 'test@example.com',
        'client_certificate': 'cert_data',
        'client_key': 'key_data',
        'endpoint': 'https://k8s.example.com'
    }


class TestLambdaHandler:
    """Test Lambda handler"""

    def test_legacy_task_route_removed(self, api_event):
        """Non-exam routes should reject the removed legacy game API."""
        response = lambda_handler(api_event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'legacy game request API was removed' in body['message']

    @patch('app.get_email_from_event')
    def test_exam_verify_code_route(self, mock_get_email, api_event):
        """Test verifying an exam code via the exam route"""
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/exam/verify-code',
            'queryStringParameters': {'examCode': 'EXAM-001'},
            'headers': {'x-api-key': 'test-key'}
        }

        with patch('app.exam_service.verify_code', return_value={
            'email': 'student@example.com',
            'exam_code': 'EXAM-001',
            'session_id': 'session-1',
            'game': 'exam01',
            'allowed_tasks': ['exam_task_01'],
            'max_attempts': 3,
        }):
            response = lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'VERIFIED'
        assert body['exam_code'] == 'EXAM-001'

    @patch('app.get_email_from_event')
    def test_exam_reset_route_dispatch(self, mock_get_email):
        """Test that /exam/reset dispatches to reset handler."""
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/exam/reset',
            'queryStringParameters': {
                'examCode': 'EXAM-001',
                'game': 'game02',
                'task': '087_kustomize_configuration',
            },
            'headers': {'x-api-key': 'test-key'}
        }

        with patch('app.handle_exam_reset', return_value=ok_response("reset ok")) as mock_reset:
            response = lambda_handler(event, None)

        assert mock_reset.call_count == 1
        assert response['statusCode'] == 200

    @patch('app.get_email_from_event')
    def test_exam_run_async_invokes_durable_function(self, mock_get_email):
        """Async exam run should queue the durable Lambda function."""
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/exam/run',
            'queryStringParameters': {
                'examCode': 'EXAM-001',
                'game': 'game02',
                'task': '087_kustomize_configuration',
                'async': 'true',
            },
            'headers': {'x-api-key': 'test-key'}
        }

        state = TaskState(
            email='student@example.com',
            game='game02',
            task_id='087_kustomize_configuration',
            npc='exam',
            status=TaskStatus.IN_PROGRESS,
            current_phase_id='setup',
            mode='exam',
            session_data={}
        )
        phase = Mock()
        phase.name = 'Setup'
        manifest = Mock()
        manifest.get_phase.return_value = phase

        with patch('app.exam_service.authorize', return_value=(True, '', {})), \
             patch('app.exam_service.task_repo.get', return_value=state), \
             patch('common.models.task_manifest.TaskManifest.load', return_value=manifest), \
             patch('app.invoke_durable_function', return_value='request-123') as mock_start, \
             patch('app.broadcast_exam_update') as mock_broadcast:
            response = lambda_handler(event, None)

        mock_start.assert_called_once()
        mock_broadcast.assert_called_once()
        body = json.loads(response['body'])
        assert body['status'] == 'QUEUED'
        assert body['request_id'] == 'request-123'

    @patch('app.get_email_from_event')
    def test_exam_reset_rejects_completed_status(self, mock_get_email):
        """Student reset must be blocked for completed tasks."""
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/exam/reset',
            'queryStringParameters': {
                'examCode': 'EXAM-001',
                'game': 'game02',
                'task': '087_kustomize_configuration',
            },
            'headers': {'x-api-key': 'test-key'}
        }

        completed_state = TaskState(
            email='student@example.com',
            game='game02',
            task_id='087_kustomize_configuration',
            npc='exam',
            status=TaskStatus.COMPLETED,
            current_phase_id='check',
            mode='exam',
            session_data={}
        )

        with patch('app.exam_service.authorize', return_value=(True, '', {})), \
             patch('app.exam_service.task_repo.get', return_value=completed_state):
            response = lambda_handler(event, None)

        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'not allowed after task completion' in body['message']

    @patch('app.get_email_from_event')
    def test_exam_start_resets_abandoned_state(self, mock_get_email):
        """Test abandoned exam state is reset when start is called."""
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/exam/start',
            'queryStringParameters': {
                'examCode': 'EXAM-001',
                'game': 'game02',
                'task': '087_kustomize_configuration',
            },
            'headers': {'x-api-key': 'test-key'}
        }

        abandoned_state = TaskState(
            email='student@example.com',
            game='game02',
            task_id='087_kustomize_configuration',
            npc='exam',
            status=TaskStatus.ABANDONED,
            current_phase_id='check',
            mode='exam',
            session_data={}
        )
        fresh_state = TaskState(
            email='student@example.com',
            game='game02',
            task_id='087_kustomize_configuration',
            npc='exam',
            status=TaskStatus.IN_PROGRESS,
            current_phase_id='setup',
            mode='exam',
            session_data={}
        )

        phase = Mock()
        phase.name = 'Setup'
        phase.description = 'Initialize'
        manifest = Mock()
        manifest.get_phase.return_value = phase

        with patch('app.exam_service.authorize', return_value=(True, '', {})), \
             patch('app.get_user_data', return_value={
                 'email': 'student@example.com',
                 'client_certificate': 'cert_data',
                 'client_key': 'key_data',
                 'endpoint': 'https://k8s.example.com'
             }), \
             patch('app.extract_k8s_credentials', return_value=('cert_data', 'key_data', 'https://k8s.example.com')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('common.models.task_manifest.TaskManifest.load', return_value=manifest), \
             patch('app.exam_service.ensure_state', return_value=abandoned_state), \
             patch('app.exam_service.task_repo.delete') as mock_delete, \
             patch('app.exam_service.task_service.start_exam_task', return_value=fresh_state) as mock_start_exam_task, \
             patch('app.exam_service.task_repo.save'):
            response = lambda_handler(event, None)

        mock_delete.assert_called_once_with('student@example.com', 'game02', '087_kustomize_configuration')
        mock_start_exam_task.assert_called_once_with(
            'student@example.com', 'game02', '087_kustomize_configuration', 'EXAM-001'
        )
        body = json.loads(response['body'])
        assert body['status'] == 'STARTED'
        assert body['current_phase'] == 'setup'

    @patch.dict(os.environ, {'TeacherEmails': 'teacher@example.com'}, clear=False)
    @patch('app.get_email_from_event')
    def test_teacher_overview_route(self, mock_get_email):
        mock_get_email.return_value = 'teacher@example.com'
        event = {
            'path': '/teacher/overview',
            'queryStringParameters': {},
            'headers': {'x-api-key': 'teacher-key'}
        }

        with patch('app.teacher_dashboard_service.list_students', return_value=[
            {'email': 'student@example.com', 'status': 'ACTIVE'}
        ]) as mock_list:
            response = lambda_handler(event, None)

        mock_list.assert_called_once()
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['teacher_email'] == 'teacher@example.com'
        assert body['students'][0]['email'] == 'student@example.com'

    @patch.dict(os.environ, {'TeacherEmails': 'teacher@example.com'}, clear=False)
    @patch('app.get_email_from_event')
    def test_teacher_overview_route_includes_teacher_accounts(self, mock_get_email):
        mock_get_email.return_value = 'teacher@example.com'
        event = {
            'path': '/teacher/overview',
            'queryStringParameters': {},
            'headers': {'x-api-key': 'teacher-key'}
        }

        with patch('app.teacher_dashboard_service.list_students', return_value=[
            {'email': 'teacher@example.com', 'status': 'FINISHED'},
            {'email': 'student@example.com', 'status': 'ACTIVE'},
        ]):
            response = lambda_handler(event, None)

        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert [item['email'] for item in body['students']] == [
            'teacher@example.com',
            'student@example.com',
        ]

    @patch.dict(os.environ, {'TeacherEmails': 'teacher@example.com'}, clear=False)
    @patch('app.get_email_from_event')
    def test_teacher_student_route(self, mock_get_email):
        mock_get_email.return_value = 'teacher@example.com'
        event = {
            'path': '/teacher/student',
            'queryStringParameters': {
                'studentEmail': 'student@example.com',
                'game': 'game01',
                'mode': 'exam',
                'examCode': 'EXAM-001',
            },
            'headers': {'x-api-key': 'teacher-key'}
        }

        with patch('app.teacher_dashboard_service.get_student_detail', return_value={
            'student': {'email': 'student@example.com'},
            'task_states': [],
            'exam_sessions': [],
            'reports': [],
        }) as mock_detail:
            response = lambda_handler(event, None)

        mock_detail.assert_called_once_with(
            'student@example.com',
            game='game01',
            mode='exam',
            exam_code='EXAM-001',
        )
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['student']['email'] == 'student@example.com'

    def test_portal_games_route(self):
        event = {
            'path': '/portal/games',
            'queryStringParameters': {},
            'headers': {}
        }

        with patch('app.game_source_repo.list_games', return_value=['game01', 'game02']) as mock_list, \
             patch('app.game_access_repo.get_mode', side_effect=['exercise', 'exercise']) as mock_get_mode:
            response = lambda_handler(event, None)

        mock_list.assert_called_once()
        assert mock_get_mode.call_count == 2
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['games'] == ['game01', 'game02']

    def test_portal_games_route_filters_exam_only_games(self):
        event = {
            'path': '/portal/games',
            'queryStringParameters': {},
            'headers': {}
        }

        with patch('app.game_source_repo.list_games', return_value=['game01', 'game02', 'game03']) as mock_list, \
             patch('app.game_access_repo.get_mode', side_effect=['exercise', 'exam', 'exercise']) as mock_get_mode:
            response = lambda_handler(event, None)

        mock_list.assert_called_once()
        assert mock_get_mode.call_count == 3
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['games'] == ['game01', 'game03']

    @patch.dict(os.environ, {'TeacherEmails': 'teacher@example.com'}, clear=False)
    @patch('app.get_email_from_event')
    def test_teacher_route_rejects_non_teacher(self, mock_get_email):
        mock_get_email.return_value = 'student@example.com'
        event = {
            'path': '/teacher/overview',
            'queryStringParameters': {},
            'headers': {'x-api-key': 'student-key'}
        }

        response = lambda_handler(event, None)

        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'Teacher access denied' in body['message']

class TestResponseHelpers:
    """Test response helper functions"""
    
    def test_error_response(self):
        """Test error response format"""
        response = error_response("Test error")
        
        assert response['statusCode'] == 200
        assert 'Content-Type' in response['headers']
        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert body['message'] == 'Test error'
    
    def test_ok_response(self):
        """Test OK response format"""
        response = ok_response("Test message")
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['message'] == 'Test message'
    
    def test_task_started_response(self, sample_task_state, sample_manifest):
        """Test task started response"""
        sample_task_state.status = TaskStatus.IN_PROGRESS
        sample_task_state.current_phase_id = 'setup'
        
        response = task_started_response(sample_task_state, sample_manifest)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'STARTED'
        assert body['task_id'] == '01_test_task'
        assert body['current_phase'] == 'setup'
        assert body['phase_name'] == 'Setup'
        assert 'Initialize environment' in body['message']
        assert body['progress'] == 0.0
    
    def test_phase_passed_response(self, in_progress_task_state, sample_manifest):
        """Test phase passed response"""
        in_progress_task_state.current_phase_id = 'challenge'
        in_progress_task_state.total_points = 100
        
        result = {
            'state': in_progress_task_state,
            'report_url': 'https://report.url'
        }
        
        response = phase_passed_response(result, in_progress_task_state, sample_manifest)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'OK'
        assert body['current_phase'] == 'challenge'
        assert body['phase_name'] == 'Challenge'
        assert body['points'] == 100
        assert 'progress' in body
    
    def test_phase_failed_response(self, in_progress_task_state, sample_manifest):
        """Test phase failed response"""
        in_progress_task_state.current_phase_id = 'setup'
        phase_state = PhaseState('setup', PhaseStatus.FAILED)
        phase_state.attempts = 2
        in_progress_task_state.phase_states['setup'] = phase_state
        
        result = {
            'error': 'Tests failed',
            'test_result': TestResult.TESTS_FAILED,
            'report_url': 'https://report.url'
        }
        
        response = phase_failed_response(result, in_progress_task_state, sample_manifest)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'FAILED'
        assert body['current_phase'] == 'setup'
        assert body['phase_name'] == 'Setup'
        assert 'Initialize environment' in body['message']
        assert body['attempts'] == 2
        assert body['max_attempts'] == 3
        assert body['test_result'] == 'TESTS_FAILED'
    
    def test_task_completed_response(self, in_progress_task_state):
        """Test task completed response"""
        in_progress_task_state.status = TaskStatus.COMPLETED
        in_progress_task_state.total_points = 150
        
        completion_result = {
            'state': in_progress_task_state,
            'total_points': 150
        }
        
        with patch('app.get_easter_egg_link', return_value='https://easter.egg'):
            response = task_completed_response(completion_result, 'https://report.url')
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'COMPLETED'
            assert body['total_points'] == 150
            assert body['progress'] == 1.0
            assert body['easter_egg_url'] == 'https://easter.egg'
