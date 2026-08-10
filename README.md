# 944_HVAC

Custom HVAC / Electronic Climate Control for a 1987 Porsche 944S restomod,
running on a Raspberry Pi 4. Replaces the OEM heater controls and an earlier
Node-RED prototype with a Python backend and a touchscreen React dashboard.

## What's here

```
944_HVAC/
├── hvac_backend.py            # Backend: hardware IO, PID loops, WebSocket + REST
├── dashboard/                 # React touchscreen UI (1920×720)
│   └── src/HVACDashboard.jsx  #   the whole UI, one component
├── deploy/                    # Provisioning and bench tools
│   ├── install.sh             #   systemd unit + labwc autostart
│   ├── setup-displays.sh      #   pins each panel to its job (3 config files)
│   ├── setup-rtc.sh           #   DS3231 RTC
│   ├── hvac-backend.service   #   the systemd unit
│   ├── kiosk-launch.sh        #   dashboard kiosk (HDMI-A-1)
│   ├── aux-launch.sh          #   clock / G-meter kiosk (HDMI-A-2)
│   ├── labwc-autostart        #   waits for outputs, then starts both kiosks
│   ├── boot-splash/           #   plymouth theme, splash art, install script
│   ├── flap-pulse.py          #   flap movement + calibration (bench)
│   └── check-adc.py           #   raw millivolts from both ADS1115s
└── docs/
    ├── DEPLOYMENT_GUIDE.md       # how code gets to the car
    ├── 944S_HVAC_CHEATSHEET.md   # IO map, constants, API, diagnostics
    ├── DISPLAYS_AND_BOOT.md      # two screens, kiosks, splash, boot timing
    ├── FLAP_CALIBRATION.md       # measuring the flap actuators
    ├── ACCELEROMETER_WIRING.md   # ADXL335 for the G-meter
    ├── 944S_HVAC_FOR_DUMMIES.md  # plain-English operation
    └── GIT_SETUP_GUIDE.md
```

## Hardware

- Raspberry Pi 4, Bookworm, Wayland/labwc
- **Two** displays: 1920×720 touchscreen bar (dashboard) + 480×480 round gauge
  (Sport Chrono clock / G-meter)
- DS18B20 temp sensors (1-Wire), ADS1115 at `0x48` for flap feedback, a second
  at `0x49` for the ADXL335 accelerometer, DS3231 RTC at `0x68`
- Relays for blower / A-C clutch / heat valve / fresh air; H-bridges for the
  blend, defrost and footwell flaps
- MOSFET PWM for BMW E90 heated seats
- MS3 Pro Evo+ engine ECU (A/C clutch handshake)

## Architecture

The **backend** owns all hardware and runs the control loops at 10 Hz. The
**dashboard** is a thin client — every control sends a command over WebSocket,
and the backend broadcasts full state back to all connected screens. HVAC keeps
running even if a display crashes.

## Quick start (on the Pi)

```bash
sudo systemctl restart hvac-backend        # after a backend change
cd ~/hvac/dashboard && npm run build       # after a UI change

curl -s localhost:8000/api/state | python3 -m json.tool
journalctl -u hvac-backend -f
```

The backend runs as a systemd service — do **not** start it by hand with
`python3 hvac_backend.py`. See [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md).

## Current state (2026-08-06)

- Both screens pinned and verified stable across reboots; ~19 s from power-on
  to a live dashboard
- Blend flap calibrated on its permanent linkage and no longer held —
  **its hot/cold direction is still unverified**, pending a running engine.
  See [`docs/FLAP_CALIBRATION.md`](docs/FLAP_CALIBRATION.md)
