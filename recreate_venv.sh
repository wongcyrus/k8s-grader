#!/bin/bash
# Recreate virtual environment with correct paths

set -e

echo "🔧 Recreating virtual environment..."

# Remove old venv
if [ -d "venv" ]; then
    echo "Removing old venv..."
    rm -rf venv
fi

# Create new venv
echo "Creating new venv..."
python3 -m venv venv

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate

# Install boto3 for tools
pip install -q boto3>=1.26.0

echo "✅ Virtual environment recreated successfully!"
echo ""
echo "To activate:"
echo "  source venv/bin/activate"
echo ""
echo "To run reset_game.py:"
echo "  python tools/reset_game.py"
