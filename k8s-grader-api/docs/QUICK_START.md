# Quick Start Guide

Get up and running in minutes!

## 🚀 Deploy and Test

```bash
cd k8s-grader/k8s-grader-api

# Deploy with automatic integration tests
./deploy.sh

# Or skip integration tests
./deploy.sh --skip-integration
```

That's it! The deployment script will:
1. ✅ Run unit tests (106 tests)
2. ✅ Build and deploy to AWS
3. ✅ Run integration tests automatically
4. ✅ Clean up test data

## 🧪 Running Tests Locally

### Unit Tests (Fast)
```bash
./run_tests.sh  # 106 tests, < 5 seconds
```

### Integration Tests (Automatic)
```bash
./run_integration_tests.sh  # Current deployed integration suite
# No manual setup needed - fully self-contained!
```

### Private Game Source (Exercise first)
```bash
# Dry-run validation
python scripts/seed_game_source.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --game game02

# Apply after dry-run output looks correct
python scripts/seed_game_source.py ... --apply
```

This makes the private game playable from the **Exercise Portal** without exposing a public zip URL.

### Exam Code (Validate first, then apply)
```bash
# Dry-run validation
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

# Apply after dry-run output looks correct
python scripts/seed_exam_code.py ... --apply
```

Recommended order for a new private game such as `game02`:
1. Run `seed_game_source.py` to upload the private archive and enable exercise mode.
2. Open the Exercise Portal and choose `game02`.
3. Run `seed_exam_code.py` to publish the exam scope for `game02`.
4. Open the Exam Page and use the exam code there.

### Reset Task Stage (DB state fix)
```bash
# Dry-run reset to CHECK phase (no write)
python scripts/reset_task_stage.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --email student@example.com \
  --game game02 \
  --task 087_kustomize_configuration \
  --phase-id check

# Apply
python scripts/reset_task_stage.py ... --apply
```

### Reset all tasks for one game
```bash
# Dry-run reset every saved game02 task back to setup
python scripts/reset_task_stage.py \
  --stack-name k8s-grader-api-dev \
  --region us-east-1 \
  --email student@example.com \
  --game game02 \
  --all-tasks \
  --phase-id setup \
  --clear-all-phases

# Apply
python scripts/reset_task_stage.py ... --apply
```

This reset regenerates the task `session_data` with the same deterministic per-student generator used by the Lambda exam flow, so local reset/admin reset values stay aligned with runtime values.

## 🎯 Key Concepts

### Task Manifest
Declarative task configuration in `manifest.json`:

```json
{
  "task_id": "01_test_task",
  "title": "Test Task",
  "difficulty": "beginner",
  "phases": [
    {
      "id": "setup",
      "test_file": "test_01_setup.py",
      "timeout_seconds": 30,
      "points": 0
    }
  ]
}
```

See [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md) for complete documentation.

### State Machine
Manages task lifecycle:

```
NOT_STARTED → IN_PROGRESS → COMPLETED
                    ↓
                 FAILED
```

### Runtime Endpoints

- **Exercise portal:** use the published `StudentPortalUrl` output for `index.html`, save the API key once, then launch the RPG game from that page
- **Exam page:** open `StudentPortalUrl/exam.html` for exam verify/start/run flows
- **Teacher dashboard:** open `StudentPortalUrl/teacher.html` with a teacher API key whose email is included in the `TeacherEmails` deploy parameter
- **Exam mode:** use `/exam/verify-code`, `/exam/start`, `/exam/run`, `/exam/status`, and `/exam/records`
- **Legacy note:** the old game `/task` request/response API has been removed

## 📂 Project Structure

```
k8s-grader-api/
├── common-layer/common/
│   ├── models/              # Core domain models
│   ├── state_machine/       # State transitions
│   ├── database/            # DynamoDB repos
│   └── services/            # Business logic
├── task-handler/            # Exam REST endpoints
├── tests/                   # 239 unit tests
│   └── integration/         # Self-contained deployed-stack integration tests
└── template.yaml            # SAM infrastructure
```

## 🧪 Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| Core Models | 48 | 98% |
| Repositories | 15 | 75% |
| Services | 24 | 95-100% |
| Handler | 19 | 85% |
| **Total** | **239** | **66%** |

**Integration Tests**: self-contained deployed-stack validation, mainly for REST/bootstrap coverage

## 💡 Common Tasks

### Add a New Task
1. Create directory: `k8s-game-rule/tests/game01/XX_task_name/`
2. Create `manifest.json`
3. Create test files
4. Test locally

### Debug Tests
```bash
# Verbose output
pytest tests/ -vv

# Specific test
pytest tests/test_task_service.py::test_start_task -v

# With print statements
pytest tests/ -s
```

### Local API Testing
```bash
sam build && sam local start-api
curl "http://localhost:3000/exam/verify-code?examCode=EXAM-001" -H "x-api-key: test"
```

## 📚 Full Documentation

- **[../README.md](../README.md)** - Complete project overview
- **[DOCS_INDEX.md](DOCS_INDEX.md)** - Documentation index
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Deployment instructions
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Complete testing guide
- **[MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)** - Task configuration
- **[SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)** - Security guide

## 🎉 What's New

- ✅ **Self-contained integration tests** - No manual setup required!
- ✅ **Automatic API key generation** - Tests generate their own keys
- ✅ **Automatic cleanup** - 9 DynamoDB tables + API Gateway
- ✅ **239 unit tests passing** - 66% coverage
- ✅ **Self-contained deployed-stack integration tests** - For REST/bootstrap validation

See [CHANGELOG.md](CHANGELOG.md) for recent updates.
