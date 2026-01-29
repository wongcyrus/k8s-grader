"""Tests for TestRunner service"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from common.services.test_runner import TestRunner
from common.models.phase_config import PhaseConfig
from common.status import TestResult


class TestTestRunner:
    """Test TestRunner service"""
    
    def test_run_phase_success(self, sample_phase_config):
        """Test running phase successfully"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.OK), \
             patch.object(runner, '_upload_report', return_value='https://report.url'):
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.OK
            assert report_url == 'https://report.url'
    
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
        """Test running phase with test failure"""
        runner = TestRunner()
        session_data = {
            '$endpoint': 'https://k8s.example.com',
            '$email': 'test@example.com'
        }
        
        with patch('common.file.create_json_input'), \
             patch('common.pytest.run_tests', return_value=TestResult.TESTS_FAILED), \
             patch.object(runner, '_upload_report', return_value='https://report.url'):
            
            result, report_url = runner.run_phase(
                'game01', '01_task', sample_phase_config, session_data
            )
            
            assert result == TestResult.TESTS_FAILED
            assert report_url == 'https://report.url'
    
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
