#!/bin/bash
# radicale-cli.sh — Safe CalDAV CLI wrapper for Radicale
# Enforces rate limits, audit logging, and destructive action blocking.
# The agent calls this instead of raw curl against Radicale.

CALDAV_URL="${CALDAV_URL:-http://localhost:5232/user/calendar.ics}"
AUDIT_DIR="${AUDIT_DIR:-$HOME/.radicale-audit}"
LOG_FILE="${AUDIT_DIR}/calendar-$(date +%Y%m%d).log"
RATE_FILE="${AUDIT_DIR}/calendar-rate-$(date +%Y%m%d)"

MAX_CREATES_PER_DAY=10
MAX_DELETES_PER_DAY=3
MAX_UPDATES_PER_DAY=15

mkdir -p "$AUDIT_DIR"

log() { echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"; }

# Sanitize text for iCalendar values (RFC 5545)
ical_escape() {
  echo "$1" | sed 's/\\/\\\\/g; s/;/\\;/g; s/,/\\,/g' | tr '\n' ' '
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
  echo "Usage: radicale-cli.sh <action> [options]"
  echo ""
  echo "Actions:"
  echo "  list                          List all events"
  echo "  get <uid>                     Get a specific event"
  echo "  create <uid> <summary> <start> <end> [description] [status]"
  echo "                                Create an event (times in YYYYMMDDTHHMMSSZ)"
  echo "  update <uid> <summary> <start> <end> [description] [status]"
  echo "                                Update an event"
  echo "  delete <uid>                  Delete an event"
  echo ""
  echo "Examples:"
  echo "  radicale-cli.sh list"
  echo "  radicale-cli.sh create meeting-004 'Team Lunch' 20260503T040000Z 20260503T050000Z 'Lunch at cafe' CONFIRMED"
  echo "  radicale-cli.sh delete meeting-004"
  exit 1
}

ACTION="$1"
[ -z "$ACTION" ] && usage
shift

case "$ACTION" in
  list)
    log "LIST"
    curl -s "$CALDAV_URL/" | grep -E "^(SUMMARY|DTSTART|DTEND|UID|STATUS|DESCRIPTION):" | sed 's/\r//'
    ;;

  get)
    UID_VAL="$1"
    [ -z "$UID_VAL" ] && echo "Error: uid required" && exit 1
    log "GET uid=$UID_VAL"
    RESP=$(curl -s -w "\n%{http_code}" "${CALDAV_URL}/${UID_VAL}.ics")
    CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')
    if [ "$CODE" = "200" ]; then
      echo "$BODY" | sed 's/\r//'
    else
      echo "Event '$UID_VAL' not found."
    fi
    ;;

  create)
    UID_VAL="$1"; SUMMARY=$(ical_escape "$2"); DTSTART="$3"; DTEND="$4"
    DESCRIPTION="${5:-}"; STATUS="${6:-CONFIRMED}"
    [ -z "$UID_VAL" ] || [ -z "$SUMMARY" ] || [ -z "$DTSTART" ] || [ -z "$DTEND" ] && \
      echo "Error: create requires <uid> <summary> <start> <end>" && exit 1
    increment_counter "create" $MAX_CREATES_PER_DAY
    log "CREATE uid=$UID_VAL summary=$SUMMARY start=$DTSTART end=$DTEND"
    DESC_LINE=""
    [ -n "$DESCRIPTION" ] && DESC_LINE="
DESCRIPTION:$(ical_escape "$DESCRIPTION")"
    curl -s -o /dev/null -w "%{http_code}" -X PUT \
      -H "Content-Type: text/calendar" \
      --data-binary "BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:${UID_VAL}
DTSTART:${DTSTART}
DTEND:${DTEND}
SUMMARY:${SUMMARY}${DESC_LINE}
STATUS:${STATUS}
END:VEVENT
END:VCALENDAR" \
      "${CALDAV_URL}/${UID_VAL}.ics" | {
        read -r code
        if [ "$code" = "201" ] || [ "$code" = "204" ]; then
          echo "Created event '$UID_VAL'."
        else
          echo "Failed to create event (HTTP $code)."
        fi
      }
    ;;

  update)
    UID_VAL="$1"; SUMMARY=$(ical_escape "$2"); DTSTART="$3"; DTEND="$4"
    DESCRIPTION="${5:-}"; STATUS="${6:-CONFIRMED}"
    [ -z "$UID_VAL" ] || [ -z "$SUMMARY" ] || [ -z "$DTSTART" ] || [ -z "$DTEND" ] && \
      echo "Error: update requires <uid> <summary> <start> <end>" && exit 1
    increment_counter "update" $MAX_UPDATES_PER_DAY
    log "UPDATE uid=$UID_VAL summary=$SUMMARY start=$DTSTART end=$DTEND"
    DESC_LINE=""
    [ -n "$DESCRIPTION" ] && DESC_LINE="
DESCRIPTION:$(ical_escape "$DESCRIPTION")"
    curl -s -o /dev/null -w "%{http_code}" -X PUT \
      -H "Content-Type: text/calendar" \
      --data-binary "BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:${UID_VAL}
DTSTART:${DTSTART}
DTEND:${DTEND}
SUMMARY:${SUMMARY}${DESC_LINE}
STATUS:${STATUS}
END:VEVENT
END:VCALENDAR" \
      "${CALDAV_URL}/${UID_VAL}.ics" | {
        read -r code
        if [ "$code" = "201" ] || [ "$code" = "204" ]; then
          echo "Updated event '$UID_VAL'."
        else
          echo "Failed to update event (HTTP $code)."
        fi
      }
    ;;

  delete)
    UID_VAL="$1"
    [ -z "$UID_VAL" ] && echo "Error: uid required" && exit 1
    increment_counter "delete" $MAX_DELETES_PER_DAY
    log "DELETE uid=$UID_VAL"
    curl -s -o /dev/null -w "%{http_code}" -X DELETE \
      "${CALDAV_URL}/${UID_VAL}.ics" | {
        read -r code
        if [ "$code" = "200" ] || [ "$code" = "204" ]; then
          echo "Deleted event '$UID_VAL'."
        else
          echo "Failed to delete event (HTTP $code)."
        fi
      }
    ;;

  *)
    echo "Unknown action: $ACTION"
    usage
    ;;
esac
