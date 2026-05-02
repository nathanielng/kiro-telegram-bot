# AgentMail Extension

Optional extension that adds email capabilities via [AgentMail](https://agentmail.to/) — an email service designed for AI agents with isolated inboxes.

## Prerequisites

- An AgentMail account ([console.agentmail.to](https://console.agentmail.to/))
- An API key from the AgentMail dashboard

## Setup

1. Set your API key in `.env`:

```
AGENTMAIL_API_KEY=am_us_XXXXXXXXXXXX
```

2. Copy the CLI wrapper to your project or PATH:

```bash
cp extensions/agentmail/agentmail-cli.sh ~/kiro-telegram-bot/
chmod +x ~/kiro-telegram-bot/agentmail-cli.sh
```

3. Install the Kiro skill:

```bash
cp extensions/agentmail/agentmail.md .kiro/skills/
```

4. Create an inbox:

```bash
./agentmail-cli.sh create-inbox "My Agent"
```

5. Optionally save the inbox address in `.env`:

```
AGENTMAIL_INBOX=your-inbox-id@agentmail.to
```

## Security Controls

The CLI wrapper (`agentmail-cli.sh`) enforces:

| Control | Limit |
|---|---|
| Sends per day | 20 |
| Deletes per day | 5 |
| Read operations | Unlimited |

All operations are logged to `~/.agentmail-audit/`.

## CLI Usage

```
agentmail-cli.sh inboxes                              # List inboxes
agentmail-cli.sh create-inbox [display_name]           # Create inbox
agentmail-cli.sh list <inbox_id>                       # List messages
agentmail-cli.sh read <inbox_id> <message_id>          # Read message
agentmail-cli.sh send <inbox_id> <to> <subject> <body> # Send email
agentmail-cli.sh reply <inbox_id> <message_id> <body>  # Reply to message
agentmail-cli.sh delete <inbox_id> <message_id>        # Delete message
```
