# kiro-telegram-bot

Telegram bot with dual modes: chat with AWS Bedrock or execute commands via Kiro CLI.

## Features

- **/chat mode**: Send prompts to AWS Bedrock (Claude Sonnet 4.5)
- **/code mode**: Execute commands through Kiro CLI with automatic file operations
- **Content filtering**: Optional Bedrock Guardrail integration for input validation
- **Security scanning**: Automatic security checks for generated HTML/CSS/JS files with quarantine
- **Sensitive file protection**: Blocks attempts to access .env files via shell commands
- **Chat history**: Tracks last 10 conversation exchanges for context
- **Folder monitoring**: Automatic S3 upload and CloudFront URL sharing for generated files
- **Output truncation**: Long outputs are automatically truncated with full version saved to S3
- **PII redaction**: Optional privacy protection for uploaded files and steering files
- **Auto-sync**: Files are immediately synced to S3 after each Kiro command
- Long-polling for reliable message delivery
- Background execution with logging
- Auto-start on system boot (optional)

## Prerequisites

- Python 3.8+
- [UV](https://docs.astral.sh/uv/) package manager
- [Kiro CLI](https://github.com/aws/kiro-cli) installed
- AWS credentials configured (for Bedrock access)
- Telegram Bot API key

## Installation

### 1. Install UV

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and Setup

```bash
git clone <repository-url>
cd kiro-telegram-bot
uv sync
```

## Configuration

### 1. Create Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow prompts
3. Save the API key provided (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Chat ID

```bash
export TELEGRAM_API_KEY='your_api_key_here'
uv run telegram_bot_init.py
```

This will output your chat ID. Save it for the next step.

### 3. (Optional) Create Bedrock Guardrail

To enable content filtering for user inputs:

```bash
export AWS_REGION='us-west-2'  # Optional, defaults to us-west-2
uv run create_guardrail.py
```

This creates a guardrail with filters for sexual content, violence, hate speech, insults, misconduct, and prompt attacks. The guardrail ID is automatically saved to your `.env` file.

### 4. Set Environment Variables

#### Required Variables

```bash
export TELEGRAM_API_KEY='your_api_key_here'
export TELEGRAM_CHAT_ID='your_chat_id_here'
```

#### Optional Variables

```bash
# AWS Configuration
export AWS_REGION='us-west-2'  # Defaults to us-west-2

# Bedrock Guardrail (optional content filtering)
export BEDROCK_GUARDRAIL_ID='your-guardrail-id'  # Optional
export BEDROCK_GUARDRAIL_VERSION='DRAFT'  # Defaults to DRAFT

# Kiro Output Directory (for folder monitoring)
export KIRO_OUTPUT_DIR='kirobot-out'  # Defaults to kirobot-out

# S3 and CloudFront (for file uploads)
export S3_BUCKET_NAME='your-bucket-name'
export S3_PREFIX='telegram-bot/'  # Optional prefix for S3 keys
export CLOUDFRONT_BASE_URL='https://your-distribution.cloudfront.net'

# PII Redaction
export ENABLE_PII_REDACTION='true'  # Defaults to true

# Chat History
export CHAT_HISTORY_SIZE='10'  # Number of recent exchanges to track (default: 10)
```

Add these to your `~/.bashrc` or `~/.zshrc` to persist.

## Usage

### Run Interactively

```bash
uv run telegram_bot.py
```

### Run in Background

```bash
./run_telegram.sh
```

View logs:
```bash
tail -f log/telegram_bot.log
```

### Bot Commands

- `/chat` - Switch to Bedrock chat mode (default)
- `/code` - Switch to Kiro CLI mode
- `/status` - Check folder monitor status
- `/clear` - Clear chat history
- `/model` - Select Kiro CLI model
- `/help` - Show available commands
- Any other text - Processed based on current mode

### Security Features

**Content Filtering (Guardrail):**
- If configured, all user inputs are checked against Bedrock Guardrail
- Blocks inappropriate content (sexual, violence, hate speech, insults, misconduct, prompt attacks)
- Shows "🛡️ Your input was blocked by the content guardrail." message when triggered

**File Security Scanning:**
- Automatically scans generated HTML/CSS/JS files for security issues
- Checks for: external scripts, eval(), XSS vulnerabilities, suspicious keywords
- Quarantines unsafe files to `.quarantine/` folder (excluded from S3 sync)
- Shows ✅ for safe files, ❌ for quarantined files with issue details

**Sensitive File Protection:**
- Blocks shell commands attempting to access .env files
- Prevents: `!cat .env`, `!cat ~/.env`, `!cat ../.env` and similar commands
- Returns "⛔ Access to .env files is blocked for security reasons."

### Example Usage

#### Basic Commands

```
/code
Create a html css javascript todo application
```

```
/clear
```

#### Sample Prompts for Code Mode

**Todo Application:**
```
Create a html css javascript todo application
```

**Side-scrolling Game:**
```
Create a html css javascript side scrolling shooting game with scoring
```

**Data Visualization:**
```
Create a dashboard with charts showing sample sales data
```

**API Integration:**
```
Create a weather app that fetches data from a public API
```

#### Workflow Example

1. Switch to code mode: `/code`
2. Give Kiro a task: `Create a html css javascript todo application`
3. Kiro creates the file and uploads to S3
4. Bot sends you the CloudFront URL to view the app
5. Continue the conversation: `Add a dark mode toggle`
6. Clear history when starting a new project: `/clear`

## Project Structure

```
kiro-telegram-bot/
├── telegram_bot.py          # Main bot implementation
├── telegram_bot_init.py     # Initial setup script
├── create_guardrail.py      # Bedrock Guardrail setup script
├── kiro_interactive.py      # PTY-based interactive Kiro CLI runner
├── folder_monitor.py        # S3 upload and file monitoring
├── run_telegram.sh          # Background execution script
├── run_monitor.sh           # Background folder monitor script
├── setup_autostart.sh       # Auto-start configuration
├── .kiroignore              # Files to exclude from Kiro context
├── requirements.txt         # Python dependencies
├── pyproject.toml           # UV project configuration
└── README.md                # This file
```

## Troubleshooting

**Bot not responding**: Check that you've sent `/start` to your bot in Telegram

**AWS errors**: Verify AWS credentials with `aws sts get-caller-identity`

**Kiro CLI not found**: Ensure Kiro CLI is installed and in PATH

**Permission denied on run_telegram.sh**: Run `chmod +x run_telegram.sh`
