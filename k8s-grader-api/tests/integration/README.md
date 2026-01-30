# Integration Tests

Integration tests for the K8s Grader API that test against the **real deployed stack** on AWS.

## Overview

These tests:
- Call the actual deployed API Gateway endpoints
- Interact with real DynamoDB tables
- Verify end-to-end functionality
- Test performance and error handling

Unlike unit tests (which use mocks), these tests validate the deployed infrastructure.

## Prerequisites

### 1. Deploy the Stack

```bash
cd k8s-grader/k8s-grader-api
./deploy.sh
```

### 2. Generate Test API Key

The API uses **encrypted API keys** that contain the user's email. You need to generate one:

```bash
# Get stack outputs
STACK_NAME="k8s-grader-api-dev"
API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)
SECRET_HASH=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' --output text)

# Generate encrypted API key
TEST_EMAIL="integration-test@example.com"
echo "Visit this URL to generate your test API key:"
echo "${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=${TEST_EMAIL}"

# Copy the generated key and set it
export TEST_API_KEY="your-generated-encrypted-key"
```

**Note:** The TestApiKey in stack outputs is an API Gateway key ID, not the encrypted key needed for authentication.

### 3. Set Environment Variables

```bash
# Required
export STACK_NAME="k8s-grader-api-dev"
export TEST_API_KEY="your-encrypted-api-key"  # From keygen endpoint

# Optional (defaults shown)
export AWS_REGION="us-east-1"
export TEST_EMAIL="integration-test@example.com"
```

### 4. Install Dependencies

```bash
pip install pytest requests boto3
```

## Running Tests

### Run All Integration Tests

```bash
cd tests/integration
pytest
```

### Run Specific Test Classes

```bash
# Test API endpoints only
pytest test_api_integration.py::TestAPIIntegration

# Test DynamoDB integration
pytest test_api_integration.py::TestDynamoDBIntegration

# Test performance
pytest test_api_integration.py::TestAPIPerformance

# Test error handling
pytest test_api_integration.py::TestErrorHandling
```

### Run with Different Stack

```bash
STACK_NAME=k8s-grader-api-prod pytest
```

### Run with Verbose Output

```bash
pytest -v -s
```

### Run Full Integration Tests (requires real user)

```bash
pytest --run-full-integration
```

## Test Categories

### 1. API Integration Tests (`TestAPIIntegration`)
- Stack outputs availability
- API endpoint reachability
- Parameter validation
- Error responses

### 2. Task Flow Tests (`TestTaskFlow`)
- Complete task workflow
- Task state transitions
- Phase execution
- Task completion

**Note:** Full task flow tests require a real user account with K8s credentials and are skipped by default.

### 3. DynamoDB Integration Tests (`TestDynamoDBIntegration`)
- Task state persistence
- Data consistency
- Table operations

### 4. Performance Tests (`TestAPIPerformance`)
- Response time validation
- Concurrent request handling
- Load testing

### 5. Error Handling Tests (`TestErrorHandling`)
- Invalid API keys
- Missing authentication
- Malformed requests
- Security validation

## How It Works

### Dynamic Configuration

Tests use CloudFormation API to get stack outputs:

```python
# Get stack outputs dynamically
stack_outputs = cfn_client.describe_stacks(StackName=stack_name)

# Extract values
api_endpoint = outputs['ApiEndpoint']
task_state_table = outputs['TaskStateTable']
```

No hardcoded URLs or table names!

### Automatic Cleanup

Each test automatically cleans up test data before and after execution:

```python
@pytest.fixture(autouse=True)
def cleanup_test_data(...):
    # Clean before test
    clean()
    yield
    # Clean after test
    clean()
```

### Test Isolation

- Each test uses unique test data
- Tests don't interfere with each other
- Production data is never touched (uses test email)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STACK_NAME` | No | `k8s-grader-api-dev` | CloudFormation stack name |
| `TEST_API_KEY` | **Yes** | - | **Encrypted** API key (generate via keygen endpoint) |
| `AWS_REGION` | No | `us-east-1` | AWS region |
| `TEST_EMAIL` | No | `integration-test@example.com` | Test user email |

**Important:** The API uses encrypted API keys that contain the user's email. You must generate one using the keygen endpoint.

## Expected Stack Outputs

The stack must have these outputs:

- `ApiEndpoint` - API Gateway endpoint URL
- `TestApiKey` - Test API key (automatically created)
- `TaskStateTable` - DynamoDB table name for task states
- `NpcLockTable` - DynamoDB table name for NPC locks
- `NpcAssignmentTable` - DynamoDB table name for NPC assignments

These are automatically configured in `template.yaml`.

## Troubleshooting

### "Stack not found"

```bash
# Verify stack exists
aws cloudformation describe-stacks --stack-name k8s-grader-api-dev

# Or deploy it
cd k8s-grader/k8s-grader-api
./deploy.sh
```

### "TEST_API_KEY not set"

```bash
# Get API key from AWS
aws apigateway get-api-keys --include-values

# Or create one
aws apigateway create-api-key --name integration-test-key --enabled

# Set environment variable
export TEST_API_KEY="your-key-here"
```

### "Permission denied"

Ensure your AWS credentials have permissions for:
- CloudFormation (DescribeStacks)
- API Gateway (invoke)
- DynamoDB (GetItem, PutItem, DeleteItem)

### Tests are slow

Integration tests are slower than unit tests because they:
- Make real HTTP requests
- Wait for AWS services
- Include network latency

This is expected. Use unit tests for fast feedback during development.

## Best Practices

1. **Run unit tests first** - They're faster and catch most issues
2. **Run integration tests before deployment** - Validate the stack
3. **Run integration tests after deployment** - Verify production
4. **Don't run integration tests in CI/CD** - Unless you have a dedicated test environment
5. **Use separate test accounts** - Don't test against production data

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on:
  push:
    branches: [main]

jobs:
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Run Integration Tests
        env:
          STACK_NAME: k8s-grader-api-test
          TEST_API_KEY: ${{ secrets.TEST_API_KEY }}
        run: |
          cd k8s-grader/k8s-grader-api/tests/integration
          pytest -v
```

## Comparison: Unit vs Integration Tests

| Aspect | Unit Tests | Integration Tests |
|--------|-----------|-------------------|
| Speed | Fast (milliseconds) | Slow (seconds) |
| Dependencies | Mocked | Real AWS services |
| Cost | Free | AWS charges apply |
| Isolation | Complete | Shared resources |
| Coverage | Code logic | End-to-end flow |
| When to run | Every commit | Before/after deploy |

Both are important! Use unit tests for development, integration tests for validation.
