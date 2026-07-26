#!/bin/sh
# ─────────────────────────────────────────────────────────────
# 944S round auxiliary screen kiosk.
#
# Loads /aux.html, which hosts EITHER the Sport Chrono clock or the G-meter
# and swaps between them live from the backend's `aux_display` state (set
# from the HVAC dashboard). The kiosk never restarts to switch pages.
#
# Runs as its own Chromium instance (separate profile + --class) so it can
# coexist with the dashboard kiosk. NOTE: --class stays "hvac-clock" because
# ~/.config/labwc/rc.xml pins that window class to HDMI-A-1 (the round panel);
# renaming it means updating rc.xml too.
# ─────────────────────────────────────────────────────────────
URL="http://localhost:8000/aux.html"
LOG="$HOME/hvac/clock.log"
PROFILE="$HOME/.config/chromium-clock"

exec >>"$LOG" 2>&1
echo "$(date '+%F %T') aux-launch starting"

# Wait up to ~90s for the backend to serve the page
i=0
while [ "$i" -lt 90 ]; do
  if curl -sf -o /dev/null "$URL"; then break; fi
  i=$((i + 1)); sleep 1
done

# Suppress Chromium's "restore pages" bar
PREFS="$PROFILE/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i \
    -e 's/"exit_type":"[^"]*"/"exit_type":"Normal"/' \
    -e 's/"exited_cleanly":false/"exited_cleanly":true/' \
    "$PREFS" 2>/dev/null || true
fi

echo "$(date '+%F %T') launching chromium aux kiosk -> $URL"
exec chromium-browser \
  --kiosk \
  --ozone-platform=wayland \
  --class=hvac-clock \
  --user-data-dir="$PROFILE" \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --disable-translate \
  --no-first-run \
  --no-default-browser-check \
  --check-for-update-interval=31536000 \
  "$URL"
