#!/bin/bash

# Generate encrypted API key for integration tests
# Usage: ./generate_test_api_key.sh [stack-name] [email]

set -e

STACK_NAME="${1:-${STACK_NAME:-k8s-grader-api-dev}}"
TEST_EMAIL="${2:-${TEST_EMAIL:-integration-test@example.com}}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "Generating Test API Key"
echo "======================="
echo ""
echo "Stack Name: $STACK_NAME"
echo "Test Email: $TEST_EMAIL"
echo "AWS Region: $AWS_REGION"
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

# Get stack outputs
echo "Getting stack outputs..."
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

SECRET_HASH=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' \
  --output text)

if [ -z "$API_ENDPOINT" ] || [ -z "$SECRET_HASH" ]; then
    echo "❌ Error: Could not get API endpoint or secret hash from stack outputs"
    exit 1
fi

echo "✅ Got stack outputs"
echo ""

# Generate keygen URL
KEYGEN_URL="${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=${TEST_EMAIL}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 To generate your encrypted API key:"
echo ""
echo "1. Visit this URL in your browser:"
echo "   $KEYGEN_URL"
echo ""
echo "2. Copy the generated API key"
echo ""
echo "3. Set it as an environment variable:"
echo "   export TEST_API_KEY='your-generated-key-here'"
echo ""
echo "4. Run the integration tests:"
echo "   ./run_integration_tests.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Try to open in browser (optional)
if command -v xdg-open &> /dev/null; then
    read -p "Open URL in browser? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        xdg-open "$KEYGEN_URL"
    fi
elif command -v open &> /dev/null; then
    read -p "Open URL in browser? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open "$KEYGEN_URL"
    fi
fi
