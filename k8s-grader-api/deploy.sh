#!/bin/bash

# K8s Grader API Deployment Script
# This script automates the deployment process

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
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

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check AWS CLI
    if command -v aws &> /dev/null; then
        print_success "AWS CLI installed: $(aws --version)"
    else
        print_error "AWS CLI not found. Please install it first."
        exit 1
    fi
    
    # Check SAM CLI
    if command -v sam &> /dev/null; then
        print_success "SAM CLI installed: $(sam --version)"
    else
        print_error "SAM CLI not found. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if aws sts get-caller-identity &> /dev/null; then
        print_success "AWS credentials configured"
    else
        print_error "AWS credentials not configured. Run 'aws configure'"
        exit 1
    fi
    
    # Check Python
    if command -v python3 &> /dev/null; then
        print_success "Python installed: $(python3 --version)"
    else
        print_error "Python 3 not found"
        exit 1
    fi
}

# Run tests
run_tests() {
    print_header "Running Tests"
    
    if [ -d "venv" ]; then
        source venv/bin/activate
        print_info "Virtual environment activated"
    fi
    
    if [ -f "run_tests.sh" ]; then
        print_info "Running unit test suite (integration tests excluded)..."
        bash run_tests.sh
        print_success "All unit tests passed"
    else
        print_info "No test script found, skipping tests"
    fi
}

# Validate template
validate_template() {
    print_header "Validating SAM Template"
    
    if sam validate; then
        print_success "Template validation passed"
    else
        print_error "Template validation failed"
        exit 1
    fi
}

# Build
build() {
    print_header "Building Application"
    
    print_info "Running sam build..."
    if sam build; then
        print_success "Build completed successfully"
    else
        print_error "Build failed"
        exit 1
    fi
}

# Deploy
deploy() {
    print_header "Deploying to AWS"
    
    if [ "$1" == "--guided" ]; then
        print_info "Running guided deployment..."
        sam deploy --guided
    else
        print_info "Deploying with saved configuration..."
        sam deploy
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Deployment completed successfully"
    else
        print_error "Deployment failed"
        exit 1
    fi
}

# Get outputs
get_outputs() {
    print_header "Stack Outputs"
    
    STACK_NAME=$(grep stack_name samconfig.toml | head -n 1 | cut -d'"' -f2 || echo "k8s-grader-api-dev")
    
    print_info "Fetching outputs for stack: $STACK_NAME"
    
    # Use --no-cli-pager to prevent interactive pager
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs' \
        --output table \
        --no-cli-pager
}

# Show next steps
show_next_steps() {
    print_header "Deployment Complete"
    
    STACK_NAME=$(grep stack_name samconfig.toml | head -n 1 | cut -d'"' -f2 || echo "k8s-grader-api-dev")
    
    BASE_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`BaseUrl`].OutputValue' \
        --output text \
        --no-cli-pager 2>/dev/null || echo "")
    
    print_success "Stack deployed successfully!"
    
    if [ -n "$BASE_URL" ]; then
        echo ""
        echo "API Endpoint: ${BASE_URL}"
        echo ""
        echo "Quick Start:"
        echo ""
        echo "1. Generate an API key:"
        echo "   curl \"${BASE_URL}keygen?secret=YOUR_SECRET&email=YOUR_EMAIL\""
        echo ""
        echo "2. Test the /task endpoint:"
        echo "   curl -H \"x-api-key: YOUR_API_KEY\" \\"
        echo "     \"${BASE_URL}task?action=start&game=game01&task=01&npc=npc01\""
        echo ""
        echo "Monitoring:"
        echo ""
        echo "• SAM logs:       sam logs -n TaskHandlerFunction --tail"
        echo "• CloudWatch:     aws logs tail /aws/lambda/${STACK_NAME}-TaskHandlerFunction --follow"
        echo ""
    fi
}

# Run integration tests
run_integration_tests() {
    print_header "Running Integration Tests"
    
    print_info "Integration tests are now self-contained!"
    print_info "Tests will automatically:"
    echo "  • Generate unique test user"
    echo "  • Create test account in DynamoDB"
    echo "  • Generate encrypted API key"
    echo "  • Run all tests"
    echo "  • Clean up all test data"
    echo ""
    
    if [ -d "venv" ]; then
        source venv/bin/activate
        print_info "Virtual environment activated"
    fi
    
    if [ -f "run_integration_tests.sh" ]; then
        print_info "Running self-contained integration test suite..."
        if bash run_integration_tests.sh; then
            print_success "All integration tests passed"
            echo ""
            print_success "Test data automatically cleaned up"
        else
            print_error "Some integration tests failed"
            echo ""
            echo "⚠️  Integration test failures don't affect the deployment."
            echo "The API is deployed and functional."
            echo "Review the test output above for details."
            echo ""
            echo "To manually clean up test data (if needed):"
            echo "  python tests/integration/cleanup_test_keys.py"
            return 1
        fi
    else
        print_info "No integration test script found, skipping"
    fi
}

# Main script
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   K8s Grader API Deployment Script    ║"
    echo "╚════════════════════════════════════════╝"
    
    # Parse arguments
    GUIDED=false
    SKIP_TESTS=false
    SKIP_BUILD=false
    SKIP_INTEGRATION=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --guided)
                GUIDED=true
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --skip-integration)
                SKIP_INTEGRATION=true
                shift
                ;;
            --help)
                echo ""
                echo "Usage: ./deploy.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --guided              Run guided deployment (first time)"
                echo "  --skip-tests          Skip running unit tests"
                echo "  --skip-build          Skip build step (use existing build)"
                echo "  --skip-integration    Skip self-contained integration tests"
                echo "  --help                Show this help message"
                echo ""
                echo "Integration Tests:"
                echo "  Integration tests are now self-contained and run automatically"
                echo "  after deployment. They will:"
                echo "    • Generate unique test user"
                echo "    • Create test account in DynamoDB"
                echo "    • Auto-generate encrypted API key"
                echo "    • Run all tests"
                echo "    • Clean up all test data"
                echo ""
                echo "  No manual API key setup required!"
                echo ""
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    # Run deployment steps
    check_prerequisites
    
    if [ "$SKIP_TESTS" = false ]; then
        run_tests
    else
        print_info "Skipping tests (--skip-tests flag)"
    fi
    
    validate_template
    
    if [ "$SKIP_BUILD" = false ]; then
        build
    else
        print_info "Skipping build (--skip-build flag)"
    fi
    
    if [ "$GUIDED" = true ]; then
        deploy --guided
    else
        deploy
    fi
    
    get_outputs
    show_next_steps
    
    # Run integration tests unless skipped
    if [ "$SKIP_INTEGRATION" = false ]; then
        echo ""
        run_integration_tests || true  # Don't fail deployment if integration tests fail
    else
        print_info "Skipping integration tests (--skip-integration flag)"
        echo ""
        echo "To run integration tests manually:"
        echo "  bash run_integration_tests.sh"
    fi
}

# Run main function
main "$@"
