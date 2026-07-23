#!/bin/bash

# K8s Grader API Undeploy Script
# Empties stack-owned S3 buckets, then deletes the CloudFormation stack.
# CloudFormation custom resources are deleted by the stack itself; this script
# only clears S3 buckets that commonly block stack deletion.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CONFIG_ENV="${SAM_CONFIG_ENV:-default}"
AUTO_APPROVE=false
SKIP_WAIT=false

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

check_prerequisites() {
    print_header "Checking Prerequisites"

    if command -v aws &> /dev/null; then
        print_success "AWS CLI installed: $(aws --version)"
    else
        print_error "AWS CLI not found. Please install it first."
        exit 1
    fi

    if aws sts get-caller-identity --no-cli-pager &> /dev/null; then
        print_success "AWS credentials configured"
    else
        print_error "AWS credentials not configured. Run 'aws configure'"
        exit 1
    fi

    if [ -f "samconfig.toml" ]; then
        print_success "samconfig.toml found"
    else
        print_error "samconfig.toml not found. Run this script from k8s-grader-api/"
        exit 1
    fi
}

validate_stack_access() {
    print_header "Validating AWS Access"

    if aws cloudformation describe-stack-resources \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --no-cli-pager >/dev/null 2>&1; then
        print_success "CloudFormation read access verified"
    else
        print_error "Missing CloudFormation access for stack inspection"
        echo "Required IAM actions include at least:"
        echo "  - cloudformation:DescribeStacks"
        echo "  - cloudformation:DescribeStackResource"
        echo "  - cloudformation:DescribeStackResources"
        echo "  - cloudformation:DeleteStack"
        exit 1
    fi
}

stack_exists() {
    aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --no-cli-pager >/dev/null 2>&1
}

get_stack_resource_physical_id() {
    local logical_id="$1"
    aws cloudformation describe-stack-resource \
        --stack-name "${STACK_NAME}" \
        --logical-resource-id "${logical_id}" \
        --region "${REGION}" \
        --query 'StackResourceDetail.PhysicalResourceId' \
        --output text \
        --no-cli-pager 2>/dev/null || true
}

empty_bucket() {
    local bucket_name="$1"

    if [ -z "${bucket_name}" ] || [ "${bucket_name}" = "None" ]; then
        return 0
    fi

    print_info "Emptying s3://${bucket_name}"
    aws s3 rm "s3://${bucket_name}" --recursive --region "${REGION}" --no-cli-pager >/dev/null || {
        print_error "Failed to empty bucket: ${bucket_name}"
        exit 1
    }
    print_success "Bucket emptied: ${bucket_name}"
}

confirm_delete() {
    echo "⚠ This will delete the following AWS stack resources:"
    echo "  - CloudFormation stack: ${STACK_NAME}"
    echo "  - API Gateway / Lambda / DynamoDB / CloudFront resources in the stack"
    echo "  - CloudFormation-managed custom resources (for example PostDeployment init hooks)"
    echo "  - S3 bucket contents for:"
    if [ ${#STACK_BUCKETS[@]} -eq 0 ]; then
        echo "    • None found"
    else
        for bucket in "${STACK_BUCKETS[@]}"; do
            echo "    • ${bucket}"
        done
    fi
    echo ""

    if [ "${AUTO_APPROVE}" = true ]; then
        print_info "Auto-approval enabled (--yes)"
        return 0
    fi

    read -r -p "Are you sure you want to continue? (y/n): " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo "Undeploy cancelled."
        exit 0
    fi
}

delete_stack() {
    print_header "Deleting CloudFormation Stack"

    aws cloudformation delete-stack \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --no-cli-pager

    print_success "Delete request submitted for stack: ${STACK_NAME}"

    if [ "${SKIP_WAIT}" = true ]; then
        print_info "Skipping wait (--no-wait)"
        return 0
    fi

    print_info "Waiting for stack deletion to complete..."
    aws cloudformation wait stack-delete-complete \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --no-cli-pager
    print_success "Stack deleted successfully"
}

show_help() {
    echo ""
    echo "Usage: ./undeploy.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --yes        Delete without confirmation"
    echo "  --no-wait    Exit after submitting delete-stack"
    echo "  --help       Show this help message"
    echo ""
    echo "Environment:"
    echo "  SAM_CONFIG_ENV=<env>  Use stack/region from samconfig.toml (default: default)"
    echo ""
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes)
                AUTO_APPROVE=true
                shift
                ;;
            --no-wait)
                SKIP_WAIT=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    STACK_NAME="$(get_stack_name || echo "k8s-grader-api-dev")"
    REGION="$(get_region || echo "us-east-1")"

    check_prerequisites

    print_header "Resolving Stack"
    print_info "Environment: ${CONFIG_ENV}"
    print_info "Stack: ${STACK_NAME}"
    print_info "Region: ${REGION}"

    if ! stack_exists; then
        print_success "Stack '${STACK_NAME}' does not exist. Nothing to undeploy."
        exit 0
    fi

    validate_stack_access

    STACK_BUCKETS=()

    exam_website_bucket="$(get_stack_resource_physical_id "ExamWebsiteBucket")"
    game_source_bucket="$(get_stack_resource_physical_id "GameSourceBucket")"
    test_result_bucket="$(get_stack_resource_physical_id "TestResultBucket")"

    for bucket in "${exam_website_bucket}" "${game_source_bucket}" "${test_result_bucket}"; do
        if [ -n "${bucket}" ] && [ "${bucket}" != "None" ]; then
            STACK_BUCKETS+=("${bucket}")
        fi
    done

    confirm_delete

    print_header "Emptying Stack Buckets"
    for bucket in "${STACK_BUCKETS[@]}"; do
        empty_bucket "${bucket}"
    done

    delete_stack
}

main "$@"
