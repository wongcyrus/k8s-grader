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

### API Endpoint

**POST /task**

Start task:
```bash
curl -X POST https://api.example.com/task \
  -H "x-api-key: YOUR_KEY" \
  -d '{"action":"start","game":"game01","npc":"npc1"}'
```

## 📂 Project Structure

```
k8s-grader-api/
├── common-layer/common/
│   ├── models/              # Core domain models
│   ├── state_machine/       # State transitions
│   ├── database/            # DynamoDB repos
│   └── services/            # Business logic
├── task-handler/            # Main /task endpoint
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
curl -X POST http://localhost:3000/task -H "x-api-key: test" -d '{...}'
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
