"""Tests for database repositories"""
import pytest
from datetime import datetime, timedelta, timezone

from common.database.repositories import TaskStateRepository, NpcRepository
from common.models.task_state import TaskState, TaskStatus, PhaseState, PhaseStatus


class TestTaskStateRepository:
    """Test TaskStateRepository"""
    
    def test_save_and_get(self, dynamodb_tables, sample_task_state):
        """Test saving and retrieving task state"""
        repo = TaskStateRepository()
        
        # Save
        success = repo.save(sample_task_state)
        assert success is True
        
        # Get
        retrieved = repo.get(
            sample_task_state.email,
            sample_task_state.game,
            sample_task_state.task_id
        )
        
        assert retrieved is not None
        assert retrieved.email == sample_task_state.email
        assert retrieved.game == sample_task_state.game
        assert retrieved.task_id == sample_task_state.task_id
        assert retrieved.status == sample_task_state.status
    
    def test_get_nonexistent(self, dynamodb_tables):
        """Test getting non-existent task state"""
        repo = TaskStateRepository()
        
        retrieved = repo.get("nonexistent@example.com", "game01", "01_task")
        
        assert retrieved is None
    
    def test_save_updates_timestamp(self, dynamodb_tables, sample_task_state):
        """Test that save updates the timestamp"""
        repo = TaskStateRepository()
        
        original_time = sample_task_state.updated_at
        
        # Save
        repo.save(sample_task_state)
        
        # Check timestamp was updated
        assert sample_task_state.updated_at != original_time
    
    def test_save_with_phase_states(self, dynamodb_tables, sample_task_state):
        """Test saving task state with phase states"""
        repo = TaskStateRepository()
        
        # Add phase states
        sample_task_state.phase_states['setup'] = PhaseState('setup', PhaseStatus.PASSED)
        sample_task_state.phase_states['challenge'] = PhaseState('challenge', PhaseStatus.FAILED, attempts=2)
        
        # Save
        repo.save(sample_task_state)
        
        # Retrieve
        retrieved = repo.get(
            sample_task_state.email,
            sample_task_state.game,
            sample_task_state.task_id
        )
        
        assert len(retrieved.phase_states) == 2
        assert 'setup' in retrieved.phase_states
        assert retrieved.phase_states['setup'].status == PhaseStatus.PASSED
        assert retrieved.phase_states['challenge'].attempts == 2
    
    def test_delete(self, dynamodb_tables, sample_task_state):
        """Test deleting task state"""
        repo = TaskStateRepository()
        
        # Save first
        repo.save(sample_task_state)
        
        # Delete
        success = repo.delete(
            sample_task_state.email,
            sample_task_state.game,
            sample_task_state.task_id
        )
        
        assert success is True
        
        # Verify deleted
        retrieved = repo.get(
            sample_task_state.email,
            sample_task_state.game,
            sample_task_state.task_id
        )
        assert retrieved is None
    
    def test_get_completed_tasks(self, dynamodb_tables):
        """Test getting completed tasks"""
        repo = TaskStateRepository()
        
        # Create and save multiple tasks
        tasks = [
            TaskState(
                email="user@test.com",
                game="game01",
                task_id=f"0{i}_task",
                npc="npc1",
                status=TaskStatus.COMPLETED if i % 2 == 0 else TaskStatus.IN_PROGRESS,
                current_phase_id=None
            )
            for i in range(1, 6)
        ]
        
        for task in tasks:
            repo.save(task)
        
        # Get completed tasks
        completed = repo.get_completed_tasks("user@test.com", "game01")
        
        # Should have 2 completed tasks (02_task, 04_task)
        assert len(completed) == 2
        assert "02_task" in completed
        assert "04_task" in completed
    
    def test_get_in_progress_task(self, dynamodb_tables):
        """Test getting in-progress task"""
        repo = TaskStateRepository()
        
        # Create completed task
        completed_task = TaskState(
            email="user@test.com",
            game="game01",
            task_id="01_task",
            npc="npc1",
            status=TaskStatus.COMPLETED,
            current_phase_id=None
        )
        repo.save(completed_task)
        
        # Create in-progress task
        in_progress_task = TaskState(
            email="user@test.com",
            game="game01",
            task_id="02_task",
            npc="npc1",
            status=TaskStatus.IN_PROGRESS,
            current_phase_id="setup"
        )
        repo.save(in_progress_task)
        
        # Get in-progress task
        retrieved = repo.get_in_progress_task("user@test.com", "game01")
        
        assert retrieved is not None
        assert retrieved.task_id == "02_task"
        assert retrieved.status == TaskStatus.IN_PROGRESS


class TestNpcRepository:
    """Test NpcRepository"""
    
    def test_lock_and_check(self, dynamodb_tables):
        """Test locking and checking NPC"""
        repo = NpcRepository()
        
        # Initially not locked
        is_locked = repo.is_locked("user@test.com", "game01", "npc1")
        assert is_locked is False
        
        # Lock NPC
        success = repo.lock_npc("user@test.com", "game01", "npc1", minutes=30)
        assert success is True
        
        # Now should be locked
        is_locked = repo.is_locked("user@test.com", "game01", "npc1")
        assert is_locked is True
    
    def test_lock_expiration(self, dynamodb_tables):
        """Test that lock expires after TTL"""
        repo = NpcRepository()
        
        # Lock with negative minutes (expired)
        success = repo.lock_npc("user@test.com", "game01", "npc1", minutes=-1)
        assert success is True
        
        # Should not be locked (expired)
        is_locked = repo.is_locked("user@test.com", "game01", "npc1")
        assert is_locked is False
    
    def test_unlock_npc(self, dynamodb_tables):
        """Test unlocking NPC"""
        repo = NpcRepository()
        
        # Lock first
        repo.lock_npc("user@test.com", "game01", "npc1", minutes=30)
        assert repo.is_locked("user@test.com", "game01", "npc1") is True
        
        # Unlock
        success = repo.unlock_npc("user@test.com", "game01", "npc1")
        assert success is True
        
        # Should not be locked
        is_locked = repo.is_locked("user@test.com", "game01", "npc1")
        assert is_locked is False
    
    def test_different_npcs_independent(self, dynamodb_tables):
        """Test that different NPCs have independent locks"""
        repo = NpcRepository()
        
        # Lock npc1
        repo.lock_npc("user@test.com", "game01", "npc1", minutes=30)
        
        # npc1 should be locked
        assert repo.is_locked("user@test.com", "game01", "npc1") is True
        
        # npc2 should not be locked
        assert repo.is_locked("user@test.com", "game01", "npc2") is False
    
    def test_assign_and_get_npc(self, dynamodb_tables):
        """Test assigning and getting NPC"""
        repo = NpcRepository()
        
        # Initially no assignment
        npc = repo.get_assigned_npc("user@test.com", "game01")
        assert npc is None
        
        # Assign task
        success = repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        assert success is True
        
        # Get assigned NPC
        npc = repo.get_assigned_npc("user@test.com", "game01")
        assert npc == "npc1"
    
    def test_clear_assignment(self, dynamodb_tables):
        """Test clearing assignment"""
        repo = NpcRepository()
        
        # Assign first
        repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        assert repo.get_assigned_npc("user@test.com", "game01") == "npc1"
        
        # Clear
        success = repo.clear_assignment("user@test.com", "game01")
        assert success is True
        
        # Should be None
        npc = repo.get_assigned_npc("user@test.com", "game01")
        assert npc is None
    
    def test_reassign_npc(self, dynamodb_tables):
        """Test reassigning to different NPC"""
        repo = NpcRepository()
        
        # Assign to npc1
        repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        assert repo.get_assigned_npc("user@test.com", "game01") == "npc1"
        
        # Reassign to npc2
        repo.assign_task("user@test.com", "game01", "npc2", "02_task")
        
        # Should be npc2 now
        npc = repo.get_assigned_npc("user@test.com", "game01")
        assert npc == "npc2"
    
    def test_different_games_independent(self, dynamodb_tables):
        """Test that different games have independent assignments"""
        repo = NpcRepository()
        
        # Assign in game01
        repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        
        # game01 should have assignment
        assert repo.get_assigned_npc("user@test.com", "game01") == "npc1"
        
        # game02 should not have assignment
        assert repo.get_assigned_npc("user@test.com", "game02") is None
