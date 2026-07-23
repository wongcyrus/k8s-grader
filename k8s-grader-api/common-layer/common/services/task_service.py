"""Task service for high-level task management"""
# DEPLOYMENT: 2026-02-02 - Bug fix: pass state to complete_task to avoid eventual consistency
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

    def get_completed_tasks(self, email: str, game: str) -> list[str]:
        """
        Get completed tasks for a user in game order.

        Args:
            email: User email
            game: Game identifier

        Returns:
            Ordered list of completed task IDs
        """
        try:
            from common.pytest import get_tasks

            all_tasks = get_tasks(game)
            states = {
                state.task_id: state
                for state in self.task_repo.list_by_game(email, game)
                if state.status == TaskStatus.COMPLETED and not getattr(state, "skipped", False)
            }
            return [task_id for task_id in all_tasks if task_id in states]
        except Exception as e:
            logger.error(f"Failed to get completed tasks: {e}")
            return []

    def get_skipped_tasks(self, email: str, game: str) -> list[str]:
        """
        Get skipped tasks for a user in game order.

        Args:
            email: User email
            game: Game identifier

        Returns:
            Ordered list of skipped task IDs
        """
        try:
            from common.pytest import get_tasks

            all_tasks = get_tasks(game)
            states = {
                state.task_id: state
                for state in self.task_repo.list_by_game(email, game)
                if state.status == TaskStatus.COMPLETED and getattr(state, "skipped", False)
            }
            return [task_id for task_id in all_tasks if task_id in states]
        except Exception as e:
            logger.error(f"Failed to get skipped tasks: {e}")
            return []

    def get_total_score(self, email: str, game: str) -> int:
        """
        Get cumulative score across all saved task states for a game.

        Args:
            email: User email
            game: Game identifier

        Returns:
            Total points accumulated across the game's task states
        """
        try:
            states = self.task_repo.list_by_game(email, game)
            return sum(int(getattr(state, "total_points", 0) or 0) for state in states)
        except Exception as e:
            logger.error(f"Failed to get total score: {e}")
            return 0

    def skip_task(self, email: str, game: str, task_id: str, npc: str = "portal") -> Dict[str, Any]:
        """
        Skip a task by marking it completed with zero points.

        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            npc: Fallback NPC/source name when no state exists yet

        Returns:
            Dictionary containing the updated state
        """
        state = self.task_repo.get(email, game, task_id)
        if not state:
            state = TaskState(
                email=email,
                game=game,
                task_id=task_id,
                npc=npc,
                status=TaskStatus.NOT_STARTED,
                current_phase_id=None,
            )

        state.total_points = 0
        state.skipped = True
        state.current_phase_id = None
        state.mark_completed()
        self.task_repo.save(state)

        if state.mode != 'exam':
            self.npc_repo.clear_assignment(email, game)

        logger.info(f"Skipped task {task_id} for {email}")
        return {
            'success': True,
            'state': state,
            'total_points': 0,
            'skipped': True,
        }
    
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
            # Verify it's the same NPC
            if existing.npc != npc:
                raise ValueError(f"Complete task from {existing.npc} first!")
            logger.info(f"Task {task_id} already started for {email}")
            return existing
        
        # Try to assign NPC atomically FIRST (prevents race condition)
        assigned = self.npc_repo.assign_task(email, game, npc, task_id)
        if not assigned:
            # Another NPC already assigned - check which one
            assigned_npc = self.npc_repo.get_assigned_npc(email, game)
            raise ValueError(f"Complete task from {assigned_npc} first!")
        
        try:
            # Load manifest
            manifest = TaskManifest.load(game, task_id)
            
            # Generate session data
            session_data = generate_session(email, game, task_id)
            
            # Add task instruction from manifest
            session_data['$instruction'] = manifest.description
            
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
                # Rollback assignment on failure
                self.npc_repo.clear_assignment(email, game)
                raise ValueError(f"Failed to start task: {error}")
            
            # Save state
            self.task_repo.save(state)
            
            logger.info(f"Started task {task_id} for {email} with NPC {npc}")
            return state
        except Exception as e:
            # Rollback assignment on any error
            self.npc_repo.clear_assignment(email, game)
            raise

    def start_exam_task(self, email: str, game: str, task_id: str, exam_code: str) -> TaskState:
        """Start an exam task without NPC assignment or locking."""
        existing = self.task_repo.get(email, game, task_id)
        if existing:
            if existing.mode != 'exam' or existing.exam_code != exam_code:
                raise ValueError("Exam task already started with a different exam code")
            logger.info(f"Exam task {task_id} already started for {email}")
            return existing

        manifest = TaskManifest.load(game, task_id)
        session_data = generate_session(email, game, task_id)
        session_data['$instruction'] = manifest.description
        session_data['$exam_code'] = exam_code

        state = TaskState(
            email=email,
            game=game,
            task_id=task_id,
            npc='exam',
            mode='exam',
            status=TaskStatus.NOT_STARTED,
            current_phase_id=None,
            session_data=session_data,
            exam_code=exam_code
        )

        sm = TaskStateMachine(manifest, state)
        success, error = sm.start_task()
        if not success:
            raise ValueError(f"Failed to start exam task: {error}")

        self.task_repo.save(state)
        logger.info(f"Started exam task {task_id} for {email} with code {exam_code}")
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
    
    def complete_task(self, email: str, game: str, task_id: str, state=None) -> Dict[str, Any]:
        """
        Complete a task including cleanup
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            state: Optional TaskState instance (if None, loads from DB)
            
        Returns:
            Dictionary with completion results
            
        Raises:
            ValueError: If state not found
        """
        # Load state and manifest (use provided state if available)
        if state is None:
            state = self.task_repo.get(email, game, task_id)
        if not state:
            raise ValueError(f"Task state not found: {task_id}")
        
        manifest = TaskManifest.load(game, task_id)
        sm = TaskStateMachine(manifest, state)
        
        # Run cleanup if exists
        cleanup_phase = manifest.get_phase('cleanup')
        if cleanup_phase:
            logger.info(f"Cleanup phase found for task {task_id}: auto_run={cleanup_phase.auto_run}")
            if cleanup_phase.auto_run:
                logger.info(f"Running cleanup for completed task {task_id}")
                try:
                    test_result, report_url = self.test_runner.run_phase(
                        game, task_id, cleanup_phase, state.session_data
                    )
                    sm.execute_phase('cleanup', test_result, report_url)
                    logger.info(f"Cleanup completed for task {task_id}: result={test_result.name}")
                except Exception as e:
                    logger.error(f"Cleanup failed for task {task_id}: {e}", exc_info=True)
            else:
                logger.info(f"Cleanup phase exists but auto_run=False for task {task_id}")
        else:
            logger.info(f"No cleanup phase found for task {task_id}")
        
        # Mark complete
        success, error = sm.complete_task()
        if not success:
            return {'success': False, 'error': error}
        
        # Save state
        self.task_repo.save(state)
        
        if state.mode != 'exam':
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
    
    def abandon_task(self, email: str, game: str, task_id: str, reason: str) -> Dict[str, Any]:
        """
        Abandon a task (e.g., max attempts reached)
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            reason: Reason for abandonment
            
        Returns:
            Dictionary with abandonment results
            
        Raises:
            ValueError: If state not found
        """
        # Load state and manifest
        state = self.task_repo.get(email, game, task_id)
        if not state:
            raise ValueError(f"Task state not found: {task_id}")
        
        manifest = TaskManifest.load(game, task_id)
        sm = TaskStateMachine(manifest, state)
        
        # Run cleanup if exists (cleanup resources even on failure)
        cleanup_phase = manifest.get_phase('cleanup')
        if cleanup_phase:
            logger.info(f"Cleanup phase found for task {task_id}: auto_run={cleanup_phase.auto_run}")
            if cleanup_phase.auto_run:
                logger.info(f"Running cleanup for abandoned task {task_id}")
                try:
                    test_result, report_url = self.test_runner.run_phase(
                        game, task_id, cleanup_phase, state.session_data
                    )
                    sm.execute_phase('cleanup', test_result, report_url)
                    logger.info(f"Cleanup completed for abandoned task {task_id}: result={test_result.name}")
                except Exception as e:
                    logger.error(f"Cleanup failed for abandoned task {task_id}: {e}", exc_info=True)
            else:
                logger.info(f"Cleanup phase exists but auto_run=False for task {task_id}")
        else:
            logger.info(f"No cleanup phase found for task {task_id}")
        
        # Mark as abandoned
        success, error = sm.fail_task(reason)
        if not success:
            return {'success': False, 'error': error}
        
        # Save state
        self.task_repo.save(state)
        
        if state.mode != 'exam':
            # Clear NPC assignment (don't lock - allow immediate retry)
            self.npc_repo.clear_assignment(email, game)
        
        logger.warning(f"Abandoned task {task_id} for {email}: {reason}")
        
        return {
            'success': True,
            'state': state,
            'reason': reason
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
