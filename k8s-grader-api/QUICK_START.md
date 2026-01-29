# Quick Start Guide

## 🚀 Running Tests

```bash
cd k8s-grader/k8s-grader-api
./run_tests.sh
```

Or manually:
```bash
venv/bin/python -m pytest tests/ -v --cov=common --cov-report=html
```

## 📦 Deployment

```bash
./deploy.sh --guided
```

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

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
  -d '{"action":"start_task","game":"game01","task_id":"01_test","npc":"npc1"}'
```

Execute phase:
```bash
curl -X POST https://api.example.com/task \
  -H "x-api-key: YOUR_KEY" \
  -d '{"action":"execute_phase","game":"game01","task_id":"01_test","phase_id":"setup"}'
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
├── tests/                   # 93 tests, 61% coverage
└── template.yaml            # SAM infrastructure
```

## 🧪 Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| Core Models | 48 | 98% |
| Repositories | 15 | 75% |
| Services | 24 | 95-100% |
| Handler | 6 | 100% |
| **Total** | **93** | **61%** |

## 💡 Common Tasks

### Add a New Task
1. Create directory: `k8s-game-rule/tests/game01/XX_task_name/`
2. Create `manifest.json`
3. Create test files
4. Test locally

### Debug Tests
```bash
# Verbose output
venv/bin/python -m pytest tests/ -vv

# Specific test
venv/bin/python -m pytest tests/test_task_service.py::test_start_task -v

# With print statements
venv/bin/python -m pytest tests/ -s
```

### Local API Testing
```bash
sam build && sam local start-api
curl -X POST http://localhost:3000/task -H "x-api-key: test" -d '{...}'
```

## 📚 Full Documentation

- **[README.md](README.md)** - Complete project overview
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Deployment instructions
- **[MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)** - Task configuration
- **[SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)** - Security guide
