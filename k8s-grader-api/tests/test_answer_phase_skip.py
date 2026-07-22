"""
Behavior tests for answer phase execution.

This test ensures that:
1. Answer phase runs test_03_answer.py
2. Setup, answer, and check phases all execute normally
3. The phase mapping stays aligned with the standard task files
"""
import pytest
import os
import sys
import subprocess
from unittest.mock import MagicMock, patch

# Add common layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common-layer'))

from common.status import GamePhrase, TestResult
from common.pytest import run_tests


class TestAnswerPhaseExecutionBehavior:
    """Test that answer phase executes the standard answer test file"""
    
    def test_answer_phase_runs_standard_answer_test(self):
        """
        Answer phase must execute test_03_answer.py.
        """
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.subprocess.run', return_value=MagicMock(returncode=0)) as mock_subprocess_run:
            result = run_tests(
                test_phase=GamePhrase.ANSWER,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        assert result == TestResult.OK
        call_args = mock_subprocess_run.call_args[0][0]
        assert 'test_03_answer.py' in call_args[-1]
    
    def test_setup_phase_runs_normally(self):
        """
        Test that setup phase still runs (not skipped)
        """
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.subprocess.run', return_value=MagicMock(returncode=0)):
            result = run_tests(
                test_phase=GamePhrase.SETUP,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        assert result == TestResult.OK, \
            "Setup phase should run normally and return OK"
    
    def test_check_phase_runs_normally(self):
        """
        Test that check phase still runs (not skipped)
        """
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.subprocess.run', return_value=MagicMock(returncode=0)):
            result = run_tests(
                test_phase=GamePhrase.CHECK,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        assert result == TestResult.OK, \
            "Check phase should run normally and return OK"
    
    def test_challenge_phase_runs_normally(self):
        """
        Test that challenge phase still runs (not skipped)
        """
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.subprocess.run', return_value=MagicMock(returncode=0)):
            result = run_tests(
                test_phase=GamePhrase.CHALLENGE,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        assert result == TestResult.OK, \
            "Challenge phase should run normally and return OK"
    
    def test_all_standard_phases_run(self):
        """
        Verify that the standard phase files all run, including answer.
        """
        phases_to_test = [
            (GamePhrase.SETUP, TestResult.OK, "Setup should run"),
            (GamePhrase.READY, TestResult.OK, "Ready should run"),
            (GamePhrase.ANSWER, TestResult.OK, "Answer should run"),
            (GamePhrase.CHALLENGE, TestResult.OK, "Challenge should run"),
            (GamePhrase.CHECK, TestResult.OK, "Check should run"),
            (GamePhrase.CLEANUP, TestResult.OK, "Cleanup should run"),
        ]
        
        for phase, expected_result, message in phases_to_test:
            with patch('common.pytest.get_tests'), \
                 patch('common.pytest.subprocess.run', return_value=MagicMock(returncode=0)):
                result = run_tests(
                    test_phase=phase,
                    game='game01',
                    task='test_task',
                    timeout=30
                )
                
                assert result == expected_result, \
                    f"{message}. Got {result}, expected {expected_result}"


class TestGame01Task02ExpectedBehavior:
    """
    Expected behavior for game01/02_create_namespace
    Based on hardcoded session data
    """
    
    def test_instruction_message_rendering(self):
        """
        Test that instruction message is rendered with session variables
        
        Session data (hardcoded based on DB):
        - namespace: blissfularyabhata2developer
        """
        from jinja2 import Environment
        
        template = "Create a namespace called '{{namespace}}'."
        session_data = {
            'namespace': 'blissfularyabhata2developer',
            '$email': 'developer@example.com'
        }
        
        env = Environment()
        jinja_template = env.from_string(template)
        rendered = jinja_template.render(session_data)
        
        expected = "Create a namespace called 'blissfularyabhata2developer'."
        assert rendered == expected, \
            f"Template should render correctly. Got: {rendered}"


class TestPytestExecution:
    def test_timeout_returns_timeout_result(self):
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=30)):
            result = run_tests(
                test_phase=GamePhrase.CHECK,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )

        assert result == TestResult.TIME_OUT
    
    def test_expected_flow_description(self):
        """
        Document the expected flow for task 02_create_namespace
        
        This is a documentation test that describes expected behavior.
        """
        expected_flow = """
        Expected Flow for game01/02_create_namespace:
        
        1. Player talks to NPC
        2. Setup phase runs → OK
        3. Answer phase runs → Executes test_03_answer.py
        4. Check phase runs → Validates the task result
        5. If passed: Task complete, player earns points
        """
        
        # This test always passes - it's documentation
        assert True, expected_flow


class TestGame01Task01ExpectedBehavior:
    """
    Expected behavior for game01/01_default_namespace (auto-check task)
    """
    
    def test_expected_flow_description(self):
        """
        Document the expected flow for task 01_default_namespace
        
        This task has NO answer phase (auto-check only).
        """
        expected_flow = """
        Expected Flow for game01/01_default_namespace:
        
        1. Player talks to NPC
        2. Setup phase runs → OK
        3. Check phase runs → Validates default namespace exists
           Message: "Please provide the Kubernetes confidential information..."
        4. If default namespace exists: PASS ✅
        5. Task complete
        
        NOTE: This is an auto-check task. Player doesn't need to do anything.
        It just validates K8s credentials work.
        """
        
        # This test always passes - it's documentation
        assert True, expected_flow


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
