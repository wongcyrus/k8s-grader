"""
Test for task completion bug fix.

This test verifies that when all phases pass, the task is properly marked as COMPLETED
and subsequent calls return COMPLETED status instead of trying to re-execute phases.

Bug: After completing all phases, the task status remained "in_progress" because
complete_task() was loading a fresh state from DynamoDB instead of using the
updated state from execute_phase().
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from common.services.task_service import TaskService
from common.models.task_state import TaskState, TaskStatus, PhaseState, PhaseStatus
from common.models.task_manifest import TaskManifest, PhaseConfig
from common.status import TestResult


@pytest.fixture
def mock_repos():
    """Create mock repositories"""
    task_repo = Mock()
    npc_repo = Mock()
    test_runner = Mock()
    return task_repo, npc_repo, test_runner


@pytest.fixture
def sample_manifest():
    """Create a sample task manifest with 3 phases"""
    return TaskManifest(
        task_id='02_create_namespace',
        title='Create Namespace',
        description='Create a Kubernetes namespace',
        difficulty='beginner',
        estimated_minutes=5,
        phases=[
            PhaseConfig(
                id='setup',
                name='Setup',
                description='Initialize environment',
                test_file='test_01_setup.py',
                required=True,
                auto_run=False,
                timeout_seconds=30,
                max_attempts=3,
                points=0
            ),
            PhaseConfig(
                id='answer',
                name='Answer',
                description='Create namespace',
                test_file='test_03_answer.py',
                required=True,
                auto_run=False,
                timeout_seconds=30,
                max_attempts=3,
                points=10
            ),
            PhaseConfig(
                id='check',
                name='Check',
                description='Verify namespace',
                test_file='test_05_check.py',
                required=True,
                auto_run=False,
                timeout_seconds=30,
                max_attempts=3,
                points=20
            ),
        ],
        prerequisites=[],
        tags=['namespace', 'beginner'],
        hints=[]
    )


@pytest.fixture
def task_state_all_phases_passed():
    """Create a task state where all phases have passed"""
    state = TaskState(
        email='developer@example.com',
        game='game01',
        task_id='02_create_namespace',
        npc='Lila',
        status=TaskStatus.IN_PROGRESS,
        current_phase_id='check',  # Still on check phase
        session_data={'namespace': 'test-namespace'}
    )
    
    # Mark all phases as passed
    state.phase_states = {
        'setup': PhaseState(
            phase_id='setup',
            status=PhaseStatus.PASSED,
            attempts=0,
            points_earned=0,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
        'answer': PhaseState(
            phase_id='answer',
            status=PhaseStatus.PASSED,
            attempts=0,
            points_earned=10,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
        'check': PhaseState(
            phase_id='check',
            status=PhaseStatus.PASSED,
            attempts=1,
            points_earned=20,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
    }
    state.total_points = 30
    
    return state


def test_task_completion_with_state_parameter(mock_repos, sample_manifest, task_state_all_phases_passed):
    """
    Test that complete_task() properly uses the provided state parameter
    instead of loading from database.
    
    This is the fix for the bug where tasks remained "in_progress" after all phases passed.
    """
    task_repo, npc_repo, test_runner = mock_repos
    service = TaskService(task_repo, npc_repo, test_runner)
    
    # Mock manifest loading
    with patch.object(TaskManifest, 'load', return_value=sample_manifest):
        # Call complete_task with the state parameter (the fix)
        result = service.complete_task(
            email='developer@example.com',
            game='game01',
            task_id='02_create_namespace',
            state=task_state_all_phases_passed  # Pass the state directly
        )
    
    # Verify task was marked as completed
    assert result['success'] is True
    assert task_state_all_phases_passed.status == TaskStatus.COMPLETED
    assert task_state_all_phases_passed.completed_at is not None
    
    # Verify state was saved
    task_repo.save.assert_called_once_with(task_state_all_phases_passed)
    
    # Verify NPC was locked and assignment cleared
    npc_repo.lock_npc.assert_called_once_with('developer@example.com', 'game01', 'Lila', minutes=30)
    npc_repo.clear_assignment.assert_called_once_with('developer@example.com', 'game01')


def test_task_completion_without_state_parameter_loads_from_db(mock_repos, sample_manifest, task_state_all_phases_passed):
    """
    Test that complete_task() still works when state parameter is not provided
    (backward compatibility - loads from database).
    """
    task_repo, npc_repo, test_runner = mock_repos
    service = TaskService(task_repo, npc_repo, test_runner)
    
    # Mock database load
    task_repo.get.return_value = task_state_all_phases_passed
    
    # Mock manifest loading
    with patch.object(TaskManifest, 'load', return_value=sample_manifest):
        # Call complete_task WITHOUT state parameter (backward compatibility)
        result = service.complete_task(
            email='developer@example.com',
            game='game01',
            task_id='02_create_namespace'
            # No state parameter - should load from DB
        )
    
    # Verify it loaded from database
    task_repo.get.assert_called_once_with('developer@example.com', 'game01', '02_create_namespace')
    
    # Verify task was marked as completed
    assert result['success'] is True
    assert task_state_all_phases_passed.status == TaskStatus.COMPLETED


def test_execute_phase_then_complete_task_integration(mock_repos, sample_manifest):
    """
    Integration test: Execute the last phase, then complete the task.
    This simulates the exact flow in the handler.
    """
    task_repo, npc_repo, test_runner = mock_repos
    service = TaskService(task_repo, npc_repo, test_runner)
    
    # Create state with setup and answer already passed, on check phase
    state = TaskState(
        email='developer@example.com',
        game='game01',
        task_id='02_create_namespace',
        npc='Lila',
        status=TaskStatus.IN_PROGRESS,
        current_phase_id='check',
        session_data={'namespace': 'test-namespace'}
    )
    state.phase_states = {
        'setup': PhaseState(
            phase_id='setup',
            status=PhaseStatus.PASSED,
            attempts=0,
            points_earned=0,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
        'answer': PhaseState(
            phase_id='answer',
            status=PhaseStatus.PASSED,
            attempts=0,
            points_earned=10,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
    }
    state.total_points = 10
    
    # Mock database and test runner
    task_repo.get.return_value = state
    test_runner.run_phase.return_value = (TestResult.OK, 'https://s3.amazonaws.com/report.html')
    
    # Mock manifest loading
    with patch.object(TaskManifest, 'load', return_value=sample_manifest):
        # Step 1: Execute check phase (last phase)
        result = service.execute_phase('developer@example.com', 'game01', '02_create_namespace')
        
        assert result['success'] is True
        assert result['test_result'] == TestResult.OK
        
        # Get the updated state from result
        updated_state = result['state']
        
        # Verify check phase is now passed
        assert updated_state.phase_states['check'].status == PhaseStatus.PASSED
        assert updated_state.total_points == 30  # 0 + 10 + 20
        
        # Step 2: Complete task using the updated state (THE FIX)
        completion_result = service.complete_task(
            email='developer@example.com',
            game='game01',
            task_id='02_create_namespace',
            state=updated_state  # Pass the updated state
        )
        
        # Verify task is completed
        assert completion_result['success'] is True
        assert updated_state.status == TaskStatus.COMPLETED
        assert updated_state.completed_at is not None


def test_can_complete_task_with_all_phases_passed(sample_manifest, task_state_all_phases_passed):
    """
    Test that can_complete_task() returns True when all required phases are passed.
    """
    from common.state_machine.task_state_machine import TaskStateMachine
    
    sm = TaskStateMachine(sample_manifest, task_state_all_phases_passed)
    can_complete, error = sm.can_complete_task()
    
    assert can_complete is True
    assert error is None


def test_can_complete_task_with_missing_phase(sample_manifest):
    """
    Test that can_complete_task() returns False when a required phase is not passed.
    """
    from common.state_machine.task_state_machine import TaskStateMachine
    
    # Create state with only setup passed
    state = TaskState(
        email='developer@example.com',
        game='game01',
        task_id='02_create_namespace',
        npc='Lila',
        status=TaskStatus.IN_PROGRESS,
        current_phase_id='answer',
        session_data={}
    )
    state.phase_states = {
        'setup': PhaseState(
            phase_id='setup',
            status=PhaseStatus.PASSED,
            attempts=0,
            points_earned=0,
            test_result='OK',
            report_url='',
            passed_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc)
        ),
    }
    
    sm = TaskStateMachine(sample_manifest, state)
    can_complete, error = sm.can_complete_task()
    
    assert can_complete is False
    assert 'not completed' in error.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
