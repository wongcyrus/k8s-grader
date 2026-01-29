#!/bin/bash
# Test runner script for refactored code

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

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
    "$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/common-layer/requirements.txt"
fi

# Run tests
echo -e "${GREEN}Running all tests...${NC}"
"$VENV_PYTHON" -m pytest "$SCRIPT_DIR/tests/" -v --tb=short --cov=common --cov-report=term-missing

echo ""
echo -e "${GREEN}✅ All tests completed!${NC}"
echo ""
echo "To view detailed coverage report:"
echo "  open htmlcov/index.html"
