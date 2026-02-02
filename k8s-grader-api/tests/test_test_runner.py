"""Tests for TestRunner service"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from common.services.test_runner import TestRunner
from common.models.phase_config import PhaseConfig
from common.status import TestResult


class TestTestRunner:
    """Test TestRunner service"""
    
    def test_run_phase_success(self, sample_phase_config):
        """Test running phase successfully - no report upload on success"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.OK), \
             patch.object(runner, '_upload_report', return_value='https://report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.OK
            assert report_url == ""  # No report URL on success
            mock_upload.assert_not_called()  # Upload should NOT be called on success
    
    def test_run_phase_no_endpoint(self, sample_phase_config):
        """Test running phase without endpoint"""
        runner = TestRunner()
        session_data = {}  # No endpoint
        
        result, report_url = runner.run_phase(
            'game01', '01_task', sample_phase_config, session_data
        )
        
        assert result == TestResult.USAGE_ERROR
        assert report_url == ""
    
    def test_run_phase_test_failure(self, sample_phase_config):
        """Test running phase with test failure - report should be uploaded"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.TESTS_FAILED), \
             patch.object(runner, '_upload_report', return_value='https://report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.TESTS_FAILED
            assert report_url == 'https://report.url'
            mock_upload.assert_called_once()  # Upload SHOULD be called on failure
    
    def test_run_phase_file_not_found(self, sample_phase_config):
        """Test running phase when test file not found"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', side_effect=FileNotFoundError("Test file not found")):
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.NO_TESTS_COLLECTED
            assert report_url == ""
    
    def test_run_phase_internal_error(self, sample_phase_config):
        """Test running phase with internal error"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', side_effect=Exception("Internal error")):
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.INTERNAL_ERROR
            assert report_url == ""
    
    def test_upload_report_success(self):
        """Test uploading report successfully"""
        runner = TestRunner()
        
        with patch('common.s3.upload_test_result'), \
             patch('common.s3.generate_presigned_url', return_value='https://report.url'):
            
            url = runner._upload_report(
                'game01', '01_task', 'setup', '2024-01-01_12-00-00', 'test@example.com'
            )
            
            assert url == 'https://report.url'
    
    def test_upload_report_failure(self):
        """Test uploading report with failure"""
        runner = TestRunner()
        
        with patch('common.s3.upload_test_result', side_effect=Exception("Upload failed")):
            
            url = runner._upload_report(
                'game01', '01_task', 'setup', '2024-01-01_12-00-00', 'test@example.com'
            )
            
            assert url == ""
    
    def test_run_phase_timeout_uploads_report(self, sample_phase_config):
        """Test that timeout results upload a report"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.TIME_OUT), \
             patch.object(runner, '_upload_report', return_value='https://timeout-report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.TIME_OUT
            assert report_url == 'https://timeout-report.url'
            mock_upload.assert_called_once()
    
    def test_run_phase_usage_error_uploads_report(self, sample_phase_config):
        """Test that usage errors upload a report"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.USAGE_ERROR), \
             patch.object(runner, '_upload_report', return_value='https://error-report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.USAGE_ERROR
            assert report_url == 'https://error-report.url'
            mock_upload.assert_called_once()
    
    def test_run_phase_internal_error_uploads_report(self, sample_phase_config):
        """Test that internal errors upload a report"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.INTERNAL_ERROR), \
             patch.object(runner, '_upload_report', return_value='https://internal-error-report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.INTERNAL_ERROR
            assert report_url == 'https://internal-error-report.url'
            mock_upload.assert_called_once()
    
    def test_run_phase_no_tests_collected_uploads_report(self, sample_phase_config):
        """Test that NO_TESTS_COLLECTED uploads a report"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.NO_TESTS_COLLECTED), \
             patch.object(runner, '_upload_report', return_value='https://no-tests-report.url') as mock_upload:
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.NO_TESTS_COLLECTED
            assert report_url == 'https://no-tests-report.url'
            mock_upload.assert_called_once()
