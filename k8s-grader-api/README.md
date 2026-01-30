# K8s Grader API

A serverless Kubernetes learning game grading system built with AWS SAM, Lambda, and DynamoDB. This system provides automated grading for Kubernetes challenges with progress tracking, points system, and NPC-based task assignment.

## 🎯 Project Overview

A serverless Kubernetes learning game grading system with clean architecture:
- **Single unified endpoint** (`/task`) for all task operations
- **Simplified database** using repository pattern
- **State machine pattern** for explicit state transitions
- **Declarative task configuration** via manifest.json files
- **Progress tracking** with points system and retry limits

### Architecture Highlights

- **106 tests passing** with 63% overall coverage
- **Unit tests**: Fast, mocked, test business logic (106 tests)
- **Integration tests**: Real API calls, test deployed stack
- **Core models**: PhaseConfig, TaskManifest, TaskState (98% coverage)
- **Services layer**: TaskService, TestRunner (95-100% coverage)
- **Database repositories**: TaskState, NpcAssignment (75% coverage)
- **Unified handler**: Single `/task` endpoint (100% coverage)

## 📂 Project Structure

```
k8s-grader-api/
├── common-layer/common/          # Shared Lambda layer
│   ├── models/                   # Core domain models
│   ├── state_machine/            # State transition logic
│   ├── database/                 # DynamoDB repositories
│   ├── services/                 # Business logic
│   └── handler.py                # Common utilities
├── task-handler/                 # Main task endpoint
├── keygen/                       # API key generation
├── save-k8s-account/             # Account registration
├── post_deployment/              # Post-deploy setup
├── tests/                        # Unit tests (106 tests)
│   └── integration/              # Integration tests (real API)
├── template.yaml                 # SAM infrastructure
└── deploy.sh                     # Automated deployment

## 🚀 Quick Start

### Prerequisites
- AWS SAM CLI
- Python 3.11+
- Docker
- AWS credentials configured

### Deploy
```bash
./deploy.sh --guided
```

Follow the prompts to configure your deployment. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

### Run Tests
```bash
./run_tests.sh
```

Or manually:
```bash
venv/bin/python -m pytest tests/ -v --cov=common
```

## 🎯 Key Concepts

### Session Data & Personalization

Each user gets **unique, personalized task parameters** to prevent cheating:

**How it works:**
1. When a user starts a task, the system generates unique session data using:
   - `random_name()` - generates random names seeded by student ID
   - `random_number(from, to)` - generates random numbers seeded by student ID  
   - `student_id()` - extracts from email (e.g., "john" from "john@example.com")
   - `base64_encode()` - encodes values

2. Session data is stored in `TaskState.session_data` (in TaskStateTable)

3. When tests run, session data is passed to pytest via `/tmp/json_input.json`

**Example session.json template:**
```json
{
  "namespace": "{{random_name()}}{{student_id()}}"
}
```

**Generated for user john@example.com:**
```json
{
  "namespace": "happy_dolphin_john"
}
```

This ensures each user has different resource names, preventing copy-paste cheating!

**Note:** Session data is stored directly in TaskState (in TaskStateTable), not in a separate table. This provides better data locality and simplifies the architecture.

### Task Manifest (manifest.json)
Each task has a declarative configuration file (optional):

```json
{
  "task_id": "01_default_namespace",
  "title": "Default Namespace",
  "difficulty": "beginner",
  "estimated_minutes": 15,
  "phases": [
    {
      "id": "setup",
      "name": "Setup",
      "test_file": "test_01_setup.py",
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 0
    },
    {
      "id": "challenge",
      "name": "Challenge",
      "test_file": "test_04_challenge.py",
      "timeout_seconds": 60,
      "max_attempts": 5,
      "points": 100
    }
  ]
}
```

**Note:** manifest.json is **optional**! If not present, the system auto-generates a manifest by discovering test files (test_01_setup.py, test_04_challenge.py, etc.).

**Generate manifests automatically:**
```bash
# Generate for all tasks in game01
python k8s-game-rule/tools/generate_manifests.py game01

# Generate for specific task
python k8s-game-rule/tools/generate_manifests.py game01 --task 01_default_namespace

# Preview without writing files
python k8s-game-rule/tools/generate_manifests.py game01 --dry-run
```

See [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md) for complete documentation.

### State Machine
The system uses a state machine pattern for explicit state transitions:

```
NOT_STARTED → IN_PROGRESS → COMPLETED
                    ↓
                 FAILED
```

Each phase tracks:
- Execution status (pending/running/passed/failed)
- Attempt count and retry limits
- Test results and reports
- Points earned

### API Endpoint

**POST /task**
- Unified endpoint for all task operations
- Handles task start, phase execution, and completion
- Returns current state and next actions

Request:
```json
{
  "action": "start_task",
  "game": "game01",
  "task_id": "01_default_namespace",
  "npc": "npc1"
}
```

Response:
```json
{
  "success": true,
  "state": {
    "status": "in_progress",
    "current_phase_id": "setup",
    "progress_percentage": 0,
    "total_points": 0
  },
  "next_action": {
    "phase_id": "setup",
    "test_file": "test_01_setup.py"
  }
}
```

## 🔧 Development

### Local Testing
```bash
# Run all tests
./run_tests.sh

# Run specific test file
venv/bin/python -m pytest tests/test_task_service.py -v

# Run with coverage
venv/bin/python -m pytest tests/ --cov=common --cov-report=html
```

### Local API Testing
```bash
# Start local API
sam build && sam local start-api

# Test endpoint
curl -X POST http://localhost:3000/task \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-test-key" \
  -d '{"action":"start_task","game":"game01","task_id":"01_default_namespace","npc":"npc1"}'
```

### Adding a New Task
1. Create task directory: `k8s-game-rule/tests/game01/XX_task_name/`
2. Create `manifest.json` (see MANIFEST_GUIDE.md)
3. Create test files referenced in manifest
4. Create `instruction.md` for users
5. Test locally before deploying

## 📚 Documentation

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)** - Task manifest creation guide
- **[SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)** - API key encryption guide
- **[QUICK_START.md](QUICK_START.md)** - Quick reference for common tasks

## 🏗️ Infrastructure

### AWS Resources
- **API Gateway**: REST API with custom domain support
- **Lambda Functions**: 
  - TaskHandler (main endpoint)
  - KeyGen (API key generation)
  - SaveK8sAccount (account registration)
  - PostDeployment (setup automation)
- **DynamoDB Tables**:
  - TaskStateTable (task progress tracking, includes session data)
  - NpcAssignmentTable (NPC locks and assignments)
  - AccountTable, ApiKeyTable, TestRecordTable, etc. (supporting tables)
- **S3 Bucket**: Test reports storage
- **Secrets Manager**: Sensitive configuration

### Cost Estimate
- Lambda: ~$5-10/month (1000 requests/day)
- DynamoDB: ~$2-5/month (on-demand)
- API Gateway: ~$3.50/month (1M requests)
- S3: ~$1/month (storage + requests)
- **Total: ~$12-20/month**

## 🔒 Security

- API key authentication with Fernet encryption
- Secrets stored in AWS Secrets Manager
- IAM roles with least privilege
- VPC endpoints for private access (optional)
- CloudTrail logging enabled

See [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md) for security details.

## 🧪 Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| Core Models | 48 | 98% |
| Database Repositories | 15 | 75% |
| Services Layer | 24 | 95-100% |
| Lambda Handler | 6 | 100% |
| **Total** | **93** | **61%** |

## 🐛 Troubleshooting

### Common Issues

**Tests failing locally**
```bash
# Ensure venv is activated
source venv/bin/activate
# Reinstall dependencies
pip install -r tests/requirements.txt
```

**Deployment fails**
```bash
# Check AWS credentials
aws sts get-caller-identity
# Validate template
sam validate
# Check CloudFormation events
aws cloudformation describe-stack-events --stack-name k8s-grader-api
```

**API returns 500 error**
```bash
# Check Lambda logs
sam logs -n TaskHandlerFunction --stack-name k8s-grader-api --tail
```

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for more troubleshooting tips.

## 🧪 Testing

### Unit Tests (Fast, Mocked)

Run unit tests locally with mocked AWS services:

```bash
./run_tests.sh
```

- **106 tests** covering all components
- **63% code coverage**
- Uses `moto` to mock AWS services
- Fast execution (< 5 seconds)
- No AWS credentials required

### Integration Tests (Real API)

Test against the deployed stack on AWS:

```bash
# 1. Deploy the stack
./deploy.sh

# 2. Generate encrypted API key
./generate_test_api_key.sh
# Visit the URL, copy the generated key, and set it:
export TEST_API_KEY="your-generated-encrypted-key"

# 3. Run integration tests
./run_integration_tests.sh
```

Integration tests:
- Call real API Gateway endpoints
- Interact with real DynamoDB tables
- Verify end-to-end functionality
- Test performance and error handling
- Require deployed stack and AWS credentials
- **Use encrypted API keys** (contains user email)

See [tests/integration/README.md](tests/integration/README.md) for detailed documentation.

### Test Comparison

| Aspect | Unit Tests | Integration Tests |
|--------|-----------|-------------------|
| Speed | Fast (< 5s) | Slow (30s+) |
| Dependencies | Mocked | Real AWS |
| Cost | Free | AWS charges |
| When to run | Every commit | Before/after deploy |
| Purpose | Code logic | End-to-end validation |

**Best Practice:** Run unit tests during development, integration tests before deployment.

## 📝 License

See [LICENSE](../LICENSE) file for details.

## 🤝 Contributing

The architecture is designed to be:
- Easy to understand and maintain
- Well-tested with high coverage
- Documented with clear guides
- Extensible for new features

When adding features:
1. Write tests first (both unit and integration)
2. Update documentation
3. Follow existing patterns
4. Maintain test coverage above 60%
