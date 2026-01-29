"""Tests for TaskManifest model"""
import pytest
from common.models.task_manifest import TaskManifest
from common.models.phase_config import PhaseConfig


class TestTaskManifest:
    """Test TaskManifest model"""
    
    def test_create_manifest(self, sample_manifest):
        """Test creating a TaskManifest instance"""
        assert sample_manifest.task_id == "01_test_task"
        assert sample_manifest.title == "Test Task"
        assert sample_manifest.difficulty == "beginner"
        assert sample_manifest.estimated_minutes == 15
        assert len(sample_manifest.phases) == 4
        assert len(sample_manifest.tags) == 2
        assert len(sample_manifest.hints) == 1
    
    def test_get_phase(self, sample_manifest):
        """Test getting a phase by ID"""
        phase = sample_manifest.get_phase("setup")
        assert phase is not None
        assert phase.id == "setup"
        assert phase.name == "Setup"
        
        # Test non-existent phase
        phase = sample_manifest.get_phase("nonexistent")
        assert phase is None
    
    def test_get_first_phase(self, sample_manifest):
        """Test getting the first phase"""
        first = sample_manifest.get_first_phase()
        assert first.id == "setup"
    
    def test_get_next_phase(self, sample_manifest):
        """Test getting next phase"""
        # From setup to challenge
        next_phase = sample_manifest.get_next_phase("setup")
        assert next_phase is not None
        assert next_phase.id == "challenge"
        
        # From challenge to check
        next_phase = sample_manifest.get_next_phase("challenge")
        assert next_phase is not None
        assert next_phase.id == "check"
        
        # From check - no more phases (cleanup is auto_run)
        next_phase = sample_manifest.get_next_phase("check")
        assert next_phase is None
    
    def test_get_next_phase_skips_auto_run(self, sample_phases):
        """Test that get_next_phase skips auto_run phases"""
        # Cleanup is auto_run, so it should be skipped
        manifest = TaskManifest(
            task_id="test",
            title="Test",
            description="Test",
            difficulty="beginner",
            estimated_minutes=10,
            phases=sample_phases,
            prerequisites=[],
            tags=[],
            hints=[]
        )
        
        next_phase = manifest.get_next_phase("check")
        assert next_phase is None  # cleanup is auto_run, so no next phase
    
    def test_get_total_points(self, sample_manifest):
        """Test calculating total points"""
        # setup: 0, challenge: 100, check: 50, cleanup: 0
        total = sample_manifest.get_total_points()
        assert total == 150
    
    def test_from_dict(self, sample_phases):
        """Test creating TaskManifest from dictionary"""
        data = {
            'task_id': '02_test',
            'title': 'Test Task 2',
            'description': 'Another test',
            'difficulty': 'intermediate',
            'estimated_minutes': 20,
            'phases': [p.to_dict() for p in sample_phases],
            'prerequisites': ['01_test'],
            'tags': ['test'],
            'hints': ['hint1', 'hint2']
        }
        
        manifest = TaskManifest.from_dict(data)
        
        assert manifest.task_id == '02_test'
        assert manifest.difficulty == 'intermediate'
        assert len(manifest.phases) == 4
        assert len(manifest.prerequisites) == 1
        assert len(manifest.hints) == 2
    
    def test_to_dict(self, sample_manifest):
        """Test converting TaskManifest to dictionary"""
        data = sample_manifest.to_dict()
        
        assert data['task_id'] == '01_test_task'
        assert data['title'] == 'Test Task'
        assert len(data['phases']) == 4
        assert isinstance(data['phases'][0], dict)
    
    def test_round_trip_conversion(self, sample_manifest):
        """Test converting to dict and back"""
        data = sample_manifest.to_dict()
        manifest = TaskManifest.from_dict(data)
        
        assert manifest.task_id == sample_manifest.task_id
        assert manifest.title == sample_manifest.title
        assert len(manifest.phases) == len(sample_manifest.phases)
        assert manifest.get_total_points() == sample_manifest.get_total_points()
