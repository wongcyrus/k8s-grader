"""Tests for TaskState model"""
import pytest
from common.models.task_state import TaskState, TaskStatus, PhaseState, PhaseStatus


class TestPhaseState:
    """Test PhaseState model"""
    
    def test_create_phase_state(self):
        """Test creating a PhaseState instance"""
        state = PhaseState("setup", PhaseStatus.PENDING)
        
        assert state.phase_id == "setup"
        assert state.status == PhaseStatus.PENDING
        assert state.attempts == 0
        assert state.passed_at is None
        assert state.points_earned == 0
    
    def test_mark_passed(self):
        """Test marking phase as passed"""
        state = PhaseState("challenge", PhaseStatus.RUNNING)
        state.mark_passed("https://report.url", 100)
        
        assert state.status == PhaseStatus.PASSED
        assert state.test_result == "OK"
        assert state.report_url == "https://report.url"
        assert state.points_earned == 100
        assert state.passed_at is not None
        assert state.last_attempt_at is not None
    
    def test_mark_failed(self):
        """Test marking phase as failed"""
        state = PhaseState("check", PhaseStatus.RUNNING)
        state.mark_failed("TESTS_FAILED", "https://report.url")
        
        assert state.status == PhaseStatus.FAILED
        assert state.attempts == 1
        assert state.test_result == "TESTS_FAILED"
        assert state.report_url == "https://report.url"
        assert state.last_attempt_at is not None
        
        # Mark failed again
        state.mark_failed("TESTS_FAILED", "https://report2.url")
        assert state.attempts == 2
    
    def test_to_dict(self):
        """Test converting PhaseState to dictionary"""
        state = PhaseState("setup", PhaseStatus.PASSED, attempts=1, points_earned=50)
        data = state.to_dict()
        
        assert data['phase_id'] == 'setup'
        assert data['status'] == 'passed'
        assert data['attempts'] == 1
        assert data['points_earned'] == 50
    
    def test_from_dict(self):
        """Test creating PhaseState from dictionary"""
        data = {
            'phase_id': 'challenge',
            'status': 'failed',
            'attempts': 2,
            'test_result': 'TESTS_FAILED',
            'report_url': 'https://report.url',
            'points_earned': 0
        }
        
        state = PhaseState.from_dict(data)
        
        assert state.phase_id == 'challenge'
        assert state.status == PhaseStatus.FAILED
        assert state.attempts == 2
        assert state.test_result == 'TESTS_FAILED'


class TestTaskState:
    """Test TaskState model"""
    
    def test_create_task_state(self, sample_task_state):
        """Test creating a TaskState instance"""
        assert sample_task_state.email == "test@example.com"
        assert sample_task_state.game == "game01"
        assert sample_task_state.task_id == "01_test_task"
        assert sample_task_state.npc == "test_npc"
        assert sample_task_state.status == TaskStatus.NOT_STARTED
        assert sample_task_state.total_points == 0
    
    def test_partition_and_sort_keys(self, sample_task_state):
        """Test DynamoDB key properties"""
        assert sample_task_state.pk == "test@example.com"
        assert sample_task_state.sk == "game01#01_test_task"
    
    def test_get_phase_state(self, sample_task_state):
        """Test getting phase state"""
        # Add a phase state
        phase_state = PhaseState("setup", PhaseStatus.PASSED)
        sample_task_state.phase_states["setup"] = phase_state
        
        # Get it
        retrieved = sample_task_state.get_phase_state("setup")
        assert retrieved is not None
        assert retrieved.phase_id == "setup"
        
        # Get non-existent
        retrieved = sample_task_state.get_phase_state("nonexistent")
        assert retrieved is None
    
    def test_get_or_create_phase_state(self, sample_task_state):
        """Test getting or creating phase state"""
        # Create new
        state = sample_task_state.get_or_create_phase_state("setup")
        assert state.phase_id == "setup"
        assert state.status == PhaseStatus.PENDING
        
        # Get existing
        state2 = sample_task_state.get_or_create_phase_state("setup")
        assert state2 is state
    
    def test_calculate_progress(self, sample_task_state, sample_manifest):
        """Test calculating progress"""
        # No phases completed
        progress = sample_task_state.calculate_progress(sample_manifest)
        assert progress == 0.0
        
        # Setup completed (0 points, but counts for progress)
        setup_state = PhaseState("setup", PhaseStatus.PASSED)
        sample_task_state.phase_states["setup"] = setup_state
        progress = sample_task_state.calculate_progress(sample_manifest)
        assert progress == pytest.approx(1/3)  # 1 of 3 required non-auto phases
        
        # Challenge completed
        challenge_state = PhaseState("challenge", PhaseStatus.PASSED)
        sample_task_state.phase_states["challenge"] = challenge_state
        progress = sample_task_state.calculate_progress(sample_manifest)
        assert progress == pytest.approx(2/3)
        
        # All completed
        check_state = PhaseState("check", PhaseStatus.PASSED)
        sample_task_state.phase_states["check"] = check_state
        progress = sample_task_state.calculate_progress(sample_manifest)
        assert progress == 1.0
    
    def test_mark_completed(self, sample_task_state):
        """Test marking task as completed"""
        sample_task_state.status = TaskStatus.IN_PROGRESS
        sample_task_state.mark_completed()
        
        assert sample_task_state.status == TaskStatus.COMPLETED
        assert sample_task_state.completed_at is not None
        assert sample_task_state.updated_at is not None
    
    def test_to_dict(self, sample_task_state):
        """Test converting TaskState to dictionary"""
        # Add a phase state
        phase_state = PhaseState("setup", PhaseStatus.PASSED)
        sample_task_state.phase_states["setup"] = phase_state
        
        data = sample_task_state.to_dict()
        
        assert data['email'] == 'test@example.com'
        assert data['gameTask'] == 'game01#01_test_task'
        assert data['status'] == 'not_started'
        assert 'phase_states' in data
        assert 'setup' in data['phase_states']
    
    def test_from_dict(self):
        """Test creating TaskState from dictionary"""
        data = {
            'email': 'user@test.com',
            'game': 'game02',
            'task_id': '02_task',
            'npc': 'npc2',
            'status': 'in_progress',
            'current_phase_id': 'challenge',
            'phase_states': {
                'setup': {
                    'phase_id': 'setup',
                    'status': 'passed',
                    'attempts': 1,
                    'points_earned': 0
                }
            },
            'session_data': {'key': 'value'},
            'total_points': 50,
            'created_at': '2024-01-01T00:00:00',
            'updated_at': '2024-01-01T01:00:00'
        }
        
        state = TaskState.from_dict(data)
        
        assert state.email == 'user@test.com'
        assert state.status == TaskStatus.IN_PROGRESS
        assert state.current_phase_id == 'challenge'
        assert 'setup' in state.phase_states
        assert state.total_points == 50
    
    def test_round_trip_conversion(self, sample_task_state):
        """Test converting to dict and back"""
        # Add some data
        sample_task_state.status = TaskStatus.IN_PROGRESS
        sample_task_state.current_phase_id = "setup"
        sample_task_state.phase_states["setup"] = PhaseState("setup", PhaseStatus.PASSED)
        sample_task_state.total_points = 100
        
        data = sample_task_state.to_dict()
        state = TaskState.from_dict(data)
        
        assert state.email == sample_task_state.email
        assert state.status == sample_task_state.status
        assert state.current_phase_id == sample_task_state.current_phase_id
        assert state.total_points == sample_task_state.total_points
        assert len(state.phase_states) == len(sample_task_state.phase_states)
