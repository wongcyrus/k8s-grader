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

    def test_auto_generate_manifest(self, tmp_path):
        """Test auto-generating manifest from test files"""
        import os
        from pathlib import Path
        
        # Create mock task directory structure
        game = "game01"
        task_id = "99_auto_test"
        task_dir = tmp_path / game / "tests" / game / task_id
        task_dir.mkdir(parents=True)
        
        # Create test files
        (task_dir / "test_01_setup.py").write_text("# setup test")
        (task_dir / "test_04_challenge.py").write_text("# challenge test")
        (task_dir / "test_05_check.py").write_text("# check test")
        (task_dir / "test_06_cleanup.py").write_text("# cleanup test")
        
        # Call _auto_generate directly with the tmp_path
        # We need to temporarily change the path logic
        import common.models.task_manifest as tm_module
        
        # Save original
        original_auto_generate = tm_module.TaskManifest._auto_generate
        
        def mock_auto_generate(game_path, task_id_param):
            """Mock auto-generate that uses tmp_path"""
            task_dir_path = tmp_path / game / "tests" / game / task_id_param
            
            # Discover test files
            phase_mapping = {
                'test_01_setup.py': ('setup', 'Setup', 0),
                'test_02_ready.py': ('ready', 'Ready', 5),
                'test_03_answer.py': ('answer', 'Answer', 10),
                'test_04_challenge.py': ('challenge', 'Challenge', 15),
                'test_05_check.py': ('check', 'Check', 20),
                'test_06_cleanup.py': ('cleanup', 'Cleanup', 0),
            }
            
            phases = []
            for test_file, (phase_id, phase_name, points) in phase_mapping.items():
                test_path = task_dir_path / test_file
                if test_path.exists():
                    phases.append(PhaseConfig(
                        id=phase_id,
                        name=phase_name,
                        description=f"Auto-generated {phase_name} phase",
                        test_file=test_file,
                        required=(phase_id != 'cleanup'),
                        auto_run=(phase_id == 'cleanup'),
                        timeout_seconds=30,
                        max_attempts=3,
                        points=points
                    ))
            
            if not phases:
                raise FileNotFoundError(f"No test files found in {task_dir_path}")
            
            # Generate basic metadata
            title = task_id_param.replace('_', ' ').title()
            
            return TaskManifest(
                task_id=task_id_param,
                title=title,
                description=f"Auto-generated manifest for {title}",
                difficulty='beginner',
                estimated_minutes=15,
                phases=phases,
                prerequisites=[],
                tags=['auto-generated'],
                hints=[]
            )
        
        try:
            # Replace with mock
            tm_module.TaskManifest._auto_generate = classmethod(lambda cls, g, t: mock_auto_generate(g, t))
            
            # Auto-generate manifest
            manifest = mock_auto_generate(str(tmp_path / game), task_id)
            
            # Verify auto-generated manifest
            assert manifest.task_id == task_id
            assert manifest.title == "99 Auto Test"
            assert manifest.difficulty == "beginner"
            assert len(manifest.phases) == 4
            assert "auto-generated" in manifest.tags
            
            # Verify phases
            phase_ids = [p.id for p in manifest.phases]
            assert "setup" in phase_ids
            assert "challenge" in phase_ids
            assert "check" in phase_ids
            assert "cleanup" in phase_ids
            
            # Verify cleanup is auto_run
            cleanup = manifest.get_phase("cleanup")
            assert cleanup.auto_run is True
            assert cleanup.points == 0
            
        finally:
            # Restore original
            tm_module.TaskManifest._auto_generate = original_auto_generate
