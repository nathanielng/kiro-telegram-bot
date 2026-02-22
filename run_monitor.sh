#!/bin/bash
# Run the folder monitor in the background.
# The monitor watches KIRO_OUTPUT_DIR for new/modified files, redacts PII,
# uploads them to S3, and sends Telegram notifications with CloudFront URLs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/.venv}"

# Load .env if present (does not override variables already set in the environment)
if [ -f "${SCRIPT_DIR}/.env" ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env"
  set +o allexport
fi

if [ -z "$TELEGRAM_API_KEY" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set"
  echo "Copy .env.sample to .env and fill in your values."
  exit 1
fi

if [ -z "$KIRO_OUTPUT_DIR" ]; then
  echo "Error: KIRO_OUTPUT_DIR is not set"
  echo "Add KIRO_OUTPUT_DIR to your .env file."
  exit 1
fi

if [ -z "$S3_BUCKET_NAME" ]; then
  echo "Error: S3_BUCKET_NAME is not set"
  echo "Add S3_BUCKET_NAME to your .env file."
  exit 1
fi

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
  echo "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &> /dev/null; then
    echo "Error: Failed to install uv"
    exit 1
  fi
  echo "uv installed successfully."
fi

# Set up virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  echo "Virtual environment not found at $VENV_DIR. Creating..."
  uv venv "$VENV_DIR"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment at $VENV_DIR"
    exit 1
  fi
  echo "Virtual environment created at $VENV_DIR."
fi

source "$VENV_DIR/bin/activate" && nohup uv run "${SCRIPT_DIR}/folder_monitor.py" > "${SCRIPT_DIR}/folder_monitor.log" 2>&1 &
echo "Folder monitor started in background. PID: $!"
echo "Watching: $KIRO_OUTPUT_DIR"
echo "View logs: tail -f ${SCRIPT_DIR}/folder_monitor.log"
