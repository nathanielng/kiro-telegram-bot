#!/usr/bin/env python3
"""
Telegram Bot with AWS Bedrock Integration and Kiro CLI

Supports two modes:
- /chat: Send prompts to Bedrock (default)
- /code: Send prompts to Kiro CLI
- /help: Show available commands

Requires: TELEGRAM_API_KEY, TELEGRAM_CHAT_ID
Optional:  AWS_REGION, KIRO_OUTPUT_DIR, S3_BUCKET_NAME, S3_PREFIX,
           CLOUDFRONT_BASE_URL, CHAT_HISTORY_SIZE
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import boto3
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv()
        logging.info(f"Loaded configuration from {env_file}")
    else:
        logging.info("No .env file found, using environment variables for configuration")
except ImportError:
    logging.warning("python-dotenv not installed, using environment variables for configuration")

# Path to the Kiro steering file that tells Kiro where to save outputs
KIRO_STEERING_FILE = Path(__file__).parent / ".kiro" / "steering" / "output-config.md"
CHAT_HISTORY_FILE = Path(__file__).parent / "log" / "chat_history.json"


# ---------------------------------------------------------------------------
# Chat history management
# ---------------------------------------------------------------------------

def load_chat_history():
    """Load chat history from JSON file."""
    if CHAT_HISTORY_FILE.exists():
        try:
            return json.loads(CHAT_HISTORY_FILE.read_text())
        except Exception as e:
            logging.warning(f"Failed to load chat history: {e}")
    return []


def save_chat_history(history):
    """Save chat history to JSON file."""
    try:
        CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHAT_HISTORY_FILE.write_text(json.dumps(history, indent=2))
    except Exception as e:
        logging.error(f"Failed to save chat history: {e}")


def add_to_history(history, role, content, max_size):
    """Add a message to history and trim to max_size."""
    history.append({"role": role, "content": content})
    if len(history) > max_size * 2:  # *2 because each exchange is 2 messages
        history = history[-(max_size * 2):]
    return history


def format_history_for_kiro(history):
    """Format chat history as a prefix for Kiro CLI prompts."""
    if not history:
        return ""
    
    lines = ["Here is the recent conversation history:"]
    for msg in history:
        role = "Human" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    lines.append("\nYour instruction:")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def redact_key(value):
    """Redact middle portion of API keys, keeping first 4 and last 4 characters."""
    if not value or len(value) <= 8:
        return value
    return f"{value[:4]}...{value[-4:]}"


def get_config():
    api_key = os.environ.get('TELEGRAM_API_KEY')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    region = os.environ.get('AWS_REGION', 'us-west-2')
    kiro_output_dir = os.environ.get('KIRO_OUTPUT_DIR', '').strip()
    cloudfront_base_url = os.environ.get('CLOUDFRONT_BASE_URL', '').rstrip('/')
    s3_prefix = os.environ.get('S3_PREFIX', '').strip('/')
    chat_history_size = int(os.environ.get('CHAT_HISTORY_SIZE', '10'))

    logging.info("Environment variables loaded:")
    logging.info(f"  TELEGRAM_API_KEY: {redact_key(api_key)}")
    logging.info(f"  TELEGRAM_CHAT_ID: {chat_id}")
    logging.info(f"  AWS_REGION: {region}")
    logging.info(f"  KIRO_OUTPUT_DIR: {kiro_output_dir}")
    logging.info(f"  CLOUDFRONT_BASE_URL: {cloudfront_base_url}")
    logging.info(f"  S3_PREFIX: {s3_prefix}")
    logging.info(f"  CHAT_HISTORY_SIZE: {chat_history_size}")

    if not api_key or not chat_id:
        print("Error: TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set")
        sys.exit(1)

    return api_key, chat_id, region, kiro_output_dir, cloudfront_base_url, s3_prefix, chat_history_size


# ---------------------------------------------------------------------------
# Kiro output directory and context file
# ---------------------------------------------------------------------------

def ensure_output_dir(kiro_output_dir):
    """Create the Kiro output directory if it does not exist."""
    if not kiro_output_dir:
        return
    path = Path(kiro_output_dir)
    path.mkdir(parents=True, exist_ok=True)
    print(f"Kiro output directory: {path.resolve()}")


def generate_kiro_context(kiro_output_dir, cloudfront_base_url="", s3_prefix=""):
    """Write (or overwrite) the Kiro steering file with the current output path.

    The file lives at .kiro/steering/output-config.md and is automatically
    picked up by Kiro CLI on every invocation so it always knows where to
    save generated files.
    """
    if not kiro_output_dir:
        return

    KIRO_STEERING_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Build URL instruction if CloudFront is configured
    url_instruction = ""
    if cloudfront_base_url:
        if s3_prefix:
            url_pattern = f"{cloudfront_base_url}/{s3_prefix}/$FILENAME"
        else:
            url_pattern = f"{cloudfront_base_url}/$FILENAME"
        
        url_instruction = f"""
## File Access URLs

After saving a file, inform the user that it can be accessed at:

**URL Pattern:** `{url_pattern}`

Replace `$FILENAME` with the actual filename (including any subdirectories relative to the output directory).

**Example:**
- If you save `report.html`, the URL is: `{cloudfront_base_url}/{s3_prefix + '/' if s3_prefix else ''}report.html`
- If you save `data/analysis.csv`, the URL is: `{cloudfront_base_url}/{s3_prefix + '/' if s3_prefix else ''}data/analysis.csv`
"""
    
    content = f"""# Kiro CLI Output Configuration

> **Note:** This file is automatically regenerated by `telegram_bot.py` on
> every startup from the `KIRO_OUTPUT_DIR` environment variable. Manual edits
> will be overwritten. To change the output directory, update `KIRO_OUTPUT_DIR`
> in your `.env` file and restart the bot.

## File Output Location

When saving files, outputs, reports, code, or any other generated content,
**always save them to the configured output directory** shown below.

**Output Directory:** `{kiro_output_dir}`
{url_instruction}
## Naming Conventions

- Use lowercase filenames with hyphens as word separators (e.g., `my-report.html`)
- Include a date suffix for time-sensitive outputs (e.g., `summary-2024-01-15.md`)
- Use the appropriate file extension for the content type

## Guidelines

- Save all generated HTML, Markdown, JSON, CSV, and other output files to the
  output directory above.
- Create subdirectories within the output directory when organising related files
  (e.g., `images/`, `data/`, `reports/`).
- Do **not** save temporary or intermediate working files to the output directory.
- After completing a task, confirm which files were saved and their filenames so
  the bot can report the correct URLs.
"""
    KIRO_STEERING_FILE.write_text(content, encoding="utf-8")
    print(f"Kiro context file updated: {KIRO_STEERING_FILE}")


# ---------------------------------------------------------------------------
# File detection helpers
# ---------------------------------------------------------------------------

def snapshot_dir(directory):
    """Return a dict mapping file paths to their modification times."""
    result = {}
    if not directory:
        return result
    base = Path(directory)
    if not base.exists():
        return result
    for f in base.rglob("*"):
        if f.is_file():
            try:
                result[str(f)] = f.stat().st_mtime
            except OSError:
                pass
    return result


def new_files_since(before, after):
    """Return paths that are new or have been modified between two snapshots."""
    changed = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            changed.append(path)
    return changed


def build_url(file_path, kiro_output_dir, cloudfront_base_url, s3_prefix):
    """Build the CloudFront URL for a file that lives inside kiro_output_dir."""
    if not cloudfront_base_url:
        return None
    try:
        rel = Path(file_path).relative_to(kiro_output_dir)
    except ValueError:
        return None
    parts = [cloudfront_base_url]
    if s3_prefix:
        parts.append(s3_prefix)
    parts.append(str(rel))
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    return re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', text)


def clean_kiro_output(text, kiro_output_dir="", cloudfront_base_url="", s3_prefix=""):
    """Clean Kiro CLI output for Telegram display.
    
    Returns (cleaned_text, full_output_url or None).
    """
    # Strip ANSI codes
    text = strip_ansi(text)
    
    # Remove verbose file diff markers (lines starting with background color codes)
    # These are the +/- line numbers with syntax highlighting
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip lines that look like diff output (start with + followed by line number)
        if re.match(r'^\s*\+\s+\d+:', line):
            continue
        # Keep other lines
        cleaned_lines.append(line)
    
    full_output_url = None
    
    # Truncate middle if output is very long (>100 lines)
    if len(cleaned_lines) > 100:
        # Save full output to file
        if kiro_output_dir and cloudfront_base_url:
            try:
                output_file = Path(kiro_output_dir) / "kiro-full-output.txt"
                output_file.write_text('\n'.join(cleaned_lines), encoding='utf-8')
                
                # Build CloudFront URL
                if s3_prefix:
                    full_output_url = f"{cloudfront_base_url}/{s3_prefix}/kiro-full-output.txt"
                else:
                    full_output_url = f"{cloudfront_base_url}/kiro-full-output.txt"
            except Exception as e:
                logging.error(f"Failed to save full output: {e}")
        
        head = cleaned_lines[:40]
        tail = cleaned_lines[-40:]
        omitted = len(cleaned_lines) - 80
        cleaned_lines = head + [f"\n... ({omitted} lines omitted) ...\n"] + tail
    
    return '\n'.join(cleaned_lines).strip(), full_output_url


def paginate_message(text, max_length=4000):
    """Split long messages into chunks that fit Telegram's limit."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def send_message(api_key, chat_id, text):
    """Send message to Telegram, automatically paginating if too long."""
    try:
        chunks = paginate_message(text)
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                # Add page indicator for multi-part messages
                prefix = f"[Part {i+1}/{len(chunks)}]\n\n"
                chunk = prefix + chunk
            
            requests.post(
                f"https://api.telegram.org/bot{api_key}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=10
            )
            # Small delay between chunks to maintain order
            if i < len(chunks) - 1:
                time.sleep(0.5)
    except Exception as e:
        print(f"Failed to send message: {e}")


def check_monitor_status():
    """Check if the folder monitor process is running."""
    pid_file = Path(__file__).parent / "log" / "folder_monitor.pid"
    
    if not pid_file.exists():
        return "❌ Folder monitor is not running\n\nStart it with: ./run_monitor.sh"
    
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is running
        try:
            os.kill(pid, 0)  # Signal 0 checks if process exists
            kiro_output_dir = os.environ.get('KIRO_OUTPUT_DIR', 'kirobot-out')
            return f"✅ Folder monitor is running\n\nPID: {pid}\nWatching: {kiro_output_dir}"
        except OSError:
            return f"❌ Folder monitor is not running\n\nStale PID file found (PID {pid} not active)\nStart it with: ./run_monitor.sh"
    except (ValueError, OSError) as e:
        return f"❌ Error checking monitor status: {e}"


# ---------------------------------------------------------------------------
# Backend invocations
# ---------------------------------------------------------------------------

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


def invoke_kiro(prompt, kiro_output_dir, cloudfront_base_url, s3_prefix, history_prefix=""):
    """Run kiro-cli and detect any files it creates in kiro_output_dir.

    Returns (output_text, list_of_(filename, url) tuples, full_output_url or None).
    """
    before = snapshot_dir(kiro_output_dir)
    
    # Prepend history if provided
    full_prompt = history_prefix + prompt if history_prefix else prompt

    try:
        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", full_prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result.stdout if result.stdout else result.stderr
        # Clean the output for Telegram
        output, full_output_url = clean_kiro_output(output, kiro_output_dir, cloudfront_base_url, s3_prefix)
    except Exception as e:
        return f"Error: {e}", [], None

    after = snapshot_dir(kiro_output_dir)
    changed = new_files_since(before, after)

    urls = []
    if cloudfront_base_url and changed:
        for file_path in sorted(changed):
            url = build_url(file_path, kiro_output_dir, cloudfront_base_url, s3_prefix)
            if url:
                urls.append((Path(file_path).name, url))

    return output, urls, full_output_url


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    api_key, chat_id, region, kiro_output_dir, cloudfront_base_url, s3_prefix, chat_history_size = get_config()

    # Ensure output directory exists and update Kiro's steering file
    ensure_output_dir(kiro_output_dir)
    generate_kiro_context(kiro_output_dir, cloudfront_base_url, s3_prefix)

    bedrock = boto3.client('bedrock-runtime', region_name=region)
    offset = 0
    mode = "chat"
    awaiting_model = False
    
    # Load chat history
    chat_history = load_chat_history()

    # Kiro CLI slash commands that should be passed through
    kiro_commands = {
        "/context show", "/context clear", "/agent list",
        "/prompts list", "/prompts get",
        "/prompts create", "/hooks", "/usage", "/mcp", "/tangents"
    }

    # Available models
    models = [
        ("auto", "1.00x credits", "Models chosen by task for optimal usage and consistent q.."),
        ("claude-opus-4.6", "2.20x credits", "Experimental preview of Claude Opus 4.6"),
        ("claude-opus-4.6-1m", "2.20x credits", "[Internal] Experimental preview of Claude Opus 4.6 1M co.."),
        ("claude-sonnet-4.6", "1.30x credits", "Experimental preview of the latest Claude Sonnet model"),
        ("claude-sonnet-4.6-1m", "1.30x credits", "[Internal] Experimental preview of Claude Sonnet 4.6 1M .."),
        ("claude-opus-4.5", "2.20x credits", "The Claude Opus 4.5 model"),
        ("claude-sonnet-4.5", "1.30x credits", "The Claude Sonnet 4.5 model"),
        ("claude-sonnet-4.5-1m", "1.30x credits", "[Internal] Experimental preview of Claude Sonnet 4.5 1M .."),
        ("claude-sonnet-4", "1.30x credits", "Hybrid reasoning and coding for regular use"),
        ("claude-haiku-4.5", "0.40x credits", "The latest Claude Haiku model"),
        ("deepseek-3.2", "0.25x credits", "Experimental preview of DeepSeek V3.2"),
        ("kimi-k2.5", "0.25x credits", "[Internal] Experimental preview of Kimi K2.5"),
        ("minimax-m2.1", "0.15x credits", "Experimental preview of MiniMax M2.1"),
        ("glm-4.7", "0.15x credits", "[Internal] Experimental preview of GLM 4.7"),
        ("glm-4.7-flash", "0.05x credits", "[Internal] Experimental preview of GLM 4.7 Flash"),
        ("qwen3-coder-next", "0.05x credits", "Experimental preview of Qwen3 Coder Next"),
        ("agi-nova-beta-1m", "0.01x credits", "[Internal] AGI Nova SWE Beta"),
        ("qwen3-coder-480b", "0.01x credits", "[Internal] Experimental preview of the Qwen3 model"),
    ]
    model_names = {m[0] for m in models}

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

                        # Handle model selection if awaiting
                        if awaiting_model:
                            if user_text in model_names:
                                reply, new_files, full_url = invoke_kiro(
                                    f"/model {user_text}",
                                    kiro_output_dir,
                                    cloudfront_base_url,
                                    s3_prefix,
                                )
                                send_message(api_key, chat_id, reply)
                                if full_url:
                                    send_message(api_key, chat_id, f"📄 Full output: {full_url}")
                                awaiting_model = False
                            else:
                                send_message(api_key, chat_id, f"Invalid model: {user_text}. Please select from the list.")
                            continue

                        # Check if it's a Kiro CLI command (exact match or starts with pattern)
                        is_kiro_cmd = any(user_text == cmd or user_text.startswith(cmd + " ") 
                                         for cmd in kiro_commands)

                        if user_text == "/chat":
                            mode = "chat"
                            reply = "Switched to chat mode (Bedrock)"
                            send_message(api_key, chat_id, reply)

                        elif user_text == "/code":
                            mode = "code"
                            reply = "Switched to code mode (Kiro CLI)"
                            send_message(api_key, chat_id, reply)

                        elif user_text == "/status":
                            reply = check_monitor_status()
                            send_message(api_key, chat_id, reply)

                        elif user_text == "/clear":
                            chat_history = []
                            save_chat_history(chat_history)
                            send_message(api_key, chat_id, "✅ Chat history cleared")

                        elif user_text == "/model":
                            lines = ["Select model (type to search):"]
                            for name, credits, desc in models:
                                lines.append(f"  {name:<23} {credits:<18} {desc}")
                            send_message(api_key, chat_id, "\n".join(lines))
                            awaiting_model = True

                        elif user_text == "/help":
                            reply = (
                                "Available commands:\n"
                                "/chat - Switch to Bedrock chat mode\n"
                                "/code - Switch to Kiro CLI mode\n"
                                "/status - Check folder monitor status\n"
                                "/clear - Clear chat history\n"
                                "/help - Show this help message\n\n"
                                "Kiro CLI commands (work in code mode):\n"
                                "/context show, /context clear\n"
                                "/model, /agent list\n"
                                "/prompts list, /prompts get, /prompts create\n"
                                "/hooks, /usage, /mcp, /tangents"
                            )
                            send_message(api_key, chat_id, reply)

                        elif is_kiro_cmd:
                            # Pass Kiro commands directly to Kiro CLI (no history for commands)
                            reply, new_files, full_url = invoke_kiro(
                                user_text,
                                kiro_output_dir,
                                cloudfront_base_url,
                                s3_prefix,
                            )
                            send_message(api_key, chat_id, reply)
                            
                            if full_url:
                                send_message(api_key, chat_id, f"📄 Full output: {full_url}")

                            if new_files:
                                lines = ["Files created by Kiro:"]
                                for filename, url in new_files:
                                    lines.append(f"  {filename}: {url}")
                                send_message(api_key, chat_id, "\n".join(lines))

                        else:
                            if mode == "chat":
                                reply = invoke_bedrock(bedrock, user_text)
                                send_message(api_key, chat_id, reply)
                                
                                # Add to chat history
                                chat_history = add_to_history(chat_history, "user", user_text, chat_history_size)
                                chat_history = add_to_history(chat_history, "assistant", reply, chat_history_size)
                                save_chat_history(chat_history)
                            else:
                                # Format history for Kiro
                                history_prefix = format_history_for_kiro(chat_history)
                                
                                reply, new_files, full_url = invoke_kiro(
                                    user_text,
                                    kiro_output_dir,
                                    cloudfront_base_url,
                                    s3_prefix,
                                    history_prefix,
                                )
                                send_message(api_key, chat_id, reply)
                                
                                if full_url:
                                    send_message(api_key, chat_id, f"📄 Full output: {full_url}")

                                if new_files:
                                    lines = ["Files created by Kiro:"]
                                    for filename, url in new_files:
                                        lines.append(f"  {filename}: {url}")
                                    send_message(api_key, chat_id, "\n".join(lines))
                                
                                # Add to chat history
                                chat_history = add_to_history(chat_history, "user", user_text, chat_history_size)
                                chat_history = add_to_history(chat_history, "assistant", reply, chat_history_size)
                                save_chat_history(chat_history)

                        print(f"Sent reply ({mode} mode)")

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
