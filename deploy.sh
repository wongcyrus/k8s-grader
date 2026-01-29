#!/bin/bash
set -e

cd k8s-grader-api

# Optional: specify environment with --config-env (dev, prod)
ENV="${ENV:-default}"

echo "Building SAM application..."
sam build

echo "Deploying to $ENV environment..."
if [ -n "$1" ]; then
    sam deploy --config-env "$ENV" --parameter-overrides SecretHash="$1"
else
    sam deploy --config-env "$ENV"
fi

echo "Deployment complete!"
