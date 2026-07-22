#!/bin/bash
set -euo pipefail

# Set Docker API version to avoid version mismatch
export DOCKER_API_VERSION=1.43

cd $(dirname $0)

echo ">> Building AWS Lambda layer inside a docker image..."

TAG='aws-lambda-layer'
KUBECTL_VERSION="${KUBECTL_VERSION:-1.36.2}"
HELM_VERSION="${HELM_VERSION:-3.14.4}"

build_layer_without_docker() {
    echo ">> Docker unavailable inside SAM build container, building layer directly..."

    : "${ARTIFACTS_DIR:?ARTIFACTS_DIR must be set}"
    mkdir -p "${ARTIFACTS_DIR}/kubectl" "${ARTIFACTS_DIR}/helm"

    echo ">> Downloading kubectl ${KUBECTL_VERSION}..."
    curl -fsSL -o "${ARTIFACTS_DIR}/kubectl/kubectl" \
        "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
    chmod +x "${ARTIFACTS_DIR}/kubectl/kubectl"

    echo ">> Downloading helm ${HELM_VERSION}..."
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "${TMP_DIR}"' EXIT
    curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz" | tar -xz -C "${TMP_DIR}"
    cp "${TMP_DIR}/linux-amd64/helm" "${ARTIFACTS_DIR}/helm/helm"
    chmod +x "${ARTIFACTS_DIR}/helm/helm"

    echo ">> Direct layer build complete"
}

if ! command -v docker >/dev/null 2>&1; then
    build_layer_without_docker
    exit 0
fi

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