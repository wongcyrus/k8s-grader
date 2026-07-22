# Architecture Overview

## System Design

The K8s Grader API is a serverless application built on AWS using:
- **AWS Lambda** - Serverless compute
- **API Gateway** - REST API endpoints
- **DynamoDB** - NoSQL database
- **S3** - Test report storage
- **SAM** - Infrastructure as Code

## Architecture Diagram

```
┌─────────────┐
│   Browser   │
│   (Game)    │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────────────────────────────┐
│       API Gateway                   │
│  /task, /keygen, /save-k8s-account  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Lambda Functions            │
│  ┌──────────────────────────────┐   │
│  │  TaskHandler (Unified)       │   │
│  │  - Start task                │   │
│  │  - Execute phases            │   │
│  │  - Complete task             │   │
│  └──────────────────────────────┘   │
│  ┌──────────────────────────────┐   │
│  │  Keygen                      │   │
│  │  - Generate encrypted keys   │   │
│  └──────────────────────────────┘   │
│  ┌──────────────────────────────┐   │
│  │  SaveK8sAccount              │   │
│  │  - Register K8s credentials  │   │
│  └──────────────────────────────┘   │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         DynamoDB Tables             │
│  - TaskStateTable                   │
│  - AccountTable                     │
│  - ApiKeyTable                      │
│  - NpcLockTable                     │
│  - NpcAssignmentTable               │
│  - NpcBackgroundTable               │
│  - GameSourceTable                  │
│  - TestRecordTable                  │
└─────────────────────────────────────┘
```

## Core Components

### Exam Mode

Exam mode uses a separate WebSocket + durable Lambda path so the browser can queue actions and receive pushed status updates without direct Lambda-to-Lambda orchestration between grading steps.

See [EXAM_DURABLE_FLOW.md](EXAM_DURABLE_FLOW.md) for the full exam-specific flow, state transitions, and runtime-fix history.

### 1. Lambda Functions

#### TaskHandler (Unified Endpoint)
- **Path:** `/task`
- **Purpose:** Single endpoint for all task operations
- **Operations:**
  - Start new task
  - Execute test phases
  - Complete task
  - Get task status

#### Keygen
- **Path:** `/keygen`
- **Purpose:** Generate encrypted API keys
- **Features:**
  - Fernet encryption
  - Email embedded in key
  - Persistent keys (reused)

#### SaveK8sAccount
- **Path:** `/save-k8s-account`
- **Purpose:** Register user K8s credentials
- **Stores:**
  - K8s endpoint URL
  - Client certificate
  - Client key

### 2. Database Layer

#### Repository Pattern
All database access uses repository classes:

```python
from common.database import TaskStateRepository

repo = TaskStateRepository()
state = repo.get(email, game, task_id)
repo.save(state)
```

#### Key Repositories
- **TaskStateRepository** - Task progress and state
- **AccountRepository** - User K8s credentials
- **ApiKeyRepository** - Encrypted API keys
- **NpcRepository** - NPC locks and assignments
- **GameSourceRepository** - Game source URIs (private S3 archive)

See [DATABASE_GUIDE.md](DATABASE_GUIDE.md) for details.

### 3. State Machine

Task execution follows a state machine pattern:

```
NOT_STARTED → IN_PROGRESS → COMPLETED
                    ↓
                 FAILED
```

**Phase States:**
```
PENDING → RUNNING → PASSED
              ↓
           FAILED (with retry)
```

See `common/state_machine/task_state_machine.py` for implementation.

### 4. Domain Models

#### TaskState
Represents user's progress on a task:
- Current phase
- Phase states (passed/failed/pending)
- Attempt counts
- Points earned
- Session data

#### PhaseConfig
Defines a test phase:
- Phase ID
- Test file path
- Max attempts
- Points value
- Prerequisites

#### TaskManifest
Defines task structure:
- Task metadata
- Phase configurations
- Execution order

## Data Flow

### Starting a Task

```
1. User → API Gateway → TaskHandler
2. TaskHandler validates user credentials
3. TaskStateMachine.start_task()
4. Create TaskState (status: IN_PROGRESS)
5. TaskStateRepository.save()
6. Return task info to user
```

### Executing a Phase

```
1. User → API Gateway → TaskHandler
2. TaskHandler loads TaskState
3. TaskStateMachine.can_execute_phase()
4. TestRunner.run_phase()
   - Download private game source archive from S3
   - Generate session data
   - Run pytest
   - Upload report to S3
5. TaskStateMachine.execute_phase()
6. Update phase state (PASSED/FAILED)
7. TaskStateRepository.save()
8. Return results to user
```

### Completing a Task

```
1. User → API Gateway → TaskHandler
2. TaskHandler loads TaskState
3. TaskStateMachine.can_complete_task()
4. TaskStateMachine.complete_task()
5. Update status to COMPLETED
6. TaskStateRepository.save()
7. Return completion info
```

## Security

### API Key Authentication
- Encrypted with Fernet (symmetric encryption)
- Email embedded in key
- Validated on every request
- Keys stored in ApiKeyTable

### K8s Credentials
- Stored encrypted in DynamoDB
- Only accessible by user's email
- Used for test execution

### IAM Roles
- Lambda execution role with minimal permissions
- DynamoDB access scoped to specific tables
- S3 access for test reports only

## Scalability

### Serverless Benefits
- Auto-scaling Lambda functions
- Pay-per-use pricing
- No server management
- High availability

### DynamoDB
- On-demand capacity mode
- Automatic scaling
- Single-digit millisecond latency
- Global tables support (future)

### Caching
- Repository instances reuse connections
- Lazy table initialization
- Session data cached in TaskState

## Testing Strategy

### Unit Tests (119 tests)
- Mock all AWS services
- Test business logic
- Fast execution (< 1 minute)
- 55% code coverage

### Integration Tests (13 tests)
- Real AWS services
- End-to-end workflows
- Deployed stack validation
- Performance testing

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for details.

## Deployment

### Infrastructure as Code
All infrastructure defined in `template.yaml`:
- Lambda functions
- API Gateway
- DynamoDB tables
- IAM roles
- S3 buckets

### Automated Deployment
```bash
./deploy.sh
```

Runs:
1. Unit tests
2. SAM build
3. SAM deploy
4. Post-deployment setup

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for details.

## Monitoring

### CloudWatch Logs
- All Lambda functions log to CloudWatch
- Structured logging with context
- Error tracking and alerting

### CloudWatch Metrics
- Lambda invocations
- Error rates
- Duration
- DynamoDB metrics

### X-Ray Tracing
- Distributed tracing enabled
- Performance analysis
- Bottleneck identification

## Future Enhancements

### Planned Features
1. Batch operations for repositories
2. Caching layer (Redis/ElastiCache)
3. GraphQL API
4. WebSocket support for real-time updates
5. Multi-region deployment
6. Advanced analytics dashboard

### Performance Optimizations
1. Connection pooling
2. Query optimization
3. Batch DynamoDB operations
4. Lambda provisioned concurrency
5. API Gateway caching

## Best Practices

### Code Organization
- Repository pattern for data access
- Service layer for business logic
- State machine for state transitions
- Domain models for data structures

### Error Handling
- Graceful degradation
- Detailed error logging
- User-friendly error messages
- Retry logic for transient failures

### Testing
- Test-driven development
- High code coverage
- Integration tests for critical paths
- Performance testing

### Documentation
- Code comments
- API documentation
- Architecture diagrams
- Deployment guides

## Related Documentation

- [../README.md](../README.md) - Project overview
- [GAME_LOGIC.md](GAME_LOGIC.md) - Complete game flow and mechanics
- [DATABASE_GUIDE.md](DATABASE_GUIDE.md) - Database layer
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Testing strategy
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deployment process
- [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md) - Task configuration
