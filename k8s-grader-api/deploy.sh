#!/bin/bash

# K8s Grader API Deployment Script
# This script automates the deployment process

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

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

get_teacher_emails() {
    local block
    local line
    if [ "${CONFIG_ENV}" = "default" ]; then
        block=$(grep '^\[default.deploy.parameters\]' -A 20 samconfig.toml)
    else
        block=$(grep "^\[${CONFIG_ENV}\.deploy.parameters\]" -A 20 samconfig.toml)
    fi

    line=$(printf '%s\n' "$block" | grep 'parameter_overrides' | head -n 1 || true)
    if [ -z "$line" ]; then
        return 0
    fi

    printf '%s\n' "$line" | sed -n 's/.*TeacherEmails=\\"\([^"]*\)\\".*/\1/p'
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

    # Check Node.js and npm for static web builds
    if command -v node &> /dev/null; then
        print_success "Node.js installed: $(node --version)"
    else
        print_error "Node.js not found"
        exit 1
    fi

    if command -v npm &> /dev/null; then
        print_success "npm installed: $(npm --version)"
    else
        print_error "npm not found"
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
    print_header "Deploying Student Portal"

    local stack_name region exam_web_dir game_web_dir doom_web_dir doom_dist_dir bucket website_url
    local base_url game_ws_url exam_ws_url config_path distribution_id
    stack_name="$(get_stack_name || echo "k8s-grader-api-dev")"
    region="$(get_region || echo "us-east-1")"
    exam_web_dir="$(cd ../exam-web && pwd)"
    game_web_dir="$(cd ../../k8s-isekai && pwd)"
    doom_web_dir="$(cd ../../doom.ts && pwd)"
    doom_dist_dir="${doom_web_dir}/dist"
    config_path="${exam_web_dir}/config.js"

    if [ ! -d "$exam_web_dir" ]; then
        print_error "Exam web directory not found at $exam_web_dir"
        exit 1
    fi

    if [ ! -d "$game_web_dir" ]; then
        print_error "Game web directory not found at $game_web_dir"
        exit 1
    fi

    if [ ! -d "$doom_web_dir" ]; then
        print_error "Doom web directory not found at $doom_web_dir"
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

    base_url=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`BaseUrl`].OutputValue' \
        --output text \
        --no-cli-pager)

    game_ws_url=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`GameWebSocketUrl`].OutputValue' \
        --output text \
        --no-cli-pager)

    exam_ws_url=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`ExamWebSocketUrl`].OutputValue' \
        --output text \
        --no-cli-pager)

    if [ -z "$base_url" ] || [ "$base_url" = "None" ]; then
        print_error "BaseUrl output not found"
        exit 1
    fi

    if [ -z "$game_ws_url" ] || [ "$game_ws_url" = "None" ]; then
        print_error "GameWebSocketUrl output not found"
        exit 1
    fi

    if [ -z "$exam_ws_url" ] || [ "$exam_ws_url" = "None" ]; then
        print_error "ExamWebSocketUrl output not found"
        exit 1
    fi

    cat > "$config_path" <<EOF
window.__K8S_PORTAL_CONFIG__ = {
  baseUrl: "${base_url%/}",
  gameWsUrl: "${game_ws_url}",
  examWsUrl: "${exam_ws_url}"
};
EOF
    trap "rm -f '$config_path'" RETURN

    print_info "Uploading student portal files to s3://${bucket}"
    aws s3 sync "$exam_web_dir" "s3://${bucket}" --delete --exclude "game/*" --exclude "doom/*" --no-cli-pager >/dev/null
    print_success "Student portal uploaded"

    print_info "Uploading RPG game files to s3://${bucket}/game"
    aws s3 sync "$game_web_dir" "s3://${bucket}/game" \
        --delete \
        --exclude ".git/*" \
        --exclude ".github/*" \
        --exclude ".devcontainer/*" \
        --exclude ".vscode/*" \
        --exclude "python_tools/*" \
        --exclude "package*.json" \
        --exclude ".prettierrc.json" \
        --exclude "README.md" \
        --no-cli-pager >/dev/null
    print_success "RPG game uploaded"

    print_info "Building Doom web for /doom/"
    (
        cd "$doom_web_dir"
        DOOM_BASE_PATH=/doom/ npm run build >/dev/null
    )
    print_success "Doom web built"

    if [ ! -d "$doom_dist_dir" ]; then
        print_error "Doom build output not found at $doom_dist_dir"
        exit 1
    fi

    print_info "Uploading Doom web files to s3://${bucket}/doom"
    aws s3 sync "$doom_dist_dir" "s3://${bucket}/doom" --delete --no-cli-pager >/dev/null
    print_success "Doom web uploaded"

    distribution_id=$(aws cloudformation describe-stack-resources \
        --stack-name "$stack_name" \
        --logical-resource-id ExamWebsiteCloudFrontDistribution \
        --query 'StackResources[0].PhysicalResourceId' \
        --output text \
        --no-cli-pager)

    if [ -n "$distribution_id" ] && [ "$distribution_id" != "None" ]; then
        print_info "Invalidating CloudFront cache"
        aws cloudfront create-invalidation \
            --distribution-id "$distribution_id" \
            --paths \
            / \
            /index.html \
            /config.js \
            /app.js \
            /exam.html \
            /exam.js \
            /teacher.html \
            /teacher.js \
            /styles.css \
            /doom \
            /doom/ \
            /doom/index.html \
            --no-cli-pager >/dev/null
        print_success "CloudFront invalidation requested"
    fi

    website_url=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`StudentPortalUrl`].OutputValue' \
        --output text \
        --no-cli-pager)

    if [ -n "$website_url" ] && [ "$website_url" != "None" ]; then
        echo "Student Portal URL: ${website_url}"
        echo "RPG Game URL: ${website_url%/}/game/index.html"
        echo "Doom URL: ${website_url%/}/doom/"
    fi

    trap - RETURN
    rm -f "$config_path"
}

# Deploy
deploy() {
    print_header "Deploying to AWS"

    local guided_flag="${1:-}"
    local parameter_overrides=("PythonVersion=${PYTHON_VERSION_OVERRIDE}")
    local teacher_emails="${TEACHER_EMAILS_OVERRIDE:-$(get_teacher_emails)}"
    if [ -n "${SECRET_HASH_OVERRIDE:-}" ]; then
        parameter_overrides+=("SecretHash=${SECRET_HASH_OVERRIDE}")
    fi
    if [ -n "${teacher_emails}" ]; then
        parameter_overrides+=("TeacherEmails=${teacher_emails}")
    fi

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
        STUDENT_PORTAL_URL=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`StudentPortalUrl`].OutputValue' \
            --output text \
            --no-cli-pager 2>/dev/null || echo "")
        echo "2. Open the exercise portal, save the API key and Kubernetes login, then use:"
        if [ -n "$STUDENT_PORTAL_URL" ] && [ "$STUDENT_PORTAL_URL" != "None" ]; then
            echo "   Exercise: ${STUDENT_PORTAL_URL}"
            echo "   Exam:     ${STUDENT_PORTAL_URL}/exam.html"
        else
            echo "   ${BASE_URL}exam/verify-code?examCode=YOUR_EXAM_CODE"
        fi
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
