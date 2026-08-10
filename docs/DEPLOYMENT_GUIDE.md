# 944S HVAC — Deployment Guide

How code gets from the Mac to the car. Current as of 2026-08-06.

> This replaced a guide describing an install that no longer exists —
> `/home/pi`, a `setup.sh` bootstrap, a `hvac` service, `unclutter` on X11, and
> Node-RED to disable. None of that is true now. If you find those names
> anywhere else, they are stale.

---

## The system as it stands

| Piece | Where | Runs as |
|-------|-------|---------|
| Backend | `/home/mark/hvac/hvac_backend.py` | systemd service **`hvac-backend`** |
| Dashboard | `/home/mark/hvac/dashboard/build/` | served by the backend at `:8000` |
| Dashboard kiosk | Chromium `--kiosk`, class `hvac-dash` | labwc autostart → `HDMI-A-1` |
| Aux kiosk | Chromium `--kiosk`, class `hvac-clock` | labwc autostart → `HDMI-A-2` |

Raspberry Pi 4, Bookworm, **Wayland/labwc**, user `mark`, autologin session
`LXDE-pi-labwc`. Passwordless sudo. Python 3.11.

---

## Reaching the Pi

```bash
ssh pi944                                        # alias, key ~/.ssh/id_944pi
ssh -i ~/.ssh/id_944pi mark@192.168.1.142        # fallback
```

The alias resolves `944HVACPi.local` over mDNS. **That name does not always
resolve from the Mac** — it failed outright on 2026-08-06 with `nodename nor
servname provided`. When it does, go straight to the IP rather than assuming
the Pi is down. DHCP: eth0 `192.168.1.142`, wlan0 varies.

The Pi is often off the network entirely. The workflow assumes that.

---

## The deploy loop

Edit and commit on the Mac, push, pull on the Pi.

```bash
# Mac
cd ~/Downloads/944_HVAC_repo
git add -A && git commit -m "..." && git push origin main

# Pi
ssh pi944 'cd ~/hvac && git pull'
```

Then, depending on what changed:

| Changed | Also needed |
|---------|-------------|
| `hvac_backend.py` | `sudo systemctl restart hvac-backend` |
| `dashboard/src/*.jsx` | `cd ~/hvac/dashboard && npm run build`, then restart the backend |
| `deploy/*.sh` | run the relevant script — see below |
| kiosk/display config | `bash ~/hvac/deploy/setup-displays.sh`, then reboot |

`dashboard/build/` is gitignored and device-local. **Editing `src/` does
nothing until a rebuild.** Browser cache is the usual reason a rebuilt
dashboard still looks old — hard-refresh with Ctrl+Shift+R, or restart the
kiosk.

### Never start the backend by hand

```bash
python3 hvac_backend.py      # ← don't
```

The service is already running. A second copy fights it for port 8000 and for
the GPIO, and you get `A PWM object already exists`. Use `systemctl`. If
something is genuinely stuck on the port, `sudo fuser -k 8000/tcp`.

### The pkill footgun

Never `pkill -f hvac_backend` or `pkill -f chromium` in an SSH one-liner. The
pattern matches the SSH shell's own argv and kills your session. Use
`systemctl`, `fuser`, or name-only `pkill chromium`.

---

## Provisioning scripts

All idempotent, all in `deploy/`. Run from `~/hvac`.

| Script | Run as | Does |
|--------|--------|------|
| `install.sh` | `mark` | systemd unit, enables it, installs the labwc autostart |
| `setup-displays.sh` | `mark` | Writes `cmdline.txt` video mode, kanshi layout, labwc window rules + touch mapping — all three from one pair of constants. Reboot after |
| `boot-splash/install-splash.sh` | `sudo` | Splash images, plymouth theme, per-output wallpaper, transparent pointer, disables the panel |
| `setup-rtc.sh` | `sudo` | DS3231 RTC on I²C `0x68` |
| `check-adc.py` | `mark` | Reads both ADS1115s from raw millivolts |
| `flap-pulse.py` | `mark` | Flap movement and calibration — **stop the backend first** |

`setup-displays.sh` and `install-splash.sh` share the output→role mapping
(`HDMI-A-1` = dashboard bar, `HDMI-A-2` = round aux). Change it in both.

See [`DISPLAYS_AND_BOOT.md`](DISPLAYS_AND_BOOT.md) for what those two actually
configure and why it is more delicate than it looks.

---

## Health check

```bash
systemctl is-active hvac-backend
journalctl -u hvac-backend -f
curl -s localhost:8000/api/state | python3 -m json.tool | head -40

pgrep -cf chromium-dash ; pgrep -cf chromium-clock   # kiosks (multi-process, >1 each)
wlr-randr                                            # outputs and their geometry
tail -3 ~/hvac/kiosk.log ~/hvac/clock.log
```

Expect **~19 s from power-on to a live dashboard**. If it is closer to 70 s,
something has reintroduced a `network-online.target` dependency on
`hvac-backend.service` — see `DISPLAYS_AND_BOOT.md`.

---

## Hardware interfaces

```bash
i2cdetect -y 1                     # 48 = flap ADS1115, 68 = DS3231 RTC, 49 = accelerometer ADS
ls /sys/bus/w1/devices/28-*        # DS18B20 sensors
```

Sensor IDs in the backend have **no `28-` prefix** — `w1thermsensor` strips it.
Mixing chamber `000000bd3d51`, exterior `000000be5d11`, interior
`000000bbdd26`. The bus is re-scanned periodically, not only at startup, so a
sensor that comes back after a bad connection is picked up without a restart.

---

## Building the dashboard

```bash
cd ~/hvac/dashboard && npm run build
```

`package-lock.json` is tracked — use it. The build is fussy:

- A leftover `.eslintrc.js` referencing `airbnb` fails the build. Delete it.
- React 18 needs `createRoot` in `index.js`, not `ReactDOM.render`.

`node_modules/` and `build/` are gitignored and stay on the device.

---

## Backend invariants

These have regressed before when the file was regenerated wholesale. Keep them:

1. ADS channels via `AnalogIn(ads, 0/1/2)` — **not** `ADS.P0/P1/P2` (removed from the library).
2. `connected_clients = set()` with **no** type hint — `set[WebSocket]` breaks on Python 3.11.
3. `control_loop()` starts with `global connected_clients`.
4. `uvicorn.run(app, ...)` with the app **object**, not the string
   `"hvac_backend:app"` — the string form double-loads the module and crashes
   on GPIO PWM re-init.
5. Static mount present, absolute path:
   `app.mount("/", StaticFiles(directory="/home/mark/hvac/dashboard/build", html=True), name="dashboard")`
6. Seat-heater PWM init wrapped in `try: GPIO.cleanup(pin) except: pass`.
7. DS18B20 IDs without the `28-` prefix.

---

## Troubleshooting

**Dashboard blank, splash showing.** The kiosk polls the backend before
launching Chromium. Check `systemctl status hvac-backend` and
`tail ~/hvac/kiosk.log`.

**Screens swapped.** `wlr-randr` to see which connector is which, then
`setup-displays.sh` — do not hand-edit `rc.xml`.

**SIMULATION mode with hardware attached.** I²C or 1-Wire not enabled
(`raspi-config` → Interface Options), or `RPi.GPIO` missing. `i2cdetect -y 1`
and `ls /sys/bus/w1/devices/`.

**Flap will not move.** Check `FLAP_HELD` in `hvac_backend.py` — it is a
deliberate code-level hold, not a runtime toggle. Then check
`<flap>_flap_fault` in state: `FLAP_MAX_DRIVE_S` cuts a motor that drives 8 s
without progress.

**Wi-Fi wants a passphrase.** There is no on-screen prompt any more — the panel
that drew it is disabled. `nmcli device wifi connect <SSID> --ask` over SSH.
