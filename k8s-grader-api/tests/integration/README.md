# Integration Tests - Complete Guide

Self-contained integration tests that run against the deployed AWS infrastructure with automatic setup and cleanup.

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [How It Works](#how-it-works)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Cleanup](#cleanup)
- [Design Decisions](#design-decisions)
- [Troubleshooting](#troubleshooting)
- [CI/CD Integration](#cicd-integration)

---

## Quick Start

### TL;DR

```bash
# See demonstration (no AWS required)
python tests/integration/dry_run_test.py

# Run actual tests (requires deployed stack)
./run_integration_tests.sh
```

That's it! Everything else is automatic.

### Prerequisites

1. **Deploy the stack**:
   ```bash
   cd k8s-grader-api
   ./deploy.sh
   ```

2. **Install dependencies** (if not already installed):
   ```bash
   pip install pytest requests boto3
   ```

3. **Configure AWS credentials** (tests use boto3 default credential chain)

---

## Features

✅ **Self-Contained** - Tests create their own random test users, run tests, and clean up automatically  
✅ **Isolated** - Each test run uses a unique user email to avoid conflicts  
✅ **Comprehensive Cleanup** - Automatically cleans up all test data from 9 DynamoDB tables + API Gateway  
✅ **Real Environment** - Tests against actual deployed API and DynamoDB tables  
✅ **No Manual Setup** - Automatically generates test users and API keys  
✅ **CI/CD Ready** - No secrets or manual steps needed  
✅ **Safe** - Never touches production data  

---

## How It Works

### 1. Test Session Setup

```python
# Generate unique test run ID
test_run_id = f"test-{uuid.uuid4().hex[:8]}-{int(time.time())}"

# Create unique test email
test_email = f'integration-test-{test_run_id}@example.com'
# Example: integration-test-abc12345-1769918948@example.com

# Create test user account in DynamoDB
dynamodb_client.put_item(
    TableName='AccountTable',
    Item={
        'email': {'S': test_email},
        'endpoint': {'S': f'https://test-k8s-{test_run_id}.example.com:6443'},
        'client_certificate': {'S': f'test-cert-{test_run_id}'},
        'client_key': {'S': f'test-key-{test_run_id}'},
        'time': {'N': str(int(time.time()))}
    }
)
```

### 2. API Key Generation

```python
# Automatically generates encrypted API key via keygen endpoint
response = requests.get(
    f"{api_endpoint}/keygen/",
    params={'secret': secret_hash, 'email': test_email}
)
api_key = response.text.strip()
```

### 3. Test Execution

Each test runs with:
- Unique test user
- Valid API key
- Clean database state

### 4. Comprehensive Cleanup

After all tests complete:

```python
# Clean DynamoDB tables (9 tables)
tables = [
    'AccountTable',
    'TaskStateTable',
    'NpcLockTable',
    'NpcAssignmentTable',
    'GameTaskTable',
    'SessionTable',
    'NpcTaskTable',
    'TestRecordTable',
    'ApiKeyTable'
]

# Clean API Gateway
apigateway_client.delete_api_key(apiKey=api_key_id)
```

---

## Running Tests

### Basic Usage

```bash
# From k8s-grader-api directory
./run_integration_tests.sh
```

The tests will automatically:
1. Generate a unique test user email
2. Create test user account in DynamoDB
3. Generate encrypted API key
4. Run all 15 tests
5. Clean up all test data

### Custom Configuration

```bash
# Use specific stack
export STACK_NAME=my-custom-stack
./run_integration_tests.sh

# Use different region
export AWS_REGION=us-west-2
./run_integration_tests.sh

# Use pre-generated API key (optional)
export TEST_API_KEY=my-encrypted-key
./run_integration_tests.sh

# Combine options
export STACK_NAME=my-stack AWS_REGION=us-west-2
./run_integration_tests.sh
```

### Run Specific Tests

```bash
cd tests/integration

# Run specific test class
pytest test_api_integration.py::TestAPIIntegration -v

# Run specific test
pytest test_api_integration.py::TestAPIIntegration::test_api_endpoint_reachable -v

# Run with markers
pytest -m integration -v
```

---

## Test Coverage

### 15 Integration Tests Across 6 Test Classes

#### 1. TestAPIIntegration (6 tests)
- `test_stack_outputs_available` - Verify stack outputs
- `test_api_endpoint_reachable` - Test API endpoint
- `test_missing_parameters` - Parameter validation
- `test_invalid_game_format` - Input validation
- `test_npc_not_found` - Error handling
- `test_user_not_found` - User validation

#### 2. TestTaskFlow (1 test)
- `test_complete_task_flow` - End-to-end task workflow

#### 3. TestDynamoDBIntegration (1 test)
- `test_task_state_persistence` - Database operations

#### 4. TestAPIPerformance (2 tests)
- `test_api_response_time` - Response time < 5s
- `test_concurrent_requests` - Handle 5+ concurrent requests

#### 5. TestSaveAccountAPI (2 tests)
- `test_save_account_get_returns_html` - GET endpoint
- `test_save_account_validates_endpoint_uniqueness` - Validation

#### 6. TestErrorHandling (3 tests)
- `test_invalid_api_key` - Invalid key handling
- `test_missing_api_key` - Missing key handling
- `test_malformed_request` - Security validation

---

## Cleanup

### Automatic Cleanup

Cleanup happens automatically after each test run:

**DynamoDB Tables (9):**
- AccountTable
- TaskStateTable
- NpcLockTable
- NpcAssignmentTable
- GameTaskTable
- SessionTable
- NpcTaskTable
- TestRecordTable
- ApiKeyTable

**API Gateway:**
- API keys (created via keygen endpoint)

### Manual Cleanup Script

If automatic cleanup fails or you want to verify:

```bash
# Check for leftover data (safe)
python tests/integration/cleanup_test_keys.py --dry-run

# Actually clean up
python tests/integration/cleanup_test_keys.py

# Clean only API Gateway
python tests/integration/cleanup_test_keys.py --api-gateway-only

# Clean only DynamoDB
python tests/integration/cleanup_test_keys.py --dynamodb-only
```

See `CLEANUP_SCRIPT.md` for detailed documentation.

### Why API Gateway Cleanup Matters

The keygen endpoint creates actual API Gateway API keys:

```python
# Creates API key in API Gateway
api_key_id = client.create_api_key(
    name=email,  # Uses email as key name
    value=encrypted_token,
    enabled=True
)

# Saves to DynamoDB
save_api_key(email, api_key_value)
```

Without cleanup, API keys accumulate (1 per test run), potentially increasing costs.

---

## Design Decisions

### Why Direct DynamoDB Insert Instead of save-k8s-account API?

We directly insert test users into DynamoDB rather than calling the save-k8s-account API because:

1. **Same Result** - The API just wraps `AccountRepository.save()` which does a DynamoDB `put_item()`
2. **Faster** - Direct insert ~50ms vs API call ~500-2000ms (includes Lambda cold start)
3. **Better Control** - Can use fake K8s credentials and bypass validation
4. **Test Isolation** - Tests don't depend on API Gateway or Lambda being functional
5. **API Is Tested** - The save-k8s-account API is tested separately in `TestSaveAccountAPI`

**The save-k8s-account API is still fully tested**, just not used for test setup.

---

## Troubleshooting

### Stack Not Found

```
❌ Error: Stack 'k8s-grader-api-dev' not found
```

**Solution**: Deploy the stack first:
```bash
cd k8s-grader-api
./deploy.sh
```

### API Key Generation Failed

```
⚠️ Warning: Could not generate API key
```

**Solution**: The keygen endpoint may be unavailable. Generate manually:
```bash
# Get stack outputs
API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)
SECRET_HASH=$(aws cloudformation describe-stacks --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' --output text)

# Generate key
curl "${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=test@example.com"

# Set environment variable
export TEST_API_KEY='generated-key'
```

### Cleanup Failed

```
⚠️ Warning: Could not clean TaskStateTable
```

**Cause**: Usually permission issues or table doesn't exist

**Solution**: Check AWS credentials have DynamoDB and API Gateway permissions:
- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem`, `dynamodb:Query`, `dynamodb:Scan`
- `apigateway:GetApiKeys`, `apigateway:DeleteApiKey`
- `cloudformation:DescribeStacks`

### Tests Are Slow

Integration tests are slower than unit tests because they:
- Make real HTTP requests
- Wait for AWS services
- Include network latency

This is expected. Use unit tests for fast feedback during development.

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  integration-test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd k8s-grader-api
          pip install pytest requests boto3
      
      - name: Run Integration Tests
        env:
          STACK_NAME: k8s-grader-api-${{ github.ref_name }}
          AWS_REGION: us-east-1
        run: |
          cd k8s-grader-api
          ./run_integration_tests.sh
      
      - name: Cleanup (if tests fail)
        if: failure()
        run: |
          cd k8s-grader-api
          python tests/integration/cleanup_test_keys.py
```

### Jenkins Example

```groovy
pipeline {
    agent any
    
    environment {
        STACK_NAME = 'k8s-grader-api-dev'
        AWS_REGION = 'us-east-1'
    }
    
    stages {
        stage('Integration Tests') {
            steps {
                sh '''
                    cd k8s-grader-api
                    ./run_integration_tests.sh
                '''
            }
        }
    }
    
    post {
        always {
            sh 'python k8s-grader-api/tests/integration/cleanup_test_keys.py'
        }
    }
}
```

---

## Test Data Isolation

Each test run is completely isolated:

```
Test Run 1: integration-test-abc12345-1234567890@example.com
Test Run 2: integration-test-def67890-0987654321@example.com
Test Run 3: integration-test-ghi13579-1357924680@example.com
```

No conflicts between:
- Parallel test runs
- Sequential test runs
- Different developers
- CI/CD pipelines

---

## Performance Expectations

- **API response time**: < 5 seconds
- **Concurrent requests**: 5+ simultaneous requests
- **Test suite duration**: ~30-60 seconds
- **Cleanup duration**: ~5-10 seconds

---

## Comparison: Unit vs Integration Tests

| Aspect | Unit Tests | Integration Tests |
|--------|-----------|-------------------|
| Speed | Fast (milliseconds) | Slow (seconds) |
| Dependencies | Mocked | Real AWS services |
| Cost | Free | AWS charges apply |
| Isolation | Complete | Shared resources |
| Coverage | Code logic | End-to-end flow |
| When to run | Every commit | Before/after deploy |
| Setup | None | Deploy stack first |
| Cleanup | Automatic | Automatic |

Both are important! Use unit tests for development, integration tests for validation.

---

## Files

### Test Files
- `test_api_integration.py` - All integration tests
- `conftest.py` - Test fixtures and setup/cleanup
- `dry_run_test.py` - Demonstration without AWS

### Scripts
- `run_integration_tests.sh` - Main test runner
- `cleanup_test_keys.py` - Manual cleanup script

### Documentation
- `README.md` - This file (complete guide)
- `CLEANUP_SCRIPT.md` - Cleanup script documentation

---

## Summary

✅ **Self-contained** - Create users, run tests, clean up automatically  
✅ **Zero manual setup** - Just run `./run_integration_tests.sh`  
✅ **Complete isolation** - Unique user per test run  
✅ **Comprehensive cleanup** - 9 DynamoDB tables + API Gateway  
✅ **CI/CD ready** - No secrets or manual steps  
✅ **Safe** - Never touches production data  
✅ **Well documented** - Complete guides and examples  

The integration tests provide complete end-to-end validation of your deployed infrastructure with zero manual setup required!

---

## Quick Reference

```bash
# Run tests
./run_integration_tests.sh

# See demo
python tests/integration/dry_run_test.py

# Check for leftover data
python tests/integration/cleanup_test_keys.py --dry-run

# Clean up manually
python tests/integration/cleanup_test_keys.py

# Run specific test
cd tests/integration
pytest test_api_integration.py::TestAPIIntegration::test_api_endpoint_reachable -v
```

For more details, see the inline documentation in the test files.
