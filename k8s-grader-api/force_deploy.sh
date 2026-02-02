#!/bin/bash

# Force Clean Deployment Script
# This script forces SAM to rebuild and redeploy everything by clearing caches

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_header() {
    echo ""
    echo "================================"
    echo "$1"
    echo "================================"
}

print_header "Force Clean Deployment"

# Step 1: Remove SAM build cache
print_info "Removing SAM build cache..."
if [ -d ".aws-sam" ]; then
    rm -rf .aws-sam
    print_success "Removed .aws-sam directory"
else
    print_info ".aws-sam directory not found (already clean)"
fi

# Step 2: Touch source files to update timestamps
print_info "Updating file timestamps to force rebuild..."
touch task-handler/app.py
touch common-layer/common/state_machine/task_state_machine.py
touch common-layer/common/services/task_service.py
print_success "Updated timestamps for modified files"

# Step 3: Build with --use-container flag (ensures clean build)
print_header "Building with Clean Environment"
print_info "Running: sam build --use-container"
sam build --use-container

if [ $? -eq 0 ]; then
    print_success "Build completed successfully"
else
    print_error "Build failed"
    exit 1
fi

# Step 4: Deploy
print_header "Deploying to AWS"
print_info "Running: sam deploy --no-confirm-changeset"
sam deploy --no-confirm-changeset

if [ $? -eq 0 ]; then
    print_success "Deployment completed successfully"
else
    print_error "Deployment failed"
    exit 1
fi

# Step 5: Get stack outputs
print_header "Deployment Complete"

STACK_NAME=$(grep stack_name samconfig.toml | head -n 1 | cut -d'"' -f2 || echo "k8s-grader-api-dev")

print_success "Stack deployed: $STACK_NAME"
echo ""
print_info "Fetching Lambda function name..."

FUNCTION_NAME=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --query 'StackResources[?ResourceType==`AWS::Lambda::Function` && LogicalResourceId==`TaskHandlerFunction`].PhysicalResourceId' \
    --output text \
    --no-cli-pager 2>/dev/null || echo "")

if [ -n "$FUNCTION_NAME" ]; then
    print_success "Lambda function: $FUNCTION_NAME"
    echo ""
    print_info "Verifying deployment..."
    
    # Get last modified time
    LAST_MODIFIED=$(aws lambda get-function \
        --function-name "$FUNCTION_NAME" \
        --query 'Configuration.LastModified' \
        --output text \
        --no-cli-pager 2>/dev/null || echo "")
    
    if [ -n "$LAST_MODIFIED" ]; then
        print_success "Last modified: $LAST_MODIFIED"
    fi
    
    # Get layer ARN
    LAYER_ARN=$(aws lambda get-function \
        --function-name "$FUNCTION_NAME" \
        --query 'Configuration.Layers[?contains(Arn, `CommonLayer`)].Arn' \
        --output text \
        --no-cli-pager 2>/dev/null || echo "")
    
    if [ -n "$LAYER_ARN" ]; then
        print_success "Common layer: $LAYER_ARN"
    fi
    
    echo ""
    print_header "Next Steps"
    echo ""
    echo "1. Watch CloudWatch logs for new deployment:"
    echo "   aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
    echo ""
    echo "2. Test the fix by completing a task in the game"
    echo ""
    echo "3. Look for these NEW log messages (proof of deployment):"
    echo "   • \"Phase 'check' passed (+20 points)\""
    echo "   • \"No more phases - task ready for completion\""
    echo "   • \"Task XX_task_name completed by user@example.com\""
    echo ""
    echo "4. If you still see old logs, the Lambda may be cached."
    echo "   Wait 1-2 minutes and try again."
    echo ""
else
    print_error "Could not find Lambda function name"
fi
