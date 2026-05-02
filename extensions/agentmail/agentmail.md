# AgentMail Skill

You can send and receive emails using the AgentMail API through the `agentmail-cli.sh` wrapper. Always use the wrapper — never call curl against the AgentMail API directly.

## Environment Variables

- `AGENTMAIL_API_KEY` — your AgentMail API key (required)
- `AGENTMAIL_INBOX` — your default inbox address (optional, for convenience)

## CLI Reference

```
agentmail-cli.sh inboxes                              # List all inboxes
agentmail-cli.sh create-inbox [display_name]           # Create a new inbox
agentmail-cli.sh list <inbox_id>                       # List messages
agentmail-cli.sh read <inbox_id> <message_id>          # Read a message
agentmail-cli.sh send <inbox_id> <to> <subject> <body> # Send an email
agentmail-cli.sh reply <inbox_id> <message_id> <body>  # Reply to a message
agentmail-cli.sh delete <inbox_id> <message_id>        # Delete a message
```

## Rate Limits

| Action | Daily Limit |
|---|---|
| Send / Reply | 20 |
| Delete | 5 |
| Read / List | Unlimited |

All operations are logged to `~/.agentmail-audit/`.

## Usage Patterns

**Check inbox:**
```bash
agentmail-cli.sh list <inbox_id>
```

**Read a specific email:**
```bash
agentmail-cli.sh read <inbox_id> <message_id>
```

**Send an email:**
```bash
agentmail-cli.sh send <inbox_id> 'recipient@example.com' 'Subject line' 'Email body text'
```

**Reply to an email:**
```bash
agentmail-cli.sh reply <inbox_id> <message_id> 'Thanks for your email!'
```

## Guidelines

- Always use `agentmail-cli.sh` — never call the AgentMail API directly
- If a rate limit is hit, inform the user and suggest trying again tomorrow
- Confirm before sending emails to external addresses
- Confirm before deleting any messages
- Never expose the API key in responses
- The inbox ID is the part before `@agentmail.to` in the inbox address
