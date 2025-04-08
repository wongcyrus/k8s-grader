#!/bin/bash
# set -x

cd k8s-grader-api

sam build || { echo "sam build failed"; exit 1; }
if [ -n "$1" ]; then
    sam deploy --capabilities CAPABILITY_IAM --parameter-overrides SecretHash="$1" || { echo "sam deploy failed"; exit 1; }
else
    sam deploy --capabilities CAPABILITY_IAM || { echo "sam deploy failed"; exit 1; }
fi
