# Radicale CalDAV Extension

Optional extension that adds calendar management via a local [Radicale](https://radicale.org/) CalDAV server.

## Prerequisites

- Radicale installed and running (`sudo apt install radicale`)
- A calendar collection created (e.g., `http://localhost:5232/pi/calendar.ics/`)

## Setup

1. Copy the CLI wrapper to your project or PATH:

```bash
cp extensions/radicale/radicale-cli.sh ~/kiro-telegram-bot/
chmod +x ~/kiro-telegram-bot/radicale-cli.sh
```

2. Install the Kiro skill:

```bash
cp extensions/radicale/caldav-calendar.md .kiro/skills/
```

3. Optionally set `CALDAV_URL` in `.env` (defaults to `http://localhost:5232/pi/calendar.ics`):

```
CALDAV_URL=http://localhost:5232/your-user/calendar.ics
```

## Security Controls

The CLI wrapper (`radicale-cli.sh`) enforces:

| Control | Limit |
|---|---|
| Creates per day | 10 |
| Deletes per day | 3 |
| Updates per day | 15 |
| Read operations | Unlimited |

All operations are logged to `~/.radicale-audit/`.

## CLI Usage

```
radicale-cli.sh list
radicale-cli.sh get <uid>
radicale-cli.sh create <uid> <summary> <start> <end> [description] [status]
radicale-cli.sh update <uid> <summary> <start> <end> [description] [status]
radicale-cli.sh delete <uid>
```

Times are in UTC format: `YYYYMMDDTHHMMSSZ`.
