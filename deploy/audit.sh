#!/bin/bash
# Audit: does the repo fully capture what is running on the 944S HVAC Pi?
# Run ON the Pi (piped over ssh). Read-only — changes nothing.
set -u
cd ~/hvac || { echo "FATAL: no ~/hvac"; exit 1; }
FAIL=0
say()  { printf '%s\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  DRIFT %s\n' "$*"; FAIL=1; }

say "════ 1. GIT LAYER ════"
git fetch -q origin 2>/dev/null || say "  (no GitHub reach — comparing to last-fetched origin)"
L=$(git rev-parse HEAD); R=$(git rev-parse origin/main)
[ "$L" = "$R" ] && ok "HEAD = origin/main ($(git rev-parse --short HEAD))" \
                || bad "HEAD $(git rev-parse --short HEAD) != origin/main $(git rev-parse --short origin/main) — pull needed"
D=$(git status --porcelain)
[ -z "$D" ] && ok "working tree clean (no edits stranded on the Pi)" \
            || { bad "uncommitted changes on the Pi:"; echo "$D" | sed 's/^/        /'; }

say "════ 2. INSTALLED COPIES vs REPO SOURCES ════"
cmp_files() {  # cmp_files <installed> <repo-source>
  if [ ! -e "$1" ]; then bad "$1 missing"; return; fi
  if cmp -s "$1" "$2"; then ok "$1"; else bad "$1 differs from $2"; fi
}
cmp_files /etc/systemd/system/hvac-backend.service      deploy/hvac-backend.service
cmp_files "$HOME/.config/labwc/autostart"               deploy/labwc-autostart
cmp_files /usr/share/plymouth/themes/944s/944s.plymouth deploy/boot-splash/944s.plymouth
cmp_files /usr/share/plymouth/themes/944s/944s.script   deploy/boot-splash/944s.script
cmp_files /usr/share/plymouth/themes/944s/splash-main.png deploy/boot-splash/splash-main.png
cmp_files /usr/share/plymouth/themes/944s/splash-aux.png  deploy/boot-splash/splash-aux.png
# the dependency systemd actually loaded (catches daemon-reload never run).
# Query the property, NOT `systemctl cat` — the unit file's own comment names
# network-online.target while explaining why it must not be used, and grepping
# the text produced a false DRIFT on the first run of this audit.
systemctl show hvac-backend -p After --no-pager | grep -q "network-online" \
  && bad "LOADED unit still waits for network-online (daemon-reload missed?)" \
  || ok "loaded unit has no network-online dependency"

say "════ 3. GENERATED CONFIGS have the values the scripts write ════"
chk() {  # chk <desc> <file> <grep-pattern>
  if grep -qE "$3" "$2" 2>/dev/null; then ok "$1"; else bad "$1  [$2 lacks: $3]"; fi
}
chk "cmdline: video forced on A-1 only"  /boot/firmware/cmdline.txt 'video=HDMI-A-1:1920x720M@60e'
[ "$(grep -co 'video=' /boot/firmware/cmdline.txt)" = 1 ] && ok "cmdline: exactly one video=" || bad "cmdline: multiple video= args"
[ "$(wc -l < /boot/firmware/cmdline.txt)" = 1 ] && ok "cmdline: single line" || bad "cmdline: NOT one line"
chk "cmdline: logo.nologo"               /boot/firmware/cmdline.txt 'logo\.nologo'
chk "cmdline: cursor off"                /boot/firmware/cmdline.txt 'vt\.global_cursor_default=0'
chk "config.txt: firmware splash off"    /boot/firmware/config.txt  '^disable_splash=1'
chk "kanshi: dash bar at 0,0"            "$HOME/.config/kanshi/config" 'HDMI-A-1 mode 1920x720 position 0,0'
chk "kanshi: round at 1920,0"            "$HOME/.config/kanshi/config" 'HDMI-A-2 mode 480x480 position 1920,0'
chk "rc.xml: dash pinned to A-1"         "$HOME/.config/labwc/rc.xml" 'hvac-dash.*matchOnce="false".*HDMI-A-1'
chk "rc.xml: clock pinned to A-2"        "$HOME/.config/labwc/rc.xml" 'hvac-clock.*matchOnce="false".*HDMI-A-2'
chk "rc.xml: touch mapped to A-1"        "$HOME/.config/labwc/rc.xml" 'touch deviceName.*mapToOutput="HDMI-A-1"'
chk "plymouth default theme = 944s"      /etc/plymouth/plymouthd.conf 'Theme=944s'
D1="$HOME/.config/pcmanfm/LXDE-pi/desktop-items-HDMI-A-1.conf"
D2="$HOME/.config/pcmanfm/LXDE-pi/desktop-items-HDMI-A-2.conf"
chk "wallpaper A-1 = car"                "$D1" 'wallpaper=.*/splash-main\.png'
chk "wallpaper A-2 = crest"              "$D2" 'wallpaper=.*/splash-aux\.png'
chk "wallpaper A-1 common=1"             "$D1" 'wallpaper_common=1'
chk "desktop_bg black (A-1)"             "$D1" 'desktop_bg=#000000'
chk "cursor: user env blank"             "$HOME/.config/labwc/environment" 'XCURSOR_THEME=blank'
chk "cursor: system env blank"           /etc/xdg/labwc/environment 'XCURSOR_THEME=blank'
chk "cursor: gtk settings blank"         "$HOME/.config/gtk-3.0/settings.ini" 'gtk-cursor-theme-name=blank'
[ -f /usr/share/icons/blank/cursors/left_ptr ] && ok "blank cursor theme installed" || bad "blank cursor theme missing"
grep -qE '^[^#]*wf-panel-pi' /etc/xdg/labwc/autostart && bad "wf-panel-pi still launched at login" || ok "wf-panel-pi disabled"
G=$(sudo -u mark DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus" gsettings get org.gnome.desktop.interface cursor-theme 2>/dev/null)
[ "$G" = "'blank'" ] && ok "portal dconf cursor-theme = blank" || bad "portal dconf cursor-theme = ${G:-unreadable}"

say "════ 4. ANYTHING ELSE LIVING ONLY ON THE PI ════"
U=$(git status --porcelain --ignored | grep '^!!' | grep -vE 'node_modules|dashboard/build|hvac_state\.json|__pycache__|\.log$|kiosk\.log|clock\.log')
[ -z "$U" ] && ok "no unexpected ignored files" || { say "  review these (ignored, Pi-only):"; echo "$U" | sed 's/^!!/        /'; }
say ""
say "════ RUNTIME (context, not drift) ════"
say "  backend: $(systemctl is-active hvac-backend)   boot: $(uptime -p)"
say ""
[ $FAIL = 0 ] && say "RESULT: NO DRIFT — the repo fully captures the Pi." \
              || say "RESULT: DRIFT FOUND — items marked DRIFT above."
exit $FAIL
