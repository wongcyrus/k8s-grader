# K8s Grader API

A serverless Kubernetes learning game grading system built with AWS SAM, Lambda, and DynamoDB. This system provides automated grading for Kubernetes challenges with progress tracking, points system, and NPC-based task assignment.

## 🎯 Project Overview

A serverless Kubernetes learning game grading system with clean architecture:
- **REST exam endpoints** under `/exam/*`
- **WebSocket + durable Lambda flow** for exam mode
- **WebSocket + durable Lambda flow** for RPG game mode
- **Simplified database** using repository pattern
- **State machine pattern** for explicit state transitions
- **Declarative task configuration** via manifest.json files
- **Shared Kubernetes account storage** across exam and game flows
- **Progress tracking** with points system and game-specific retry behavior

### Architecture Highlights

- **239 passing unit tests** with 66% overall coverage
- **Unit tests**: Fast, mocked, test business logic and current WebSocket runtime behavior
- **Integration tests**: Self-contained deployed-stack validation for REST/bootstrap flows
- **Core models**: PhaseConfig, TaskManifest, TaskState (98% coverage)
- **Services layer**: TaskService, TestRunner (95-100% coverage)
- **Database repositories**: TaskState, NpcAssignment (75% coverage)
- **Exam handler**: shared `/exam/*` REST entrypoint

## 📂 Project Structure

```
k8s-grader-api/
├── common-layer/common/          # Shared Lambda layer
│   ├── models/                   # Core domain models
│   ├── state_machine/            # State transition logic
│   ├── database/                 # DynamoDB repositories
│   ├── services/                 # Business logic
│   └── handler.py                # Common utilities
├── exam-durable-handler/         # Durable exam command worker
├── exam-ws-handler/              # Exam WebSocket entrypoint
├── game-command-handler/         # Durable RPG game command worker
├── game-ws-handler/              # Game WebSocket entrypoint
├── task-handler/                 # Exam REST endpoints and shared responses
├── keygen/                       # API key generation
├── save-k8s-account/             # Account registration
├── post_deployment/              # Post-deploy setup
├── tests/                        # Unit tests (239 tests)
│   └── integration/              # Deployed-stack integration tests
├── template.yaml                 # SAM infrastructure
├── deploy.sh                     # Automated deployment
└── undeploy.sh                   # Automated AWS teardown

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

The deploy script now packages `../k8s-game-rule` into a private S3 archive, uploads it into the stack-owned **private game source bucket**, and then seeds `GameSourceTable` so `game01` points to that archive. This bucket is separate from SAM's packaging bucket. Follow the prompts to configure your deployment. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

### Undeploy
```bash
./undeploy.sh
```

The undeploy script empties the stack-owned S3 buckets first, then deletes the CloudFormation stack. CloudFormation-managed custom resources, including the post-deployment initializer, are removed as part of normal stack deletion.

`game01` stays the public sample. To make a private game like `game02` usable without any public download link:

1. Seed a private S3 source for **exercise** mode:

```bash
python scripts/seed_game_source.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --game game02
```

2. Apply after the dry-run output looks correct:

```bash
python scripts/seed_game_source.py ... --apply
```

3. Seed an **exam code** for the same game:

```bash
python scripts/seed_exam_code.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --exam-code GAME02-EXAM-20260721 \
  --game game02 \
  --game-tests-root ../../k8s-game-rule/tests \
  --task-folder . \
  --order-mode numeric_prefix \
  --starts-at 2026-01-01T00:00:00+00:00 \
  --ends-at 2026-12-31T23:59:59+00:00 \
  --max-attempts 3
```

4. Apply the exam seed after reviewing the dry-run output:

```bash
python scripts/seed_exam_code.py ... --apply
```

After that:
- the **Exercise Portal** can launch `game02`
- the **Exam Page** can verify codes for `game02`

### Run Tests
```bash
./run_tests.sh
```

Or manually:
```bash
venv/bin/python -m pytest tests/ -v --cov=common
```

### Seed exam code with validation
Use the validator tool to fail fast before enabling exam mode:

```bash
python scripts/seed_exam_code.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --exam-code GAME02-EXAM-20260721 \
  --game game02 \
  --game-tests-root ../../k8s-game-rule/tests \
  --task-folder . \
  --order-mode numeric_prefix \
  --starts-at 2026-01-01T00:00:00+00:00 \
  --ends-at 2026-12-31T23:59:59+00:00 \
  --max-attempts 3
```

Then apply after the dry-run output looks correct:

```bash
python scripts/seed_exam_code.py ... --apply
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

See [docs/MANIFEST_GUIDE.md](docs/MANIFEST_GUIDE.md) for complete documentation.

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

### Runtime Entry Points

- **Exercise portal:** static frontend hosted with the stack at `StudentPortalUrl`; saves the API key/Kubernetes login and launches the RPG flow from `index.html`
- **Exam page:** same hosted site at `StudentPortalUrl/exam.html`; used for exam verify/start/run flows
- **Teacher dashboard:** same hosted site at `StudentPortalUrl/teacher.html`; read-only class overview for progress, score, and recent reports. Access is restricted by the `TeacherEmails` stack parameter.
- **Game mode:** WebSocket-only via `game-ws-handler/` and `game-command-handler/`
- **Exam mode:** REST `/exam/*` plus exam WebSocket updates
- **Account setup:** `/save-k8s-account/`
- **API key generation:** `/keygen/`

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

# Example exam endpoint
curl "http://localhost:3000/exam/verify-code?examCode=EXAM-001" \
  -H "x-api-key: your-test-key"
```

### Adding a New Task
1. Create task directory: `k8s-game-rule/tests/game01/XX_task_name/`
2. Create `manifest.json` (see MANIFEST_GUIDE.md)
3. Create test files referenced in manifest
4. Create `instruction.md` for users
5. Test locally before deploying

## 📚 Documentation

- **[docs/GAME_LOGIC.md](docs/GAME_LOGIC.md)** - Complete game flow and mechanics with diagrams
- **[docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[docs/MANIFEST_GUIDE.md](docs/MANIFEST_GUIDE.md)** - Task manifest creation guide
- **[docs/SECRET_HASH_GUIDE.md](docs/SECRET_HASH_GUIDE.md)** - API key encryption guide
- **[docs/QUICK_START.md](docs/QUICK_START.md)** - Quick reference for common tasks
- **[docs/DOCS_INDEX.md](docs/DOCS_INDEX.md)** - Complete documentation index

## 🏗️ Infrastructure

### AWS Resources
- **API Gateway**: REST API with custom domain support
- **Lambda Functions**: 
  - TaskHandler (exam REST endpoints)
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

- **138 tests** covering all components
- **63% code coverage**
- Uses `moto` to mock AWS services
- Fast execution (< 5 seconds)
- No AWS credentials required

### Integration Tests (Self-Contained, Automatic)

Test against the deployed stack on AWS with **zero manual setup**:

```bash
# 1. Deploy the stack
./deploy.sh  # Integration tests run automatically!

# Or run manually anytime
./run_integration_tests.sh
```

**That's it!** Tests automatically:
- Generate unique test user
- Create test account in DynamoDB
- Auto-generate encrypted API key
- Run the current deployed integration suite
- Clean up all test data

**No manual API key setup required!**

Integration tests:
- ✅ Self-contained (automatic setup/cleanup)
- ✅ Call real API Gateway endpoints
- ✅ Interact with real DynamoDB tables
- ✅ Validate REST/bootstrap workflows against the deployed stack
- ⚠️ Do not yet fully cover the live WebSocket runtime end-to-end
- ✅ **Self-contained** - automatic setup and cleanup
- ✅ **Use encrypted API keys** (contains user email)

See [tests/integration/README.md](tests/integration/README.md) for detailed documentation.

### Test Comparison

| Aspect | Unit Tests | Integration Tests |
|--------|-----------|-------------------|
| Speed | Fast (< 5s) | Moderate (~60s) |
| Dependencies | Mocked | Real AWS |
| Setup | None | **Automatic** ✅ |
| Cleanup | Automatic | **Automatic** ✅ |
| Cost | Free | AWS charges (minimal) |
| When to run | Every commit | **Auto after deploy** ✅ |
| Purpose | Code logic | End-to-end validation |

**Best Practice:** Run unit tests during development. The current integration suite is still useful for deployed REST/bootstrap validation, while most exam/game runtime behavior is now covered by the WebSocket-focused unit/regression suites.

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
