# kiro-telegram-bot

Telegram bot with dual modes: chat with AWS Bedrock or execute commands via Kiro CLI.

## Features

- **/chat mode**: Send prompts to AWS Bedrock (Claude Sonnet 4.5)
- **/code mode**: Execute commands through Kiro CLI with interactive prompt support
- **Interactive Kiro CLI**: PTY-based execution that handles mid-execution prompts via Telegram
- **Folder monitoring**: Automatic S3 upload and CloudFront URL sharing for generated files
- **PII redaction**: Optional privacy protection for uploaded files
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

### 3. Set Environment Variables

#### Required Variables

```bash
export TELEGRAM_API_KEY='your_api_key_here'
export TELEGRAM_CHAT_ID='your_chat_id_here'
```

#### Optional Variables

```bash
# AWS Configuration
export AWS_REGION='us-west-2'  # Defaults to us-west-2

# Kiro Output Directory (for folder monitoring)
export KIRO_OUTPUT_DIR='kirobot-out'  # Defaults to kirobot-out

# S3 and CloudFront (for file uploads)
export S3_BUCKET_NAME='your-bucket-name'
export S3_PREFIX='telegram-bot/'  # Optional prefix for S3 keys
export CLOUDFRONT_BASE_URL='https://your-distribution.cloudfront.net'

# PII Redaction
export ENABLE_PII_REDACTION='true'  # Defaults to true
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
tail -f telegram_bot.log
```

### Bot Commands

- `/chat` - Switch to Bedrock chat mode (default)
- `/code` - Switch to Kiro CLI mode
- Any other text - Processed based on current mode

## Project Structure

```
kiro-telegram-bot/
├── telegram_bot.py          # Main bot implementation
├── telegram_bot_init.py     # Initial setup script
├── kiro_interactive.py      # PTY-based interactive Kiro CLI runner
├── folder_monitor.py        # S3 upload and file monitoring
├── run_telegram.sh          # Background execution script
├── run_monitor.sh           # Background folder monitor script
├── setup_autostart.sh       # Auto-start configuration
├── requirements.txt         # Python dependencies
├── pyproject.toml           # UV project configuration
└── README.md                # This file
```

## Troubleshooting

**Bot not responding**: Check that you've sent `/start` to your bot in Telegram

**AWS errors**: Verify AWS credentials with `aws sts get-caller-identity`

**Kiro CLI not found**: Ensure Kiro CLI is installed and in PATH

**Permission denied on run_telegram.sh**: Run `chmod +x run_telegram.sh`
