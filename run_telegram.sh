#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/.venv}"
LOG_DIR="${SCRIPT_DIR}/log"
PID_FILE="${LOG_DIR}/telegram_bot.pid"

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
  echo "For multi-user mode (no TELEGRAM_CHAT_ID), run: uv run telegram_bot.py"
  exit 1
fi

# Check if bot is already running
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Error: Bot is already running (PID: $OLD_PID)"
    echo "Stop it first: kill $OLD_PID"
    exit 1
  fi
  rm -f "$PID_FILE"
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

mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/telegram_bot_${TIMESTAMP}.log"

source "$VENV_DIR/bin/activate" || { echo "Error: Failed to activate virtual environment"; exit 1; }
nohup uv run "${SCRIPT_DIR}/telegram_bot.py" > "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > "$PID_FILE"

echo "Bot started in background. PID: $BOT_PID"
echo "View logs: tail -f $LOG_FILE"
