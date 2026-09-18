#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DEPLOY_SCRIPT="${SCRIPT_DIR}/k8s-grader-api/deploy.sh"

if [ ! -f "$API_DEPLOY_SCRIPT" ]; then
    echo "Deploy script not found: $API_DEPLOY_SCRIPT" >&2
    exit 1
fi

DEPLOY_ENV="${ENV:-${DEPLOY_ENV:-dev}}"
case "$DEPLOY_ENV" in
    dev|default)
        export SAM_CONFIG_FILE="${SAM_CONFIG_FILE:-${SCRIPT_DIR}/k8s-grader-api/samconfig.dev.toml}"
        ;;
    prod)
        export SAM_CONFIG_FILE="${SAM_CONFIG_FILE:-${SCRIPT_DIR}/k8s-grader-api/samconfig.prod.toml}"
        ;;
    *)
        echo "Unsupported deploy environment: ${DEPLOY_ENV}. Use dev or prod." >&2
        exit 1
        ;;
esac
export SAM_CONFIG_ENV="${SAM_CONFIG_ENV:-default}"

if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    export SECRET_HASH_OVERRIDE="$1"
    shift
fi

exec bash "$API_DEPLOY_SCRIPT" "$@"
