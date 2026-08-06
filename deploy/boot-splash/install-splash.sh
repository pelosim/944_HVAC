#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Install the 944S boot splash on a Raspberry Pi (Bookworm/labwc).
#
#   sudo bash install-splash.sh
#
# Two images, taken from beside this script:
#   splash-main.png   the car        -> the 1920x720 dash bar   (HDMI-A-1)
#   splash-aux.png    the crest      -> the 480x480 round gauge (HDMI-A-2)
#
# Hides every stock boot visual in order:
#   1. firmware rainbow      disable_splash=1        (config.txt)
#   2. kernel logos/cursor   logo.nologo, vt.global_cursor_default=0
#   3. plymouth splash       this theme, both images
#   4. desktop flash         wallpaper set to the same images per output
#   5. mouse pointer         a fully transparent Xcursor theme
#   6. panel + its popups    wf-panel-pi is not started at all
#
# Idempotent. Backs up both boot files before touching them — they carry
# load-bearing settings on this car (disable-bt, the forced video mode, and
# the deliberate ABSENCE of console=serial0) and a careless edit is a Pi
# that does not come back.
#
# Undo is printed at the end.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
THEME=/usr/share/plymouth/themes/944s
HERE="$(cd "$(dirname "$0")" && pwd)"

# Which image each output gets. Keep in step with deploy/setup-displays.sh.
OUT_MAIN=HDMI-A-1
OUT_AUX=HDMI-A-2

IMG_MAIN="$HERE/splash-main.png"
IMG_AUX="$HERE/splash-aux.png"

[ -f "$IMG_MAIN" ] && [ -f "$IMG_AUX" ] || {
  echo "missing splash-main.png / splash-aux.png beside this script" >&2; exit 2; }
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 2; }

echo "==> 1. Theme files"
install -d "$THEME"
install -m644 "$HERE/944s.plymouth" "$HERE/944s.script" "$THEME/"
install -m644 "$IMG_MAIN" "$THEME/splash-main.png"
install -m644 "$IMG_AUX" "$THEME/splash-aux.png"
# The old single-image theme left this behind; the script no longer reads it.
rm -f "$THEME/splash.png"

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

echo "==> 5. Desktop layer — the same images behind the kiosks"
# The desktop is only visible for the moment between the session starting and
# Chromium covering it. Painting it with the SAME images makes that handoff
# invisible rather than trying to win a race against it.
#
# pcmanfm keeps ONE config PER OUTPUT — desktop-items-HDMI-A-1.conf and so on
# — and falls back to the stock wallpaper for any output it has no file for.
# Patching only the files that already exist leaves the second screen showing
# fisherman.jpg, so write a file for every connected connector. /sys/class/drm
# is used rather than wlr-randr because this runs under sudo with no Wayland
# session to talk to.
#
# wallpaper_common stays 1. It selects one wallpaper across WORKSPACES, not
# across monitors — the per-output file is what picks the per-output image.
# Setting it to 0 sends pcmanfm looking for per-workspace settings that do not
# exist here and it paints nothing at all, leaving both screens plain black.
CONNECTED=$(for s in /sys/class/drm/card*-*/status; do
  [ "$(cat "$s" 2>/dev/null)" = connected ] || continue
  d=${s%/status}; basename "$d" | sed 's|^card[0-9]*-||'
done | sort -u)
echo "    connected outputs: $(echo $CONNECTED)"

for U in $(ls /home); do
  D="/home/$U/.config/pcmanfm/LXDE-pi"
  [ -d "$D" ] || continue

  for OUT in $CONNECTED; do
    case "$OUT" in
      "$OUT_AUX") WP="$THEME/splash-aux.png" ;;
      *)          WP="$THEME/splash-main.png" ;;
    esac
    f="$D/desktop-items-$OUT.conf"
    [ -f "$f" ] || printf '[*]\n' > "$f"
    echo "    $OUT -> $(basename "$WP")"
    # Set each key by name, appending it under [*] when the file lacks it.
    python3 - "$f" "$WP" <<'PY'
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
done

echo "==> 6. Transparent mouse pointer"
# labwc has no idle-hide for the pointer, and unclutter is X11-only. The way
# to get rid of it on Wayland is to give every client a cursor theme whose
# images are a single transparent pixel. This hides the pointer ALWAYS, not
# just when idle — including over VNC. To get it back:
#   rm /home/<user>/.config/labwc/environment   (then log out and in)
CURSORS=/usr/share/icons/blank/cursors
install -d "$CURSORS"
python3 - "$CURSORS/left_ptr" <<'PY'
import struct, sys, pathlib
# Xcursor file format: a 16-byte header, one 12-byte TOC entry per nominal
# size, then one image chunk each. Every image here is a single fully
# transparent ARGB pixel, which is what makes the pointer invisible.
SIZES = [16, 24, 32, 48, 64]
IMG_TYPE = 0xFFFD0002

def chunk(nominal):
    # header, type, subtype, version, width, height, xhot, yhot, delay
    return struct.pack("<9I", 36, IMG_TYPE, nominal, 1, 1, 1, 0, 0, 0) \
        + struct.pack("<I", 0x00000000)

header = struct.pack("<4sIII", b"Xcur", 16, 0x00010000, len(SIZES))
pos = 16 + 12 * len(SIZES)
toc, body = b"", b""
for s in SIZES:
    c = chunk(s)
    toc += struct.pack("<3I", IMG_TYPE, s, pos)
    body += c
    pos += len(c)
pathlib.Path(sys.argv[1]).write_bytes(header + toc + body)
PY
# Clients ask for cursors by many names; anything the theme does not define
# falls back to the visible default, so alias them all to the blank one.
for n in default pointer arrow top_left_arrow left_ptr_watch watch wait text \
         xterm ibeam hand hand1 hand2 pointing_hand crosshair cross tcross \
         fleur move grabbing progress not-allowed no-drop help question_arrow \
         sb_h_double_arrow sb_v_double_arrow col-resize row-resize \
         bottom_right_corner bottom_left_corner top_right_corner \
         top_left_corner bottom_side top_side left_side right_side; do
  ln -sf left_ptr "$CURSORS/$n"
done
cat > /usr/share/icons/blank/index.theme <<'EOF'
[Icon Theme]
Name=blank
Comment=Fully transparent pointer for the 944S kiosk
EOF

for U in $(ls /home); do
  L="/home/$U/.config/labwc"
  [ -d "$L" ] || continue
  # labwc parses this file at startup and exports the variables, so the two
  # kiosks started from its autostart inherit them.
  cat > "$L/environment" <<'EOF'
# Written by deploy/boot-splash/install-splash.sh
XCURSOR_THEME=blank
XCURSOR_SIZE=24
EOF
  chown "$U:$U" "$L/environment"
done

# The user file alone is not enough. labwc reads $XDG_CONFIG_HOME's environment
# and THEN the one in $XDG_CONFIG_DIRS, and the later assignment wins — so
# /etc/xdg/labwc/environment's XCURSOR_THEME=PiXflat silently overrode the
# user's setting and the pointer stayed visible. Set it in both.
SYSENV=/etc/xdg/labwc/environment
if [ -f "$SYSENV" ] && ! grep -q '^XCURSOR_THEME=blank' "$SYSENV"; then
  cp -n "$SYSENV" "$SYSENV.bak-splash"
  sed -i 's|^XCURSOR_THEME=.*|XCURSOR_THEME=blank|' "$SYSENV"
fi

echo "==> 7. Panel off — it draws the boot-time notification popups"
# The "You are now connected to ..." bubbles at the top of the screen come
# from wf-panel-pi, which /etc/xdg/labwc/autostart starts under lwrespawn.
# There is no notification daemon on this system to disable instead, and
# killing the panel just makes lwrespawn bring it back — so stop launching it.
# The panel is dead weight on a kiosk anyway.
SYSAUTO=/etc/xdg/labwc/autostart
if grep -q '^[^#].*wf-panel-pi' "$SYSAUTO" 2>/dev/null; then
  cp -n "$SYSAUTO" "$SYSAUTO.bak-splash"
  sed -i 's|^\(.*wf-panel-pi.*\)$|# 944S kiosk: panel disabled by install-splash.sh\n#\1|' "$SYSAUTO"
fi
pkill -x wf-panel-pi 2>/dev/null || true

echo
echo "==> Done. Reboot to see it."
echo "    Undo:  sudo plymouth-set-default-theme -R bgrt"
echo "           sudo cp /boot/firmware/cmdline.txt.bak-splash /boot/firmware/cmdline.txt"
echo "           sudo cp /boot/firmware/config.txt.bak-splash /boot/firmware/config.txt"
echo "           sudo cp $SYSAUTO.bak-splash $SYSAUTO"
echo "           sudo cp $SYSENV.bak-splash $SYSENV; rm ~/.config/labwc/environment  # pointer back"
