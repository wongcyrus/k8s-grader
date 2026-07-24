#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DEPLOY_SCRIPT="${SCRIPT_DIR}/k8s-grader-api/deploy.sh"

if [ ! -f "$API_DEPLOY_SCRIPT" ]; then
    echo "Deploy script not found: $API_DEPLOY_SCRIPT" >&2
    exit 1
fi

export SAM_CONFIG_ENV="${ENV:-${SAM_CONFIG_ENV:-default}}"

if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    export SECRET_HASH_OVERRIDE="$1"
    shift
fi

exec bash "$API_DEPLOY_SCRIPT" "$@"
