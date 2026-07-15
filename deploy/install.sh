#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Provision the 944S HVAC Pi:
#   1. systemd service for the backend (auto-start on boot, auto-restart)
#   2. Chromium kiosk autostart under labwc (dashboard fullscreen on boot)
#   3. remove the stale @reboot cron entry
#
# Run as the 'mark' user (NOT with sudo); it calls sudo where needed:
#   bash ~/hvac/deploy/install.sh
# Idempotent — safe to re-run.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME"
echo "Repo:  $REPO_DIR"
echo "Home:  $HOME_DIR"

# ── 1. Backend systemd service ───────────────────────────────
echo "==> Installing hvac-backend.service"
sudo cp "$REPO_DIR/deploy/hvac-backend.service" /etc/systemd/system/hvac-backend.service
sudo systemctl daemon-reload
sudo systemctl enable hvac-backend

# Free port 8000 from any manually-started backend, then (re)start the service
echo "==> Stopping any manually-started backend on :8000"
sudo fuser -k -TERM 8000/tcp 2>/dev/null || true
sleep 4
sudo systemctl restart hvac-backend

# ── 2. Kiosk launcher + labwc autostart ──────────────────────
echo "==> Installing kiosk autostart"
chmod +x "$REPO_DIR/deploy/kiosk-launch.sh"
mkdir -p "$HOME_DIR/.config/labwc"
install -m 0755 "$REPO_DIR/deploy/labwc-autostart" "$HOME_DIR/.config/labwc/autostart"

# ── 3. Drop the stale @reboot /home/mark/kiosk cron entry ────
echo "==> Cleaning stale cron entry"
( crontab -l 2>/dev/null | grep -vF '/home/mark/kiosk' ) | crontab - || true

echo "==> Done. Backend: $(systemctl is-active hvac-backend). Reboot to verify the kiosk autostarts."
