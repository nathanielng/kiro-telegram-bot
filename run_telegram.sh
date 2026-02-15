#!/bin/bash

VENV_DIR="${VENV_DIR:-$HOME/.venv}"

if [ -z "$TELEGRAM_API_KEY" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set"
  exit 1
fi

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
  echo "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Source the uv environment so it's available in this session
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

source "$VENV_DIR/bin/activate" && nohup uv run telegram_bot.py > telegram_bot.log 2>&1 &
echo "Bot started in background. PID: $!"
echo "View logs: tail -f telegram_bot.log"
