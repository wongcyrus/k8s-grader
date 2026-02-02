"""
Test that pytest.py correctly handles both string and enum inputs.

This test verifies the fix for the KeyError bug where test_runner.py
was passing string phase IDs ('check', 'cleanup') but run_tests() 
expected GamePhrase enums.
"""
import pytest
from unittest.mock import patch, MagicMock
from common.pytest import run_tests, get_next_game_phrase
from common.status import GamePhrase, TestResult


class TestStringEnumConversion:
    """Test that run_tests handles both string and enum inputs"""
    
    @patch('common.pytest.get_tests')
    @patch('common.pytest.pytest.main')
    def test_run_tests_with_string_phase(self, mock_pytest_main, mock_get_tests):
        """Test run_tests accepts string phase ID"""
        mock_pytest_main.return_value = 0
        mock_get_tests.return_value = None
        
        # Pass string instead of enum (this is what test_runner.py does)
        result = run_tests('check', 'game01', '01_default_namespace')
        
        # Should convert string to enum and work correctly
        assert result == TestResult.OK
        assert mock_pytest_main.called
    
    @patch('common.pytest.get_tests')
    @patch('common.pytest.pytest.main')
    def test_run_tests_with_enum_phase(self, mock_pytest_main, mock_get_tests):
        """Test run_tests still accepts enum phase"""
        mock_pytest_main.return_value = 0
        mock_get_tests.return_value = None
        
        # Pass enum (backward compatibility)
        result = run_tests(GamePhrase.CHECK, 'game01', '01_default_namespace')
        
        assert result == TestResult.OK
        assert mock_pytest_main.called
    
    @patch('common.pytest.get_tests')
    def test_run_tests_with_string_answer_phase(self, mock_get_tests):
        """Test answer phase skip works with string input"""
        mock_get_tests.return_value = None
        
        # Pass 'answer' as string
        result = run_tests('answer', 'game01', '02_create_namespace')
        
        # Should skip and return NO_TESTS_COLLECTED
        assert result == TestResult.NO_TESTS_COLLECTED
    
    @patch('common.pytest.get_tests')
    def test_run_tests_with_enum_answer_phase(self, mock_get_tests):
        """Test answer phase skip works with enum input"""
        mock_get_tests.return_value = None
        
        # Pass GamePhrase.ANSWER enum
        result = run_tests(GamePhrase.ANSWER, 'game01', '02_create_namespace')
        
        # Should skip and return NO_TESTS_COLLECTED
        assert result == TestResult.NO_TESTS_COLLECTED
    
    @patch('common.pytest.get_tests')
    def test_run_tests_with_invalid_string(self, mock_get_tests):
        """Test run_tests handles invalid phase string"""
        mock_get_tests.return_value = None
        
        # Pass invalid string
        result = run_tests('invalid_phase', 'game01', '01_default_namespace')
        
        # Should return USAGE_ERROR
        assert result == TestResult.USAGE_ERROR
    
    @patch('common.pytest.get_tests')
    @patch('common.pytest.os.path.exists')
    def test_get_next_game_phrase_with_string(self, mock_exists, mock_get_tests):
        """Test get_next_game_phrase accepts string input"""
        mock_get_tests.return_value = None
        mock_exists.return_value = True
        
        # Pass string instead of enum
        result = get_next_game_phrase('game01', '01_default_namespace', 'setup')
        
        # Should convert and return next phase
        assert result == GamePhrase.READY
    
    @patch('common.pytest.get_tests')
    @patch('common.pytest.os.path.exists')
    def test_get_next_game_phrase_with_enum(self, mock_exists, mock_get_tests):
        """Test get_next_game_phrase still accepts enum"""
        mock_get_tests.return_value = None
        mock_exists.return_value = True
        
        # Pass enum (backward compatibility)
        result = get_next_game_phrase('game01', '01_default_namespace', GamePhrase.SETUP)
        
        assert result == GamePhrase.READY
    
    @patch('common.pytest.get_tests')
    def test_get_next_game_phrase_with_invalid_string(self, mock_get_tests):
        """Test get_next_game_phrase handles invalid string"""
        mock_get_tests.return_value = None
        
        # Pass invalid string
        result = get_next_game_phrase('game01', '01_default_namespace', 'invalid')
        
        # Should return None
        assert result is None


class TestRealWorldScenario:
    """Test the actual scenario from test_runner.py"""
    
    @patch('common.pytest.get_tests')
    @patch('common.pytest.pytest.main')
    def test_test_runner_scenario(self, mock_pytest_main, mock_get_tests):
        """
        Simulate what test_runner.py does:
        - PhaseConfig.id is a string ('check', 'cleanup', etc.)
        - test_runner passes phase.id to run_tests()
        - run_tests must handle the string
        """
        mock_pytest_main.return_value = 0
        mock_get_tests.return_value = None
        
        # Simulate PhaseConfig with string id
        phase_id = 'check'  # This is what PhaseConfig.id contains
        
        # This is what test_runner.py does
        result = run_tests(phase_id, 'game01', '02_create_namespace')
        
        # Should work without KeyError
        assert result == TestResult.OK
        assert mock_pytest_main.called
        
        # Verify the correct test file path was used
        call_args = mock_pytest_main.call_args[0][0]
        assert 'test_05_check.py' in call_args[-1]
