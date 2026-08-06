#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Install the 944S boot splash on a Raspberry Pi (Bookworm/labwc).
#
#   sudo bash install-splash.sh                  (uses splash.png beside this script)
#   sudo bash install-splash.sh /path/to/other.png
#
# The image should be SQUARE — see make-splash.py for why.
#
# Hides every stock boot visual in order:
#   1. firmware rainbow      disable_splash=1        (config.txt)
#   2. kernel logos/cursor   logo.nologo, vt.global_cursor_default=0
#   3. plymouth splash       this theme, your image
#   4. desktop flash         wallpaper set to the same image, panel hidden
#
# Idempotent. Backs up both boot files before touching them — they carry
# load-bearing settings on this car (disable-bt, the forced video mode, and
# the deliberate ABSENCE of console=serial0) and a careless edit is a Pi
# that does not come back.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
THEME=/usr/share/plymouth/themes/944s
HERE="$(cd "$(dirname "$0")" && pwd)"
IMG="${1:-$HERE/splash.png}"

[ -f "$IMG" ] || { echo "usage: sudo bash install-splash.sh [/path/to/splash.png]" >&2; exit 2; }
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 2; }

echo "==> 1. Theme files"
install -d "$THEME"
install -m644 "$HERE/944s.plymouth" "$HERE/944s.script" "$THEME/"
install -m644 "$IMG" "$THEME/splash.png"
echo "    $(identify -format '%wx%h' "$THEME/splash.png" 2>/dev/null || echo 'image installed')"

echo "==> 2. Firmware splash off"
grep -q '^disable_splash=1' /boot/firmware/config.txt || {
  cp -n /boot/firmware/config.txt /boot/firmware/config.txt.bak-splash
  echo 'disable_splash=1' >> /boot/firmware/config.txt
}

echo "==> 3. Kernel logos and cursor off"
CL=/boot/firmware/cmdline.txt
cp -n "$CL" "$CL.bak-splash" 2>/dev/null || true
# cmdline.txt MUST remain ONE line. A stray newline truncates the kernel args
# and the Pi boots without its root options or video mode.
python3 - "$CL" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); parts = p.read_text().split()
for a in ("logo.nologo", "vt.global_cursor_default=0", "loglevel=3"):
    if not any(x.split("=")[0] == a.split("=")[0] for x in parts):
        parts.append(a)
p.write_text(" ".join(parts) + "\n")
PY
grep -q 'root=' "$CL" || { echo "!! cmdline lost root= — restoring backup" >&2; cp "$CL.bak-splash" "$CL"; exit 1; }

echo "==> 4. Make it the default theme and rebuild the initramfs"
plymouth-set-default-theme 944s -R

echo "==> 5. Desktop layer — same image behind the kiosk, no panel"
# The desktop is only visible for the moment between the session starting and
# Chromium covering it. Painting it with the SAME image makes that handoff
# invisible rather than trying to win a race against it.
#
# wallpaper_mode=fit letterboxes a square image on the 1920x720 bar, and the
# letterbox is painted in desktop_bg — which ships a light lavender. Setting
# the image without also blacking out desktop_bg is why the stock background
# was still showing: two grey bars either side of the splash.
#
# pcmanfm keeps ONE config PER OUTPUT — desktop-items-HDMI-A-1.conf and so on
# — and falls back to the stock wallpaper for any output it has no file for.
# Patching only the files that already exist leaves the second screen showing
# fisherman.jpg, so write a file for every connected connector. /sys/class/drm
# is used rather than wlr-randr because this runs under sudo with no Wayland
# session to talk to.
CONNECTED=$(for s in /sys/class/drm/card*-*/status; do
  [ "$(cat "$s" 2>/dev/null)" = connected ] || continue
  d=${s%/status}; basename "$d" | sed 's|^card[0-9]*-||'
done | sort -u)
echo "    connected outputs: $(echo $CONNECTED)"

for U in $(ls /home); do
  D="/home/$U/.config/pcmanfm/LXDE-pi"
  [ -d "$D" ] || continue
  install -d "$D"

  for OUT in $CONNECTED; do
    f="$D/desktop-items-$OUT.conf"
    [ -f "$f" ] || printf '[*]\n' > "$f"
  done

  for f in "$D"/desktop-items-*.conf; do
    [ -f "$f" ] || continue
    # Set each key, appending it under [*] when the file does not have it yet.
    python3 - "$f" "$THEME/splash.png" <<'PY'
import sys, pathlib, re
f, img = pathlib.Path(sys.argv[1]), sys.argv[2]
want = {
    "wallpaper": img, "wallpaper_mode": "fit", "wallpaper_common": "1",
    "desktop_bg": "#000000", "desktop_fg": "#000000", "desktop_shadow": "#000000",
    "show_documents": "0", "show_trash": "0", "show_mounts": "0",
}
lines = f.read_text().splitlines()
if not any(l.strip() == "[*]" for l in lines):
    lines.insert(0, "[*]")
seen = set()
for i, l in enumerate(lines):
    m = re.match(r"^(\w+)=", l)
    if m and m.group(1) in want:
        lines[i] = f"{m.group(1)}={want[m.group(1)]}"
        seen.add(m.group(1))
star = lines.index("[*]")
for k, v in want.items():
    if k not in seen:
        star += 1
        lines.insert(star, f"{k}={v}")
f.write_text("\n".join(lines) + "\n")
PY
    chown "$U:$U" "$f"
  done

  # The taskbar is respawned by lwrespawn from /etc/xdg/labwc/autostart, so
  # killing it just brings it back. Auto-hide is the setting it will honour.
  PI="/home/$U/.config/wf-panel-pi.ini"
  if [ -f "$PI" ]; then
    grep -q '^autohide=' "$PI" && sed -i 's|^autohide=.*|autohide=true|' "$PI" \
      || sed -i '0,/^\[panel\]/s||[panel]\nautohide=true|' "$PI"
  else
    printf '[panel]\nautohide=true\n' > "$PI"
  fi
  chown "$U:$U" "$PI"
done

echo
echo "==> Done. Reboot to see it."
echo "    Undo:  sudo plymouth-set-default-theme -R bgrt"
echo "           sudo cp /boot/firmware/cmdline.txt.bak-splash /boot/firmware/cmdline.txt"
echo "           sudo cp /boot/firmware/config.txt.bak-splash /boot/firmware/config.txt"
