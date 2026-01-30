#!/bin/bash

# Run integration tests against deployed stack
# Usage: ./run_integration_tests.sh [stack-name]

set -e

echo "K8s Grader API - Integration Tests"
echo "===================================="
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

# Check if TEST_API_KEY is set
if [ -z "$TEST_API_KEY" ]; then
    echo "❌ Error: TEST_API_KEY environment variable not set"
    echo ""
    echo "The API uses encrypted keys that contain the user's email."
    echo "You need to generate one using the keygen endpoint:"
    echo ""
    echo "1. Get stack outputs:"
    echo "   API_ENDPOINT=\$(aws cloudformation describe-stacks --stack-name $STACK_NAME \\"
    echo "     --query 'Stacks[0].Outputs[?OutputKey==\`ApiEndpoint\`].OutputValue' --output text)"
    echo "   SECRET_HASH=\$(aws cloudformation describe-stacks --stack-name $STACK_NAME \\"
    echo "     --query 'Stacks[0].Outputs[?OutputKey==\`SecretHash\`].OutputValue' --output text)"
    echo ""
    echo "2. Generate encrypted API key:"
    echo "   Visit: \${API_ENDPOINT}/keygen/?secret=\${SECRET_HASH}&email=integration-test@example.com"
    echo ""
    echo "3. Set the generated key:"
    echo "   export TEST_API_KEY='your-generated-encrypted-key'"
    echo ""
    exit 1
fi

echo "✅ TEST_API_KEY is set"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Install dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
    echo "Installing test dependencies..."
    pip install pytest requests boto3 pytest-timeout
fi

echo ""
echo "Running integration tests..."
echo "================================"
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
else
    echo "❌ Some integration tests failed"
    exit $TEST_EXIT_CODE
fi
