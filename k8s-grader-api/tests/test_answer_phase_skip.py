"""
Behavior test to verify answer phase is skipped in production.

This test ensures that:
1. Answer phase returns NO_TESTS_COLLECTED (skipped)
2. Setup and check phases run normally
3. Players must do actual work to pass
"""
import pytest
import os
import sys
from unittest.mock import patch

# Add common layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common-layer'))

from common.status import GamePhrase, TestResult
from common.pytest import run_tests


class TestAnswerPhaseSkipBehavior:
    """Test that answer phase is skipped and players must do actual work"""
    
    def test_answer_phase_returns_no_tests_collected(self):
        """
        CRITICAL TEST: Answer phase must be skipped
        
        This ensures players cannot auto-complete tasks.
        """
        # Mock get_tests to avoid downloading
        with patch('common.pytest.get_tests'):
            result = run_tests(
                test_phase=GamePhrase.ANSWER,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        # Answer phase MUST be skipped
        assert result == TestResult.NO_TESTS_COLLECTED, \
            "❌ CRITICAL: Answer phase should return NO_TESTS_COLLECTED (skipped). " \
            "If this fails, players can auto-complete tasks without doing work!"
    
    def test_setup_phase_runs_normally(self):
        """
        Test that setup phase still runs (not skipped)
        """
        with patch('common.pytest.get_tests'), \
             patch('common.pytest.pytest.main', return_value=0):
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
             patch('common.pytest.pytest.main', return_value=0):
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
             patch('common.pytest.pytest.main', return_value=0):
            result = run_tests(
                test_phase=GamePhrase.CHALLENGE,
                game='game01',
                task='02_create_namespace',
                timeout=30
            )
        
        assert result == TestResult.OK, \
            "Challenge phase should run normally and return OK"
    
    def test_only_answer_phase_is_skipped(self):
        """
        Verify that ONLY answer phase is skipped, all others run
        """
        phases_to_test = [
            (GamePhrase.SETUP, TestResult.OK, "Setup should run"),
            (GamePhrase.READY, TestResult.OK, "Ready should run"),
            (GamePhrase.ANSWER, TestResult.NO_TESTS_COLLECTED, "Answer should be SKIPPED"),
            (GamePhrase.CHALLENGE, TestResult.OK, "Challenge should run"),
            (GamePhrase.CHECK, TestResult.OK, "Check should run"),
            (GamePhrase.CLEANUP, TestResult.OK, "Cleanup should run"),
        ]
        
        for phase, expected_result, message in phases_to_test:
            with patch('common.pytest.get_tests'), \
                 patch('common.pytest.pytest.main', return_value=0):
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
    
    def test_expected_flow_description(self):
        """
        Document the expected flow for task 02_create_namespace
        
        This is a documentation test that describes expected behavior.
        """
        expected_flow = """
        Expected Flow for game01/02_create_namespace:
        
        1. Player talks to NPC
        2. Setup phase runs → OK
        3. Answer phase SKIPPED → Shows instruction
           Message: "Create a namespace called 'blissfularyabhata2developer'."
        4. Player must manually run:
           kubectl create namespace blissfularyabhata2developer
        5. Player talks to NPC again
        6. Check phase runs → Validates player's work
           - If namespace exists: PASS ✅
           - If namespace missing: FAIL ❌ (show instruction again)
        7. If passed: Task complete, player earns points
        
        CRITICAL: Player MUST do the work manually!
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

