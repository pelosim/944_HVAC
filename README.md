# 944_HVAC

Custom HVAC / Electronic Climate Control system for a 1987 Porsche 944S restomod,
running on a Raspberry Pi 4. Replaces the OEM heater controls and a previous
Node-RED prototype with a Python backend and a touchscreen React dashboard.

## What's here

```
944_HVAC/
├── hvac_backend.py           # Python backend: hardware IO, PID loops, WebSocket server
├── kiosk.sh                  # Chromium kiosk on/off/status toggle
├── setup.sh                  # First-time Pi provisioning script
├── dashboard/                # React touchscreen UI (1920×720)
│   ├── src/
│   │   ├── HVACDashboard.jsx  # The dashboard component (main UI file)
│   │   ├── App.js            # Wrapper
│   │   ├── index.js          # React entry point
│   │   └── index.css         # Fullscreen kiosk CSS
│   ├── public/index.html
│   └── package.json
└── docs/                     # Guides
    ├── 944S_HVAC_FOR_DUMMIES.md   # Plain-English operation + deploy guide
    ├── 944S_HVAC_CHEATSHEET.md    # IO map, PID tuning, UI editing reference
    ├── DEPLOYMENT_GUIDE.md
    └── GIT_SETUP_GUIDE.md
```

## Hardware

- Raspberry Pi 4, 1920×720 IPS touchscreen (Chromium kiosk)
- DS18B20 temp sensors (1-Wire), ADS1115 ADC (I²C) for flap feedback
- Relays for blower/AC/heat-valve/fresh-air, H-bridges for blend/defrost/footwell flaps
- MOSFET PWM for BMW E90 heated seats (driver + passenger)
- MS3 Pro Evo+ engine ECU (A/C clutch handshake)

## Architecture

The **backend** owns all hardware and runs the control loops. The **dashboard**
is a thin client — every control sends a command over WebSocket, and the backend
broadcasts full state back to all connected screens at 10 Hz. HVAC keeps running
even if the display crashes.

## Quick start (on the Pi)

```bash
# Backend
cd ~/hvac && python3 hvac_backend.py

# Rebuild dashboard after UI changes
cd ~/hvac/dashboard && npm run build

# View: http://localhost:8000  (or http://<pi-ip>:8000 from another machine)
```

See `docs/944S_HVAC_FOR_DUMMIES.md` for the full operation and deployment guide.
