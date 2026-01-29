"""Task service for high-level task management"""
from typing import Optional, Dict, Any
import logging

from common.models.task_manifest import TaskManifest
from common.models.task_state import TaskState, TaskStatus
from common.state_machine.task_state_machine import TaskStateMachine
from common.database.repositories import TaskStateRepository, NpcRepository
from common.services.test_runner import TestRunner
from common.session import generate_session
from common.status import TestResult

logger = logging.getLogger(__name__)


class TaskService:
    """High-level task management service"""
    
    def __init__(self, task_repo: Optional[TaskStateRepository] = None,
                 npc_repo: Optional[NpcRepository] = None,
                 test_runner: Optional[TestRunner] = None):
        """
        Initialize service
        
        Args:
            task_repo: Task state repository (creates new if None)
            npc_repo: NPC repository (creates new if None)
            test_runner: Test runner (creates new if None)
        """
        self.task_repo = task_repo or TaskStateRepository()
        self.npc_repo = npc_repo or NpcRepository()
        self.test_runner = test_runner or TestRunner()
    
    def get_current_task(self, email: str, game: str) -> Optional[str]:
        """
        Get the first incomplete task for a user
        
        Args:
            email: User email
            game: Game identifier
            
        Returns:
            Task ID or None if all complete
        """
        try:
            from common.pytest import get_tasks
            
            # Get all tasks for game
            all_tasks = get_tasks(game)
            
            # Get completed tasks
            completed = self.task_repo.get_completed_tasks(email, game)
            
            # Find first incomplete
            for task_id in all_tasks:
                if task_id not in completed:
                    return task_id
            
            return None
        except Exception as e:
            logger.error(f"Failed to get current task: {e}")
            return None
    
    def start_task(self, email: str, game: str, task_id: str, npc: str) -> TaskState:
        """
        Start a new task
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            npc: NPC name
            
        Returns:
            TaskState instance
            
        Raises:
            ValueError: If task cannot be started
        """
        # Check if already started
        existing = self.task_repo.get(email, game, task_id)
        if existing:
            logger.info(f"Task {task_id} already started for {email}")
            return existing
        
        # Load manifest
        manifest = TaskManifest.load(game, task_id)
        
        # Generate session data
        session_data = generate_session(email, game, task_id)
        
        # Create initial state
        state = TaskState(
            email=email,
            game=game,
            task_id=task_id,
            npc=npc,
            status=TaskStatus.NOT_STARTED,
            current_phase_id=None,
            session_data=session_data
        )
        
        # Start task via state machine
        sm = TaskStateMachine(manifest, state)
        success, error = sm.start_task()
        
        if not success:
            raise ValueError(f"Failed to start task: {error}")
        
        # Save state
        self.task_repo.save(state)
        
        # Mark NPC as assigned
        self.npc_repo.assign_task(email, game, npc, task_id)
        
        logger.info(f"Started task {task_id} for {email} with NPC {npc}")
        return state
    
    def execute_phase(self, email: str, game: str, task_id: str, 
                     phase_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a task phase
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            phase_id: Phase identifier (uses current if None)
            
        Returns:
            Dictionary with execution results
            
        Raises:
            ValueError: If state not found or phase invalid
        """
        # Load state
        state = self.task_repo.get(email, game, task_id)
        if not state:
            raise ValueError(f"Task state not found: {task_id}")
        
        # Load manifest
        manifest = TaskManifest.load(game, task_id)
        
        # Create state machine
        sm = TaskStateMachine(manifest, state)
        
        # Determine phase to execute
        if not phase_id:
            phase_id = state.current_phase_id
        
        if not phase_id:
            raise ValueError("No phase specified and no current phase")
        
        # Validate can execute
        can_execute, error = sm.can_execute_phase(phase_id)
        if not can_execute:
            return {
                'success': False,
                'error': error,
                'state': state,
                'manifest': manifest
            }
        
        # Get phase config
        phase = manifest.get_phase(phase_id)
        
        # Run tests
        test_result, report_url = self.test_runner.run_phase(
            game, task_id, phase, state.session_data
        )
        
        # Update state
        success, error = sm.execute_phase(phase_id, test_result, report_url)
        
        # Save state
        self.task_repo.save(state)
        
        return {
            'success': success,
            'error': error,
            'test_result': test_result,
            'report_url': report_url,
            'state': state,
            'manifest': manifest
        }
    
    def complete_task(self, email: str, game: str, task_id: str) -> Dict[str, Any]:
        """
        Complete a task including cleanup
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            
        Returns:
            Dictionary with completion results
            
        Raises:
            ValueError: If state not found
        """
        # Load state and manifest
        state = self.task_repo.get(email, game, task_id)
        if not state:
            raise ValueError(f"Task state not found: {task_id}")
        
        manifest = TaskManifest.load(game, task_id)
        sm = TaskStateMachine(manifest, state)
        
        # Run cleanup if exists
        cleanup_phase = manifest.get_phase('cleanup')
        if cleanup_phase and cleanup_phase.auto_run:
            test_result, report_url = self.test_runner.run_phase(
                game, task_id, cleanup_phase, state.session_data
            )
            sm.execute_phase('cleanup', test_result, report_url)
        
        # Mark complete
        success, error = sm.complete_task()
        if not success:
            return {'success': False, 'error': error}
        
        # Save state
        self.task_repo.save(state)
        
        # Lock NPC for 30 minutes
        self.npc_repo.lock_npc(email, game, state.npc, minutes=30)
        
        # Clear assigned task
        self.npc_repo.clear_assignment(email, game)
        
        logger.info(f"Completed task {task_id} for {email}")
        
        return {
            'success': True,
            'state': state,
            'total_points': state.total_points
        }
    
    def validate_npc_access(self, email: str, game: str, npc: str) -> tuple[bool, Optional[str]]:
        """
        Validate if NPC can give tasks to user
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            
        Returns:
            Tuple of (can_access, error_message)
        """
        # Check NPC lock
        if self.npc_repo.is_locked(email, game, npc):
            return False, f"{npc} does not have any task for you!"
        
        # Check ongoing task from different NPC
        assigned_npc = self.npc_repo.get_assigned_npc(email, game)
        if assigned_npc and assigned_npc != npc:
            return False, f"Complete task from {assigned_npc} first!"
        
        return True, None
