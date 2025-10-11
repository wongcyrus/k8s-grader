#!/bin/bash

# Deploy Minikube Stack with CloudFormation
# This script creates a new key pair if needed and deploys the minikube infrastructure

set -e  # Exit on error

# Configuration
STACK_NAME="minikube-stack"
TEMPLATE_FILE="minikube.yaml"
KEY_PAIR_NAME="labsuser"
KEY_FILE="${KEY_PAIR_NAME}.pem"
REGION="us-east-1"

echo "=========================================="
echo "Minikube CloudFormation Deployment Script"
echo "=========================================="
echo ""

# Check if key pair already exists
echo "Checking for existing key pair: ${KEY_PAIR_NAME}..."
if aws ec2 describe-key-pairs --key-names "${KEY_PAIR_NAME}" --region "${REGION}" &>/dev/null; then
    echo "✓ Key pair '${KEY_PAIR_NAME}' already exists."
    
    # Check if local key file exists
    if [ ! -f "${KEY_FILE}" ]; then
        echo "⚠ Warning: Key file '${KEY_FILE}' not found locally."
        echo "  If you need to SSH into the instance, you'll need to provide the key file."
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Deployment cancelled."
            exit 1
        fi
    fi
else
    echo "Creating new key pair: ${KEY_PAIR_NAME}..."
    aws ec2 create-key-pair \
        --key-name "${KEY_PAIR_NAME}" \
        --region "${REGION}" \
        --query 'KeyMaterial' \
        --output text > "${KEY_FILE}"
    
    chmod 400 "${KEY_FILE}"
    echo "✓ Key pair created and saved to ${KEY_FILE}"
fi

echo ""
echo "Deploying CloudFormation stack: ${STACK_NAME}..."
echo "This may take 5-10 minutes..."
echo ""

# Deploy the CloudFormation stack
aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides KeyName="${KEY_PAIR_NAME}" \
    --region "${REGION}" \
    --capabilities CAPABILITY_IAM

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Deployment completed successfully!"
    echo "=========================================="
    echo ""
    
    # Get stack outputs
    echo "Retrieving stack outputs..."
    INSTANCE_IP=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='InstancePublicIp'].OutputValue" \
        --output text)
    
    SSH_COMMAND=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='SSHCommand'].OutputValue" \
        --output text)
    
    echo ""
    echo "Instance Public IP: ${INSTANCE_IP}"
    echo "SSH Command: ssh -i ${KEY_FILE} ec2-user@${INSTANCE_IP}"
    echo ""
    
    # Update endpoint.txt
    echo "http://${INSTANCE_IP}:8001" > endpoint.txt
    echo "✓ Endpoint saved to endpoint.txt"
    echo ""
    
    # Wait for instance to be ready
    echo "Waiting for instance to complete initialization..."
    echo "(This may take 5-10 minutes for Minikube to fully start)"
    echo ""
    
    # Optional: Wait for stack signals
    aws cloudformation wait stack-create-complete \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" 2>/dev/null || true
    
    echo ""
    echo "=========================================="
    echo "Next Steps:"
    echo "=========================================="
    echo "1. SSH into the instance:"
    echo "   ssh -i ${KEY_FILE} ec2-user@${INSTANCE_IP}"
    echo ""
    echo "2. Check Minikube status:"
    echo "   minikube status"
    echo ""
    echo "3. Access Kubernetes:"
    echo "   kubectl get nodes"
    echo ""
    echo "4. To undeploy, run: ./undeploy_minikube.sh"
    echo "=========================================="
else
    echo ""
    echo "✗ Deployment failed. Check the error messages above."
    exit 1
fi
