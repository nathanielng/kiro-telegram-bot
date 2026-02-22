#!/usr/bin/env bash
# =============================================================================
# setup_autostart.sh
#
# Configures the system to automatically launch the Telegram bot and the
# folder monitor on boot.
#
# Supported init systems (detected automatically):
#   - systemd (Linux)  → user-level services under ~/.config/systemd/user/
#   - launchd (macOS)  → user LaunchAgents under ~/Library/LaunchAgents/
#   - cron (fallback)  → @reboot entries in the user's crontab
#
# Usage:
#   ./setup_autostart.sh [--uninstall] [--system] [-h|--help]
#
#   --uninstall   Remove the previously installed services / cron entries
#   --system      Install as a system-wide service (requires sudo; systemd only)
#   -h, --help    Show this message
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_SCRIPT="${SCRIPT_DIR}/run_telegram.sh"
MONITOR_SCRIPT="${SCRIPT_DIR}/run_monitor.sh"
SERVICE_BOT="kiro-telegram-bot"
SERVICE_MON="kiro-folder-monitor"
UNINSTALL=false
SYSTEM_INSTALL=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
for arg in "$@"; do
  case "${arg}" in
    --uninstall) UNINSTALL=true ;;
    --system)    SYSTEM_INSTALL=true ;;
    -h|--help)
      sed -n '/^# ====/,/^# ====/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: ${arg}"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
warn()  { echo "[WARN]  $*"; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

detect_init_system() {
  if command -v systemctl &>/dev/null; then
    echo "systemd"
  elif [ "$(uname -s)" = "Darwin" ] && command -v launchctl &>/dev/null; then
    echo "launchd"
  else
    echo "cron"
  fi
}

INIT="$(detect_init_system)"
info "Detected init system: ${INIT}"

# ---------------------------------------------------------------------------
# systemd helpers
# ---------------------------------------------------------------------------
systemd_unit_dir() {
  if [ "${SYSTEM_INSTALL}" = true ]; then
    echo "/etc/systemd/system"
  else
    echo "${HOME}/.config/systemd/user"
  fi
}

systemd_ctl() {
  if [ "${SYSTEM_INSTALL}" = true ]; then
    sudo systemctl "$@"
  else
    systemctl --user "$@"
  fi
}

write_systemd_unit() {
  local name="$1"
  local desc="$2"
  local exec_cmd="$3"
  local unit_dir
  unit_dir="$(systemd_unit_dir)"
  mkdir -p "${unit_dir}"
  local unit_file="${unit_dir}/${name}.service"

  cat > "${unit_file}" <<EOF
[Unit]
Description=${desc}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=-${SCRIPT_DIR}/.env
ExecStart=${exec_cmd}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=$([ "${SYSTEM_INSTALL}" = true ] && echo "multi-user.target" || echo "default.target")
EOF

  ok "Wrote unit file: ${unit_file}"
}

install_systemd() {
  write_systemd_unit "${SERVICE_BOT}" \
    "Kiro Telegram Bot" \
    "/bin/bash ${BOT_SCRIPT}"

  write_systemd_unit "${SERVICE_MON}" \
    "Kiro Folder Monitor (S3 sync)" \
    "/bin/bash ${MONITOR_SCRIPT}"

  if [ "${SYSTEM_INSTALL}" = true ]; then
    sudo systemctl daemon-reload
    sudo systemctl enable --now "${SERVICE_BOT}.service"
    sudo systemctl enable --now "${SERVICE_MON}.service"
  else
    systemctl --user daemon-reload
    systemctl --user enable --now "${SERVICE_BOT}.service"
    systemctl --user enable --now "${SERVICE_MON}.service"
    # Ensure user services survive logout (requires lingering to be enabled)
    if command -v loginctl &>/dev/null; then
      loginctl enable-linger "$(whoami)" 2>/dev/null || true
    fi
  fi

  ok "Services enabled and started."
  info "Check status:  $([ "${SYSTEM_INSTALL}" = true ] && echo "sudo systemctl status ${SERVICE_BOT}" || echo "systemctl --user status ${SERVICE_BOT}")"
  info "View logs:     $([ "${SYSTEM_INSTALL}" = true ] && echo "journalctl -u ${SERVICE_BOT} -f" || echo "journalctl --user -u ${SERVICE_BOT} -f")"
}

uninstall_systemd() {
  for svc in "${SERVICE_BOT}" "${SERVICE_MON}"; do
    systemd_ctl stop  "${svc}.service" 2>/dev/null || true
    systemd_ctl disable "${svc}.service" 2>/dev/null || true
    local unit_file
    unit_file="$(systemd_unit_dir)/${svc}.service"
    [ -f "${unit_file}" ] && rm "${unit_file}" && ok "Removed ${unit_file}"
  done
  systemd_ctl daemon-reload
  ok "Services removed."
}

# ---------------------------------------------------------------------------
# launchd helpers (macOS)
# ---------------------------------------------------------------------------
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

write_plist() {
  local label="$1"
  local desc="$2"
  local exec_cmd="$3"
  local plist="${LAUNCH_AGENTS_DIR}/com.${label}.plist"
  mkdir -p "${LAUNCH_AGENTS_DIR}"

  cat > "${plist}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${exec_cmd}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${SCRIPT_DIR}/${label}.log</string>
  <key>StandardErrorPath</key>
  <string>${SCRIPT_DIR}/${label}.log</string>
</dict>
</plist>
EOF
  ok "Wrote plist: ${plist}"
}

install_launchd() {
  write_plist "${SERVICE_BOT}"  "Kiro Telegram Bot"              "${BOT_SCRIPT}"
  write_plist "${SERVICE_MON}"  "Kiro Folder Monitor (S3 sync)"  "${MONITOR_SCRIPT}"

  launchctl load -w "${LAUNCH_AGENTS_DIR}/com.${SERVICE_BOT}.plist"
  launchctl load -w "${LAUNCH_AGENTS_DIR}/com.${SERVICE_MON}.plist"

  ok "LaunchAgents loaded."
  info "Check status:  launchctl list | grep kiro"
  info "View logs:     tail -f ${SCRIPT_DIR}/${SERVICE_BOT}.log"
}

uninstall_launchd() {
  for svc in "${SERVICE_BOT}" "${SERVICE_MON}"; do
    local plist="${LAUNCH_AGENTS_DIR}/com.${svc}.plist"
    launchctl unload "${plist}" 2>/dev/null || true
    [ -f "${plist}" ] && rm "${plist}" && ok "Removed ${plist}"
  done
  ok "LaunchAgents removed."
}

# ---------------------------------------------------------------------------
# cron helpers (fallback)
# ---------------------------------------------------------------------------
install_cron() {
  local bot_entry="@reboot /bin/bash ${BOT_SCRIPT} >> ${SCRIPT_DIR}/telegram_bot.log 2>&1"
  local mon_entry="@reboot /bin/bash ${MONITOR_SCRIPT} >> ${SCRIPT_DIR}/folder_monitor.log 2>&1"

  # Remove any existing entries for these scripts, then add fresh ones
  (crontab -l 2>/dev/null | grep -v "${BOT_SCRIPT}" | grep -v "${MONITOR_SCRIPT}"; \
   echo "${bot_entry}"; echo "${mon_entry}") | crontab -

  ok "Cron @reboot entries added."
  info "Current crontab:"
  crontab -l | grep -E "(${SERVICE_BOT}|${SERVICE_MON}|telegram_bot|folder_monitor)" || true
}

uninstall_cron() {
  (crontab -l 2>/dev/null | grep -v "${BOT_SCRIPT}" | grep -v "${MONITOR_SCRIPT}") | crontab -
  ok "Cron entries removed."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [ "${UNINSTALL}" = true ]; then
  info "Uninstalling autostart for: ${INIT}"
  case "${INIT}" in
    systemd) uninstall_systemd ;;
    launchd) uninstall_launchd ;;
    cron)    uninstall_cron ;;
  esac
else
  info "Installing autostart using: ${INIT}"

  # Verify scripts exist
  [ -f "${BOT_SCRIPT}" ]     || die "${BOT_SCRIPT} not found"
  [ -f "${MONITOR_SCRIPT}" ] || die "${MONITOR_SCRIPT} not found"

  # Ensure scripts are executable
  chmod +x "${BOT_SCRIPT}" "${MONITOR_SCRIPT}"

  case "${INIT}" in
    systemd) install_systemd ;;
    launchd) install_launchd ;;
    cron)    install_cron ;;
  esac

  echo ""
  ok "Autostart configured. Both services will start automatically on next boot."
  info "To start immediately without rebooting, run:"
  info "  ${BOT_SCRIPT}"
  info "  ${MONITOR_SCRIPT}"
fi
