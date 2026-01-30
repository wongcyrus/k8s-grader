# Testing Guide

Complete guide to testing the K8s Grader API.

## Overview

The project has two types of tests:

1. **Unit Tests** - Fast, mocked tests for development
2. **Integration Tests** - Real API tests for validation

## Unit Tests

### What They Test
- Business logic and state transitions
- Data models and serialization
- Service layer functionality
- Error handling and edge cases

### How They Work
- Use `moto` to mock AWS services (DynamoDB, S3, etc.)
- Use `unittest.mock` to mock external dependencies
- Run completely in-memory
- No real AWS resources needed

### Running Unit Tests

```bash
# Run all unit tests
./run_tests.sh

# Run specific test file
pytest tests/test_task_handler.py

# Run with coverage report
pytest --cov=common-layer/common --cov-report=html

# Run specific test class
pytest tests/test_task_handler.py::TestLambdaHandler

# Run specific test
pytest tests/test_task_handler.py::TestLambdaHandler::test_missing_parameters
```

### Results
- **106 tests** in 8 test files
- **63% code coverage**
- Execution time: ~4 seconds
- All tests pass ✅

## Integration Tests

### What They Test
- Real API Gateway endpoints
- Real DynamoDB operations
- End-to-end workflows
- Performance and concurrency
- Error handling with real services

### How They Work
- Use CloudFormation API to get stack outputs dynamically
- Make real HTTP requests to deployed API
- Interact with real DynamoDB tables
- Clean up test data automatically

### Encrypted API Keys

**Important:** The API uses **encrypted API keys** that contain the user's email, not standard API Gateway keys.

```python
# Standard API Gateway key (doesn't work)
api_key = "abc123def456"

# Encrypted K8s Grader key (required)
api_key = "gAAAAABh..."  # Fernet encrypted, contains email
```

The Lambda handler decrypts keys to extract the email:

```python
from cryptography.fernet import Fernet

def get_email_from_api_key(api_key: str) -> str:
    fernet = Fernet(SECRET_HASH)
    return fernet.decrypt(api_key.encode()).decode()
```

**Why encrypted keys?**
- User identification (email embedded in key)
- Security (only API can decrypt)
- Prevents email spoofing
- Single source of truth

### Prerequisites

1. **Deploy the stack:**
   ```bash
   ./deploy.sh
   ```

2. **Get API key:**
   ```bash
   aws apigateway get-api-keys --include-values
   ```

3. **Set environment variables:**
   ```bash
   export STACK_NAME="k8s-grader-api-dev"
   export TEST_API_KEY="your-api-key-here"
   ```

### Running Integration Tests

```bash
# Run all integration tests
./run_integration_tests.sh

# Run with custom stack name
./run_integration_tests.sh my-stack-name

# Run specific test class
cd tests/integration
pytest test_api_integration.py::TestAPIIntegration

# Run with verbose output
pytest -v -s

# Run only fast tests (skip slow ones)
pytest -m "not slow"
```

### Test Categories

#### 1. API Integration Tests
```bash
pytest test_api_integration.py::TestAPIIntegration
```
- Stack outputs availability
- API endpoint reachability
- Parameter validation
- Error responses

#### 2. Task Flow Tests
```bash
pytest test_api_integration.py::TestTaskFlow
```
- Complete task workflow
- Task state transitions
- Phase execution

**Note:** Requires real user account with K8s credentials

#### 3. DynamoDB Integration Tests
```bash
pytest test_api_integration.py::TestDynamoDBIntegration
```
- Task state persistence
- Data consistency
- Table operations

#### 4. Performance Tests
```bash
pytest test_api_integration.py::TestAPIPerformance
```
- Response time validation (< 5s)
- Concurrent request handling
- Load testing

#### 5. Error Handling Tests
```bash
pytest test_api_integration.py::TestErrorHandling
```
- Invalid API keys
- Missing authentication
- Malformed requests
- Security validation

## Configuration

### Unit Tests
No configuration needed. Tests use mocked services.

### Integration Tests

#### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STACK_NAME` | No | `k8s-grader-api-dev` | CloudFormation stack name |
| `TEST_API_KEY` | Yes | - | API key for authentication |
| `AWS_REGION` | No | `us-east-1` | AWS region |
| `TEST_EMAIL` | No | `integration-test@example.com` | Test user email |

#### Using .env File

```bash
cd tests/integration
cp .env.example .env
# Edit .env with your values
```

Then run tests:
```bash
source .env
pytest
```

## Test Data Management

### Unit Tests
- Use fixtures for test data
- Data is created and destroyed per test
- No cleanup needed

### Integration Tests
- Automatic cleanup before and after each test
- Uses unique test email to avoid conflicts
- Never touches production data

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r tests/requirements.txt
      - name: Run unit tests
        run: ./run_tests.sh

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v2
      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Run integration tests
        env:
          STACK_NAME: k8s-grader-api-test
          TEST_API_KEY: ${{ secrets.TEST_API_KEY }}
        run: ./run_integration_tests.sh
```

## Best Practices

### Development Workflow

1. **Write unit tests first**
   ```bash
   # Create test file
   vim tests/test_new_feature.py
   
   # Run tests (should fail)
   pytest tests/test_new_feature.py
   
   # Implement feature
   vim common-layer/common/services/new_feature.py
   
   # Run tests (should pass)
   pytest tests/test_new_feature.py
   ```

2. **Run all unit tests before commit**
   ```bash
   ./run_tests.sh
   ```

3. **Run integration tests before deployment**
   ```bash
   ./run_integration_tests.sh
   ```

4. **Deploy and verify**
   ```bash
   ./deploy.sh
   ./run_integration_tests.sh
   ```

### When to Run Each Type

| Scenario | Unit Tests | Integration Tests |
|----------|-----------|-------------------|
| During development | ✅ Always | ❌ No |
| Before commit | ✅ Always | ❌ No |
| Before PR merge | ✅ Always | ⚠️ Optional |
| Before deployment | ✅ Always | ✅ Always |
| After deployment | ⚠️ Optional | ✅ Always |
| In CI/CD | ✅ Always | ⚠️ Test env only |

### Writing Good Tests

#### Unit Tests
```python
def test_feature():
    # Arrange - Set up test data
    state = TaskState(...)
    
    # Act - Execute the code
    result = service.do_something(state)
    
    # Assert - Verify results
    assert result.success
    assert result.value == expected
```

#### Integration Tests
```python
def test_api_feature(api_endpoint, test_api_key):
    # Arrange - Prepare request
    params = {'email': 'test@example.com', ...}
    
    # Act - Call real API
    response = requests.get(f"{api_endpoint}/task", params=params)
    
    # Assert - Verify response
    assert response.status_code == 200
    assert response.json()['status'] == 'OK'
```

## Troubleshooting

### Unit Tests

**Import errors**
```bash
# Ensure you're in the right directory
cd k8s-grader/k8s-grader-api

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r tests/requirements.txt
```

**Tests fail randomly**
```bash
# Run with verbose output
pytest -v -s

# Run single test to isolate issue
pytest tests/test_file.py::TestClass::test_method
```

### Integration Tests

**"Stack not found"**
```bash
# Verify stack exists
aws cloudformation describe-stacks --stack-name k8s-grader-api-dev

# Deploy if needed
./deploy.sh
```

**"TEST_API_KEY not set"**
```bash
# Get API key
aws apigateway get-api-keys --include-values

# Set environment variable
export TEST_API_KEY="your-key-here"
```

**Tests timeout**
```bash
# Increase timeout
pytest --timeout=60

# Or skip slow tests
pytest -m "not slow"
```

**Permission denied**
```bash
# Check AWS credentials
aws sts get-caller-identity

# Ensure IAM permissions for:
# - CloudFormation (DescribeStacks)
# - API Gateway (invoke)
# - DynamoDB (GetItem, PutItem, DeleteItem)
```

## Coverage Reports

### Generate HTML Coverage Report

```bash
# Run tests with coverage
pytest --cov=common-layer/common --cov-report=html

# Open report
open htmlcov/index.html
```

### Coverage Goals

- **Overall**: > 60%
- **Core models**: > 95%
- **Services**: > 90%
- **Repositories**: > 75%
- **Handlers**: > 80%

## Additional Resources

- [Unit Test Files](tests/) - All unit test files
- [Integration Test Files](tests/integration/) - All integration test files
- [Integration Test README](tests/integration/README.md) - Detailed integration test docs
- [pytest Documentation](https://docs.pytest.org/) - pytest framework docs
- [moto Documentation](https://docs.getmoto.org/) - AWS mocking library docs
