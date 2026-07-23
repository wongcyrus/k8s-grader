"""Tests for database repositories"""
import pytest
from datetime import datetime, timedelta, timezone

from common.database.repositories import (
    AccountRepository,
    ExecutionGuardRepository,
    NpcRepository,
    RequestThrottleRepository,
    TaskStateRepository,
    normalize_endpoint,
)
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
        """Test that reassigning to different NPC is prevented by atomic operation"""
        repo = NpcRepository()
        
        # Assign to npc1
        success1 = repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        assert success1 is True
        assert repo.get_assigned_npc("user@test.com", "game01") == "npc1"
        
        # Try to reassign to npc2 - should fail due to atomic operation
        success2 = repo.assign_task("user@test.com", "game01", "npc2", "02_task")
        assert success2 is False
        
        # Should still be npc1
        npc = repo.get_assigned_npc("user@test.com", "game01")
        assert npc == "npc1"
    
    def test_different_games_independent(self, dynamodb_tables):
        """Test that different games have independent assignments"""
        repo = NpcRepository()
        
        # Assign in game01
        repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        
        # game01 should have assignment
        assert repo.get_assigned_npc("user@test.com", "game01") == "npc1"
        
        # game02 should not have assignment
        assert repo.get_assigned_npc("user@test.com", "game02") is None
    
    def test_assign_task_atomic_operation(self, dynamodb_tables):
        """Test that assign_task prevents race conditions with atomic operation"""
        repo = NpcRepository()
        
        # First assignment should succeed
        success1 = repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        assert success1 is True
        
        # Second assignment should fail (conditional write fails)
        success2 = repo.assign_task("user@test.com", "game01", "npc2", "01_task")
        assert success2 is False
        
        # Verify only first NPC is assigned
        assigned_npc = repo.get_assigned_npc("user@test.com", "game01")
        assert assigned_npc == "npc1"
    
    def test_assign_task_after_clear(self, dynamodb_tables):
        """Test that assign_task works after clearing previous assignment"""
        repo = NpcRepository()
        
        # First assignment
        repo.assign_task("user@test.com", "game01", "npc1", "01_task")
        
        # Clear assignment
        repo.clear_assignment("user@test.com", "game01")
        
        # Second assignment should succeed
        success = repo.assign_task("user@test.com", "game01", "npc2", "02_task")
        assert success is True
        
        # Verify second NPC is assigned
        assigned_npc = repo.get_assigned_npc("user@test.com", "game01")
        assert assigned_npc == "npc2"


class TestAccountRepository:
    """Test AccountRepository"""

    def test_normalize_endpoint_trims_trailing_slash(self):
        assert normalize_endpoint("https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev/") == (
            "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev"
        )

    def test_is_endpoint_exist_treats_trailing_slash_as_same_endpoint(self, dynamodb_tables):
        repo = AccountRepository()
        repo.save(
            "student1@example.com",
            "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev/",
            "cert",
            "key",
        )

        assert repo.is_endpoint_exist(
            "student2@example.com",
            "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev",
        ) is True

    def test_save_persists_normalized_endpoint(self, dynamodb_tables):
        repo = AccountRepository()
        repo.save(
            "student1@example.com",
            "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev/",
            "cert",
            "key",
        )

        stored = repo.get("student1@example.com")
        assert stored["endpoint"] == "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev"


class TestWebSocketProtectionRepositories:
    def test_request_throttle_claim_blocks_until_expired(self, dynamodb_tables):
        repo = RequestThrottleRepository()

        assert repo.claim_request(
            "game#user@test.com#game01#talk",
            email="user@test.com",
            channel="game_ws",
            action="talk",
            cooldown_seconds=5,
        ) is True
        assert repo.claim_request(
            "game#user@test.com#game01#talk",
            email="user@test.com",
            channel="game_ws",
            action="talk",
            cooldown_seconds=5,
        ) is False

        dynamodb_tables["ws_throttle_table"].update_item(
            Key={"scope_key": "game#user@test.com#game01#talk"},
            UpdateExpression="SET expires_at = :expired",
            ExpressionAttributeValues={":expired": 0},
        )

        assert repo.claim_request(
            "game#user@test.com#game01#talk",
            email="user@test.com",
            channel="game_ws",
            action="talk",
            cooldown_seconds=5,
        ) is True

    def test_execution_guard_acquire_and_release(self, dynamodb_tables):
        repo = ExecutionGuardRepository()

        assert repo.acquire(
            "exam#user@test.com#EXAM-001#game02#087_task#run",
            email="user@test.com",
            channel="exam_ws",
            action="run",
            ttl_seconds=60,
        ) is True
        assert repo.acquire(
            "exam#user@test.com#EXAM-001#game02#087_task#run",
            email="user@test.com",
            channel="exam_ws",
            action="run",
            ttl_seconds=60,
        ) is False

        assert repo.attach_request_id(
            "exam#user@test.com#EXAM-001#game02#087_task#run",
            "request-123",
        ) is True
        item = dynamodb_tables["ws_execution_guard_table"].get_item(
            Key={"scope_key": "exam#user@test.com#EXAM-001#game02#087_task#run"}
        )["Item"]
        assert item["request_id"] == "request-123"

        assert repo.release("exam#user@test.com#EXAM-001#game02#087_task#run") is True
        assert "Item" not in dynamodb_tables["ws_execution_guard_table"].get_item(
            Key={"scope_key": "exam#user@test.com#EXAM-001#game02#087_task#run"}
        )
