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
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_missing_parameters(self, mock_get_email):
        """Test with missing parameters"""
        # Mock returns None for missing parameters
        mock_get_email.return_value = (None, None, None)
        
        event = {
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'}
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'Missing required parameters' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_invalid_game_format(self, mock_get_email):
        """Test with invalid game format"""
        mock_get_email.return_value = ('test@example.com', 'game-01', 'npc1')
        
        event = {
            'queryStringParameters': {
                'email': 'test@example.com',
                'game': 'game-01',  # Invalid: contains hyphen
                'npc': 'npc1'
            },
            'headers': {'x-api-key': 'test-key'}
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'alphanumeric' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_npc_not_found(self, mock_get_email, api_event):
        """Test with NPC not found"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value=None):
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'ERROR'
            assert 'not found' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_random_chat(self, mock_get_email, api_event):
        """Test random chat response"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.1), \
             patch('app.get_ai_random_chat', return_value='Hello there!'):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'OK'
            assert body['message'] == 'Hello there!'
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_npc_locked(self, mock_get_email, api_event, dynamodb_tables):
        """Test with locked NPC"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5):
            
            # Lock the NPC
            from common.database.repositories import NpcRepository
            npc_repo = NpcRepository()
            npc_repo.lock_npc('test@example.com', 'game01', 'npc1', minutes=30)
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'ERROR'
            assert 'does not have any task' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_different_npc_assigned(self, mock_get_email, api_event, dynamodb_tables):
        """Test with different NPC assigned"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5):
            
            # Assign task from different NPC
            from common.database.repositories import NpcRepository
            npc_repo = NpcRepository()
            npc_repo.assign_task('test@example.com', 'game01', 'npc2', '01_task')
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'ERROR'
            assert 'Complete task from npc2' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_user_not_found(self, mock_get_email, api_event):
        """Test with user not found"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.task_service.validate_npc_access', return_value=(True, None)), \
             patch('app.get_user_data', return_value=None):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'ERROR'
            assert 'User account not found' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_all_tasks_completed(self, mock_get_email, api_event, mock_user_data, dynamodb_tables):
        """Test when all tasks are completed"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.get_current_task', return_value=None):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'OK'
            assert 'Congratulations' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_start_new_task(self, mock_get_email, api_event, mock_user_data, sample_task_state, sample_manifest, dynamodb_tables):
        """Test starting a new task"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.get_current_task', return_value='01_task'), \
             patch('app.task_service.start_task', return_value=sample_task_state), \
             patch('common.models.task_manifest.TaskManifest.load', return_value=sample_manifest):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'STARTED'
            assert body['task_id'] == '01_test_task'
            assert body['progress'] == 0.0
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_execute_phase_success(self, mock_get_email, api_event, mock_user_data, in_progress_task_state, 
                                   sample_manifest, dynamodb_tables):
        """Test executing phase successfully"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        # Setup state
        in_progress_task_state.current_phase_id = 'setup'
        
        execute_result = {
            'success': True,
            'test_result': TestResult.OK,
            'report_url': 'https://report.url',
            'state': in_progress_task_state,
            'manifest': sample_manifest
        }
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.validate_npc_access', return_value=(True, None)), \
             patch('app.task_service.get_current_task', return_value='01_task'), \
             patch('common.database.repositories.TaskStateRepository.get', return_value=in_progress_task_state), \
             patch('app.task_service.execute_phase', return_value=execute_result):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'OK'
            assert 'report_url' in body
            assert 'progress' in body
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_execute_phase_failure(self, mock_get_email, api_event, mock_user_data, in_progress_task_state, 
                                   sample_manifest, dynamodb_tables):
        """Test executing phase with failure"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        in_progress_task_state.current_phase_id = 'setup'
        
        execute_result = {
            'success': False,
            'error': 'Tests failed',
            'test_result': TestResult.TESTS_FAILED,
            'report_url': 'https://report.url',
            'state': in_progress_task_state,
            'manifest': sample_manifest
        }
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.validate_npc_access', return_value=(True, None)), \
             patch('app.task_service.get_current_task', return_value='01_task'), \
             patch('common.database.repositories.TaskStateRepository.get', return_value=in_progress_task_state), \
             patch('app.task_service.execute_phase', return_value=execute_result):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'FAILED'
            assert 'Initialize' in body['message'] or 'environment' in body['message']
    
    @patch('app.get_email_game_and_npc_from_event')
    def test_complete_task(self, mock_get_email, api_event, mock_user_data, in_progress_task_state, 
                          sample_manifest, dynamodb_tables):
        """Test completing a task"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        # Mark all phases as passed
        in_progress_task_state.phase_states['setup'] = PhaseState('setup', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['challenge'] = PhaseState('challenge', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['check'] = PhaseState('check', PhaseStatus.PASSED)
        in_progress_task_state.total_points = 150
        
        execute_result = {
            'success': True,
            'test_result': TestResult.OK,
            'report_url': 'https://report.url',
            'state': in_progress_task_state,
            'manifest': sample_manifest
        }
        
        completion_result = {
            'success': True,
            'state': in_progress_task_state,
            'total_points': 150
        }
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.validate_npc_access', return_value=(True, None)), \
             patch('app.task_service.get_current_task', return_value='01_task'), \
             patch('common.database.repositories.TaskStateRepository.get', return_value=in_progress_task_state), \
             patch('app.task_service.execute_phase', return_value=execute_result), \
             patch('app.task_service.complete_task', return_value=completion_result), \
             patch('app.get_easter_egg_link', return_value='https://easter.egg'):
            
            response = lambda_handler(api_event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['status'] == 'COMPLETED'
            assert body['total_points'] == 150
            assert 'easter_egg_url' in body

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

    @patch('app.get_email_game_and_npc_from_event')
    def test_task_route_denies_exam_mode_game(self, mock_get_email, api_event):
        """Test that the legacy /task route blocks exam-mode games"""
        mock_get_email.return_value = ('student@example.com', 'exam01', 'npc1')
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.game_access_repo.get_mode', return_value='exam'):
            response = lambda_handler(api_event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'ERROR'
        assert 'exam mode' in body['message']


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
