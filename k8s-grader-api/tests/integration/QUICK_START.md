# Integration Tests - Quick Start

## 1. Deploy Stack

```bash
cd k8s-grader/k8s-grader-api
./deploy.sh
```

## 2. Generate Encrypted API Key

The API uses encrypted keys that contain the user's email:

```bash
# Get stack info
STACK_NAME="k8s-grader-api-dev"
API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)
SECRET_HASH=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' --output text)

# Generate key
TEST_EMAIL="integration-test@example.com"
echo "Visit: ${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=${TEST_EMAIL}"

# Set the generated key
export TEST_API_KEY="your-generated-encrypted-key"
```

## 3. Run Tests

```bash
./run_integration_tests.sh
```

## Common Commands

```bash
# Run all tests
./run_integration_tests.sh

# Run with custom stack
STACK_NAME=my-stack ./run_integration_tests.sh

# Run specific test class
cd tests/integration
pytest test_api_integration.py::TestAPIIntegration

# Run with verbose output
pytest -v -s

# Run only fast tests
pytest -m "not slow"
```

## What Gets Tested

✅ API endpoint reachability  
✅ Parameter validation  
✅ Error handling  
✅ DynamoDB persistence  
✅ Performance (< 5s response)  
✅ Concurrent requests  
✅ Security (API keys)  

## No Hardcoded Values!

Tests automatically discover:
- API endpoint URL
- DynamoDB table names
- AWS region
- All resources

You need to provide:
- Stack name (default: `k8s-grader-api-dev`)
- **Encrypted API key** (generate via keygen endpoint)

## Troubleshooting

**Stack not found?**
```bash
aws cloudformation describe-stacks --stack-name k8s-grader-api-dev
```

**Need to generate API key?**
```bash
# Get keygen URL
STACK_NAME="k8s-grader-api-dev"
API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)
SECRET_HASH=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' --output text)

echo "${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=integration-test@example.com"
```

**Permission denied?**
```bash
aws sts get-caller-identity
```

## More Info

- [Full Documentation](README.md)
- [Testing Guide](../../TESTING_GUIDE.md)
- [Summary](../../INTEGRATION_TESTS_SUMMARY.md)
