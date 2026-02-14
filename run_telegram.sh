#!/bin/bash

if [ -z "$TELEGRAM_API_KEY" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set"
  exit 1
fi

source ~/.venv/bin/activate && nohup uv run telegram_bot.py > telegram_bot.log 2>&1 &
echo "Bot started in background. PID: $!"
echo "View logs: tail -f telegram_bot.log"
