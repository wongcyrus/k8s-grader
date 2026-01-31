#!/bin/bash

# Setup kubectl to connect to remote minikube cluster
# Usage: ./setup_kubectl.sh <server-url>
# Example: ./setup_kubectl.sh https://silver-space-telegram-r59p4675vf5gr5-8001.app.github.dev

set -e

# Check if server URL is provided
if [ -z "$1" ]; then
    echo "Error: Server URL is required"
    echo "Usage: $0 <server-url>"
    echo "Example: $0 https://silver-space-telegram-r59p4675vf5gr5-8001.app.github.dev"
    exit 1
fi

SERVER_URL="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="$SCRIPT_DIR/minikube-client-certs"

echo "Setting up kubectl to connect to remote minikube..."
echo "Server URL: $SERVER_URL"

# Create necessary directories
echo "Creating directories..."
mkdir -p ~/.minikube/profiles/minikube
mkdir -p ~/.kube

# Copy certificates
echo "Copying certificates..."
cp "$CERTS_DIR/ca.crt" ~/.minikube/
cp "$CERTS_DIR/client.crt" ~/.minikube/profiles/minikube/
cp "$CERTS_DIR/client.key" ~/.minikube/profiles/minikube/

# Set proper permissions
chmod 600 ~/.minikube/profiles/minikube/client.key
chmod 644 ~/.minikube/profiles/minikube/client.crt
chmod 644 ~/.minikube/ca.crt

# Configure kubectl
echo "Configuring kubectl..."
kubectl config set-cluster minikube \
    --server="$SERVER_URL" \
    --insecure-skip-tls-verify=true

kubectl config set-credentials minikube \
    --client-certificate="$HOME/.minikube/profiles/minikube/client.crt" \
    --client-key="$HOME/.minikube/profiles/minikube/client.key"

kubectl config set-context minikube \
    --cluster=minikube \
    --user=minikube \
    --namespace=default

kubectl config use-context minikube

# Test connection
echo ""
echo "Testing connection..."
if kubectl cluster-info &>/dev/null; then
    echo "✓ Successfully connected to minikube cluster!"
    echo ""
    kubectl cluster-info
    echo ""
    kubectl get nodes
else
    echo "✗ Failed to connect to minikube cluster"
    echo "Please check if the server URL is correct and accessible"
    exit 1
fi
