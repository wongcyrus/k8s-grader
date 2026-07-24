"""Tests for TaskStateMachine"""
import pytest
from common.state_machine.task_state_machine import TaskStateMachine, StateTransitionError
from common.models.task_state import TaskStatus, PhaseStatus, PhaseState
from common.status import TestResult


class TestTaskStateMachine:
    """Test TaskStateMachine"""
    
    def test_start_task(self, sample_manifest, sample_task_state):
        """Test starting a task"""
        sm = TaskStateMachine(sample_manifest, sample_task_state)
        
        success, error = sm.start_task()
        
        assert success is True
        assert error is None
        assert sample_task_state.status == TaskStatus.IN_PROGRESS
        assert sample_task_state.current_phase_id == "setup"
    
    def test_start_task_already_started(self, sample_manifest, in_progress_task_state):
        """Test starting a task that's already started"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        success, error = sm.start_task()
        
        assert success is False
        assert "already started" in error
    
    def test_can_execute_phase_valid(self, sample_manifest, in_progress_task_state):
        """Test validating phase execution - valid case"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_execute, error = sm.can_execute_phase("setup")
        
        assert can_execute is True
        assert error is None
    
    def test_can_execute_phase_not_found(self, sample_manifest, in_progress_task_state):
        """Test validating phase that doesn't exist"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_execute, error = sm.can_execute_phase("nonexistent")
        
        assert can_execute is False
        assert "not found" in error
    
    def test_can_execute_phase_wrong_status(self, sample_manifest, sample_task_state):
        """Test validating phase when task not in progress"""
        sm = TaskStateMachine(sample_manifest, sample_task_state)
        
        can_execute, error = sm.can_execute_phase("setup")
        
        assert can_execute is False
        assert "expected IN_PROGRESS" in error
    
    def test_can_execute_phase_wrong_current(self, sample_manifest, in_progress_task_state):
        """Test validating phase that's not current"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_execute, error = sm.can_execute_phase("challenge")
        
        assert can_execute is False
        assert "Current phase is 'setup'" in error
    
    def test_can_execute_phase_max_attempts(self, sample_manifest, in_progress_task_state):
        """Test validating phase with max attempts reached"""
        # Add phase state with max attempts
        phase_state = PhaseState("setup", PhaseStatus.FAILED, attempts=3)
        in_progress_task_state.phase_states["setup"] = phase_state
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_execute, error = sm.can_execute_phase("setup")
        
        assert can_execute is False
        assert "Maximum attempts" in error
    
    def test_can_execute_phase_missing_prerequisite(self, sample_manifest, in_progress_task_state):
        """Test validating phase with missing prerequisite"""
        # Try to execute challenge without completing setup
        in_progress_task_state.current_phase_id = "challenge"
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_execute, error = sm.can_execute_phase("challenge")
        
        assert can_execute is False
        assert "Must complete phase 'setup' first" in error

    def test_can_execute_phase_ignores_max_attempts_for_doom(self, sample_manifest, in_progress_task_state):
        """Test Doom tasks can still retry after the normal max-attempt threshold."""
        in_progress_task_state.npc = "doom"
        in_progress_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.FAILED, attempts=3)

        sm = TaskStateMachine(sample_manifest, in_progress_task_state)

        can_execute, error = sm.can_execute_phase("setup")

        assert can_execute is True
        assert error is None
    
    def test_execute_phase_success(self, sample_manifest, in_progress_task_state):
        """Test executing phase successfully"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        success, error = sm.execute_phase("setup", TestResult.OK, "https://report.url")
        
        assert success is True
        assert error is None
        assert in_progress_task_state.current_phase_id == "challenge"
        
        # Check phase state
        phase_state = in_progress_task_state.get_phase_state("setup")
        assert phase_state.status == PhaseStatus.PASSED
        assert phase_state.report_url == "https://report.url"
    
    def test_execute_phase_failure(self, sample_manifest, in_progress_task_state):
        """Test executing phase with failure"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        success, error = sm.execute_phase("setup", TestResult.TESTS_FAILED, "https://report.url")
        
        assert success is False
        assert "Tests failed" in error
        assert in_progress_task_state.current_phase_id == "setup"  # Stay on same phase
        
        # Check phase state
        phase_state = in_progress_task_state.get_phase_state("setup")
        assert phase_state.status == PhaseStatus.FAILED
        assert phase_state.attempts == 1

    def test_execute_phase_non_counting_failure(self, exam_manifest, exam_task_state):
        """Test phases that should not consume attempts on failure"""
        exam_task_state.status = TaskStatus.IN_PROGRESS
        exam_task_state.current_phase_id = "challenge"
        exam_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        sm = TaskStateMachine(exam_manifest, exam_task_state)

        success, error = sm.execute_phase("challenge", TestResult.TESTS_FAILED, "https://report.url")

        assert success is False
        assert "Tests failed" in error
        phase_state = exam_task_state.get_phase_state("challenge")
        assert phase_state.attempts == 0
        can_execute, _ = sm.can_execute_phase("challenge")
        assert can_execute is True

    def test_execute_phase_failure_does_not_increment_attempts_for_doom(self, sample_manifest, in_progress_task_state):
        """Test Doom task failures remain retryable without consuming attempts."""
        in_progress_task_state.npc = "doom"
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)

        success, error = sm.execute_phase("setup", TestResult.TESTS_FAILED, "https://report.url")

        assert success is False
        assert "Tests failed" in error
        phase_state = in_progress_task_state.get_phase_state("setup")
        assert phase_state.attempts == 0
    
    def test_execute_phase_with_points(self, sample_manifest, in_progress_task_state):
        """Test executing phase and earning points"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        # Complete setup (0 points)
        sm.execute_phase("setup", TestResult.OK, "https://report1.url")
        assert in_progress_task_state.total_points == 0
        
        # Complete challenge (100 points)
        sm.execute_phase("challenge", TestResult.OK, "https://report2.url")
        assert in_progress_task_state.total_points == 100
        
        # Complete check (50 points)
        sm.execute_phase("check", TestResult.OK, "https://report3.url")
        assert in_progress_task_state.total_points == 150

    def test_exam_mode_awards_points_only_for_check(self, exam_manifest, exam_task_state):
        """Test exam mode only earns marks when check passes"""
        exam_task_state.status = TaskStatus.IN_PROGRESS
        exam_task_state.current_phase_id = "setup"
        sm = TaskStateMachine(exam_manifest, exam_task_state)

        sm.execute_phase("setup", TestResult.OK, "https://report1.url")
        assert exam_task_state.total_points == 0
        assert exam_task_state.get_phase_state("setup").points_earned == 0

        sm.execute_phase("challenge", TestResult.OK, "https://report2.url")
        assert exam_task_state.total_points == 0
        assert exam_task_state.get_phase_state("challenge").points_earned == 0

        sm.execute_phase("check", TestResult.OK, "https://report3.url")
        assert exam_task_state.total_points == 100
        assert exam_task_state.get_phase_state("check").points_earned == 100
    
    def test_can_complete_task_not_ready(self, sample_manifest, in_progress_task_state):
        """Test checking if task can be completed - not ready"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_complete, error = sm.can_complete_task()
        
        assert can_complete is False
        assert "not completed" in error
    
    def test_can_complete_task_ready(self, sample_manifest, in_progress_task_state):
        """Test checking if task can be completed - ready"""
        # Complete all required phases
        in_progress_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["challenge"] = PhaseState("challenge", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["check"] = PhaseState("check", PhaseStatus.PASSED)
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_complete, error = sm.can_complete_task()
        
        assert can_complete is True
        assert error is None
    
    def test_can_complete_task_already_completed(self, sample_manifest, in_progress_task_state):
        """Test checking if task can be completed - already completed"""
        in_progress_task_state.status = TaskStatus.COMPLETED
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        can_complete, error = sm.can_complete_task()
        
        assert can_complete is False
        assert "already completed" in error
    
    def test_complete_task(self, sample_manifest, in_progress_task_state):
        """Test completing a task"""
        # Complete all required phases
        in_progress_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["challenge"] = PhaseState("challenge", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["check"] = PhaseState("check", PhaseStatus.PASSED)
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        success, error = sm.complete_task()
        
        assert success is True
        assert error is None
        assert in_progress_task_state.status == TaskStatus.COMPLETED
        assert in_progress_task_state.completed_at is not None
    
    def test_get_next_action_execute_phase(self, sample_manifest, in_progress_task_state):
        """Test getting next action - execute phase"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        action = sm.get_next_action()
        
        assert action['action'] == 'execute_phase'
        assert action['phase_id'] == 'setup'
    
    def test_get_next_action_retry_phase(self, sample_manifest, in_progress_task_state):
        """Test getting next action - retry failed phase"""
        # Add failed phase state
        phase_state = PhaseState("setup", PhaseStatus.FAILED, attempts=1)
        in_progress_task_state.phase_states["setup"] = phase_state
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        action = sm.get_next_action()
        
        assert action['action'] == 'retry_phase'
        assert action['phase_id'] == 'setup'
        assert 'attempt 2/3' in action['message']
    
    def test_get_next_action_max_attempts(self, sample_manifest, in_progress_task_state):
        """Test getting next action - max attempts reached"""
        # Add failed phase state with max attempts
        phase_state = PhaseState("setup", PhaseStatus.FAILED, attempts=3)
        in_progress_task_state.phase_states["setup"] = phase_state
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        action = sm.get_next_action()
        
        assert action['action'] == 'max_attempts_reached'
        assert action['phase_id'] == 'setup'

    def test_get_next_action_keeps_retrying_for_doom_after_max_attempts(self, sample_manifest, in_progress_task_state):
        """Test Doom tasks do not transition to max-attempts-reached."""
        in_progress_task_state.npc = "doom"
        in_progress_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.FAILED, attempts=3)

        sm = TaskStateMachine(sample_manifest, in_progress_task_state)

        action = sm.get_next_action()

        assert action['action'] == 'execute_phase'
        assert action['phase_id'] == 'setup'
    
    def test_get_next_action_complete_task(self, sample_manifest, in_progress_task_state):
        """Test getting next action - complete task"""
        # Complete all required phases
        in_progress_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["challenge"] = PhaseState("challenge", PhaseStatus.PASSED)
        in_progress_task_state.phase_states["check"] = PhaseState("check", PhaseStatus.PASSED)
        
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        action = sm.get_next_action()
        
        assert action['action'] == 'complete_task'
        assert action['phase_id'] is None
    
    def test_full_task_flow(self, sample_manifest, sample_task_state):
        """Test complete task flow from start to finish"""
        sm = TaskStateMachine(sample_manifest, sample_task_state)
        
        # Start task
        success, _ = sm.start_task()
        assert success is True
        assert sample_task_state.status == TaskStatus.IN_PROGRESS
        
        # Execute setup
        success, _ = sm.execute_phase("setup", TestResult.OK, "https://report1.url")
        assert success is True
        assert sample_task_state.current_phase_id == "challenge"
        
        # Execute challenge
        success, _ = sm.execute_phase("challenge", TestResult.OK, "https://report2.url")
        assert success is True
        assert sample_task_state.current_phase_id == "check"
        
        # Execute check
        success, _ = sm.execute_phase("check", TestResult.OK, "https://report3.url")
        assert success is True
        
        # Complete task
        success, _ = sm.complete_task()
        assert success is True
        assert sample_task_state.status == TaskStatus.COMPLETED
        assert sample_task_state.total_points == 150  # 0 + 100 + 50

    def test_cannot_reexecute_passed_phase(self, sample_manifest, in_progress_task_state):
        """Test that a phase cannot be re-executed after it's already passed"""
        sm = TaskStateMachine(sample_manifest, in_progress_task_state)
        
        # Execute setup phase successfully
        success, error = sm.execute_phase("setup", TestResult.OK, "https://report1.url")
        assert success is True
        assert in_progress_task_state.total_points == 0  # Setup gives 0 points
        assert in_progress_task_state.current_phase_id == "challenge"  # Moved to next phase
        
        # Manually set current_phase_id back to setup (simulating a bug or race condition)
        in_progress_task_state.current_phase_id = "setup"
        
        # Try to execute setup again - should fail because it's already passed
        can_execute, error = sm.can_execute_phase("setup")
        assert can_execute is False
        assert "already passed" in error.lower()
        
        # Restore to correct phase
        in_progress_task_state.current_phase_id = "challenge"
        
        # Execute challenge successfully
        success, error = sm.execute_phase("challenge", TestResult.OK, "https://report2.url")
        assert success is True
        assert in_progress_task_state.total_points == 100  # Challenge gives 100 points
        assert in_progress_task_state.current_phase_id == "check"  # Moved to next phase
        
        # Manually set current_phase_id back to challenge
        in_progress_task_state.current_phase_id = "challenge"
        
        # Try to execute challenge again - should fail because it's already passed
        can_execute, error = sm.can_execute_phase("challenge")
        assert can_execute is False
        assert "already passed" in error.lower()
        
        # Verify total points haven't changed
        assert in_progress_task_state.total_points == 100
