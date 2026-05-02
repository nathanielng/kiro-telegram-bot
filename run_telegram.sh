#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/.venv}"
LOG_DIR="${SCRIPT_DIR}/log"
PID_FILE="${LOG_DIR}/telegram_bot.pid"
RESTART=false

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --restart|-r) RESTART=true ;;
  esac
done

# Load .env if present (does not override variables already set in the environment)
if [ -f "${SCRIPT_DIR}/.env" ]; then
  set -o allexport
  . "${SCRIPT_DIR}/.env"
  set +o allexport
fi

if [ -z "$TELEGRAM_API_KEY" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set"
  echo "Copy .env.sample to .env and fill in your values."
  echo "For multi-user mode (no TELEGRAM_CHAT_ID), run: uv run telegram_bot.py"
  exit 1
fi

# Optional configuration warnings
if [ -z "$BEDROCK_GUARDRAIL_ID" ] || [ -z "$BEDROCK_GUARDRAIL_VERSION" ]; then
  echo "⚠️  BEDROCK_GUARDRAIL_ID/VERSION not set. A guardrail mitigates risk by filtering harmful inputs."
fi
echo "📁 KIRO_OUTPUT_DIR: ${KIRO_OUTPUT_DIR:-kirobot-out}"
if [ -z "$S3_BUCKET_NAME" ]; then
  echo "⚠️  S3_BUCKET_NAME not set. Output files will not be synced to S3."
fi
if [ -z "$S3_PREFIX" ]; then
  echo "⚠️  S3_PREFIX not set. Files will upload to the S3 bucket root."
fi
if [ -z "$CLOUDFRONT_BASE_URL" ]; then
  echo "⚠️  CLOUDFRONT_BASE_URL not set. File URLs will not be shared via Telegram."
fi

# Check if bot is already running
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    if [ "$RESTART" = true ]; then
      echo "Stopping existing bot (PID: $OLD_PID)..."
      kill "$OLD_PID" 2>/dev/null
      sleep 1
      # Force kill if still running
      kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null
    else
      echo "Error: Bot is already running (PID: $OLD_PID)"
      echo "Stop it first: kill $OLD_PID"
      echo "Or use --restart to auto-restart."
      exit 1
    fi
  fi
  rm -f "$PID_FILE"
fi

# Install uv if not already installed
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
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

. "$VENV_DIR/bin/activate" || { echo "Error: Failed to activate virtual environment"; exit 1; }
nohup uv run "${SCRIPT_DIR}/telegram_bot.py" > "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > "$PID_FILE"

echo "Bot started in background. PID: $BOT_PID"
echo "View logs: tail -f $LOG_FILE"
