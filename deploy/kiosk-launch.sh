#!/bin/sh
# ─────────────────────────────────────────────────────────────
# 944S HVAC dashboard kiosk launcher
# Waits for the backend to be serving, then opens the dashboard
# fullscreen in Chromium with no browser chrome.
#
# To run WINDOWED instead of fullscreen kiosk (a minimal app window
# with a title bar / escape hatch), replace the "--kiosk" line below
# with:   --app="$URL" --start-maximized
# ─────────────────────────────────────────────────────────────

URL="http://localhost:8000"
LOG="$HOME/hvac/kiosk.log"
PROFILE="$HOME/.config/chromium-dash"

exec >>"$LOG" 2>&1
echo "$(date '+%F %T') kiosk-launch starting"

# Wait up to ~90s for the backend to answer (it starts as its own service)
i=0
while [ "$i" -lt 90 ]; do
  if curl -sf -o /dev/null "$URL"; then break; fi
  i=$((i + 1)); sleep 1
done

# Suppress Chromium's "restore pages / didn't shut down correctly" bar
PREFS="$PROFILE/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i \
    -e 's/"exit_type":"[^"]*"/"exit_type":"Normal"/' \
    -e 's/"exited_cleanly":false/"exited_cleanly":true/' \
    "$PREFS" 2>/dev/null || true
fi

echo "$(date '+%F %T') launching chromium kiosk -> $URL"
exec chromium-browser \
  --kiosk \
  --ozone-platform=wayland \
  --class=hvac-dash \
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
