#!/bin/bash

# Undeploy Minikube Stack
# This script deletes the CloudFormation stack and optionally the key pair

set -e  # Exit on error

# Configuration
STACK_NAME="minikube-stack"
KEY_PAIR_NAME="labsuser"
KEY_FILE="${KEY_PAIR_NAME}.pem"
REGION="us-east-1"

echo "=========================================="
echo "Minikube Stack Cleanup Script"
echo "=========================================="
echo ""

# Check if stack exists
echo "Checking if stack '${STACK_NAME}' exists..."
if ! aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" &>/dev/null; then
    echo "✓ Stack '${STACK_NAME}' does not exist. Nothing to undeploy."
    exit 0
fi

echo "⚠ This will delete the following resources:"
echo "  - CloudFormation Stack: ${STACK_NAME}"
echo "  - EC2 Instance (minikube)"
echo "  - Elastic IP"
echo "  - Security Group"
echo ""

read -p "Are you sure you want to continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Undeploy cancelled."
    exit 0
fi

echo ""
echo "Deleting CloudFormation stack: ${STACK_NAME}..."
aws cloudformation delete-stack \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo "Waiting for stack deletion to complete..."
echo "(This may take a few minutes)"
aws cloudformation wait stack-delete-complete \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo ""
echo "✓ Stack deleted successfully!"

# Ask about key pair deletion
echo ""
if aws ec2 describe-key-pairs --key-names "${KEY_PAIR_NAME}" --region "${REGION}" &>/dev/null; then
    echo "Key pair '${KEY_PAIR_NAME}' still exists in AWS."
    read -p "Do you want to delete the key pair? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        aws ec2 delete-key-pair \
            --key-name "${KEY_PAIR_NAME}" \
            --region "${REGION}"
        echo "✓ Key pair deleted from AWS."
        
        # Ask about local key file
        if [ -f "${KEY_FILE}" ]; then
            read -p "Delete local key file '${KEY_FILE}'? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm "${KEY_FILE}"
                echo "✓ Local key file deleted."
            else
                echo "Local key file kept: ${KEY_FILE}"
            fi
        fi
    else
        echo "Key pair kept in AWS."
    fi
fi

# Clean up endpoint file
if [ -f "endpoint.txt" ]; then
    rm endpoint.txt
    echo "✓ endpoint.txt removed."
fi

echo ""
echo "=========================================="
echo "✓ Cleanup completed!"
echo "=========================================="
