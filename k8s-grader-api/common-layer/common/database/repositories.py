"""Database repositories for data access"""
import os
import boto3
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)


def _get_dynamodb_resource():
    """Get DynamoDB resource (lazy initialization for testing)"""
    return boto3.resource('dynamodb')


class TaskStateRepository:
    """Repository for TaskState persistence"""
    
    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize repository
        
        Args:
            table_name: DynamoDB table name (defaults to env var)
        """
        self.table_name = table_name or os.getenv('TaskStateTable', 'TaskStateTable')
        self._table = None
    
    @property
    def table(self):
        """Lazy load table"""
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get(self, email: str, game: str, task_id: str):
        """
        Get task state
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            
        Returns:
            TaskState instance or None
        """
        from common.models.task_state import TaskState
        
        try:
            response = self.table.get_item(
                Key={
                    'email': email,
                    'gameTask': f"{game}#{task_id}"
                }
            )
            item = response.get('Item')
            return TaskState.from_dict(item) if item else None
        except Exception as e:
            logger.error(f"Failed to get task state: {e}")
            return None
    
    def save(self, state) -> bool:
        """
        Save task state
        
        Args:
            state: TaskState instance
            
        Returns:
            True if successful
        """
        try:
            # Update timestamp
            state.updated_at = datetime.now(timezone.utc).isoformat()
            
            self.table.put_item(Item=state.to_dict())
            logger.debug(f"Saved state for {state.email} - {state.task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save task state: {e}")
            return False
    
    def delete(self, email: str, game: str, task_id: str) -> bool:
        """
        Delete task state
        
        Args:
            email: User email
            game: Game identifier
            task_id: Task identifier
            
        Returns:
            True if successful
        """
        try:
            self.table.delete_item(
                Key={
                    'email': email,
                    'gameTask': f"{game}#{task_id}"
                }
            )
            logger.info(f"Deleted state for {email} - {game}#{task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete task state: {e}")
            return False
    
    def get_completed_tasks(self, email: str, game: str) -> List[str]:
        """
        Get list of completed task IDs
        
        Args:
            email: User email
            game: Game identifier
            
        Returns:
            List of task IDs
        """
        from common.models.task_state import TaskStatus
        
        try:
            response = self.table.query(
                IndexName='StatusIndex',
                KeyConditionExpression='email = :email AND #status = :status',
                FilterExpression='begins_with(gameTask, :game)',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':email': email,
                    ':status': TaskStatus.COMPLETED.value,
                    ':game': f"{game}#"
                }
            )
            items = response.get('Items', [])
            return [item['task_id'] for item in items]
        except Exception as e:
            logger.error(f"Failed to get completed tasks: {e}")
            return []
    
    def get_in_progress_task(self, email: str, game: str):
        """
        Get current in-progress task
        
        Args:
            email: User email
            game: Game identifier
            
        Returns:
            TaskState instance or None
        """
        from common.models.task_state import TaskStatus, TaskState
        
        try:
            response = self.table.query(
                IndexName='StatusIndex',
                KeyConditionExpression='email = :email AND #status = :status',
                FilterExpression='begins_with(gameTask, :game)',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':email': email,
                    ':status': TaskStatus.IN_PROGRESS.value,
                    ':game': f"{game}#"
                },
                Limit=1
            )
            items = response.get('Items', [])
            return TaskState.from_dict(items[0]) if items else None
        except Exception as e:
            logger.error(f"Failed to get in-progress task: {e}")
            return None


class NpcRepository:
    """Repository for NPC-related data"""
    
    def __init__(self, lock_table_name: Optional[str] = None, 
                 assignment_table_name: Optional[str] = None):
        """
        Initialize repository
        
        Args:
            lock_table_name: NPC lock table name
            assignment_table_name: NPC assignment table name
        """
        self.lock_table_name = lock_table_name or os.getenv('NpcLockTable', 'NpcLockTable')
        self.assignment_table_name = assignment_table_name or os.getenv('NpcAssignmentTable', 'NpcAssignmentTable')
        
        self._lock_table = None
        self._assignment_table = None
    
    @property
    def lock_table(self):
        """Lazy load lock table"""
        if self._lock_table is None:
            dynamodb = _get_dynamodb_resource()
            self._lock_table = dynamodb.Table(self.lock_table_name)
        return self._lock_table
    
    @property
    def assignment_table(self):
        """Lazy load assignment table"""
        if self._assignment_table is None:
            dynamodb = _get_dynamodb_resource()
            self._assignment_table = dynamodb.Table(self.assignment_table_name)
        return self._assignment_table
    
    def is_locked(self, email: str, game: str, npc: str) -> bool:
        """
        Check if NPC is locked for user
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            
        Returns:
            True if locked
        """
        try:
            response = self.lock_table.get_item(
                Key={
                    'email': email,
                    'gameNpc': f"{game}#{npc}"
                }
            )
            item = response.get('Item')
            if not item:
                return False
            
            # Check if TTL expired
            ttl = item.get('ttl', 0)
            return ttl > datetime.now(timezone.utc).timestamp()
        except Exception as e:
            logger.error(f"Failed to check NPC lock: {e}")
            return False
    
    def lock_npc(self, email: str, game: str, npc: str, minutes: int = 30) -> bool:
        """
        Lock NPC for specified minutes
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            minutes: Lock duration in minutes
            
        Returns:
            True if successful
        """
        try:
            ttl = int((datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp())
            self.lock_table.put_item(
                Item={
                    'email': email,
                    'gameNpc': f"{game}#{npc}",
                    'ttl': ttl,
                    'locked_at': datetime.now(timezone.utc).isoformat()
                }
            )
            logger.info(f"Locked NPC {npc} for {email} ({minutes} min)")
            return True
        except Exception as e:
            logger.error(f"Failed to lock NPC: {e}")
            return False
    
    def unlock_npc(self, email: str, game: str, npc: str) -> bool:
        """
        Unlock NPC immediately
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            
        Returns:
            True if successful
        """
        try:
            self.lock_table.delete_item(
                Key={
                    'email': email,
                    'gameNpc': f"{game}#{npc}"
                }
            )
            logger.info(f"Unlocked NPC {npc} for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to unlock NPC: {e}")
            return False
    
    def get_assigned_npc(self, email: str, game: str) -> Optional[str]:
        """
        Get NPC currently assigned to user
        
        Args:
            email: User email
            game: Game identifier
            
        Returns:
            NPC name or None
        """
        try:
            response = self.assignment_table.get_item(
                Key={
                    'email': email,
                    'game': game
                }
            )
            item = response.get('Item')
            return item.get('npc') if item else None
        except Exception as e:
            logger.error(f"Failed to get assigned NPC: {e}")
            return None
    
    def assign_task(self, email: str, game: str, npc: str, task_id: str) -> bool:
        """
        Assign task to user from NPC
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            task_id: Task identifier
            
        Returns:
            True if successful
        """
        try:
            self.assignment_table.put_item(
                Item={
                    'email': email,
                    'game': game,
                    'npc': npc,
                    'task_id': task_id,
                    'assigned_at': datetime.now(timezone.utc).isoformat()
                }
            )
            logger.info(f"Assigned task {task_id} from {npc} to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to assign task: {e}")
            return False
    
    def clear_assignment(self, email: str, game: str) -> bool:
        """
        Clear task assignment
        
        Args:
            email: User email
            game: Game identifier
            
        Returns:
            True if successful
        """
        try:
            self.assignment_table.delete_item(
                Key={
                    'email': email,
                    'game': game
                }
            )
            logger.info(f"Cleared assignment for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear assignment: {e}")
            return False
