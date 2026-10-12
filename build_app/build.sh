#!/bin/bash
# Build ShellCron.app and optionally .dmg
# Usage: bash build_app/build.sh [--dmg] [--install]

set -e
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python3"

echo "=== ShellCron App Builder ==="
echo ""

# Check PyInstaller
if ! $PYTHON -m PyInstaller --version &>/dev/null; then
    echo "PyInstaller not found. Installing..."
    $PYTHON -m pip install pyinstaller
    echo ""
fi

# Build
$PYTHON build_app/build.py "$@"

echo ""
echo "To install the app:"
echo "  open dist/  # then drag ShellCron.app to Applications"
echo ""
echo "To run directly from CLI (no app needed):"
echo "  shcron start"
