# kiro-telegram-bot

Telegram bot with dual modes: chat with AWS Bedrock or execute commands via Kiro CLI.

## Features

- **/chat mode**: Send prompts to AWS Bedrock (MiniMax M2.5 by default, configurable via `BEDROCK_MODEL_ID`)
- **/code mode**: Execute commands through Kiro CLI with automatic file operations
- **Multi-user support**: Can serve multiple users simultaneously or restrict to single user
- **Content filtering**: Optional Bedrock Guardrail integration for input validation
- **Security scanning**: Automatic security checks for generated HTML/CSS/JS files with quarantine
- **Sensitive file protection**: Blocks attempts to access .env files via shell commands
- **Chat history**: Tracks last 10 conversation exchanges for context (per user)
- **Folder monitoring**: Automatic S3 upload and CloudFront URL sharing for generated files
- **Output truncation**: Long outputs are automatically truncated with full version saved to S3
- **PII redaction**: Optional privacy protection for uploaded files and steering files
- **Auto-sync**: Files are immediately synced to S3 after each Kiro command
- **Kiro skills**: Bundled skills for cheatsheets, email drafting, presentations, and matrix visualizations
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

### 3. Configure Environment

Copy the sample environment file and fill in your values:

```bash
cp .env.sample .env
```

Edit `.env` with your settings (see Configuration below).

## Configuration

### 1. Create Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow prompts
3. Save the API key provided (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Chat ID (Optional)

For single-user mode, you can restrict the bot to only respond to your chat:

```bash
export TELEGRAM_API_KEY='your_api_key_here'
uv run telegram_bot_init.py
```

This will output your chat ID. If you set `TELEGRAM_CHAT_ID`, the bot will only respond to that specific chat. If you leave it unset, the bot will respond to any user who messages it (multi-user mode).

### 3. (Optional) Create Bedrock Guardrail

To enable content filtering for user inputs:

```bash
export AWS_REGION='ap-southeast-1'  # Optional, defaults to ap-southeast-1
uv run create_guardrail.py
```

This creates a guardrail with filters for sexual content, violence, hate speech, insults, misconduct, and prompt attacks. The guardrail ID is automatically saved to your `.env` file.

### 4. Environment Variables

All variables can be set in `.env` (see `.env.sample`) or exported in your shell.

#### Required

| Variable | Description |
|---|---|
| `TELEGRAM_API_KEY` | Telegram bot token from @BotFather |

#### Optional

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_CHAT_ID` | *(unset)* | Restrict to single user; leave unset for multi-user mode |
| `AWS_REGION` | `ap-southeast-1` | AWS region for Bedrock and S3 |
| `BEDROCK_GUARDRAIL_ID` | *(unset)* | Bedrock Guardrail ID for content filtering |
| `BEDROCK_GUARDRAIL_VERSION` | `DRAFT` | Guardrail version |
| `BEDROCK_MODEL_ID` | `global.minimax.minimax-m2.5` | Bedrock model ID for /chat mode |
| `KIRO_OUTPUT_DIR` | `kirobot-out` | Directory where Kiro saves generated files |
| `S3_BUCKET_NAME` | *(unset)* | S3 bucket for syncing output files |
| `S3_PREFIX` | *(unset)* | Optional prefix for S3 keys |
| `CLOUDFRONT_BASE_URL` | *(unset)* | CloudFront distribution URL (no trailing slash) |
| `ENABLE_PII_REDACTION` | `true` | Redact PII before uploading to S3 |
| `CHAT_HISTORY_SIZE` | `10` | Number of recent exchanges to track per user |

#### Deployment Variables (managed by `deployment/deploy.sh`)

| Variable | Description |
|---|---|
| `DEPLOY_S3_BUCKET_NAME` | S3 bucket name for deployment |
| `DEPLOY_STACK_NAME` | CloudFormation stack name (default: `kiro-static-site`) |
| `DEPLOY_CLOUDFRONT_DISTRIBUTION_ID` | Auto-populated after deployment |
| `DEPLOY_CLOUDFRONT_URL` | Auto-populated after deployment |

## Usage

### Run Interactively

```bash
uv run telegram_bot.py
```

### Run in Background

```bash
./run_telegram.sh
```

> **Note:** `run_telegram.sh` requires both `TELEGRAM_API_KEY` and `TELEGRAM_CHAT_ID` to be set. For multi-user mode, run the bot directly with `uv run telegram_bot.py` instead.

View logs:
```bash
tail -f log/telegram_bot.log
```

### Bot Commands

| Command | Description |
|---|---|
| `/chat` | Switch to Bedrock chat mode |
| `/code` | Switch to Kiro CLI mode (default) |
| `/clear` | Clear and archive chat history |
| `/model` | Select Kiro CLI model |
| `/skills` | List available Kiro skills |
| `/sync` | Force sync output directory to S3 |
| `/status` | Check folder monitor status |
| `/ping` | Check bot status, current mode, and chat ID |
| `/history on\|off` | Toggle chat history recording |
| `/bookmark` | Save and list bookmarks (`add`, `list`, `help`) |
| `/info` | Save and list info notes (`add`, `list`, `help`) |
| `/help` | Show available commands |
| `!ls` | List contents of the output directory |

Kiro CLI commands are passed through in code mode: `/context show`, `/context clear`, `/agent list`, `/prompts list`, `/prompts get`, `/prompts create`, `/hooks`, `/usage`, `/mcp`.

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

## Deployment

The `deployment/` directory contains scripts to set up an S3 bucket and CloudFront distribution for serving generated files.

### Deploy S3 + CloudFront

```bash
export DEPLOY_S3_BUCKET_NAME='your-bucket-name'
./deployment/deploy.sh
```

This will:
1. Create the S3 bucket if it doesn't exist
2. Sync static files to S3
3. Deploy a CloudFormation stack with a CloudFront distribution and S3 OAC
4. Save the CloudFront distribution ID and URL back to `.env`

Use `-y` to auto-approve prompts:

```bash
./deployment/deploy.sh -y
```

The CloudFormation template (`deployment/cloudfront-s3.yaml`) creates:
- A CloudFront distribution with S3 origin (OAC, no caching)
- An S3 bucket policy granting CloudFront access

## Kiro Skills

Bundled skills in `.kiro/skills/`:

| Skill | Description |
|---|---|
| `cheatsheet-generator` | Generates cheatsheets |
| `email_assistant` | Drafts emails using sample data from `data/email/` |
| `revealjs-presentation` | Creates reveal.js presentations |
| `2x2-matrix-generator` | Creates 2×2 matrix visualizations |
| `pdf-generation` | Generates PDF documents using reportlab |
| `pptx-generation` | Generates PowerPoint presentations using python-pptx |

## Extensions

Optional extensions in `extensions/`. These are not required for the core Telegram bot — install only what you need.

### AgentMail (`extensions/agentmail/`)

Email capabilities via [AgentMail](https://agentmail.to/) with isolated agent inboxes. Includes a CLI wrapper with:
- Rate limits (20 sends/day, 5 deletes/day)
- Sensitive content scanning (API keys, tokens, private keys)
- Two modes: `--redact` (default, replaces secrets with `[REDACTED]`) or `--block` (rejects the send entirely)
- Audit logging to `~/.agentmail-audit/`

See [`extensions/agentmail/README.md`](extensions/agentmail/README.md) for setup.

### Radicale CalDAV (`extensions/radicale/`)

Calendar management via a local [Radicale](https://radicale.org/) CalDAV server. Includes a CLI wrapper with:
- Rate limits (10 creates/day, 3 deletes/day, 15 updates/day)
- Audit logging to `~/.radicale-audit/`

See [`extensions/radicale/README.md`](extensions/radicale/README.md) for setup.

## Project Structure

```
kiro-telegram-bot/
├── telegram_bot.py          # Main bot implementation
├── telegram_bot_init.py     # Initial setup script (discover chat ID)
├── create_guardrail.py      # Bedrock Guardrail setup script
├── kiro_interactive.py      # PTY-based interactive Kiro CLI runner
├── folder_monitor.py        # S3 upload and file monitoring
├── run_telegram.sh          # Background execution script
├── run_monitor.sh           # Background folder monitor script
├── setup_autostart.sh       # Auto-start configuration (systemd/launchd/cron)
├── sync_db.py               # Cron script: JSON → SQLite, optional DynamoDB sync
├── setup_db.py              # Initialize SQLite and optionally create DynamoDB tables
├── .env.sample              # Sample environment configuration
├── .kiroignore              # Files to exclude from Kiro context
├── requirements.txt         # Python dependencies (pip)
├── pyproject.toml           # UV project configuration
├── deployment/
│   ├── deploy.sh            # S3 + CloudFront deployment script
│   └── cloudfront-s3.yaml   # CloudFormation template
├── extensions/
│   ├── agentmail/           # Optional AgentMail email extension
│   └── radicale/            # Optional CalDAV calendar extension
├── data/
│   └── email/               # Sample email files for email_assistant skill
├── .kiro/
│   ├── steering/
│   │   └── output-config.md # Auto-generated Kiro output configuration
│   └── skills/              # Kiro skill definitions
└── README.md                # This file
```

## Troubleshooting

**Bot not responding**: Check that you've sent `/start` to your bot in Telegram

**AWS errors**: Verify AWS credentials with `aws sts get-caller-identity`

**Kiro CLI not found**: Ensure Kiro CLI is installed and in PATH

**Permission denied on run_telegram.sh**: Run `chmod +x run_telegram.sh`

**Dependencies missing with `uv sync`**: The `pyproject.toml` only declares `boto3` and `requests`. If you need `watchdog` and `python-dotenv` (required by `folder_monitor.py` and `.env` loading), install them separately or use `pip install -r requirements.txt`.
