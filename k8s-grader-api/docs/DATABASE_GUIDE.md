# Database Guide

## Overview

The K8s Grader API uses a **Repository pattern** for database access, providing clean separation between business logic and data persistence.

## Architecture

```
common/database/
├── __init__.py          # Exports and convenience functions
└── repositories.py      # Repository classes
```

## Repository Classes

### 1. TaskStateRepository
Manages task state persistence and progress tracking.

```python
from common.database import TaskStateRepository

repo = TaskStateRepository()

# Get task state
state = repo.get(email="user@example.com", game="game01", task_id="task1")

# Save task state
repo.save(state)

# Delete task state
repo.delete(email="user@example.com", game="game01", task_id="task1")

# Get completed tasks
completed = repo.get_completed_tasks(email="user@example.com", game="game01")

# Get in-progress task
current = repo.get_in_progress_task(email="user@example.com", game="game01")
```

### 2. NpcRepository
Manages NPC locks and task assignments.

```python
from common.database import NpcRepository

repo = NpcRepository()

# Check if NPC is locked
is_locked = repo.is_locked(email="user@example.com", game="game01", npc="alice")

# Lock NPC for 30 minutes
repo.lock_npc(email="user@example.com", game="game01", npc="alice", minutes=30)

# Unlock NPC
repo.unlock_npc(email="user@example.com", game="game01", npc="alice")

# Get assigned NPC
npc = repo.get_assigned_npc(email="user@example.com", game="game01")

# Assign task from NPC
repo.assign_task(email="user@example.com", game="game01", npc="alice", task_id="task1")

# Clear assignment
repo.clear_assignment(email="user@example.com", game="game01")
```

### 3. AccountRepository
Manages user accounts and Kubernetes credentials.

```python
from common.database import AccountRepository

repo = AccountRepository()

# Check if endpoint exists
exists = repo.is_endpoint_exist(email="user@example.com", endpoint="https://k8s.example.com")

# Save account
repo.save(
    email="user@example.com",
    endpoint="https://k8s.example.com",
    client_certificate="cert_data",
    client_key="key_data"
)

# Get account data
account = repo.get(email="user@example.com")
```

### 4. ApiKeyRepository
Manages encrypted API keys.

```python
from common.database import ApiKeyRepository

repo = ApiKeyRepository()

# Get API key
api_key = repo.get(email="user@example.com")

# Save API key
repo.save(email="user@example.com", api_key="encrypted_key")
```

### 5. GameTaskRepository
Tracks user task progress.

```python
from common.database import GameTaskRepository

repo = GameTaskRepository()

# Get all tasks for user in game
tasks = repo.get_tasks(email="user@example.com", game="game01")

# Save task
repo.save(email="user@example.com", game="game01", task="task1")

# Delete task
repo.delete(email="user@example.com", game="game01", task="task1")
```

### 6. SessionRepository
Manages game session data.

```python
from common.database import SessionRepository

repo = SessionRepository()

# Save session
repo.save(
    email="user@example.com",
    game="game01",
    task="task1",
    session={"key": "value"}
)

# Get session
session = repo.get(email="user@example.com", game="game01", task="task1")

# Delete session
repo.delete(email="user@example.com", game="game01", task="task1")
```

### 7. TestRecordRepository
Stores test execution records.

```python
from common.database import TestRecordRepository

repo = TestRecordRepository()

# Save test record
repo.save(
    email="user@example.com",
    game="game01",
    current_task="task1",
    game_phase="PHASE_1",
    test_result="PASSED",
    bucket="test-bucket",
    key="test-key",
    report_url="https://...",
    now_str="2026-01-30T14:00:00Z"
)
```

### 8. NpcTaskRepository
Manages ongoing NPC task assignments.

```python
from common.database import NpcTaskRepository

repo = NpcTaskRepository()

# Save ongoing task
repo.save_ongoing(email="user@example.com", game="game01", npc="alice", task="task1")

# Get ongoing task
npc, task = repo.get_ongoing(email="user@example.com", game="game01")

# Delete ongoing task
repo.delete_ongoing(email="user@example.com", game="game01")
```

### 9. NpcBackgroundRepository
Stores NPC character backgrounds.

```python
from common.database import NpcBackgroundRepository

repo = NpcBackgroundRepository()

# Get NPC background
background = repo.get(name="alice")

# Save NPC background
repo.save(
    name="alice",
    age="25",
    gender="female",
    background="A skilled Kubernetes engineer..."
)
```

### 10. NpcLockRepository
Manages NPC locks with TTL.

```python
from common.database import NpcLockRepository

repo = NpcLockRepository()

# Save lock (30 minutes default)
repo.save(email="user@example.com", game="game01", npc="alice", minutes=30)

# Get lock
lock = repo.get(email="user@example.com", game="game01", npc="alice")
```

### 11. ConversationRepository
Stores AI conversation templates.

```python
from common.database import ConversationRepository

repo = ConversationRepository()

# Get instruction template
instruction = repo.get_instruction_template(game="game01", task="task1", npc="alice")

# Get random chat
chat = repo.get_random_chat(npc="alice")
```

### 12. GameSourceRepository
Manages game source URIs.

`game01` is the public sample. Private games like `game02` should store their own private `s3://bucket/key` source under the matching game ID.

```python
from common.database import GameSourceRepository

repo = GameSourceRepository()

# Get game source
source = repo.get(game="game01")

# Save game source
repo.save(game="game01", source="s3://private-bucket/game-rule.zip")

# Save private game source
repo.save(game="game02", source="s3://private-bucket/game02.zip")
```

## Convenience Functions

For simple use cases, convenience functions are available:

```python
from common.database import (
    save_game_source,
    get_game_source,
    save_npc_background,
    get_npc_background,
    get_api_key,
    save_api_key,
    is_endpoint_exist,
    save_account,
    get_user_data,
    get_ai_instruction_template,
    get_ai_random_chat,
)

# Use directly without instantiating repositories
save_game_source("game01", "s3://private-bucket/game-rule.zip")
source = get_game_source("game01")
```

## Dependency Injection

Repositories support dependency injection for testing:

```python
class MyService:
    def __init__(self, game_repo=None):
        self.game_repo = game_repo or GameSourceRepository()
    
    def get_source(self, game: str):
        return self.game_repo.get(game)

# Production
service = MyService()

# Testing with mock
from unittest.mock import Mock
mock_repo = Mock(spec=GameSourceRepository)
service = MyService(game_repo=mock_repo)
```

## Custom Table Names

For testing, you can specify custom table names:

```python
# Use custom table for testing
repo = GameSourceRepository(table_name="TestGameSourceTable")
```

## Error Handling

All repository methods handle errors gracefully:

```python
repo = GameSourceRepository()

# Returns None on error, logs error message
source = repo.get("game01")
if source is None:
    # Handle error case
    pass

# Returns False on error, logs error message
success = repo.save("game01", "s3://private-bucket/game-rule.zip")
if not success:
    # Handle error case
    pass
```

## Logging

All repositories use Python's logging module:

```python
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Repository operations will log:
# - INFO: Successful operations
# - ERROR: Failed operations with details
# - DEBUG: Detailed operation info
```

## Best Practices

### 1. Use Repository Classes
```python
# Good - testable, mockable
repo = GameSourceRepository()
source = repo.get("game01")

# Acceptable - for simple cases
from common.database import get_game_source
source = get_game_source("game01")
```

### 2. Handle None Returns
```python
# Always check for None
source = repo.get("game01")
if source is None:
    # Handle missing data
    return default_value
```

### 3. Check Boolean Returns
```python
# Check save/delete results
success = repo.save("game01", "https://...")
if not success:
    # Handle save failure
    raise Exception("Failed to save")
```

### 4. Use Dependency Injection
```python
# Makes testing easier
class TaskService:
    def __init__(self, task_repo=None):
        self.task_repo = task_repo or TaskStateRepository()
```

### 5. Log Appropriately
```python
import logging
logger = logging.getLogger(__name__)

# Log business logic, not repository internals
result = repo.get("game01")
if result:
    logger.info(f"Found game source for game01")
```

## Testing

### Unit Tests with Mocks
```python
from unittest.mock import Mock, patch
from common.database import GameSourceRepository

def test_my_function():
    # Mock repository
    mock_repo = Mock(spec=GameSourceRepository)
    mock_repo.get.return_value = "s3://private-bucket/game-rule.zip"
    
    # Test with mock
    service = MyService(game_repo=mock_repo)
    result = service.get_source("game01")
    
    assert result == "s3://private-bucket/game-rule.zip"
    mock_repo.get.assert_called_once_with("game01")
```

### Integration Tests
```python
from common.database import GameSourceRepository

def test_repository_integration():
    # Use real repository with test table
    repo = GameSourceRepository(table_name="TestGameSourceTable")
    
    # Test operations
    repo.save("test_game", "s3://test-bucket/test.zip")
    source = repo.get("test_game")
    
    assert source == "s3://test-bucket/test.zip"
```

## Environment Variables

Repositories use environment variables for table names:

```bash
# Required environment variables
export TaskStateTable="k8s-grader-api-dev-TaskStateTable-XXX"
export AccountTable="k8s-grader-api-dev-AccountTable-XXX"
export ApiKeyTable="k8s-grader-api-dev-ApiKeyTable-XXX"
export GameTaskTable="k8s-grader-api-dev-GameTaskTable-XXX"
export SessionTable="k8s-grader-api-dev-SessionTable-XXX"
export TestRecordTable="k8s-grader-api-dev-TestRecordTable-XXX"
export NpcTaskTable="k8s-grader-api-dev-NpcTaskTable-XXX"
export NpcBackgroundTable="k8s-grader-api-dev-NpcBackgroundTable-XXX"
export NpcLockTable="k8s-grader-api-dev-NpcLockTable-XXX"
export NpcAssignmentTable="k8s-grader-api-dev-NpcAssignmentTable-XXX"
export ConversationTable="k8s-grader-api-dev-ConversationTable-XXX"
export GameSourceTable="k8s-grader-api-dev-GameSourceTable-XXX"
```

These are automatically set by AWS Lambda when deployed via SAM.

## Performance Considerations

### Lazy Initialization
Tables are lazily initialized on first access:

```python
repo = GameSourceRepository()  # No DynamoDB connection yet
source = repo.get("game01")    # Connection established here
```

### Connection Reuse
Repository instances reuse DynamoDB connections:

```python
# Good - reuse instance
repo = GameSourceRepository()
for game in games:
    repo.get(game)  # Reuses connection

# Less efficient - creates new connection each time
for game in games:
    repo = GameSourceRepository()
    repo.get(game)
```

### Batch Operations
For bulk operations, consider using batch APIs:

```python
# Future improvement - batch operations
# repo.batch_save([item1, item2, item3])
```

## Troubleshooting

### Table Not Found
```python
# Error: ResourceNotFoundException
# Solution: Check environment variable is set
import os
print(os.getenv('GameSourceTable'))
```

### Permission Denied
```python
# Error: AccessDeniedException
# Solution: Ensure Lambda role has DynamoDB permissions
```

### Connection Timeout
```python
# Error: Connection timeout
# Solution: Check VPC configuration and security groups
```

## Additional Resources

- [AWS DynamoDB Documentation](https://docs.aws.amazon.com/dynamodb/)
- [Boto3 DynamoDB Guide](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/dynamodb.html)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
