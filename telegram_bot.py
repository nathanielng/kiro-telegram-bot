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

def load_chat_history(chat_id):
    """Load chat history from JSON file for specific user."""
    history_file = Path(__file__).parent / "log" / f"chat_history_{chat_id}.json"
    if history_file.exists():
        try:
            return json.loads(history_file.read_text())
        except Exception as e:
            logging.warning(f"Failed to load chat history for {chat_id}: {e}")
    return []


def save_chat_history(history, chat_id):
    """Save chat history to JSON file for specific user."""
    try:
        history_file = Path(__file__).parent / "log" / f"chat_history_{chat_id}.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(history, indent=2))
    except Exception as e:
        logging.error(f"Failed to save chat history for {chat_id}: {e}")


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


def check_file_security(file_path):
    """Check HTML/CSS/JS files for common security issues.
    
    Returns (passed: bool, issues: list of strings).
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    
    # Only check web files
    if ext not in ['.html', '.css', '.js']:
        return True, []
    
    try:
        content = path.read_text(encoding='utf-8', errors='ignore').lower()
    except Exception as e:
        logging.error(f"Failed to read {file_path} for security check: {e}")
        return False, [f"Failed to read file: {e}"]
    
    issues = []
    
    # Check for dangerous patterns
    dangerous_patterns = [
        (r'<script[^>]*src=["\']https?://(?!cdn\.)', 'External script from untrusted domain'),
        (r'eval\s*\(', 'Use of eval() function'),
        (r'document\.write\s*\(', 'Use of document.write()'),
        (r'innerhtml\s*=', 'Direct innerHTML assignment (XSS risk)'),
        (r'on\w+\s*=\s*["\']', 'Inline event handlers'),
        (r'javascript:', 'javascript: protocol in URLs'),
        (r'<iframe', 'iframe element detected'),
        (r'fetch\s*\(["\']https?://', 'External API calls'),
        (r'xmlhttprequest', 'XMLHttpRequest usage'),
    ]
    
    for pattern, description in dangerous_patterns:
        if re.search(pattern, content):
            issues.append(description)
    
    # Check for suspicious keywords
    suspicious_keywords = ['crypto', 'bitcoin', 'wallet', 'password', 'credential']
    for keyword in suspicious_keywords:
        if keyword in content and 'placeholder' not in content[max(0, content.find(keyword)-20):content.find(keyword)+20]:
            issues.append(f"Suspicious keyword: {keyword}")
    
    passed = len(issues) == 0
    return passed, issues


def quarantine_file(file_path, kiro_output_dir):
    """Move file to quarantine folder."""
    try:
        quarantine_dir = Path(kiro_output_dir) / ".quarantine"
        quarantine_dir.mkdir(exist_ok=True)
        
        src = Path(file_path)
        dst = quarantine_dir / src.name
        
        # Handle duplicate names
        counter = 1
        while dst.exists():
            dst = quarantine_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        
        src.rename(dst)
        logging.info(f"Quarantined {src.name} to {dst}")
        return str(dst)
    except Exception as e:
        logging.error(f"Failed to quarantine {file_path}: {e}")
        return None


def sync_to_s3(kiro_output_dir, s3_bucket, s3_prefix, region):
    """Force sync output directory to S3 bucket."""
    if not kiro_output_dir or not s3_bucket:
        return
    
    try:
        # Build S3 destination path
        s3_path = f"s3://{s3_bucket}/{s3_prefix}/" if s3_prefix else f"s3://{s3_bucket}/"
        
        # Use AWS CLI sync command for efficient upload, excluding quarantine folder
        subprocess.run(
            ["aws", "s3", "sync", kiro_output_dir, s3_path, 
             "--exclude", ".quarantine/*", "--region", region],
            capture_output=True,
            timeout=30
        )
        logging.info(f"Synced {kiro_output_dir} to {s3_path}")
    except Exception as e:
        logging.error(f"Failed to sync to S3: {e}")


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
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()  # Optional now
    region = os.environ.get('AWS_REGION', 'us-west-2')
    kiro_output_dir = os.environ.get('KIRO_OUTPUT_DIR', '').strip()
    cloudfront_base_url = os.environ.get('CLOUDFRONT_BASE_URL', '').rstrip('/')
    s3_prefix = os.environ.get('S3_PREFIX', '').strip('/')
    s3_bucket = os.environ.get('S3_BUCKET_NAME', '').strip()
    chat_history_size = int(os.environ.get('CHAT_HISTORY_SIZE', '10'))
    guardrail_id = os.environ.get('BEDROCK_GUARDRAIL_ID', '').strip()
    guardrail_version = os.environ.get('BEDROCK_GUARDRAIL_VERSION', 'DRAFT').strip()

    logging.info("Environment variables loaded:")
    logging.info(f"  TELEGRAM_API_KEY: {redact_key(api_key)}")
    logging.info(f"  TELEGRAM_CHAT_ID: {chat_id if chat_id else 'Not set (multi-user mode)'}")
    logging.info(f"  AWS_REGION: {region}")
    logging.info(f"  KIRO_OUTPUT_DIR: {kiro_output_dir}")
    logging.info(f"  CLOUDFRONT_BASE_URL: {cloudfront_base_url}")
    logging.info(f"  S3_PREFIX: {s3_prefix}")
    logging.info(f"  S3_BUCKET_NAME: {s3_bucket}")
    logging.info(f"  CHAT_HISTORY_SIZE: {chat_history_size}")
    logging.info(f"  BEDROCK_GUARDRAIL_ID: {guardrail_id if guardrail_id else 'Not configured'}")

    if not api_key:
        print("Error: TELEGRAM_API_KEY must be set")
        sys.exit(1)

    return api_key, chat_id, region, kiro_output_dir, cloudfront_base_url, s3_prefix, s3_bucket, chat_history_size, guardrail_id, guardrail_version


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
    
    # Use relative path to avoid exposing username
    relative_dir = Path(kiro_output_dir).name if '/' in kiro_output_dir else kiro_output_dir
    
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

**Output Directory:** `{relative_dir}`
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
    full_text = '\n'.join(cleaned_lines)
    
    # Truncate middle if output is more than 2 pages (>8000 chars)
    if len(full_text) > 8000:
        # Save full output to file
        if kiro_output_dir and cloudfront_base_url:
            try:
                output_file = Path(kiro_output_dir) / "kiro-full-output.txt"
                output_file.write_text(full_text, encoding='utf-8')
                
                # Build CloudFront URL
                if s3_prefix:
                    full_output_url = f"{cloudfront_base_url}/{s3_prefix}/kiro-full-output.txt"
                else:
                    full_output_url = f"{cloudfront_base_url}/kiro-full-output.txt"
            except Exception as e:
                logging.error(f"Failed to save full output: {e}")
        
        # Keep first 3000 and last 3000 chars, remove middle
        head = full_text[:3000]
        tail = full_text[-3000:]
        omitted_chars = len(full_text) - 6000
        return f"{head}\n\n... ({omitted_chars} characters omitted) ...\n\n{tail}".strip(), full_output_url
    
    return full_text.strip(), full_output_url


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


def check_guardrail(bedrock, text, guardrail_id, guardrail_version):
    """Check text against Bedrock Guardrail.
    
    Returns (passed: bool, message: str).
    """
    try:
        response = bedrock.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,
            source='INPUT',
            content=[{
                'text': {'text': text}
            }]
        )
        
        action = response.get('action')
        if action == 'GUARDRAIL_INTERVENED':
            return False, "🛡️ Your input was blocked by the content guardrail."
        return True, ""
    except Exception as e:
        logging.error(f"Guardrail check failed: {e}")
        return True, ""  # Fail open on errors


def is_sensitive_file_access(prompt):
    """Check if prompt attempts to access sensitive files like .env"""
    dangerous_patterns = [
        r'!cat\s+.*\.env',
        r'!cat\s+~/\.env',
        r'!cat\s+\.\./\.env',
        r'!less\s+.*\.env',
        r'!more\s+.*\.env',
        r'!head\s+.*\.env',
        r'!tail\s+.*\.env',
        r'!grep\s+.*\.env',
        r'!vim\s+.*\.env',
        r'!nano\s+.*\.env',
        r'!open\s+.*\.env',
    ]
    
    prompt_lower = prompt.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, prompt_lower):
            return True
    return False


def invoke_kiro(prompt, kiro_output_dir, cloudfront_base_url, s3_prefix, history_prefix=""):
    """Run kiro-cli and detect any files it creates in kiro_output_dir.

    Returns (output_text, list_of_(filename, url) tuples, full_output_url or None).
    """
    # Block sensitive file access attempts
    if is_sensitive_file_access(prompt):
        return "⛔ Access to .env files is blocked for security reasons.", [], None, []
    
    before = snapshot_dir(kiro_output_dir)
    
    # Prepend history if provided
    full_prompt = history_prefix + prompt if history_prefix else prompt

    try:
        result = subprocess.run(
            ["kiro-cli", "chat", "--no-interactive", "--trust-tools=fs_read,fs_write", full_prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result.stdout if result.stdout else result.stderr
        # Clean the output for Telegram
        output, full_output_url = clean_kiro_output(output, kiro_output_dir, cloudfront_base_url, s3_prefix)
        
        # Log cleaned output
        logging.info(f"Kiro CLI output:\n{output}")
    except Exception as e:
        return f"Error: {e}", [], None, []

    after = snapshot_dir(kiro_output_dir)
    changed = new_files_since(before, after)

    # Security check for web files
    security_results = []
    quarantined = []
    
    for file_path in sorted(changed):
        passed, issues = check_file_security(file_path)
        file_name = Path(file_path).name
        
        if not passed:
            # Quarantine the file
            quarantine_path = quarantine_file(file_path, kiro_output_dir)
            if quarantine_path:
                quarantined.append(file_name)
                security_results.append((file_name, False, issues))
                logging.warning(f"Security check failed for {file_name}: {', '.join(issues)}")
        else:
            security_results.append((file_name, True, []))

    # Build URLs only for non-quarantined files
    urls = []
    if cloudfront_base_url:
        for file_path in sorted(changed):
            file_name = Path(file_path).name
            if file_name not in quarantined:
                url = build_url(file_path, kiro_output_dir, cloudfront_base_url, s3_prefix)
                if url:
                    urls.append((file_name, url))

    return output, urls, full_output_url, security_results


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    api_key, chat_id, region, kiro_output_dir, cloudfront_base_url, s3_prefix, s3_bucket, chat_history_size, guardrail_id, guardrail_version = get_config()

    # Ensure output directory exists and update Kiro's steering file
    ensure_output_dir(kiro_output_dir)
    generate_kiro_context(kiro_output_dir, cloudfront_base_url, s3_prefix)

    bedrock = boto3.client('bedrock-runtime', region_name=region)
    offset = 0

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

    if chat_id:
        print(f"Bot started. Monitoring chat {chat_id} (single-user mode)")
    else:
        print(f"Bot started. Accepting messages from any user (multi-user mode)")
    
    # Track state per user
    user_states = {}  # {chat_id: {"mode": "chat", "awaiting_model": False, "history": []}}

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
                        incoming_chat_id = str(update["message"]["chat"]["id"])
                        user_text = update["message"]["text"]
                        
                        # If TELEGRAM_CHAT_ID is set, only respond to that chat
                        if chat_id and incoming_chat_id != chat_id:
                            continue
                        
                        print(f"Received from {incoming_chat_id}: {user_text}")
                        
                        # Initialize user state if new
                        if incoming_chat_id not in user_states:
                            user_states[incoming_chat_id] = {
                                "mode": "chat",
                                "awaiting_model": False,
                                "history": load_chat_history(incoming_chat_id)
                            }
                        
                        state = user_states[incoming_chat_id]

                        # Handle model selection if awaiting
                        if state["awaiting_model"]:
                            if user_text in model_names:
                                reply, new_files, full_url, security_results = invoke_kiro(
                                    f"/model {user_text}",
                                    kiro_output_dir,
                                    cloudfront_base_url,
                                    s3_prefix,
                                )
                                send_message(api_key, incoming_chat_id, reply)
                                if full_url:
                                    send_message(api_key, incoming_chat_id, f"📄 Full output: {full_url}")
                                
                                # Show security results
                                if security_results:
                                    for filename, passed, issues in security_results:
                                        if passed:
                                            send_message(api_key, incoming_chat_id, f"✅ Security check passed: {filename}")
                                        else:
                                            send_message(api_key, incoming_chat_id, f"❌ Security check failed: {filename}\n⚠️ Issues: {', '.join(issues)}\n🔒 File quarantined")
                                
                                # Force sync to S3
                                sync_to_s3(kiro_output_dir, s3_bucket, s3_prefix, region)
                                
                                state["awaiting_model"] = False
                            else:
                                send_message(api_key, incoming_chat_id, f"Invalid model: {user_text}. Please select from the list.")
                            continue

                        # Check if it's a Kiro CLI command (exact match or starts with pattern)
                        is_kiro_cmd = any(user_text == cmd or user_text.startswith(cmd + " ") 
                                         for cmd in kiro_commands)

                        if user_text == "/chat":
                            state["mode"] = "chat"
                            reply = "Switched to chat mode (Bedrock)"
                            send_message(api_key, incoming_chat_id, reply)

                        elif user_text == "/code":
                            state["mode"] = "code"
                            reply = "Switched to code mode (Kiro CLI)"
                            send_message(api_key, incoming_chat_id, reply)

                        elif user_text == "/status":
                            reply = check_monitor_status()
                            send_message(api_key, incoming_chat_id, reply)

                        elif user_text == "/clear":
                            # Archive current history with timestamp
                            if state["history"]:
                                timestamp = time.strftime("%Y%m%d_%H%M%S")
                                archive_file = Path(__file__).parent / "log" / f"chat_history_{incoming_chat_id}_{timestamp}.json"
                                archive_file.parent.mkdir(parents=True, exist_ok=True)
                                archive_file.write_text(json.dumps(state["history"], indent=2))
                                logging.info(f"Archived chat history for {incoming_chat_id} to {archive_file.name}")
                            
                            # Clear and save empty history
                            state["history"] = []
                            save_chat_history(state["history"], incoming_chat_id)
                            send_message(api_key, incoming_chat_id, "✅ Chat history cleared and archived")

                        elif user_text == "/model":
                            lines = ["Select model (type to search):"]
                            for name, credits, desc in models:
                                lines.append(f"  {name:<23} {credits:<18} {desc}")
                            send_message(api_key, incoming_chat_id, "\n".join(lines))
                            state["awaiting_model"] = True

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
                            send_message(api_key, incoming_chat_id, reply)

                        elif is_kiro_cmd:
                            # Pass Kiro commands directly to Kiro CLI (no history for commands)
                            reply, new_files, full_url, security_results = invoke_kiro(
                                user_text,
                                kiro_output_dir,
                                cloudfront_base_url,
                                s3_prefix,
                            )
                            send_message(api_key, incoming_chat_id, reply)
                            
                            if full_url:
                                send_message(api_key, incoming_chat_id, f"📄 Full output: {full_url}")

                            # Show security results
                            if security_results:
                                for filename, passed, issues in security_results:
                                    if passed:
                                        send_message(api_key, incoming_chat_id, f"✅ Security check passed: {filename}")
                                    else:
                                        send_message(api_key, incoming_chat_id, f"❌ Security check failed: {filename}\n⚠️ Issues: {', '.join(issues)}\n🔒 File quarantined")

                            if new_files:
                                lines = ["Files created by Kiro:"]
                                for filename, url in new_files:
                                    lines.append(f"  {filename}: {url}")
                                send_message(api_key, incoming_chat_id, "\n".join(lines))
                            
                            # Force sync to S3
                            sync_to_s3(kiro_output_dir, s3_bucket, s3_prefix, region)

                        else:
                            # Check guardrail if configured
                            if guardrail_id:
                                passed, msg = check_guardrail(bedrock, user_text, guardrail_id, guardrail_version)
                                if not passed:
                                    send_message(api_key, incoming_chat_id, msg)
                                    continue
                            
                            if state["mode"] == "chat":
                                reply = invoke_bedrock(bedrock, user_text)
                                send_message(api_key, incoming_chat_id, reply)
                                
                                # Add to chat history
                                state["history"] = add_to_history(state["history"], "user", user_text, chat_history_size)
                                state["history"] = add_to_history(state["history"], "assistant", reply, chat_history_size)
                                save_chat_history(state["history"], incoming_chat_id)
                            else:
                                # Format history for Kiro
                                history_prefix = format_history_for_kiro(state["history"])
                                
                                reply, new_files, full_url, security_results = invoke_kiro(
                                    user_text,
                                    kiro_output_dir,
                                    cloudfront_base_url,
                                    s3_prefix,
                                    history_prefix,
                                )
                                send_message(api_key, incoming_chat_id, reply)
                                
                                if full_url:
                                    send_message(api_key, incoming_chat_id, f"📄 Full output: {full_url}")

                                # Show security results
                                if security_results:
                                    for filename, passed, issues in security_results:
                                        if passed:
                                            send_message(api_key, incoming_chat_id, f"✅ Security check passed: {filename}")
                                        else:
                                            send_message(api_key, incoming_chat_id, f"❌ Security check failed: {filename}\n⚠️ Issues: {', '.join(issues)}\n🔒 File quarantined")

                                if new_files:
                                    lines = ["Files created by Kiro:"]
                                    for filename, url in new_files:
                                        lines.append(f"  {filename}: {url}")
                                    send_message(api_key, incoming_chat_id, "\n".join(lines))
                                
                                # Force sync to S3
                                sync_to_s3(kiro_output_dir, s3_bucket, s3_prefix, region)
                                
                                # Add to chat history
                                state["history"] = add_to_history(state["history"], "user", user_text, chat_history_size)
                                state["history"] = add_to_history(state["history"], "assistant", reply, chat_history_size)
                                save_chat_history(state["history"], incoming_chat_id)

                        print(f"Sent reply ({state['mode']} mode)")

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
