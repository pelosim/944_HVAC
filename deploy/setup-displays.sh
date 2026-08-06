#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Pin the two HDMI panels to their jobs on the 944S HVAC Pi.
#
#   bash ~/hvac/deploy/setup-displays.sh        (as 'mark', not sudo)
#
# The wiring this assumes — matches how the harness is loomed in the car:
#
#   HDMI-A-1   WaveShare WSD123, 1920x720 bar, ILI touch  ->  HVAC dashboard
#   HDMI-A-2   LTM ZL480, 480x480 round panel             ->  aux clock / G-meter
#
# Three files have to agree on that or the screens swap:
#   1. /boot/firmware/cmdline.txt   forces the bar's mode at KMS time
#   2. ~/.config/kanshi/config      lays the two outputs out side by side
#   3. ~/.config/labwc/rc.xml       pins each kiosk window to its output
#
# If you ever move the cables, run `wlr-randr` to see which connector is
# which and re-run this with the two OUT_* values below swapped.
#
# Idempotent. Backs up every file it touches. Reboot to apply.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

OUT_DASH=HDMI-A-1        # the 1920x720 bar
OUT_AUX=HDMI-A-2         # the 480x480 round panel
TOUCH_DEV="WaveShare WSD123"   # `sudo libinput list-devices` -> Device:
STAMP="$(date +%Y%m%d_%H%M%S)"

[ "$(id -u)" != 0 ] || { echo "run as 'mark', not with sudo" >&2; exit 2; }

echo "==> dashboard on $OUT_DASH, aux on $OUT_AUX"

# ── 1. Kernel video mode ─────────────────────────────────────
# The bar panel's EDID is not always up by the time KMS probes it, so the
# mode is forced. Only ONE video= arg, and only on the bar — forcing
# 1920x720 onto the round panel leaves it advertising a mode it cannot show.
CL=/boot/firmware/cmdline.txt
sudo cp -n "$CL" "$CL.bak-displays" 2>/dev/null || true
sudo python3 - "$CL" "$OUT_DASH" <<'PY'
import sys, pathlib, re
p, out = pathlib.Path(sys.argv[1]), sys.argv[2]
# cmdline.txt MUST stay ONE line — a stray newline truncates the kernel args
# and the Pi boots with no root= and no video mode.
parts = [x for x in p.read_text().split() if not x.startswith("video=")]
parts.append(f"video={out}:1920x720M@60e")
assert any(x.startswith("root=") for x in parts), "refusing to write a cmdline with no root="
p.write_text(" ".join(parts) + "\n")
PY
echo "    cmdline: $(grep -o 'video=[^ ]*' $CL)"

# ── 2. Output layout (kanshi) ────────────────────────────────
# kanshi picks the profile whose outputs exactly match what is plugged in,
# so each combination needs its own profile. Modes are stated explicitly;
# left to itself kanshi takes whatever the panel calls "preferred", and the
# round panel's preferred mode changes depending on what cmdline forced.
KD="$HOME/.config/kanshi"
mkdir -p "$KD"
[ -f "$KD/config" ] && cp "$KD/config" "$KD/config.bak.$STAMP"
cat > "$KD/config" <<EOF
# Written by deploy/setup-displays.sh — edit there, not here.
#   $OUT_DASH = 1920x720 bar   -> HVAC dashboard
#   $OUT_AUX = 480x480 round  -> aux clock / G-meter
profile dual {
    output $OUT_DASH mode 1920x720 position 0,0
    output $OUT_AUX mode 480x480 position 1920,0
}
profile dashonly {
    output $OUT_DASH mode 1920x720 position 0,0
}
profile auxonly {
    output $OUT_AUX mode 480x480 position 0,0
}
EOF
echo "    kanshi: $KD/config"

# ── 3. Window pinning + touch mapping (labwc) ────────────────
RC="$HOME/.config/labwc/rc.xml"
mkdir -p "$HOME/.config/labwc"
[ -f "$RC" ] || printf '<?xml version="1.0"?>\n<openbox_config xmlns="http://openbox.org/3.4/rc">\n</openbox_config>\n' > "$RC"
cp "$RC" "$RC.bak.$STAMP"
python3 - "$RC" "$OUT_DASH" "$OUT_AUX" "$TOUCH_DEV" <<'PY'
import sys, re, pathlib
rc, dash, aux, touch = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = pathlib.Path(rc); s = p.read_text()

# matchOnce="false" is the whole point: labwc evaluates window rules when a
# window maps, and the two kiosks race kanshi's output layout at login. With
# matchOnce="true" a kiosk that mapped before its output existed was pinned
# nowhere and stayed there. Re-evaluating on later property changes lets the
# rule land once the output actually shows up.
rules = (
    "<windowRules>"
    f'<windowRule identifier="hvac-dash" matchOnce="false">'
    f'<action name="MoveToOutput" output="{dash}"/></windowRule>'
    f'<windowRule identifier="hvac-clock" matchOnce="false">'
    f'<action name="MoveToOutput" output="{aux}"/></windowRule>'
    "</windowRules>"
)
touch_el = f'<touch deviceName="{touch}" mapToOutput="{dash}" mouseEmulation="yes"/>'

if "<windowRules>" in s:
    s = re.sub(r"<windowRules>.*?</windowRules>", lambda _: rules, s, flags=re.S)
else:
    s = s.replace("</openbox_config>", rules + "</openbox_config>")

if "<touch " in s:
    s = re.sub(r"<touch\b[^>]*/>", lambda _: touch_el, s)
else:
    s = s.replace("</openbox_config>", touch_el + "</openbox_config>")

p.write_text(s)
PY
echo "    rc.xml:  hvac-dash -> $OUT_DASH, hvac-clock -> $OUT_AUX, touch -> $OUT_DASH"

# ── 4. Autostart (gates the kiosks on the outputs being up) ──
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
install -m 0755 "$REPO_DIR/deploy/labwc-autostart" "$HOME/.config/labwc/autostart"
chmod +x "$REPO_DIR/deploy/kiosk-launch.sh" "$REPO_DIR/deploy/aux-launch.sh"
echo "    autostart installed"

echo
echo "==> Done. Reboot for the cmdline change; then check with:"
echo "    wlr-randr"
echo "    tail -3 ~/hvac/kiosk.log ~/hvac/clock.log"
