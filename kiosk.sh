#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 944S HVAC — Kiosk Mode Toggle
# ═══════════════════════════════════════════════════════════════
#
# Usage:
#   ./kiosk.sh on      Launch kiosk now + enable autostart
#   ./kiosk.sh off     Kill kiosk now + disable autostart
#   ./kiosk.sh status  Show current state
#
# ═══════════════════════════════════════════════════════════════

KIOSK_DESKTOP="$HOME/.config/autostart/hvac-kiosk.desktop"
KIOSK_URL="http://localhost:8000"

case "$1" in
  on)
    echo "Starting kiosk mode..."
    # Enable autostart
    if [ -f "$KIOSK_DESKTOP" ]; then
      sed -i 's/X-GNOME-Autostart-enabled=false/X-GNOME-Autostart-enabled=true/' "$KIOSK_DESKTOP"
    fi
    # Kill any existing instance first
    pkill -f "chromium.*kiosk" 2>/dev/null
    sleep 1
    # Launch
    chromium-browser --kiosk --noerrdialogs --disable-infobars \
      --disable-translate --no-first-run --fast --fast-start \
      --disable-features=TranslateUI --disable-session-crashed-bubble \
      --check-for-update-interval=31536000 \
      --window-size=1920,720 --window-position=0,0 \
      "$KIOSK_URL" &
    disown
    echo "Kiosk ON — autostart ENABLED"
    ;;

  off)
    echo "Stopping kiosk mode..."
    # Kill all kiosk Chromium instances
    pkill -f "chromium.*kiosk" 2>/dev/null
    # Disable autostart so it stays dead on reboot
    if [ -f "$KIOSK_DESKTOP" ]; then
      sed -i 's/X-GNOME-Autostart-enabled=true/X-GNOME-Autostart-enabled=false/' "$KIOSK_DESKTOP"
    fi
    echo "Kiosk OFF — autostart DISABLED"
    ;;

  status)
    if pgrep -f "chromium.*kiosk" > /dev/null; then
      echo "Kiosk: RUNNING (PID $(pgrep -f 'chromium.*kiosk' | head -1))"
    else
      echo "Kiosk: STOPPED"
    fi
    if grep -q "Autostart-enabled=true" "$KIOSK_DESKTOP" 2>/dev/null; then
      echo "Autostart: ENABLED (will launch on reboot)"
    else
      echo "Autostart: DISABLED (will stay off on reboot)"
    fi
    echo "Backend: $(systemctl is-active hvac 2>/dev/null || echo 'unknown')"
    ;;

  *)
    echo "Usage: $0 {on|off|status}"
    echo ""
    echo "  on      Launch kiosk + enable autostart"
    echo "  off     Kill kiosk + disable autostart"
    echo "  status  Show current state"
    exit 1
    ;;
esac
