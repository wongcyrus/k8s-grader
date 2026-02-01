"""Database repositories for data access"""
import os
import json
import time
import boto3
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from boto3.dynamodb.conditions import Key
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
        Assign task to user from NPC (atomic operation to prevent race conditions)
        
        Args:
            email: User email
            game: Game identifier
            npc: NPC name
            task_id: Task identifier
            
        Returns:
            True if successful, False if assignment already exists
        """
        try:
            # Use conditional write to prevent race condition
            # Only succeed if no assignment exists (attribute_not_exists)
            self.assignment_table.put_item(
                Item={
                    'email': email,
                    'game': game,
                    'npc': npc,
                    'task_id': task_id,
                    'assigned_at': datetime.now(timezone.utc).isoformat()
                },
                ConditionExpression='attribute_not_exists(email) AND attribute_not_exists(game)'
            )
            logger.info(f"Assigned task {task_id} from {npc} to {email}")
            return True
        except self.assignment_table.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Assignment already exists for {email} in {game}")
            return False
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



class AccountRepository:
    """Repository for user account data"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('AccountTable', 'AccountTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def is_endpoint_exist(self, email: str, endpoint: str) -> bool:
        """Check if endpoint exists for a different user"""
        try:
            response = self.table.query(
                IndexName="EndpointIndex",
                KeyConditionExpression=Key("endpoint").eq(endpoint)
            )
            items = response.get("Items", [])
            if items:
                return items[0].get("email") != email
            return False
        except Exception as e:
            logger.error(f"Failed to check endpoint: {e}")
            return False
    
    def save(self, email: str, endpoint: str, client_certificate: str, client_key: str) -> bool:
        """Save user account"""
        try:
            self.table.put_item(
                Item={
                    "email": email,
                    "endpoint": endpoint,
                    "client_certificate": client_certificate,
                    "client_key": client_key,
                    "time": int(time.time()),
                }
            )
            logger.info(f"Saved account for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to save account: {e}")
            return False
    
    def get(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user account data"""
        try:
            response = self.table.get_item(Key={"email": email})
            return response.get("Item")
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return None


class ApiKeyRepository:
    """Repository for API key management"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('ApiKeyTable', 'ApiKeyTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get(self, email: str) -> Optional[str]:
        """Get API key for user"""
        try:
            response = self.table.get_item(Key={"email": email})
            item = response.get("Item")
            return item.get("api_key") if item else None
        except Exception as e:
            logger.error(f"Failed to get API key: {e}")
            return None
    
    def save(self, email: str, api_key: str) -> bool:
        """Save API key for user"""
        try:
            self.table.put_item(Item={"email": email, "api_key": api_key})
            logger.info(f"Saved API key for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to save API key: {e}")
            return False


class GameTaskRepository:
    """Repository for game task tracking"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('GameTaskTable', 'GameTaskTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get_tasks(self, email: str, game: str) -> List[str]:
        """Get all tasks for user in game"""
        if not email or not game:
            return []
        if not game.isalnum():
            raise ValueError("Game parameter must be alphanumeric")
        
        try:
            response = self.table.query(
                KeyConditionExpression=Key("email").eq(email)
                & Key("game").begins_with(f"{game}#")
            )
            items = response.get("Items", [])
            return sorted([item["game"].split("#", 1)[1] for item in items])
        except Exception as e:
            logger.error(f"Failed to get tasks: {e}")
            return []
    
    def save(self, email: str, game: str, task: str) -> bool:
        """Save game task"""
        try:
            self.table.put_item(
                Item={"email": email, "game": f"{game}#{task}", "time": int(time.time())}
            )
            logger.debug(f"Saved task {game}#{task} for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to save task: {e}")
            return False
    
    def delete(self, email: str, game: str, task: str) -> bool:
        """Delete game task"""
        try:
            self.table.delete_item(Key={"email": email, "game": f"{game}#{task}"})
            logger.debug(f"Deleted task {game}#{task} for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            return False


class SessionRepository:
    """Repository for game session data"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('SessionTable', 'SessionTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def save(self, email: str, game: str, task: str, session: Dict[str, Any]) -> bool:
        """Save game session"""
        try:
            self.table.put_item(
                Item={
                    "email": email,
                    "game": f"{game}#{task}",
                    "session": json.dumps(session),
                    "time": int(time.time()),
                }
            )
            logger.debug(f"Saved session for {email} - {game}#{task}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    def get(self, email: str, game: str, task: str) -> Optional[Dict[str, Any]]:
        """Get game session"""
        try:
            response = self.table.get_item(Key={"email": email, "game": f"{game}#{task}"})
            item = response.get("Item")
            if item:
                return json.loads(item["session"])
            return None
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    def delete(self, email: str, game: str, task: str) -> bool:
        """Delete game session"""
        try:
            self.table.delete_item(Key={"email": email, "game": f"{game}#{task}"})
            logger.debug(f"Deleted session for {email} - {game}#{task}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False


class TestRecordRepository:
    """Repository for test execution records"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('TestRecordTable', 'TestRecordTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def save(self, email: str, game: str, current_task: str, game_phase: str,
             test_result: str, bucket: str, key: str, report_url: str, now_str: str) -> bool:
        """Save test record"""
        try:
            self.table.put_item(
                Item={
                    "email": email,
                    "gameTime": game + "#" + now_str,
                    "task": current_task,
                    "gamePhase": game_phase,
                    "testResult": test_result,
                    "bucket": bucket,
                    "key": key,
                    "reportUrl": report_url,
                    "time": now_str,
                }
            )
            logger.info(f"Saved test record for {email} - {game}#{current_task}")
            return True
        except Exception as e:
            logger.error(f"Failed to save test record: {e}")
            return False


class NpcTaskRepository:
    """Repository for NPC task assignments"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('NpcTaskTable', 'NpcTaskTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def save_ongoing(self, email: str, game: str, npc: str, task: str) -> bool:
        """Save ongoing NPC task"""
        try:
            self.table.put_item(
                Item={
                    "email": email,
                    "game": game,
                    "npc": npc,
                    "task": task,
                    "time": int(time.time()),
                }
            )
            logger.info(f"Saved ongoing task {task} from {npc} for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to save ongoing task: {e}")
            return False
    
    def get_ongoing(self, email: str, game: str) -> Tuple[Optional[str], Optional[str]]:
        """Get ongoing NPC task"""
        try:
            response = self.table.get_item(Key={"email": email, "game": game})
            item = response.get("Item")
            if item:
                return item["npc"], item["task"]
            return None, None
        except Exception as e:
            logger.error(f"Failed to get ongoing task: {e}")
            return None, None
    
    def delete_ongoing(self, email: str, game: str) -> bool:
        """Delete ongoing NPC task"""
        try:
            self.table.delete_item(Key={"email": email, "game": game})
            logger.debug(f"Deleted ongoing task for {email} - {game}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete ongoing task: {e}")
            return False


class NpcBackgroundRepository:
    """Repository for NPC background data"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('NpcBackgroundTable', 'NpcBackgroundTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get(self, name: str) -> Optional[Dict[str, str]]:
        """Get NPC background"""
        try:
            response = self.table.get_item(Key={"name": name})
            item = response.get("Item")
            if item:
                return {
                    "name": item.get("name"),
                    "age": item.get("age"),
                    "gender": item.get("gender"),
                    "background": item.get("background"),
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get NPC background: {e}")
            return None
    
    def save(self, name: str, age: str, gender: str, background: str) -> bool:
        """Save NPC background"""
        try:
            self.table.put_item(
                Item={
                    "name": name,
                    "age": age,
                    "gender": gender,
                    "background": background,
                    "time": int(time.time()),
                }
            )
            logger.info(f"Saved NPC background for {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save NPC background: {e}")
            return False


class NpcLockRepository:
    """Repository for NPC lock management"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('NpcLockTable', 'NpcLockTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def save(self, email: str, game: str, npc: str, minutes: int = 30) -> bool:
        """Save NPC lock"""
        if not email or not game or not npc:
            raise ValueError("Email, game, and npc are required")
        
        try:
            expiration_time = int((datetime.now() + timedelta(minutes=minutes)).timestamp())
            self.table.put_item(
                Item={
                    "email": email,
                    "gameNpc": game + "#" + npc,
                    "ttl": expiration_time,
                    "time": int(time.time()),
                }
            )
            logger.info(f"Locked NPC {npc} for {email} ({minutes} min)")
            return True
        except Exception as e:
            logger.error(f"Failed to save NPC lock: {e}")
            return False
    
    def get(self, email: str, game: str, npc: str) -> Optional[Dict[str, Any]]:
        """Get NPC lock"""
        try:
            response = self.table.get_item(
                Key={"email": email, "gameNpc": game + "#" + npc}
            )
            return response.get("Item")
        except Exception as e:
            logger.error(f"Failed to get NPC lock: {e}")
            return None


class ConversationRepository:
    """Repository for AI conversation templates"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('ConversationTable', 'ConversationTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get_instruction_template(self, game: str, task: str, npc: str) -> Optional[str]:
        """Get AI instruction template"""
        try:
            key = f"{game}#{task}#{npc}"
            response = self.table.get_item(Key={"key": key})
            item = response.get("Item")
            return item.get("instruction") if item else None
        except Exception as e:
            logger.error(f"Failed to get instruction template: {e}")
            return None
    
    def get_random_chat(self, npc: str) -> Optional[str]:
        """Get random chat instruction for NPC"""
        try:
            response = self.table.get_item(Key={"key": npc})
            item = response.get("Item")
            return item.get("instruction") if item else None
        except Exception as e:
            logger.error(f"Failed to get random chat: {e}")
            return None


class GameSourceRepository:
    """Repository for game source URLs"""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.getenv('GameSourceTable', 'GameSourceTable')
        self._table = None
    
    @property
    def table(self):
        if self._table is None:
            dynamodb = _get_dynamodb_resource()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def get(self, game: str) -> Optional[str]:
        """Get game source URL"""
        try:
            response = self.table.get_item(Key={"game": game})
            item = response.get("Item")
            return item.get("source") if item else None
        except Exception as e:
            logger.error(f"Failed to get game source: {e}")
            return None
    
    def save(self, game: str, source: str) -> bool:
        """Save game source URL"""
        try:
            self.table.put_item(
                Item={
                    "game": game,
                    "source": source,
                    "time": int(time.time()),
                }
            )
            logger.info(f"Saved game source for {game}")
            return True
        except Exception as e:
            logger.error(f"Failed to save game source: {e}")
            return False
