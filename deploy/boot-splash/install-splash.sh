#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Install the 944S boot splash on a Raspberry Pi (Bookworm/labwc).
#
#   sudo bash install-splash.sh /path/to/splash.png
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
IMG="${1:-}"
THEME=/usr/share/plymouth/themes/944s
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -n "$IMG" ] && [ -f "$IMG" ] || { echo "usage: sudo bash install-splash.sh /path/to/splash.png" >&2; exit 2; }
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
for U in $(ls /home); do
  D="/home/$U/.config/pcmanfm/LXDE-pi"
  [ -d "$D" ] || continue
  install -d "$D"
  for f in "$D"/desktop-items-*.conf; do
    [ -f "$f" ] || continue
    sed -i "s|^wallpaper=.*|wallpaper=$THEME/splash.png|" "$f"
    sed -i "s|^wallpaper_mode=.*|wallpaper_mode=fit|" "$f"
    sed -i "s|^show_documents=.*|show_documents=0|;s|^show_trash=.*|show_trash=0|;s|^show_mounts=.*|show_mounts=0|" "$f"
    chown "$U:$U" "$f"
  done
done

echo
echo "==> Done. Reboot to see it."
echo "    Undo:  sudo plymouth-set-default-theme -R bgrt"
echo "           sudo cp /boot/firmware/cmdline.txt.bak-splash /boot/firmware/cmdline.txt"
echo "           sudo cp /boot/firmware/config.txt.bak-splash /boot/firmware/config.txt"
