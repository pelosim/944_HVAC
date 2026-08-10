# 944S HVAC — Displays and Boot

Everything between pressing the power button and the dashboard being on screen.
Written 2026-08-06, after the two-screen install was finished and verified.

The HVAC control loop does not depend on any of this. The backend is a systemd
service that owns the hardware; the screens are Chromium kiosks pointed at it.
If the display stack breaks entirely, the car still heats and cools.

---

## The two panels

| Connector | Panel | Resolution | Shows | Touch |
|-----------|-------|-----------|-------|-------|
| `HDMI-A-1` | WaveShare WSD123 bar | 1920×720 | HVAC dashboard | yes |
| `HDMI-A-2` | LTM ZL480 round gauge | 480×480 | `aux.html` — Sport Chrono clock **or** G-meter | no |

The round panel switches between clock and G-meter live, from `aux_display` in
backend state, set from the dashboard. The kiosk never restarts to change page.

> **These connector assignments are load-bearing.** They were reversed once
> (2026-08-06) when the harness was loomed for its final routing, and the
> dashboard came up on the round gauge. Nothing detects this automatically.

---

## Three files have to agree

Which panel is which is stated in three unrelated places. If they disagree, the
screens swap, come up at the wrong resolution, or both.

| File | What it sets | Why it exists |
|------|-------------|---------------|
| `/boot/firmware/cmdline.txt` | `video=HDMI-A-1:1920x720M@60e` | The bar's EDID is not always readable when KMS probes it, so the mode is forced |
| `~/.config/kanshi/config` | Which output sits where | Position, and explicit modes so nothing depends on "preferred" |
| `~/.config/labwc/rc.xml` | `MoveToOutput` per window, touch mapping | Pins each kiosk to its panel, and the touchscreen to the bar |

**Do not hand-edit these.** Run the script that writes all three from one pair
of constants:

```bash
bash ~/hvac/deploy/setup-displays.sh
```

To move the cables, swap `OUT_DASH` / `OUT_AUX` at the top of that script and
re-run it. `wlr-randr` tells you which connector is which.

Only force **one** `video=` line, and only on the bar. Forcing 1920×720 onto
the round panel leaves it advertising a mode it cannot display.

---

## Why the kiosks used to swap screens at random

Worth understanding before touching the autostart, because the symptom looked
like flaky hardware.

`/etc/xdg/labwc/autostart` (the system one, which also starts `pcmanfm` and
`kanshi`) runs at the same moment as `~/.config/labwc/autostart` (ours, which
starts the two kiosks). labwc evaluates its `MoveToOutput` window rules **when
a window maps**. A Chromium that mapped before kanshi had laid the outputs out
was pinned to an output that did not exist yet — and with `matchOnce="true"`
it never got a second chance. Whichever kiosk won that race kept its screen.

Two changes fixed it, and both are needed:

1. `~/.config/labwc/autostart` waits for both outputs to be **enabled and
   positioned** *and* for `kanshi` to be running, before launching anything.
   The kanshi check is not redundant: the current layout (bar at 0,0, round at
   1920,0) is also labwc's own left-to-right default, so geometry alone cannot
   distinguish "kanshi applied the profile" from "kanshi has not started".
2. The window rules are `matchOnce="false"`, so a late output still catches
   them.

Verified over four consecutive reboots.

---

## Boot visuals

Every stock Raspberry Pi boot visual is suppressed, in the order it would
otherwise appear:

| Stage | Stock behaviour | Suppressed by |
|-------|----------------|---------------|
| Firmware | rainbow square | `disable_splash=1` in `config.txt` |
| Kernel | four raspberries, blinking cursor | `logo.nologo`, `vt.global_cursor_default=0`, `loglevel=3` |
| Plymouth | Pi splash | the `944s` theme |
| Desktop | wallpaper, taskbar, notifications | per-output wallpaper, panel not started |
| Pointer | white arrow | transparent Xcursor theme |

All of it is installed by one idempotent script:

```bash
sudo bash ~/hvac/deploy/boot-splash/install-splash.sh
```

### The splash images

Two, chosen **by aspect ratio** rather than by output index, so they cannot
swap if the connectors ever do:

- `splash-main.png` — the 944S, 1920×720, goes to any wide output
- `splash-aux.png` — the Stuttgart crest, 640×640, goes to any square output

Plymouth gives each connected output its own window; `944s.script` walks them,
picks by aspect, scales to fit and centres on black. The same two images are
also set as the desktop wallpaper, so the handoff from plymouth to the desktop
to Chromium is invisible rather than a race to be won.

### Three traps in the desktop layer

Each of these looked applied and did nothing:

1. **pcmanfm keeps one config per output** — `desktop-items-HDMI-A-1.conf`,
   `desktop-items-HDMI-A-2.conf` — and falls back to the stock wallpaper for
   any output it has no file for. Patching only the file that already exists
   leaves the second screen on `fisherman.jpg`.
2. **`wallpaper_common` selects across workspaces, not monitors.** The
   per-output file is what picks the per-output image. Setting it to `0` sends
   pcmanfm looking for per-workspace settings that do not exist here, and it
   paints **nothing** — both screens go black.
3. **`desktop_bg` paints the letterbox.** `wallpaper_mode=fit` on a square
   image leaves bars either side on the bar panel, in the stock lavender,
   unless `desktop_bg` is also black.

### The pointer needs three settings, not one

There is no idle-hide in labwc, and `unclutter` is X11-only. The pointer is
hidden by giving clients a cursor theme (`/usr/share/icons/blank`) whose every
image is one transparent pixel. Setting `XCURSOR_THEME` alone is **not enough**:

- The session runs `labwc -m` (merge). It reads the user's `environment` and
  *then* `/etc/xdg/labwc/environment`, and the later assignment wins — so the
  system file's `XCURSOR_THEME=PiXflat` silently overrode the user's. Both are
  set now.
- On Wayland every client draws its own pointer. GTK clients take the theme
  from `gtk-cursor-theme-name` and the xdg-desktop-portal dconf key, not from
  the environment. `pcmanfm` is a GTK client and is the only surface the arrow
  was ever visible on — Chromium's kiosk never drew one.

This hides the pointer **always**, not just when idle, including over VNC.

### Notifications

The "You are now connected to the wireless network ..." bubbles and the Wi-Fi
passphrase dialog both come from `wf-panel-pi`. There is no notification daemon
on this system to disable instead, and killing the panel only makes `lwrespawn`
restart it — so it is commented out of `/etc/xdg/labwc/autostart`.

> **Consequence:** there is no longer an on-screen prompt if Wi-Fi needs a new
> passphrase. Use `nmcli device wifi connect <SSID> --ask` over SSH. Wi-Fi
> itself is untouched and enabled.

---

## Boot timing

```
0s      power on
~2s     kernel
~13s    userspace done, session up
~9s     hvac-backend active
~19s    dashboard on screen
```

It used to be **72s**. `hvac-backend.service` depended on
`network-online.target`, which pulls in `NetworkManager-wait-online.service`,
which burns its **full 60 s timeout** whenever wlan0 cannot associate. The
backend started a minute late and the kiosk sat on the splash waiting for it.

The unit is `After=network.target` now. Nothing in the backend needs a routable
address — it binds `0.0.0.0` and the dashboard reaches it over loopback. **In
the car there is no Wi-Fi at all, so this was going to cost 60 s on every
start.** Do not reintroduce that dependency.

---

## VNC

`wayvnc.service` serves **one output at a time** on `:5900`. This build
double-frees on `output=` config pinning, and a second instance cannot read the
root-only TLS keys, so there is no second instance. Switch which screen it
shows:

```bash
sudo wayvncctl --socket=/tmp/wayvnc/wayvncctl.sock output-set HDMI-A-1  # dashboard
sudo wayvncctl --socket=/tmp/wayvnc/wayvncctl.sock output-set HDMI-A-2  # aux
```

---

## Checking it

```bash
wlr-randr                                   # which connector is which, and where
grep -a "outputs settled" ~/hvac/kiosk.log  # how long the gate waited
tail -3 ~/hvac/kiosk.log ~/hvac/clock.log   # kiosk launches

# screenshot either panel without a VNC session (-c includes the cursor)
export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000
grim -c -o HDMI-A-1 /tmp/dash.png
grim -c -o HDMI-A-2 /tmp/aux.png
```

**Never** `pkill -f chromium` or `pkill -f hvac_backend` in an SSH one-liner:
the pattern matches the SSH shell's own argv and kills your session. Use
`systemctl`, `fuser -k 8000/tcp`, or name-only `pkill chromium`.

---

## Undoing it

`install-splash.sh` prints these when it finishes. Every file it edits is
backed up first.

```bash
sudo plymouth-set-default-theme -R bgrt
sudo cp /boot/firmware/cmdline.txt.bak-splash /boot/firmware/cmdline.txt
sudo cp /boot/firmware/config.txt.bak-splash  /boot/firmware/config.txt
sudo cp /etc/xdg/labwc/autostart.bak-splash   /etc/xdg/labwc/autostart   # panel back
sudo cp /etc/xdg/labwc/environment.bak-splash /etc/xdg/labwc/environment # pointer back
rm ~/.config/labwc/environment
```

`cmdline.txt` **must stay one line**. A stray newline truncates the kernel args
and the Pi boots with no `root=` and no video mode.
