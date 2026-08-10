# 944S HVAC Controller — Cheat Sheet

Reference for the running system. Every value here was read out of the source
on 2026-08-06, not carried over from an earlier draft.

Deploy mechanics live in [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md).
Screens and boot in [`DISPLAYS_AND_BOOT.md`](DISPLAYS_AND_BOOT.md).
Flap measurement in [`FLAP_CALIBRATION.md`](FLAP_CALIBRATION.md).

---

## File map

| File | Location on Pi | What it does |
|------|---------------|--------------|
| `hvac_backend.py` | `/home/mark/hvac/` | All hardware IO, PID loops, WebSocket + REST, state persistence |
| `HVACDashboard.jsx` | `dashboard/src/` | The touchscreen UI — one React component |
| `build/` | `dashboard/build/` | Compiled dashboard. Gitignored, device-local |
| `deploy/` | `~/hvac/deploy/` | Provisioning and bench tools |
| `hvac_state.json` | `~/hvac/` | Persisted user settings. Gitignored |

---

## After a change

| Changed | Do |
|---------|-----|
| `hvac_backend.py` | `sudo systemctl restart hvac-backend` |
| `HVACDashboard.jsx` | `cd ~/hvac/dashboard && npm run build`, then restart the backend, then hard-refresh |

**Never** `python3 hvac_backend.py` — the service owns port 8000 and the GPIO.

---

## GPIO map (BCM)

```python
# Relays — active-LOW (GPIO LOW = relay ON)
PIN_BLOWER_HI   = 5      PIN_BLOWER_LOW  = 6
PIN_AC_CLUTCH   = 18     # to MS3 Pro Evo+
PIN_HEAT_VALVE  = 19     PIN_OUTSIDE_AIR = 26

# H-bridges — active-HIGH
PIN_MIX_COLD  = 23   PIN_MIX_HOT  = 24     # blend
PIN_DEF_IN1   = 16   PIN_DEF_IN2  = 20     # defrost
PIN_FOOT_IN1  = 12   PIN_FOOT_IN2 = 21     # footwell

# Seat heat — PWM at 2 Hz to MOSFETs
PIN_SEAT_HEAT_DRIVER    = 13
PIN_SEAT_HEAT_PASSENGER = 25

# 1-Wire bus
GPIO 4
```

---

## Sensors

```python
SENSOR_MIX_CHAMBER = "000000bd3d51"
SENSOR_EXTERIOR    = "000000be5d11"
SENSOR_INTERIOR    = "000000bbdd26"
```

**No `28-` prefix** — `w1thermsensor` strips it. The bus is re-scanned every
`TEMP_RESCAN_S = 10.0` s, so a sensor that returns after a bad connection is
picked up without a restart.

---

## Flap feedback

ADS1115 at `0x48`, **gain 2/3** (±6.144 V — a 5 V pot clips at gain 1 and hides
a volt of travel).

```python
ADS_MIX_CHANNEL = 0   ADS_DEF_CHANNEL = 1   ADS_FOOT_CHANNEL = 2   # CH3 spare
```

Per-flap calibration — `lo`/`hi` sit 60 mV inside each measured stop, and
`invert` makes **100% mean "more"** on all three (full hot, full defrost, foot
open):

```python
FLAP_CAL = {
    ADS_MIX_CHANNEL:  {"lo": 185, "hi": 4819, "invert": True},
    ADS_DEF_CHANNEL:  {"lo": 417, "hi": 4971, "invert": True},
    ADS_FOOT_CHANNEL: {"lo": 258, "hi": 4956, "invert": True},
}
```

There is no global mV scale any more. Anything referring to `ADC_MV_MIN` /
`ADC_MV_MAX` is stale.

A **second** ADS1115 at `0x49` reads the ADXL335 for the G-meter — see
[`ACCELEROMETER_WIRING.md`](ACCELEROMETER_WIRING.md).

---

## Control constants

```python
FLAP_PID_KP = 2.0    FLAP_PID_KI = 0.5    FLAP_PID_KD = 0.1
TEMP_PID_KP = 3.0    TEMP_PID_KI = 0.3    TEMP_PID_KD = 0.5
TEMP_DEADBAND = 1.0        # °F

FLAP_DEADBAND = 0.0        # superseded by FLAP_SETTLE — one rule, one place
FLAP_SETTLE = {            # hysteresis: stop inside, re-engage outside
    "mix":  {"stop": 3.0, "start":  7.0},   # tighter — driven by a continuous PID
    "def":  {"stop": 4.0, "start": 10.0},   # diverters only move in 25% steps
    "foot": {"stop": 4.0, "start": 10.0},
}

FLAP_HELD = set()          # flaps the controller must NOT drive. Code-level, deliberate
FLAP_MAX_DRIVE_S  = 8.0    # no-progress drive time before the motor is cut
FLAP_PROGRESS_EPS = 1.5    # % of travel that still counts as moving

SENSOR_HZ = 2              # temp read rate; control loop runs at 10 Hz
```

Setpoint is clamped **60–90 °F** in `apply_command`.

---

## Vent distribution

Diverter positions are the source of truth; face is derived from them.

```python
VENT_PRESETS = {
    "face":         {"defrost":   0, "foot":  0},
    "bilevel":      {"defrost":   0, "foot": 50},
    "feet":         {"defrost":  15, "foot": 75},   # deliberate screen bleed
    "feet_defrost": {"defrost":  50, "foot": 50},
    "defrost":      {"defrost": 100, "foot":  0},
}
VENT_STEPS = [0, 25, 50, 75, 100]    # per-outlet button steps
FACE_STEPS = [25, 50, 75, 100]       # face never offers 0
DEFROST_FRESH_AIR_PCT = 75           # above this, force outside air
```

---

## REST API

```bash
curl -s localhost:8000/api/state | python3 -m json.tool

curl -X POST localhost:8000/api/command -H "Content-Type: application/json" \
  -d '{"setpoint_f": 75, "fan_speed": "HI"}'
```

Accepted command keys (`apply_command`):

| Key | Values |
|-----|--------|
| `setpoint_f` | 60–90, clamped |
| `fan_speed` | `OFF` / `LOW` / `HI` |
| `ac_on`, `heat_valve`, `outside_air` | bool |
| `vent_mode` | a `VENT_PRESETS` name |
| `vent_cycle` | `face` / `foot` / `defrost` — steps that outlet |
| `seat_heat_driver`, `seat_heat_passenger` | 0–100 |
| `test_override` | bool |
| `test_interior_temp_f` | 20–140 |
| `aux_display` | `clock` / `gmeter` — round panel page |
| `system_view` | bool or `toggle` |
| `tsdash` | `next` / `prev` / `cfg` / `home` — pages the TunerStudio dash |

Every command persists user settings to `hvac_state.json`.

The dashboard itself uses the WebSocket at `ws://<host>/ws`, reconnecting every
2 s. State is broadcast to all clients each tick.

---

## Dashboard

1920×720, three edge-to-edge horizontal bands — `gridTemplateRows: "70px 1fr
240px"`: header rail / instrument band / control rail. No dead space top or
bottom.

Palette (`const C` at the top of the JSX):

```javascript
vfd:   "#2ce8d8"   // phosphor teal — primary
amber: "#ffb000"   // heat
ice:   "#5cb8ff"   // A/C
green: "#3aff8c"   red: "#ff3b30"
bg:    "#04070a"   fascia: "#0a0e13"
text:  "#eaf6f4"   mid: "#8ea6a3"   dim: "#46565a"
```

House rules: labels ≥19px, button text ≥20px, icons ≥42px — bigger when in
doubt. Icons are **inline vector SVG**, never emoji (they render pixelated).

---

## Simulation vs hardware

Auto-detected at startup. `SIMULATE = True` near the top forces simulation, and
it always simulates on the Mac (no `RPi.GPIO`).

| Log line | Meaning |
|----------|---------|
| `HARDWARE mode` | Real GPIO and sensors |
| `SIMULATION mode` | Fake values, no outputs |
| `ADS1115 init failed` | Flap feedback dead; everything else still runs |

---

## Diagnostics

```bash
systemctl is-active hvac-backend
journalctl -u hvac-backend -f

i2cdetect -y 1                  # 48 flap ADC · 49 accelerometer ADC · 68 RTC
ls /sys/bus/w1/devices/28-*

sudo systemctl stop hvac-backend
python3 deploy/check-adc.py                    # raw mV, both ADS1115s
python3 deploy/flap-pulse.py check             # flap positions, no motion
sudo systemctl start hvac-backend
```

Do not drive a flap with a raw `RPi.GPIO` one-liner. `flap-pulse.py pulse` has
the stall detection, the sanity band and the guaranteed motors-off on exit.

---

## Common tasks

| I want to... | Do this |
|-------------|---------|
| View the dashboard from the Mac | `http://192.168.1.142:8000` |
| Change a GPIO pin / PID gain | Edit the constant, restart the service |
| Change UI layout or colours | Edit the JSX, `npm run build`, restart, hard-refresh |
| Re-measure a flap | `FLAP_CALIBRATION.md` — stop the backend first |
| Stop a flap being driven | Add its key to `FLAP_HELD` (`mix` / `def` / `foot`) |
| Swap the round panel's page | `{"aux_display": "clock"}` or `"gmeter"` |
| See which screen is which | `wlr-randr` |
| Live logs | `journalctl -u hvac-backend -f` |
