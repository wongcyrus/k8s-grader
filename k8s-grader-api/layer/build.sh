#!/bin/bash
set -euo pipefail

# Set Docker API version to avoid version mismatch
export DOCKER_API_VERSION=1.43

cd $(dirname $0)

echo ">> Building AWS Lambda layer inside a docker image..."

TAG='aws-lambda-layer'

docker build -t ${TAG} .

echo ">> Extrating layer.zip from the build container..."
CONTAINER=$(docker run -d ${TAG} false)

echo ">> ARTIFACTS_DIR path: ${ARTIFACTS_DIR}"
docker cp ${CONTAINER}:/layer.zip ${ARTIFACTS_DIR}/layer.zip

echo ">> Stopping container..."
docker rm -f ${CONTAINER}
echo ">> layer.zip is ready"

echo ">> Extracting layer.zip..."
unzip ${ARTIFACTS_DIR}/layer.zip -d ${ARTIFACTS_DIR}

echo ">> Removing layer.zip..."
rm ${ARTIFACTS_DIR}/layer.zip

echo ">> Extraction complete"