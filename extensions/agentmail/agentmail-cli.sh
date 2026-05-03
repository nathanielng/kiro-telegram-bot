#!/bin/bash
# agentmail-cli.sh — Safe AgentMail CLI wrapper
# Enforces rate limits, audit logging, and destructive action blocking.
# The agent calls this instead of raw curl against the AgentMail API.

API_BASE="https://api.agentmail.to/v0"
AUDIT_DIR="${AUDIT_DIR:-$HOME/.agentmail-audit}"
LOG_FILE="${AUDIT_DIR}/email-$(date +%Y%m%d).log"
RATE_FILE="${AUDIT_DIR}/email-rate-$(date +%Y%m%d)"

MAX_SENDS_PER_DAY=20
MAX_DELETES_PER_DAY=5
SENSITIVE_MODE="redact"  # default: redact. Use --block to block entirely.

mkdir -p "$AUDIT_DIR"

# Parse global flags, collect remaining args
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --redact) SENSITIVE_MODE="redact" ;;
    --block)  SENSITIVE_MODE="block" ;;
    *)        ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]}"

if [ -z "$AGENTMAIL_API_KEY" ]; then
  echo "Error: AGENTMAIL_API_KEY environment variable not set."
  exit 1
fi

AUTH="Authorization: Bearer $AGENTMAIL_API_KEY"

log() { echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"; }

# Scan text for patterns that look like leaked secrets.
# In --block mode: exit with error if found.
# In --redact mode: replace matches with [REDACTED] and return cleaned text.
# Usage: cleaned=$(check_sensitive "$text")
check_sensitive() {
  text="$1"
  found=false
  for pattern in \
    'AKIA[0-9A-Z]\{16\}' \
    'sk-[a-zA-Z0-9]\{20,\}' \
    'sk-ant-[a-zA-Z0-9-]\{20,\}' \
    'ghp_[a-zA-Z0-9]\{36\}' \
    'xoxb-[0-9]*-[a-zA-Z0-9]*' \
    'am_us_[a-zA-Z0-9]\{5,\}' \
    'Bearer [a-zA-Z0-9_-]\{20,\}' \
    '-----BEGIN .* PRIVATE KEY-----' \
  ; do
    if echo "$text" | grep -q "$pattern"; then
      found=true
      if [ "$SENSITIVE_MODE" = "block" ]; then
        echo "BLOCKED: Outbound content contains what looks like a secret or API key." >&2
        log "BLOCKED_SENSITIVE pattern=$pattern"
        exit 1
      fi
      text=$(echo "$text" | sed "s/$pattern/[REDACTED]/g")
      log "REDACTED_SENSITIVE pattern=$pattern"
    fi
  done
  if [ "$found" = true ] && [ "$SENSITIVE_MODE" = "redact" ]; then
    echo "⚠️  Sensitive content was redacted before sending." >&2
  fi
  echo "$text"
}

increment_counter() {
  key="$1" max="$2"
  count=0
  [ -f "$RATE_FILE" ] && count=$(grep -c "^${key}$" "$RATE_FILE" 2>/dev/null) || count=0
  if [ "$count" -ge "$max" ]; then
    echo "RATE LIMITED: $key has reached daily limit ($max)."
    log "RATE_LIMITED action=$key count=$count"
    exit 1
  fi
  echo "$key" >> "$RATE_FILE"
}

usage() {
  echo "Usage: agentmail-cli.sh <action> [options]"
  echo ""
  echo "Actions:"
  echo "  inboxes                              List all inboxes"
  echo "  create-inbox [display_name]           Create a new inbox"
  echo "  list <inbox_id>                       List messages in an inbox"
  echo "  read <inbox_id> <message_id>          Read a specific message"
  echo "  send <inbox_id> <to> <subject> <body> Send an email"
  echo "  reply <inbox_id> <message_id> <body>  Reply to a message"
  echo "  delete <inbox_id> <message_id>        Delete a message"
  echo ""
  echo "Rate limits: $MAX_SENDS_PER_DAY sends/day, $MAX_DELETES_PER_DAY deletes/day"
  echo ""
  echo "Flags:"
  echo "  --redact  Redact sensitive content before sending (default)"
  echo "  --block   Block sends containing sensitive content entirely"
  exit 1
}

ACTION="$1"
[ -z "$ACTION" ] && usage
shift

case "$ACTION" in
  inboxes)
    log "LIST_INBOXES"
    curl -s -H "$AUTH" "$API_BASE/inboxes"
    ;;

  create-inbox)
    DISPLAY_NAME="${1:-My Agent}"
    log "CREATE_INBOX display_name=$DISPLAY_NAME"
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"display_name\": \"$DISPLAY_NAME\"}" \
      "$API_BASE/inboxes"
    ;;

  list)
    INBOX_ID="$1"
    [ -z "$INBOX_ID" ] && echo "Error: inbox_id required" && exit 1
    log "LIST_MESSAGES inbox=$INBOX_ID"
    curl -s -H "$AUTH" "$API_BASE/inboxes/$INBOX_ID/messages"
    ;;

  read)
    INBOX_ID="$1"; MSG_ID="$2"
    [ -z "$INBOX_ID" ] || [ -z "$MSG_ID" ] && echo "Error: inbox_id and message_id required" && exit 1
    log "READ inbox=$INBOX_ID message=$MSG_ID"
    curl -s -H "$AUTH" "$API_BASE/inboxes/$INBOX_ID/messages/$MSG_ID"
    ;;

  send)
    INBOX_ID="$1"; TO="$2"; SUBJECT="$3"; BODY="$4"
    [ -z "$INBOX_ID" ] || [ -z "$TO" ] || [ -z "$SUBJECT" ] || [ -z "$BODY" ] && \
      echo "Error: send requires <inbox_id> <to> <subject> <body>" && exit 1
    increment_counter "send" $MAX_SENDS_PER_DAY
    SUBJECT=$(check_sensitive "$SUBJECT")
    BODY=$(check_sensitive "$BODY")
    log "SEND inbox=$INBOX_ID to=$TO subject=$SUBJECT"
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"to\": [\"$TO\"], \"subject\": \"$SUBJECT\", \"text\": \"$BODY\"}" \
      "$API_BASE/inboxes/$INBOX_ID/messages/send"
    ;;

  reply)
    INBOX_ID="$1"; MSG_ID="$2"; BODY="$3"
    [ -z "$INBOX_ID" ] || [ -z "$MSG_ID" ] || [ -z "$BODY" ] && \
      echo "Error: reply requires <inbox_id> <message_id> <body>" && exit 1
    increment_counter "send" $MAX_SENDS_PER_DAY
    BODY=$(check_sensitive "$BODY")
    log "REPLY inbox=$INBOX_ID message=$MSG_ID"
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"text\": \"$BODY\"}" \
      "$API_BASE/inboxes/$INBOX_ID/messages/$MSG_ID/reply"
    ;;

  delete)
    INBOX_ID="$1"; MSG_ID="$2"
    [ -z "$INBOX_ID" ] || [ -z "$MSG_ID" ] && echo "Error: inbox_id and message_id required" && exit 1
    increment_counter "delete" $MAX_DELETES_PER_DAY
    log "DELETE inbox=$INBOX_ID message=$MSG_ID"
    curl -s -X DELETE -H "$AUTH" "$API_BASE/inboxes/$INBOX_ID/messages/$MSG_ID"
    ;;

  *)
    echo "Unknown action: $ACTION"
    usage
    ;;
esac
