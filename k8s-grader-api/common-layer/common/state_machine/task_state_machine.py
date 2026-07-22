"""Task state machine for managing state transitions"""
# DEPLOYMENT: 2026-02-02 - Bug fix: clear current_phase_id after last phase
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """Raised when invalid state transition is attempted"""
    pass


class TaskStateMachine:
    """Manages task state transitions with validation"""
    
    def __init__(self, manifest, state):
        """
        Initialize state machine
        
        Args:
            manifest: TaskManifest instance
            state: TaskState instance
        """
        self.manifest = manifest
        self.state = state
    
    def start_task(self) -> Tuple[bool, Optional[str]]:
        """
        Initialize task - can only be called once
        
        Returns:
            Tuple of (success, error_message)
        """
        from common.models.task_state import TaskStatus
        
        if self.state.status != TaskStatus.NOT_STARTED:
            return False, "Task already started"
        
        self.state.status = TaskStatus.IN_PROGRESS
        first_phase = self.manifest.get_first_phase()
        self.state.current_phase_id = first_phase.id
        
        logger.info(f"Task {self.state.task_id} started by {self.state.email}")
        return True, None
    
    def can_execute_phase(self, phase_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if phase can be executed
        
        Args:
            phase_id: Phase identifier
            
        Returns:
            Tuple of (can_execute, error_message)
        """
        from common.models.task_state import TaskStatus, PhaseStatus
        
        # Check phase exists
        phase = self.manifest.get_phase(phase_id)
        if not phase:
            return False, f"Phase '{phase_id}' not found in manifest"
        
        # Check task is in progress
        if self.state.status != TaskStatus.IN_PROGRESS:
            return False, f"Task status is {self.state.status.value}, expected IN_PROGRESS"
        
        # Check if it's the current phase
        if self.state.current_phase_id != phase_id:
            return False, f"Current phase is '{self.state.current_phase_id}', cannot execute '{phase_id}'"
        
        # Check if phase already passed (prevent duplicate point awards)
        phase_state = self.state.get_phase_state(phase_id)
        if phase_state and phase_state.status == PhaseStatus.PASSED:
            return False, f"Phase '{phase_id}' already passed"
        
        # Check max attempts only for phases that count attempts
        if phase.count_attempts and phase_state and phase_state.attempts >= phase.max_attempts:
            return False, f"Maximum attempts ({phase.max_attempts}) reached for phase '{phase_id}'"
        
        # Check prerequisites (previous required phases must be passed)
        for p in self.manifest.phases:
            if p.id == phase_id:
                break
            if p.required:
                prev_state = self.state.get_phase_state(p.id)
                if not prev_state or prev_state.status != PhaseStatus.PASSED:
                    return False, f"Must complete phase '{p.id}' first"
        
        return True, None
    
    def execute_phase(self, phase_id: str, test_result, report_url: str) -> Tuple[bool, Optional[str]]:
        """
        Record phase execution result
        
        Args:
            phase_id: Phase identifier
            test_result: TestResult enum value
            report_url: URL to test report
            
        Returns:
            Tuple of (success, error_message)
        """
        from common.status import TestResult
        
        # Validate
        can_execute, error = self.can_execute_phase(phase_id)
        if not can_execute:
            return False, error
        
        # Get phase config and state
        phase = self.manifest.get_phase(phase_id)
        phase_state = self.state.get_or_create_phase_state(phase_id)
        
        # Update based on result
        if test_result == TestResult.OK or test_result == TestResult.NO_TESTS_COLLECTED:
            # NO_TESTS_COLLECTED means phase was skipped (e.g., answer phase in production)
            # Treat as success and move to next phase
            if test_result == TestResult.OK:
                phase_state.mark_passed(report_url, phase.points)
                self.state.total_points += phase.points
                logger.info(f"Phase '{phase_id}' passed (+{phase.points} points)")
            else:
                # Phase skipped - no points awarded
                phase_state.mark_passed(report_url, 0)
                logger.info(f"Phase '{phase_id}' skipped (no tests collected)")
            
            # Move to next phase
            next_phase = self.manifest.get_next_phase(phase_id)
            if next_phase:
                self.state.current_phase_id = next_phase.id
                logger.info(f"Advanced to phase '{next_phase.id}'")
            else:
                # No more phases - clear current phase and task ready for completion
                self.state.current_phase_id = None
                logger.info("No more phases - task ready for completion")
            
            return True, None
        else:
            phase_state.mark_failed(test_result.name, report_url, count_attempts=phase.count_attempts)
            logger.warning(f"Phase '{phase_id}' failed: {test_result.name} "
                         f"(attempt {phase_state.attempts}/{phase.max_attempts})")
            
            # Stay on current phase for retry
            return False, f"Tests failed: {test_result.name}"
    
    def can_complete_task(self) -> Tuple[bool, Optional[str]]:
        """
        Check if task can be marked complete
        
        Returns:
            Tuple of (can_complete, error_message)
        """
        from common.models.task_state import TaskStatus, PhaseStatus
        
        if self.state.status == TaskStatus.COMPLETED:
            return False, "Task already completed"
        
        # All required non-auto phases must be passed
        for phase in self.manifest.phases:
            if phase.required and not phase.auto_run:
                phase_state = self.state.get_phase_state(phase.id)
                if not phase_state or phase_state.status != PhaseStatus.PASSED:
                    return False, f"Phase '{phase.id}' not completed"
        
        return True, None
    
    def complete_task(self) -> Tuple[bool, Optional[str]]:
        """
        Mark task as complete
        
        Returns:
            Tuple of (success, error_message)
        """
        can_complete, error = self.can_complete_task()
        if not can_complete:
            return False, error
        
        self.state.mark_completed()
        logger.info(f"Task {self.state.task_id} completed by {self.state.email} "
                   f"({self.state.total_points} points)")
        
        return True, None
    
    def fail_task(self, reason: str) -> Tuple[bool, Optional[str]]:
        """
        Mark task as failed/abandoned (e.g., max attempts reached)
        
        Args:
            reason: Reason for failure
            
        Returns:
            Tuple of (success, error_message)
        """
        from common.models.task_state import TaskStatus
        
        if self.state.status == TaskStatus.COMPLETED:
            return False, "Cannot fail a completed task"
        
        if self.state.status == TaskStatus.ABANDONED:
            return False, "Task already abandoned"
        
        self.state.status = TaskStatus.ABANDONED
        logger.warning(f"Task {self.state.task_id} abandoned for {self.state.email}: {reason}")
        
        return True, None
    
    def get_next_action(self) -> dict:
        """
        Determine what should happen next
        
        Returns:
            Dictionary with action, phase_id, and message
        """
        from common.models.task_state import PhaseStatus
        
        # Check if task is complete
        can_complete, _ = self.can_complete_task()
        if can_complete:
            return {
                'action': 'complete_task',
                'phase_id': None,
                'message': 'All required phases passed. Ready to complete task.'
            }
        
        # Check if current phase needs retry
        if self.state.current_phase_id:
            phase_state = self.state.get_phase_state(self.state.current_phase_id)
            if phase_state and phase_state.status == PhaseStatus.FAILED:
                phase = self.manifest.get_phase(self.state.current_phase_id)
                if phase_state.attempts < phase.max_attempts:
                    return {
                        'action': 'retry_phase',
                        'phase_id': self.state.current_phase_id,
                        'message': f'Retry phase {self.state.current_phase_id} '
                                 f'(attempt {phase_state.attempts + 1}/{phase.max_attempts})'
                    }
                else:
                    return {
                        'action': 'max_attempts_reached',
                        'phase_id': self.state.current_phase_id,
                        'message': f'Maximum attempts reached for {self.state.current_phase_id}'
                    }
        
        # Execute current phase
        return {
            'action': 'execute_phase',
            'phase_id': self.state.current_phase_id,
            'message': f'Execute phase {self.state.current_phase_id}'
        }
