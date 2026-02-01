#!/bin/bash

# Run integration tests against deployed stack
# Usage: ./run_integration_tests.sh [stack-name]

set -e

echo "K8s Grader API - Self-Contained Integration Tests"
echo "=================================================="
echo ""

# Get stack name from argument or environment or use default
STACK_NAME="${1:-${STACK_NAME:-k8s-grader-api-dev}}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "Configuration:"
echo "  Stack Name: $STACK_NAME"
echo "  AWS Region: $AWS_REGION"
echo ""

# Check if stack exists
echo "Checking if stack exists..."
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &> /dev/null; then
    echo "❌ Error: Stack '$STACK_NAME' not found in region '$AWS_REGION'"
    echo ""
    echo "Please deploy the stack first:"
    echo "  ./deploy.sh"
    exit 1
fi

echo "✅ Stack found"
echo ""

# Note about TEST_API_KEY
if [ -z "$TEST_API_KEY" ]; then
    echo "ℹ️  TEST_API_KEY not set - will auto-generate during tests"
    echo ""
else
    echo "✅ Using TEST_API_KEY from environment"
    echo ""
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Install dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
    echo "Installing test dependencies..."
    pip install -q pytest requests boto3 pytest-timeout
fi

echo ""
echo "Running self-contained integration tests..."
echo "============================================"
echo ""
echo "Tests will:"
echo "  1. Generate unique test user email"
echo "  2. Create test user account in DynamoDB"
echo "  3. Generate encrypted API key automatically"
echo "  4. Run all tests"
echo "  5. Clean up all test data"
echo ""

# Export variables for pytest
export STACK_NAME
export AWS_REGION

# Run tests
cd tests/integration
pytest -v --tb=short --color=yes "$@"

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All integration tests passed!"
    echo ""
    echo "Test data has been automatically cleaned up."
else
    echo "❌ Some integration tests failed"
    echo ""
    echo "Note: Test data should be automatically cleaned up."
    echo "If cleanup failed, check the test output for warnings."
    exit $TEST_EXIT_CODE
fi
