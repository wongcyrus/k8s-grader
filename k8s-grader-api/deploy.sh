#!/bin/bash

# K8s Grader API Deployment Script
# This script automates the deployment process

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
CONFIG_ENV="${SAM_CONFIG_ENV:-default}"
PYTHON_VERSION_OVERRIDE="${PYTHON_VERSION_OVERRIDE:-python3.14}"

get_stack_name() {
    if [ "${CONFIG_ENV}" = "default" ]; then
        grep '^\[default.global.parameters\]' -A 5 samconfig.toml | grep 'stack_name' | head -n 1 | cut -d'"' -f2
    else
        grep "^\[${CONFIG_ENV}\.global.parameters\]" -A 5 samconfig.toml | grep 'stack_name' | head -n 1 | cut -d'"' -f2
    fi
}

get_region() {
    if [ "${CONFIG_ENV}" = "default" ]; then
        grep '^\[default.deploy.parameters\]' -A 10 samconfig.toml | grep 'region' | head -n 1 | cut -d'"' -f2
    else
        grep "^\[${CONFIG_ENV}\.deploy.parameters\]" -A 10 samconfig.toml | grep 'region' | head -n 1 | cut -d'"' -f2
    fi
}

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

    # Check Docker (required for sam build --use-container)
    if command -v docker &> /dev/null; then
        print_success "Docker installed: $(docker --version)"
    else
        print_error "Docker not found. Containerized SAM builds require Docker."
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
    
    if sam validate --lint; then
        print_success "Template validation passed"
    else
        print_error "Template validation failed"
        exit 1
    fi
}

# Build
build() {
    print_header "Building Application"
    
    print_info "Running sam build --use-container..."
    if sam build --use-container --config-env "${CONFIG_ENV}"; then
        print_success "Build completed successfully"
    else
        print_error "Build failed"
        exit 1
    fi
}

# Prepare private game source archive (not the SAM artifacts bucket)
prepare_game_source() {
    print_header "Preparing Private Game Source"

    STACK_NAME="$(get_stack_name || echo "k8s-grader-api-dev")"
    REGION="$(get_region || echo "us-east-1")"
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)
    GAME_RULE_REPO="$(cd ../../k8s-game-rule && pwd)"
    GAME_SOURCE_BUCKET="${STACK_NAME}-game-source-${ACCOUNT_ID}-${REGION}"
    GAME_SOURCE_KEY="game01/k8s-game-rule.zip"
    ARCHIVE_NAME="k8s-game-rule-$(date -u +%Y%m%d%H%M%S).zip"
    ARCHIVE_PATH="/tmp/${ARCHIVE_NAME}"
    GAME_SOURCE_URI="s3://${GAME_SOURCE_BUCKET}/${GAME_SOURCE_KEY}"

    if [ ! -d "$GAME_RULE_REPO" ]; then
        print_error "k8s-game-rule repository not found at ${GAME_RULE_REPO}"
        exit 1
    fi

    print_info "Creating archive: ${ARCHIVE_PATH}"
    python3 - "$GAME_RULE_REPO" "$ARCHIVE_PATH" <<'PY'
from pathlib import Path
import os
import zipfile
import sys

repo = Path(sys.argv[1]).resolve()
archive_path = Path(sys.argv[2]).resolve()
skip_dirs = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", "venv", ".venv", "htmlcov", ".aws-sam"}

with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for file in files:
            path = Path(root) / file
            if any(part in skip_dirs for part in path.parts):
                continue
            zf.write(path, arcname=str(path.relative_to(repo.parent)))
PY

    print_info "Uploading archive to ${GAME_SOURCE_URI}"
    aws s3 cp "$ARCHIVE_PATH" "$GAME_SOURCE_URI" --no-cli-pager >/dev/null
    print_success "Game source uploaded privately"

    export GAME_SOURCE_BUCKET
    export GAME_SOURCE_URI
}

seed_game_source_table() {
    print_header "Seeding Game Source Table"

    STACK_NAME="$(get_stack_name || echo "k8s-grader-api-dev")"
    REGION="$(get_region || echo "us-east-1")"
    GAME_SOURCE_TABLE=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`GameSourceTable`].OutputValue' \
        --output text \
        --no-cli-pager)

    if [ -z "$GAME_SOURCE_TABLE" ]; then
        print_error "GameSourceTable output not found"
        exit 1
    fi

    aws dynamodb put-item \
        --table-name "$GAME_SOURCE_TABLE" \
        --item "{\"game\":{\"S\":\"game01\"},\"source\":{\"S\":\"${GAME_SOURCE_URI}\"}}"

    print_success "Game source table seeded for game01"
}

deploy_exam_website() {
    print_header "Deploying Exam Website"

    local stack_name region exam_web_dir bucket website_url
    stack_name="$(get_stack_name || echo "k8s-grader-api-dev")"
    region="$(get_region || echo "us-east-1")"
    exam_web_dir="$(cd ../exam-web && pwd)"

    if [ ! -d "$exam_web_dir" ]; then
        print_error "Exam web directory not found at $exam_web_dir"
        exit 1
    fi

    bucket=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`ExamWebsiteBucket`].OutputValue' \
        --output text \
        --no-cli-pager)

    if [ -z "$bucket" ] || [ "$bucket" = "None" ]; then
        print_error "ExamWebsiteBucket output not found"
        exit 1
    fi

    print_info "Uploading exam web files to s3://${bucket}"
    aws s3 sync "$exam_web_dir" "s3://${bucket}" --delete --no-cli-pager >/dev/null
    print_success "Exam website uploaded"

    website_url=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`ExamWebsiteUrl`].OutputValue' \
        --output text \
        --no-cli-pager)

    if [ -n "$website_url" ] && [ "$website_url" != "None" ]; then
        echo "Exam Website URL: ${website_url}"
    fi
}

# Deploy
deploy() {
    print_header "Deploying to AWS"

    local guided_flag="${1:-}"
    local parameter_overrides=("PythonVersion=${PYTHON_VERSION_OVERRIDE}")

    if [ "${guided_flag}" == "--guided" ]; then
        print_info "Running guided deployment..."
        sam deploy --guided --config-env "${CONFIG_ENV}" --parameter-overrides "${parameter_overrides[@]}" --no-fail-on-empty-changeset
    else
        print_info "Deploying with saved configuration (${CONFIG_ENV})..."
        sam deploy --config-env "${CONFIG_ENV}" --parameter-overrides "${parameter_overrides[@]}" --no-fail-on-empty-changeset
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
    
    STACK_NAME="$(get_stack_name || echo "k8s-grader-api-dev")"
    
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
    
    STACK_NAME="$(get_stack_name || echo "k8s-grader-api-dev")"
    
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

    prepare_game_source
    seed_game_source_table
    deploy_exam_website
    
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
