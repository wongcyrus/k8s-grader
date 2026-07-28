#!/bin/bash
# Test runner script for refactored code

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
VENV_PIP="$SCRIPT_DIR/venv/bin/pip"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Running K8s Game API Tests${NC}"
echo "================================"
echo ""

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv "$SCRIPT_DIR/venv"
    "$VENV_PIP" install -q -r "$SCRIPT_DIR/requirements-dev.txt"
fi

if ! "$VENV_PYTHON" -c "import moto, pytest_cov" >/dev/null 2>&1; then
    echo "Installing missing test dependencies..."
    "$VENV_PIP" install -q -r "$SCRIPT_DIR/requirements-dev.txt"
fi

# Run unit tests only (exclude integration tests)
echo -e "${GREEN}Running unit tests...${NC}"
"$VENV_PYTHON" -m pytest "$SCRIPT_DIR/tests/" -v --tb=short --cov=common --cov-report=term-missing:skip-covered --cov-report=html -m "not integration"

echo ""
echo -e "${GREEN}✅ All unit tests completed!${NC}"
echo ""
echo "To view detailed coverage report:"
echo "  open htmlcov/index.html"
echo ""
echo "Note: Integration tests are excluded. Run them separately with:"
echo "  bash run_integration_tests.sh"
