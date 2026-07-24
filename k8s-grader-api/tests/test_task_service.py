"""Tests for TaskService"""
import pytest
from unittest.mock import Mock, patch

from common.services.task_service import TaskService
from common.database.repositories import TaskStateRepository, NpcRepository
from common.services.test_runner import TestRunner
from common.models.task_state import TaskState, TaskStatus, PhaseStatus, PhaseState
from common.status import TestResult


@pytest.fixture
def mock_repositories(dynamodb_tables):
    """Create mock repositories"""
    task_repo = TaskStateRepository()
    npc_repo = NpcRepository()
    return task_repo, npc_repo


@pytest.fixture
def mock_test_runner():
    """Create mock test runner"""
    runner = Mock(spec=TestRunner)
    runner.run_phase.return_value = (TestResult.OK, 'https://report.url')
    return runner


@pytest.fixture
def task_service(mock_repositories, mock_test_runner):
    """Create TaskService with mocked dependencies"""
    task_repo, npc_repo = mock_repositories
    return TaskService(task_repo, npc_repo, mock_test_runner)


class TestTaskService:
    """Test TaskService"""
    
    def test_get_current_task_first_task(self, task_service):
        """Test getting current task when none completed"""
        with patch('common.pytest.get_tasks', return_value=['01_task', '02_task', '03_task']):
            current = task_service.get_current_task('user@test.com', 'game01')
            
            assert current == '01_task'
    
    def test_get_current_task_with_completed(self, task_service):
        """Test getting current task with some completed"""
        # Save completed task
        completed_state = TaskState(
            email='user@test.com',
            game='game01',
            task_id='01_task',
            npc='npc1',
            status=TaskStatus.COMPLETED,
            current_phase_id=None
        )
        task_service.task_repo.save(completed_state)
        
        with patch('common.pytest.get_tasks', return_value=['01_task', '02_task', '03_task']):
            current = task_service.get_current_task('user@test.com', 'game01')
            
            assert current == '02_task'
    
    def test_get_current_task_all_completed(self, task_service):
        """Test getting current task when all completed"""
        # Save all tasks as completed
        for i in range(1, 4):
            state = TaskState(
                email='user@test.com',
                game='game01',
                task_id=f'0{i}_task',
                npc='npc1',
                status=TaskStatus.COMPLETED,
                current_phase_id=None
            )
            task_service.task_repo.save(state)
        
        with patch('common.pytest.get_tasks', return_value=['01_task', '02_task', '03_task']):
            current = task_service.get_current_task('user@test.com', 'game01')
            
            assert current is None

    def test_get_total_score_sums_saved_task_points(self, task_service):
        for task_id, points, status in [
            ('01_task', 2, TaskStatus.COMPLETED),
            ('02_task', 3, TaskStatus.COMPLETED),
            ('03_task', 0, TaskStatus.IN_PROGRESS),
        ]:
            state = TaskState(
                email='user@test.com',
                game='game01',
                task_id=task_id,
                npc='npc1',
                status=status,
                current_phase_id=None,
                total_points=points,
            )
            task_service.task_repo.save(state)

        assert task_service.get_total_score('user@test.com', 'game01') == 5

    def test_get_completed_tasks_returns_game_order(self, task_service):
        for task_id in ['02_task', '01_task']:
            state = TaskState(
                email='user@test.com',
                game='game01',
                task_id=task_id,
                npc='npc1',
                status=TaskStatus.COMPLETED,
                current_phase_id=None,
            )
            task_service.task_repo.save(state)

        with patch('common.pytest.get_tasks', return_value=['01_task', '02_task', '03_task']):
            completed = task_service.get_completed_tasks('user@test.com', 'game01')

        assert completed == ['01_task', '02_task']

    def test_get_skipped_tasks_returns_only_skipped_tasks(self, task_service):
        saved_states = [
            TaskState(
                email='user@test.com',
                game='game01',
                task_id='01_task',
                npc='npc1',
                status=TaskStatus.COMPLETED,
                skipped=False,
                current_phase_id=None,
            ),
            TaskState(
                email='user@test.com',
                game='game01',
                task_id='02_task',
                npc='npc1',
                status=TaskStatus.COMPLETED,
                skipped=True,
                current_phase_id=None,
            ),
            TaskState(
                email='user@test.com',
                game='game01',
                task_id='03_task',
                npc='npc1',
                status=TaskStatus.COMPLETED,
                skipped=True,
                current_phase_id=None,
            ),
        ]
        for state in saved_states:
            task_service.task_repo.save(state)

        with patch('common.pytest.get_tasks', return_value=['01_task', '02_task', '03_task']):
            skipped = task_service.get_skipped_tasks('user@test.com', 'game01')

        assert skipped == ['02_task', '03_task']

    def test_skip_task_marks_existing_task_completed_with_zero_points(self, task_service):
        state = TaskState(
            email='user@test.com',
            game='game01',
            task_id='01_task',
            npc='npc1',
            status=TaskStatus.IN_PROGRESS,
            current_phase_id='challenge',
            total_points=25,
        )
        task_service.task_repo.save(state)

        result = task_service.skip_task('user@test.com', 'game01', '01_task')
        saved = task_service.task_repo.get('user@test.com', 'game01', '01_task')

        assert result['success'] is True
        assert saved.status == TaskStatus.COMPLETED
        assert saved.total_points == 0
        assert saved.skipped is True
        assert saved.current_phase_id is None
    
    def test_start_task_new(self, task_service, sample_manifest):
        """Test starting a new task"""
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest), \
             patch('common.services.task_service.generate_session', return_value={'key': 'value'}):
            
            state = task_service.start_task('user@test.com', 'game01', '01_task', 'npc1')
            
            assert state.email == 'user@test.com'
            assert state.game == 'game01'
            assert state.task_id == '01_task'
            assert state.npc == 'npc1'
            assert state.status == TaskStatus.IN_PROGRESS
            assert state.current_phase_id == 'setup'
            
            # Check NPC assignment
            assigned_npc = task_service.npc_repo.get_assigned_npc('user@test.com', 'game01')
            assert assigned_npc == 'npc1'
    
    def test_start_task_already_started(self, task_service, sample_manifest):
        """Test starting a task that's already started"""
        # Create existing state
        existing_state = TaskState(
            email='user@test.com',
            game='game01',
            task_id='01_task',
            npc='npc1',
            status=TaskStatus.IN_PROGRESS,
            current_phase_id='challenge'
        )
        task_service.task_repo.save(existing_state)
        
        # Try to start again
        state = task_service.start_task('user@test.com', 'game01', '01_task', 'npc1')
        
        # Should return existing state
        assert state.current_phase_id == 'challenge'

    def test_start_exam_task(self, task_service, sample_manifest):
        """Test starting an exam task without NPC assignment"""
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest), \
             patch('common.services.task_service.generate_session', return_value={'key': 'value'}):
            state = task_service.start_exam_task('student@test.com', 'exam01', 'exam_task_01', 'EXAM-001')

        assert state.mode == 'exam'
        assert state.exam_code == 'EXAM-001'
        assert state.npc == 'exam'
        assert state.status == TaskStatus.IN_PROGRESS
        assert task_service.npc_repo.get_assigned_npc('student@test.com', 'exam01') is None
    
    def test_execute_phase_success(self, task_service, sample_manifest, in_progress_task_state):
        """Test executing phase successfully"""
        # Save state
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.execute_phase(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id,
                'setup'
            )
            
            assert result['success'] is True
            assert result['test_result'] == TestResult.OK
            assert result['report_url'] == 'https://report.url'
            assert result['state'].current_phase_id == 'challenge'  # Advanced to next
    
    def test_execute_phase_failure(self, task_service, sample_manifest, in_progress_task_state, mock_test_runner):
        """Test executing phase with failure"""
        # Configure mock to return failure
        mock_test_runner.run_phase.return_value = (TestResult.TESTS_FAILED, 'https://report.url')
        
        # Save state
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.execute_phase(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id,
                'setup'
            )
            
            assert result['success'] is False
            assert result['test_result'] == TestResult.TESTS_FAILED
            assert result['state'].current_phase_id == 'setup'  # Stayed on same phase
    
    def test_execute_phase_state_not_found(self, task_service):
        """Test executing phase when state not found"""
        with pytest.raises(ValueError, match="Task state not found"):
            task_service.execute_phase('user@test.com', 'game01', '01_task', 'setup')
    
    def test_execute_phase_no_phase_id(self, task_service, sample_manifest):
        """Test executing phase without phase ID"""
        # Create state without current phase
        state = TaskState(
            email='user@test.com',
            game='game01',
            task_id='01_task',
            npc='npc1',
            status=TaskStatus.IN_PROGRESS,
            current_phase_id=None
        )
        task_service.task_repo.save(state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            with pytest.raises(ValueError, match="No phase specified"):
                task_service.execute_phase('user@test.com', 'game01', '01_task')
    
    def test_execute_phase_cannot_execute(self, task_service, sample_manifest, in_progress_task_state):
        """Test executing phase that cannot be executed"""
        # Save state
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            # Try to execute challenge without completing setup
            result = task_service.execute_phase(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id,
                'challenge'
            )
            
            assert result['success'] is False
            assert 'Current phase is' in result['error']
    
    def test_complete_task_success(self, task_service, sample_manifest, in_progress_task_state):
        """Test completing task successfully"""
        # Complete all required phases
        from common.models.task_state import PhaseState
        in_progress_task_state.phase_states['setup'] = PhaseState('setup', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['challenge'] = PhaseState('challenge', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['check'] = PhaseState('check', PhaseStatus.PASSED)
        
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.complete_task(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id
            )
            
            assert result['success'] is True
            assert result['state'].status == TaskStatus.COMPLETED
            
            # Check NPC is locked
            is_locked = task_service.npc_repo.is_locked(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.npc
            )
            assert is_locked is True
            
            # Check assignment cleared
            assigned = task_service.npc_repo.get_assigned_npc(
                in_progress_task_state.email,
                in_progress_task_state.game
            )
            assert assigned is None

    def test_complete_exam_task_does_not_lock_npc(self, task_service, sample_manifest, in_progress_task_state):
        """Test completing an exam task skips NPC locking"""
        in_progress_task_state.mode = 'exam'
        in_progress_task_state.exam_code = 'EXAM-001'
        in_progress_task_state.phase_states['setup'] = PhaseState('setup', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['challenge'] = PhaseState('challenge', PhaseStatus.PASSED)
        in_progress_task_state.phase_states['check'] = PhaseState('check', PhaseStatus.PASSED)
        task_service.task_repo.save(in_progress_task_state)

        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.complete_task(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id
            )

        assert result['success'] is True
        assert task_service.npc_repo.get_assigned_npc(
            in_progress_task_state.email,
            in_progress_task_state.game
        ) is None
    
    def test_complete_task_not_ready(self, task_service, sample_manifest, in_progress_task_state):
        """Test completing task when not ready"""
        # Don't complete all phases
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.complete_task(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id
            )
            
            assert result['success'] is False
            assert 'not completed' in result['error']
    
    def test_complete_task_state_not_found(self, task_service):
        """Test completing task when state not found"""
        with pytest.raises(ValueError, match="Task state not found"):
            task_service.complete_task('user@test.com', 'game01', '01_task')
    
    def test_validate_npc_access_allowed(self, task_service):
        """Test validating NPC access when allowed"""
        can_access, error = task_service.validate_npc_access('user@test.com', 'game01', 'npc1')
        
        assert can_access is True
        assert error is None

    def test_validate_npc_access_allows_doom_source(self, task_service):
        """Test Doom source bypasses NPC-specific access checks"""
        task_service.npc_repo.lock_npc('user@test.com', 'game01', 'doom', minutes=30)
        task_service.npc_repo.assign_task('user@test.com', 'game01', 'npc1', '01_task')

        can_access, error = task_service.validate_npc_access('user@test.com', 'game01', 'doom')

        assert can_access is True
        assert error is None
    
    def test_validate_npc_access_locked(self, task_service):
        """Test validating NPC access when locked"""
        # Lock NPC
        task_service.npc_repo.lock_npc('user@test.com', 'game01', 'npc1', minutes=30)
        
        can_access, error = task_service.validate_npc_access('user@test.com', 'game01', 'npc1')
        
        assert can_access is False
        assert 'does not have any task' in error
    
    def test_validate_npc_access_different_npc_assigned(self, task_service):
        """Test validating NPC access when different NPC assigned"""
        # Assign task from npc1
        task_service.npc_repo.assign_task('user@test.com', 'game01', 'npc1', '01_task')
        
        # Try to access npc2
        can_access, error = task_service.validate_npc_access('user@test.com', 'game01', 'npc2')
        
        assert can_access is False
        assert 'Complete task from npc1' in error
    
    def test_validate_npc_access_same_npc_assigned(self, task_service):
        """Test validating NPC access when same NPC assigned"""
        # Assign task from npc1
        task_service.npc_repo.assign_task('user@test.com', 'game01', 'npc1', '01_task')
        
        # Access same npc1
        can_access, error = task_service.validate_npc_access('user@test.com', 'game01', 'npc1')
        
        assert can_access is True
        assert error is None
    
    def test_race_condition_prevention(self, task_service, sample_manifest):
        """Test that race condition is prevented when two NPCs try to assign simultaneously"""
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest), \
             patch('common.services.task_service.generate_session', return_value={'key': 'value'}):
            
            # First NPC successfully starts task
            state1 = task_service.start_task('user@test.com', 'game01', '01_task', 'npc1')
            assert state1.npc == 'npc1'
            
            # Second NPC tries to start same task - should raise error
            with pytest.raises(ValueError, match="Complete task from npc1 first"):
                task_service.start_task('user@test.com', 'game01', '01_task', 'npc2')
            
            # Verify only npc1 is assigned
            assigned_npc = task_service.npc_repo.get_assigned_npc('user@test.com', 'game01')
            assert assigned_npc == 'npc1'
            
            # Verify task state still belongs to npc1
            state = task_service.task_repo.get('user@test.com', 'game01', '01_task')
            assert state.npc == 'npc1'
    
    def test_abandon_task_success(self, task_service, sample_manifest, in_progress_task_state):
        """Test abandoning a task"""
        task_service.task_repo.save(in_progress_task_state)
        
        with patch('common.services.task_service.TaskManifest.load', return_value=sample_manifest):
            result = task_service.abandon_task(
                in_progress_task_state.email,
                in_progress_task_state.game,
                in_progress_task_state.task_id,
                'Max attempts reached'
            )
            
            assert result['success'] is True
            assert result['state'].status == TaskStatus.ABANDONED
            assert result['reason'] == 'Max attempts reached'
            
            # Check assignment cleared (not locked - allow retry)
            assigned = task_service.npc_repo.get_assigned_npc(
                in_progress_task_state.email,
                in_progress_task_state.game
            )
            assert assigned is None
    
    def test_abandon_task_state_not_found(self, task_service):
        """Test abandoning task when state not found"""
        with pytest.raises(ValueError, match="Task state not found"):
            task_service.abandon_task('user@test.com', 'game01', '01_task', 'reason')
