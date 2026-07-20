#!/bin/sh
# ─────────────────────────────────────────────────────────────
# 944S Sport Chrono clock kiosk — for the round HDMI screen.
# Runs as its own Chromium instance (separate profile + --class) so it can
# coexist with the dashboard kiosk and be pinned to its own output later.
# ─────────────────────────────────────────────────────────────
URL="http://localhost:8000/clock.html"
LOG="$HOME/hvac/clock.log"
PROFILE="$HOME/.config/chromium-clock"

exec >>"$LOG" 2>&1
echo "$(date '+%F %T') clock-launch starting"

# Wait up to ~90s for the backend to serve the clock page
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

echo "$(date '+%F %T') launching chromium clock -> $URL"
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
