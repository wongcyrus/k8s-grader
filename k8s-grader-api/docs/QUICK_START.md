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
3. ✅ Run integration tests automatically (15 tests)
4. ✅ Clean up test data

## 🧪 Running Tests Locally

### Unit Tests (Fast)
```bash
./run_tests.sh  # 106 tests, < 5 seconds
```

### Integration Tests (Automatic)
```bash
./run_integration_tests.sh  # 15 tests, ~60 seconds
# No manual setup needed - fully self-contained!
```

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

- **Game mode:** use the published `GameUrl` output with `wsUrl`
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
├── tests/                   # 106 unit tests
│   └── integration/         # 15 integration tests (self-contained)
└── template.yaml            # SAM infrastructure
```

## 🧪 Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| Core Models | 48 | 98% |
| Repositories | 15 | 75% |
| Services | 24 | 95-100% |
| Handler | 19 | 85% |
| **Total** | **106** | **63%** |

**Integration Tests**: 15 tests, self-contained, automatic setup/cleanup

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
- ✅ **106 unit tests passing** - 63% coverage
- ✅ **15 integration tests passing** - All self-contained

See [CHANGELOG.md](CHANGELOG.md) for recent updates.
