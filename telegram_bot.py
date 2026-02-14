#!/usr/bin/env python3
"""
Telegram Bot with AWS Bedrock Integration and Kiro CLI

Supports two modes:
- /chat: Send prompts to Bedrock (default)
- /code: Send prompts to Kiro CLI
- /help: Show available commands

Requires: TELEGRAM_API_KEY, TELEGRAM_CHAT_ID, AWS_REGION (optional)
"""

import json
import os
import re
import subprocess
import sys
import time
import boto3
import requests


def get_config():
    api_key = os.environ.get('TELEGRAM_API_KEY')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    region = os.environ.get('AWS_REGION', 'us-west-2')

    if not api_key or not chat_id:
        print("Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set")
        sys.exit(1)

    return api_key, chat_id, region


def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def send_message(api_key, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{api_key}/sendMessage",
            json={"chat_id": chat_id, "text": strip_ansi(text)},
            timeout=10
        )
    except Exception as e:
        print(f"Failed to send message: {e}")


def invoke_bedrock(bedrock, prompt):
    try:
        response = bedrock.invoke_model(
            modelId="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
    except Exception as e:
        return f"Error: {e}"


def invoke_kiro(prompt):
    try:
        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.stdout if result.stdout else result.stderr
    except Exception as e:
        return f"Error: {e}"


def main():
    api_key, chat_id, region = get_config()
    bedrock = boto3.client('bedrock-runtime', region_name=region)
    offset = 0
    mode = "chat"

    print(f"Bot started. Monitoring chat {chat_id}")

    while True:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{api_key}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            data = response.json()

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1

                    if "message" in update and "text" in update["message"]:
                        user_text = update["message"]["text"]
                        print(f"Received: {user_text}")

                        if user_text == "/chat":
                            mode = "chat"
                            reply = "Switched to chat mode (Bedrock)"
                        elif user_text == "/code":
                            mode = "code"
                            reply = "Switched to code mode (Kiro CLI)"
                        elif user_text == "/help":
                            reply = (
                                "Available commands:\n"
                                "/chat - Switch to Bedrock chat mode\n"
                                "/code - Switch to Kiro CLI mode\n"
                                "/help - Show this help message"
                            )
                        else:
                            if mode == "chat":
                                reply = invoke_bedrock(bedrock, user_text)
                            else:
                                reply = invoke_kiro(user_text)

                        send_message(api_key, chat_id, reply)
                        print(f"Sent: {reply[:100]}...")

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
