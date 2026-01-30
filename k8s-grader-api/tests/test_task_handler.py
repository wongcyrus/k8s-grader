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
    def test_start_new_task(self, mock_get_email, api_event, mock_user_data, sample_task_state, dynamodb_tables):
        """Test starting a new task"""
        mock_get_email.return_value = ('test@example.com', 'game01', 'npc1')
        
        with patch('app.get_npc_background', return_value={'name': 'npc1'}), \
             patch('app.random.random', return_value=0.5), \
             patch('app.get_user_data', return_value=mock_user_data), \
             patch('app.extract_k8s_credentials', return_value=('cert', 'key', 'endpoint')), \
             patch('app.clear_tmp_directory'), \
             patch('app.write_user_files'), \
             patch('app.task_service.get_current_task', return_value='01_task'), \
             patch('app.task_service.start_task', return_value=sample_task_state):
            
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
            assert 'Tests failed' in body['message']
    
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
    
    def test_task_started_response(self, sample_task_state):
        """Test task started response"""
        sample_task_state.status = TaskStatus.IN_PROGRESS
        sample_task_state.current_phase_id = 'setup'
        sample_task_state.session_data['$instruction'] = 'Start the task'
        
        response = task_started_response(sample_task_state)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'STARTED'
        assert body['task_id'] == '01_test_task'
        assert body['current_phase'] == 'setup'
        assert body['message'] == 'Start the task'
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
        assert body['points'] == 100
        assert 'progress' in body
    
    def test_phase_failed_response(self, in_progress_task_state):
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
        
        response = phase_failed_response(result, in_progress_task_state)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'FAILED'
        assert body['current_phase'] == 'setup'
        assert body['attempts'] == 2
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
