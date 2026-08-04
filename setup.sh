#!/usr/bin/env bash
# One-time setup for macOS: install dependencies for both Step 1 and Step 2.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_CMD="${PYTHON_CMD:-python3}"

echo "Using Python: $PYTHON_CMD"
echo

echo "[1/2] Installing Python dependencies..."
"$PYTHON_CMD" -m pip install --user -r "$SCRIPT_DIR/requirements.txt"

echo
echo "[2/2] Installing Playwright Chromium (needed for concert scraping)..."
"$PYTHON_CMD" -m playwright install chromium

echo
echo "Done. Run ./run.sh to start Step 1 or Step 2."
echo
echo "IMPORTANT: Before running Step 1, copy .env.example to .env and set ARK_API_KEY."
echo "  cp .env.example .env"
