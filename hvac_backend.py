#!/usr/bin/env python3
"""
944S HVAC Controller — Python Backend
======================================
Hardware interface + PID control loops + WebSocket API for React dashboard.

Architecture:
  ┌─────────────────────────────────────────────────────────────────┐
  │  React Dashboard (Chromium kiosk @ localhost:8000)              │
  │    ↕ WebSocket (ws://localhost:8000/ws)                         │
  ├─────────────────────────────────────────────────────────────────┤
  │  FastAPI Server (this file)                                     │
  │    ├── HardwareManager — GPIO, 1-Wire, I2C                     │
  │    ├── PIDController — flap position control                   │
  │    ├── HVACStateMachine — mode logic, safety interlocks         │
  │    └── ControlLoop — 10Hz background task                      │
  └─────────────────────────────────────────────────────────────────┘

GPIO Map (active-low relays, active-high H-bridges):
  GPIO  5  — Blower HI relay (active-low: 0=ON)
  GPIO  6  — Blower LOW relay (active-low: 0=ON)
  GPIO 13  — Seat heater DRIVER (PWM to MOSFET board)
  GPIO 18  — AC clutch command to MS3 (RLY1, active-low)
  GPIO 19  — Heating valve solenoid (RLY2, active-low)
  GPIO 25  — Seat heater PASSENGER (PWM to MOSFET board)
  GPIO 26  — Outside air solenoid (RLY3, active-low)
  GPIO 23  — Mixing flap H-bridge IN1 (COLD direction)
  GPIO 24  — Mixing flap H-bridge IN2 (HOT direction)
  GPIO 16  — Defrost flap H-bridge IN1
  GPIO 20  — Defrost flap H-bridge IN2
  GPIO 12  — Footwell flap H-bridge IN1
  GPIO 21  — Footwell flap H-bridge IN2

DS18B20 (1-Wire, GPIO 4):
  28-000000bd3d51 — Mixing chamber temp
  28-000000be5d11 — Exterior temp
  28-000000bbdd26 — Interior (cabin) temp

ADS1115 (I2C 0x48):
  CH0 — Mixing flap position feedback    (225–4090 mV → 0–100%)
  CH1 — Defrost flap position feedback    (225–4090 mV → 0–100%)
  CH2 — Footwell flap position feedback   (225–4090 mV → 0–100%)
  CH3 — (spare)

Install:
  pip install fastapi uvicorn websockets --break-system-packages
  pip install RPi.GPIO w1thermsensor adafruit-circuitpython-ads1x15 --break-system-packages
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration — edit these to match your wiring
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# --- GPIO Pin Assignments (BCM) ---
PIN_BLOWER_HI   = 5     # Relay, active-low
PIN_BLOWER_LOW  = 6     # Relay, active-low
PIN_AC_CLUTCH   = 18    # Relay to MS3, active-low
PIN_HEAT_VALVE  = 19    # Solenoid relay, active-low
PIN_OUTSIDE_AIR = 26    # Solenoid relay, active-low

PIN_MIX_COLD    = 23    # H-bridge IN1 — drives mixing flap toward COLD
PIN_MIX_HOT     = 24    # H-bridge IN2 — drives mixing flap toward HOT
PIN_DEF_IN1     = 16    # H-bridge IN1 — defroster flap
PIN_DEF_IN2     = 20    # H-bridge IN2 — defroster flap
PIN_FOOT_IN1    = 12    # H-bridge IN1 — footwell flap
PIN_FOOT_IN2    = 21    # H-bridge IN2 — footwell flap

# --- Seat Heater PWM Outputs ---
# Drive MOSFET boards (e.g., IRF520 or BTS7960) to heating elements
# Bypass BMW E90 seat modules — Pi controls elements directly
PIN_SEAT_HEAT_DRIVER    = 13   # PWM to driver seat MOSFET
PIN_SEAT_HEAT_PASSENGER = 25   # PWM to passenger seat MOSFET

# Seat heater PWM config
SEAT_HEAT_PWM_FREQ = 2    # Hz — slow cycle, same as OEM modules
SEAT_HEAT_PRESETS = {      # Named presets → duty cycle %
    "OFF": 0,
    "LOW": 33,
    "MED": 66,
    "HIGH": 100,
}

# --- DS18B20 Sensor IDs (w1thermsensor reports IDs WITHOUT "28-" prefix) ---
SENSOR_MIX_CHAMBER = "000000bd3d51"
SENSOR_EXTERIOR    = "000000be5d11"
SENSOR_INTERIOR    = "000000bbdd26"

# --- State persistence ---
# User settings survive power loss; saved on every command
STATE_FILE = "/home/mark/hvac/hvac_state.json"
PERSISTED_FIELDS = ["setpoint_f", "fan_speed", "ac_on", "heat_valve",
                    "outside_air", "vent_mode", "seat_heat_driver", "seat_heat_passenger"]

# --- Persistent state file (survives power loss) ---
STATE_FILE = "/home/mark/hvac/hvac_state.json"

# --- ADS1115 ---
ADS_I2C_ADDR       = 0x48
ADS_MIX_CHANNEL    = 0   # P0 — mixing flap feedback
ADS_DEF_CHANNEL    = 1   # P1 — defroster flap feedback
ADS_FOOT_CHANNEL   = 2   # P2 — footwell flap feedback

# --- Vent distribution -------------------------------------------
# There is no face flap. Defrost and footwell are DIVERTERS, and face gets
# whatever they do not take — which is why face can only ever be commanded
# indirectly, by making room for it.
#
# These are flap POSITIONS, not airflow shares. Ducting is nonlinear and the
# split shifts with fan speed, so 50% foot is a position you learn the feel
# of, not half the air. Repeatable and controllable; not a measurement.
VENT_PRESETS = {
    "face":         {"defrost":   0, "foot":  0},
    "bilevel":      {"defrost":   0, "foot": 50},
    # 15% defrost in FOOT is a deliberate bleed to keep the screen clear —
    # production cars do the same, for the same reason outside air is forced
    # below when defrost is high.
    "feet":         {"defrost":  15, "foot": 75},
    "feet_defrost": {"defrost":  50, "foot": 50},
    "defrost":      {"defrost": 100, "foot":  0},
}
VENT_MODE_ORDER = ["face", "bilevel", "feet", "feet_defrost", "defrost"]

# Button steps. Face never offers 0: it is the default path, "no face at all"
# is not a thing the ducting does, and a step nobody wants costs a press
# every time round the cycle.
VENT_STEPS = [0, 25, 50, 75, 100]
FACE_STEPS = [25, 50, 75, 100]

# Above this much defrost, force outside air — recirculated air fogs a screen.
DEFROST_FRESH_AIR_PCT = 75

# --- Per-flap feedback calibration -------------------------------
# Measured end stop to end stop with deploy/flap-pulse.py on 2026-08-02,
# at ADC gain 2/3. One global pair could never have worked: the three
# spans differ by hundreds of mV, and the old 225/4090 stopped a full
# volt short of the real top, so the last fifth of travel reported 100%
# before the flap got there.
#
# lo/hi are held 60 mV INSIDE each measured stop so the PID settles just
# short of the mechanical limit instead of leaning on it.
#
# invert=True means the pot runs backwards relative to the sense we want
# to publish. Blend is the case: GPIO24 is the HOT drive and it moves the
# pot DOWN, so raw-low is hot — and the control logic wants 100% = hot.
FLAP_CAL = {
    # Blend re-measured 2026-08-06 on the PERMANENT LINKAGE, flap-pulse.py
    # --gentle, after setting the door against a known actuator datum. Motion
    # ended at 125 and 4879 mV (peaking 4896), which is within 14 and 11 mV of
    # the actuator's OWN free stops measured the same day with the arm off:
    # 111 and 4907. The door is no longer what limits travel — the linkage
    # costs 34 mV of 4788, against 108 mV on the temporary one it replaced.
    #
    # Back to the usual 60 mV margin. The 120 mV used before was doubled
    # specifically because the linkage was temporary, and it no longer is.
    #
    # DIRECTION IS NOT VERIFIED. invert=True says raw-low (the GPIO24/in2 end,
    # where the flap now sits) is HOT and publishes as 100%. That follows the
    # in1=COLD/in2=HOT record in flap-pulse.py, but the door is not visible
    # with the dash in and could not be confirmed by eye on 2026-08-06. The
    # span and the linearity are measured and trustworthy; only the SENSE is
    # inherited. To settle it, run the engine to temperature, command full
    # heat, and feel the duct: if it blows cold, flip this one flag to False
    # and nothing else — the limits stay correct either way, because they
    # describe travel, not direction.
    ADS_MIX_CHANNEL:  {"lo":  185, "hi": 4819, "invert": True},   # blend
    # Both confirmed against the physical flaps on 2026-08-02: defrost read
    # 0% while fully OPEN, footwell read 100% while fully CLOSED. Both
    # inverted, so on all three flaps 100% now means "more" — full hot,
    # full defrost, foot open.
    ADS_DEF_CHANNEL:  {"lo":  417, "hi": 4971, "invert": True},   # defrost
    ADS_FOOT_CHANNEL: {"lo":  258, "hi": 4956, "invert": True},   # footwell
}

# --- Accelerometer: ADXL335 on a second ADS1115 -------------------
# Mounted flat and square to the car (docs/ACCELEROMETER_WIRING.md §4):
#   A0 = X = left/right  -> g_lateral       (+ = right-hand turn)
#   A1 = Y = rear/front  -> g_longitudinal  (+ = acceleration)
#   A2 = Z = down/up     -> sanity only; should read ~1 g at rest
ACCEL_I2C_ADDR = 0x49
ACCEL_CH = {"x": 0, "y": 1, "z": 2}
ACCEL_REF_CH = 3          # wired to nothing — the floating-pin reference

# Datasheet typicals at 3.3 V. Replace with a real 6-point tumble
# calibration once the sensor is in its final mounting — see §6. Measured
# on the bench 2026-08-02: Y 1646 mV and Z 1986 mV at rest, both within
# 6 mV of these, so the part is close to typical.
ACCEL_ZERO_MV = 1650.0
ACCEL_MV_PER_G = 330.0

# An axis reading within this of the unused A3 pin is not connected. A
# floating ADC input does not read zero — it settles wherever leakage puts
# it, and every floating pin on the same chip settles in the same place.
# Without this check a disconnected axis reports a confident, wrong g.
ACCEL_FLOAT_MV = 25.0

# Sign flips, applied after the zero offset. Set these from the car, not
# from the bench: push the nose down and g_longitudinal must go NEGATIVE
# (braking), roll right and g_lateral must go POSITIVE.
ACCEL_INVERT_X = False
ACCEL_INVERT_Y = False

# --- iBooster CAN (read-only) --------------------------------------
# Tesla Gen1 iBooster on two private 2-node CAN buses, via the two CANable
# adapters pinned by udev to can-veh / can-yaw (see the tesla-ibooster-can
# repo's deploy/). Decode constants come from that repo's docs/DECODE.md and
# were measured on this exact unit — do not "correct" them from community
# sources, which describe other variants.
#
# READ-ONLY IS STRUCTURAL: this file opens raw AF_CAN sockets and only ever
# recv()s. There is no send path, and none may be added — the device on the
# other end is a brake actuator. The interfaces must stay in normal (ACK)
# mode, which deploy/ibooster-can-up already guarantees: link-layer ACK is
# not a command, and listen-only on a 2-node bus drives the booster bus-off.
BOOSTER_IFACES = {"canveh": "can-veh", "canyaw": "can-yaw"}
BOOSTER_STALE_S = 2.0      # 0x39D arrives at 25 Hz — 2 s is 50 missed frames

# --- Steering CAN: 2004-2009 Prius (NHW20) EPS — FRAMEWORK ONLY ----
# NOTHING HERE IS DECODED. No CAN ID, bitrate, signal or scaling for this
# column has been measured, and none is asserted below. The screen exists so
# the raw bus can be explored the same way the iBooster's was — capture,
# rank fields by smoothness, hold known positions — not because anything is
# known yet. Community figures for other Toyota EPS units are NOT carried
# over; that mistake would have put a wrong 0x38E full-scale into the brake
# decode had it not been checked against this unit.
#
# Bitrate is a guess until measured. 500 kbps is the usual Toyota chassis
# rate, so the interface is brought up there, but treat a silent bus as
# "wrong rate" before "dead unit" — see the iBooster bench log.
#
# ⚠️ ARCHITECTURAL UNKNOWN, and it is the important one. The iBooster
# assists standalone, which is what made a passive monitor sufficient. EPS
# columns are widely reported to require CAN traffic before they will
# assist at all. If that holds here, read-only monitoring cannot be the end
# state for steering, and commanding a steering actuator is a different
# safety conversation than anything in this project so far. Answer that
# BEFORE building anything past this framework. This file has no send path.
STEER_IFACE = "can-steer"          # third adapter — NOT PRESENT YET
STEER_STALE_S = 2.0

# Every CAN link this process reads. Reader threads are identical; only the
# per-ID decode below differs, and only for the two booster buses.
CAN_IFACES = {"canveh": "can-veh", "canyaw": "can-yaw", "cansteer": STEER_IFACE}

# 0x39D (vehicle bus): b2:b3 = stroke, uint16 LE. Combined 5-point fit.
BRAKE_STROKE_SCALE  = 320.68     # counts per mm
BRAKE_STROKE_OFFSET = 3.3
# Physical end stop measured at 13606 counts. On a latched fault the booster
# pins the stroke to a SENTINEL (16354) with a still-valid checksum, so
# anything past the end stop is fault signalling, not travel.
BRAKE_STROKE_SENTINEL = 13700

# 0x38E (YAW bus): position = b3 | ((b4 & 0x0F) << 8)  (12-bit — the high
# nibble of b4 is STATUS, not position; only an induced fault revealed that).
# status: 1 = healthy, 2 = fault. THE FAULT LATCHES: reconnecting the sensor
# does not clear it and assist stays off until the booster is power-cycled.
# status==2 therefore means "assist unavailable", NOT "position invalid" —
# after a reconnect 0x38E resumes live position while still reporting 2.
BRAKE_POS_SCALE  = 0.015207      # mm per count
BRAKE_POS_OFFSET = 1.94

# --- Brake pressure sensors (ON ORDER — not yet fitted) ------------
# Two transducers, one per hydraulic circuit. ADS channel audit 2026-08-10:
#   0x48  P0/P1/P2 flaps, P3 FREE          -> one channel available
#   0x49  X/Y/Z accel + P3 floating ref    -> full; the ref is load-bearing
#         (the disconnected-axis check compares against it — do not steal it)
# Two sensors therefore need a THIRD ADS1115 at 0x4A (ADDR strapped to SDA).
# When the parts arrive: set INSTALLED True and fill in the transfer function
# from the sensor datasheet (typically 0.5–4.5 V ratiometric).
BRAKE_PRESS_INSTALLED = False
BRAKE_PRESS_I2C_ADDR  = 0x4A
BRAKE_PRESS_CH_FRONT  = 0
BRAKE_PRESS_CH_REAR   = 1

# --- PID Tuning ---
# These are starting points — tune on the car
FLAP_PID_KP = 2.0    # Proportional gain
FLAP_PID_KI = 0.5    # Integral gain
FLAP_PID_KD = 0.1    # Derivative gain
# Settling band, WITH HYSTERESIS. The old single 2% deadband had none: stop
# at 2, start at 2. A flap that parks just under the edge — measured wandering
# 1.14 to 1.66% — crosses it on any drift and kicks the motor, over and over.
# That is the chatter, and it is not a tuning problem you can gain your way
# out of, because drive_hbridge() is bang-bang: there is no PWM on these pins,
# so ANY non-zero command is full motor power. The PID's carefully scaled
# magnitude is discarded and only its sign survives.
#
# So: stop when close, and refuse to start again until the error is large
# enough to be worth a motor movement. These are air flaps — a few percent of
# travel is not perceptible, and every avoided kick is motor life.
#
# The blend flap gets a tighter pair than the diverters because it is the
# temperature element, driven by an outer PID that moves its target
# continuously. The diverters only ever move in 25% button steps, so a 10%
# re-engage threshold there can never block a real command.
FLAP_SETTLE = {
    "mix":  {"stop": 3.0, "start":  7.0},
    "def":  {"stop": 4.0, "start": 10.0},
    "foot": {"stop": 4.0, "start": 10.0},
}
FLAP_DEADBAND = 0.0  # owned by FLAP_SETTLE now — one rule, one place

# ── Flaps the controller must NOT drive ───────────────────────────
# A deliberate, code-level hold. Not a runtime toggle: re-enabling one of
# these should be a decision someone makes on purpose, with the reason in
# front of them, not something a stray command can undo.
#
# "mix" (blend) was held 2026-08-04 → 2026-08-06. Both conditions that hold
# named have now been met: the permanent linkage is fitted, and the damper
# reference is no longer assumed — the door was set against a measured
# actuator hard stop rather than an eyeballed mid position, which is the
# error that made the old millivolts self-consistent and completely wrong.
#
# What is still unverified is DIRECTION, not position: see the invert note on
# ADS_MIX_CHANNEL. That is deliberately not a reason to keep holding. A wrong
# invert is self-limiting — the loop drives to one end, FLAP_MAX_DRIVE_S cuts
# the motor after 8 s of no progress, and the result is wrong-temperature air,
# not a damaged actuator. Holding the flap instead would make the very test
# that settles the question impossible to run.
FLAP_HELD = set()
# Flap overdrive protection: if a flap is driven this long without its feedback
# advancing at least FLAP_PROGRESS_EPS, cut the motor — stall, end-stop, or lost
# feedback. Set from the measured full-travel time + margin (bench test).
FLAP_MAX_DRIVE_S  = 8.0   # seconds of no-progress driving before cutoff
FLAP_PROGRESS_EPS = 1.5   # % of travel that still counts as "moving"

# Temperature control PID (drives mixing flap setpoint)
TEMP_PID_KP = 3.0
TEMP_PID_KI = 0.3
TEMP_PID_KD = 0.5
TEMP_DEADBAND = 1.0  # °F

# --- H-Bridge Pulse Timing ---
HBRIDGE_PULSE_MS = 80     # Minimum pulse width for motor response
HBRIDGE_MAX_ON_S = 5.0    # Safety: max continuous drive time

# --- Control Loop Rate ---
CONTROL_HZ = 10       # Main loop frequency
SENSOR_HZ  = 2        # Temp sensor read frequency
IDRIVE_ACTIVE_S = 4.0 # iDrive knob mirror stays "live" this long after input

# How often the 1-Wire bus is re-scanned for DS18B20s. Discovery used to run
# only at startup, so any sensor that dropped off the bus — loose connector,
# brownout, a marginal pull-up — stayed gone until someone restarted the
# service, and a single bad connection looked like total loss of climate
# sensing. The scan is a directory listing of /sys/bus/w1/devices; it does not
# drive the bus itself, so it is cheap and safe to repeat.
TEMP_RESCAN_S = 10.0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Detect platform — use stubs if not on a Pi
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SIMULATE = False
try:
    import RPi.GPIO as GPIO
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    from w1thermsensor import W1ThermSensor, NoSensorFoundError
except ImportError:
    SIMULATE = True
    logging.warning("RPi libraries not found — running in SIMULATION mode")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hvac")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FanSpeed(str, Enum):
    OFF = "OFF"
    LOW = "LOW"
    HI  = "HI"

class VentMode(str, Enum):
    FACE    = "face"
    BILEVEL = "bilevel"
    FEET    = "feet"
    DEFROST = "defrost"

@dataclass
class HVACState:
    """Complete system state — sent to dashboard every tick."""
    # User commands
    setpoint_f: float = 72.0
    fan_speed: str = "LOW"
    ac_on: bool = False
    heat_valve: bool = False
    outside_air: bool = True
    vent_mode: str = "face"       # a VENT_PRESETS name, or "custom"
    # Diverter positions are the source of truth; face is derived from them.
    defrost_level: float = 0.0
    foot_level: float = 0.0
    face_level: float = 100.0

    # Sensor readings
    mix_chamber_temp_f: float = 0.0
    exterior_temp_f: float = 0.0
    interior_temp_f: float = 0.0

    # Flap positions (0–100%)
    mix_flap_pos: float = 50.0
    defrost_flap_pos: float = 0.0
    footwell_flap_pos: float = 0.0

    # Flap setpoints (computed by mode logic)
    mix_flap_target: float = 50.0
    defrost_flap_target: float = 0.0
    footwell_flap_target: float = 0.0

    # Flap drive-watchdog faults (stall / end-stop / lost feedback → motor cut)
    flaps_held: str = ""              # space-separated; see FLAP_HELD
    mix_flap_fault: bool = False
    defrost_flap_fault: bool = False
    footwell_flap_fault: bool = False

    # System status
    control_active: bool = False
    onewire_ok: bool = False
    ads_ok: bool = False
    uptime_s: float = 0.0

    # Seat heaters (0–100% duty cycle)
    seat_heat_driver: float = 0.0
    seat_heat_passenger: float = 0.0

    # Bench-test override — inject a fake cabin temp (NOT persisted; off on reboot)
    test_override: bool = False
    test_interior_temp_f: float = 72.0

    # Which page the round auxiliary screen shows: "clock" or "gmeter"
    aux_display: str = "clock"

    # ── iDrive controller (BMW knob on the console, over UART) ────
    # The ESP32 reads the knob off CAN and sends events on /dev/serial0.
    # Real commands are applied through apply_command() like any other
    # client; these fields exist only so the dashboard can mirror the
    # physical knob on screen — which mode it is in, what it owns, and
    # how far it has been turned.
    idrive_mode: str = "radio"        # radio | hvac | illum | gauge | tsdash
    idrive_detents: int = 0           # signed running total; rotates the mirror
    idrive_action: str = ""           # last action name, for the caption
    idrive_active: bool = False       # True briefly after any knob input
    idrive_last_s: float = 0.0        # monotonic stamp of the last event
    idrive_online: bool = False       # UART link proven alive by the heartbeat
    idrive_age_s: float = -1.0        # seconds since ANY line arrived; -1 = never

    # ── Interior lighting (ESP32 output board, over USB) ──────────
    # The lighting board owns these values; we only mirror what it
    # reports. Commands sent to it are relative ("brighter"), never
    # absolute, so the round knob and the iDrive cannot disagree.
    illum_online: bool = False        # serial link to the board is up
    illum_ch1: int = 0                # ambient strip brightness 0-255
    illum_ch2: int = 0                # switch dimmer brightness 0-255
    illum_color: int = 0              # palette index 0-9
    illum_relay: bool = False         # dome light
    illum_night: bool = False         # illumination sense: headlights on
    illum_age_s: float = -1.0         # seconds since the board last reported

    # ── TSDash bridge (ESP32 HID keyboard board, over USB) ────────
    # Write-only. The bridge types Ctrl+Left/Right at the TSDash Pi and
    # has no way to read back which dash is showing, so there is no
    # "current dash" field here and there must never be one — see
    # tsdash_send() for why.
    tsdash_online: bool = False       # serial link to the bridge is up
    tsdash_last: str = ""             # last command sent, for the mirror
    tsdash_mac: str = ""              # MAC the bridge reports; see TSDASH_MAC
    tsdash_init: bool = False         # bridge: tinyusb_init() succeeded at boot
    tsdash_usb: bool = False          # bridge: a USB host has enumerated it
    tsdash_age_s: float = -1.0        # seconds since the bridge last reported

    # ── Accelerometer / G-meter (ADXL335 on ADS1115 #2) ──────────
    # The round aux screen's G-meter reads these two. accel_ok is false
    # whenever any axis looks disconnected, so the display can fall back
    # rather than draw a confident dot in the wrong place.
    accel_ok: bool = False
    g_lateral: float = 0.0            # + = right-hand cornering
    g_longitudinal: float = 0.0       # + = acceleration, - = braking
    g_vertical: float = 0.0           # ~+1.0 at rest; sanity check
    accel_axes_bad: str = ""          # e.g. "x" when an axis reads floating

    # ── System status screen ──────────────────────────────────────
    system_view: bool = False         # touchscreen shows the link topology page

    # ── Main-screen selector ──────────────────────────────────────
    # "hvac", "brake" or "steer". Deliberately NOT persisted: a car should
    # always wake up showing climate control, not whatever was up at
    # shutdown. system_view stays a separate boolean rather than a fourth
    # value here because the iDrive knob toggles it by name — folding it in
    # would break the knob for no gain.
    main_screen: str = "hvac"

    # ── iBooster (read-only CAN) ──────────────────────────────────
    booster_veh_online: bool = False  # 0x39D bus alive (can-veh)
    booster_yaw_online: bool = False  # 0x38E bus alive (can-yaw)
    booster_veh_age_s: float = -1.0
    booster_yaw_age_s: float = -1.0
    brake_stroke_mm: float = 0.0      # from 0x39D, checksum-validated
    brake_stroke_raw: int = -1        # raw counts; -1 = never seen
    brake_pos_yaw: int = -1           # 0x38E 12-bit position, cross-check
    # 0 = unknown, 1 = healthy, 2 = FAULT (latched — power cycle to clear).
    # 2 means "assist unavailable", not "position invalid": after a sensor
    # reconnect the yaw position is live again while this still reads 2.
    brake_status: int = 0
    brake_sentinel: bool = False      # 0x39D pinned past the end stop

    # ── Brake pressure (sensors on order — see BRAKE_PRESS_*) ────
    brake_press_ok: bool = False
    brake_press_front_psi: float = 0.0
    brake_press_rear_psi: float = 0.0

    # ── Steering (Prius EPS) — FRAMEWORK, NOTHING DECODED ────────
    # steer_decoded stays False until a signal is actually confirmed on this
    # column. The screen reads it and refuses to draw numbers rather than
    # showing a confident zero, which is the failure mode the whole
    # VERIFY_FIRST discipline exists to prevent.
    steer_online: bool = False
    steer_age_s: float = -1.0
    steer_ids_seen: int = 0
    steer_decoded: bool = False
    steer_angle_deg: float = 0.0
    steer_torque: float = 0.0
    steer_status: int = 0

    # ── Raw CAN view ─────────────────────────────────────────────
    # Per-ID snapshot for the dashboard's raw-frames table, rebuilt each
    # tick. Per-ID rather than per-frame on purpose: the buses run ~186
    # frames/s, and a scrolling firehose at 10 Hz would show a random
    # sample. A cansniffer-style table shows everything that exists and
    # lets the eye catch the bytes that move.
    can_frames: list = field(default_factory=list)

    def to_json(self):
        return json.dumps(asdict(self))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PID Controller
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PIDController:
    """Discrete PID with anti-windup, deadband, and output clamping."""

    def __init__(self, kp: float, ki: float, kd: float, deadband: float = 0,
                 out_min: float = -100, out_max: float = 100,
                 integral_limit: float = 50):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.deadband = deadband
        self.out_min = out_min
        self.out_max = out_max
        self.integral_limit = integral_limit

        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def update(self, setpoint: float, measurement: float) -> float:
        now = time.monotonic()
        error = setpoint - measurement

        # Deadband — zero output if within tolerance
        if abs(error) < self.deadband:
            self._prev_error = error
            self._prev_time = now
            return 0.0

        if self._prev_time is None:
            dt = 1.0 / CONTROL_HZ
        else:
            dt = now - self._prev_time
            if dt <= 0:
                dt = 1.0 / CONTROL_HZ

        # Proportional
        p_term = self.kp * error

        # Integral with anti-windup
        self._integral += error * dt
        self._integral = max(-self.integral_limit, min(self.integral_limit, self._integral))
        i_term = self.ki * self._integral

        # Derivative (on error, could also be on measurement)
        d_term = self.kd * (error - self._prev_error) / dt if dt > 0 else 0

        output = p_term + i_term + d_term
        output = max(self.out_min, min(self.out_max, output))

        self._prev_error = error
        self._prev_time = now

        return output


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Hardware Abstraction Layer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HardwareManager:
    """Direct hardware IO — GPIO, 1-Wire, I2C ADC."""

    def __init__(self):
        self._ads_channels = {}
        self._temp_sensors = {}
        self._seat_pwm = {}

        # Latest DS18B20 readings (°F), filled by a background reader thread.
        # A 1-Wire conversion blocks ~750ms per sensor — reading inline in the
        # async control loop stalled the whole event loop to ~0.4Hz.
        self._temp_cache = {}

        # Latest accelerometer reading, filled by its own background thread.
        # NOT read inline in the control loop: three more I2C conversions per
        # tick would double the bus traffic the flap reads already generate,
        # and the DS18B20s already taught this project what blocking the loop
        # costs (docs/ACCELEROMETER_WIRING.md §7).
        self._accel_cache = None
        self._accel_channels = {}

        if not SIMULATE:
            self._init_gpio()
            self._init_ads()
            self._init_accel()
            self._init_temps()
            threading.Thread(target=self._temp_reader_loop, daemon=True,
                             name="ds18b20-reader").start()
            if self._accel_channels:
                threading.Thread(target=self._accel_reader_loop, daemon=True,
                                 name="accel-reader").start()
        else:
            log.info("SIMULATION: Hardware stubs active")
            self._sim_mix_pos = 50.0
            self._sim_def_pos = 0.0
            self._sim_foot_pos = 0.0
            self._sim_mix_temp = 68.0
            self._sim_ext_temp = 47.0
            self._sim_int_temp = 72.0

    def _init_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Relay outputs — set HIGH initially (relays are active-low, so HIGH = off)
        for pin in [PIN_BLOWER_HI, PIN_BLOWER_LOW, PIN_AC_CLUTCH, PIN_HEAT_VALVE, PIN_OUTSIDE_AIR]:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)

        # H-bridge outputs — set LOW initially (motors off)
        for pin in [PIN_MIX_COLD, PIN_MIX_HOT, PIN_DEF_IN1, PIN_DEF_IN2,
                     PIN_FOOT_IN1, PIN_FOOT_IN2]:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

        # Seat heater PWM outputs — start at 0% (off)
        for pin in [PIN_SEAT_HEAT_DRIVER, PIN_SEAT_HEAT_PASSENGER]:
            try:
                GPIO.cleanup(pin)
            except Exception:
                pass
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            pwm = GPIO.PWM(pin, SEAT_HEAT_PWM_FREQ)
            pwm.start(0)
            self._seat_pwm[pin] = pwm

        log.info("GPIO initialized (incl. seat heater PWM @ %d Hz)", SEAT_HEAT_PWM_FREQ)

    def _init_ads(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=ADS_I2C_ADDR)
            # ±6.144 V full scale, NOT ±4.096. The pot dividers are excited at ~5 V, so
            # the top of flap travel sits above the ±4.096 V range gain=1 gives —
            # it clipped at exactly 4095.9 mV with zero spread, which reads as a
            # confident "100%" while hiding how much travel is left. Resolution
            # drops to 187.5 uV/bit, which is irrelevant against a 5 V span.
            ads.gain = 2 / 3
            self._ads_channels = {
                ADS_MIX_CHANNEL:  AnalogIn(ads, 0),
                ADS_DEF_CHANNEL:  AnalogIn(ads, 1),
                ADS_FOOT_CHANNEL: AnalogIn(ads, 2),
            }
            log.info("ADS1115 initialized at 0x%02X", ADS_I2C_ADDR)
        except Exception as e:
            log.error("ADS1115 init failed: %s", e)

    def _init_accel(self):
        """Second ADS1115 at 0x49 reading the ADXL335. Optional hardware —
        absence is logged once and everything else carries on."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=ACCEL_I2C_ADDR)
            ads.gain = 1  # ±4.096 V — ADXL335 runs on 3.3 V, so this fits
                          # and gives finer resolution than the flap ADC's 2/3
            self._accel_channels = {
                name: AnalogIn(ads, ch) for name, ch in ACCEL_CH.items()
            }
            self._accel_channels["ref"] = AnalogIn(ads, ACCEL_REF_CH)
            log.info("Accelerometer ADS1115 initialized at 0x%02X", ACCEL_I2C_ADDR)
        except Exception as e:
            self._accel_channels = {}
            log.warning("Accelerometer not present at 0x%02X (%s) — G-meter "
                        "will stay in fallback", ACCEL_I2C_ADDR, e)

    def _accel_reader_loop(self):
        """Daemon thread: sample the ADXL335 and cache g values.

        20 Hz is plenty — the G-meter is a human-readable display, not a
        datalogger, and this shares an I2C bus with the flap ADC.
        """
        while True:
            try:
                mv = {n: c.voltage * 1000.0
                      for n, c in self._accel_channels.items()}
                ref = mv.pop("ref")
                bad = [n for n, v in mv.items()
                       if abs(v - ref) < ACCEL_FLOAT_MV]
                g = {n: (v - ACCEL_ZERO_MV) / ACCEL_MV_PER_G
                     for n, v in mv.items()}
                self._accel_cache = {"g": g, "bad": bad, "ref_mv": ref}
            except Exception as e:
                self._accel_cache = None
                log.debug("Accel read failed: %s", e)
            time.sleep(0.05)

    def read_accel(self):
        """Latest {"g": {x,y,z}, "bad": [axes], "ref_mv": float} or None."""
        if SIMULATE:
            return {"g": {"x": 0.0, "y": 0.0, "z": 1.0}, "bad": [], "ref_mv": 0.0}
        return self._accel_cache

    def _scan_temps(self):
        """(Re)discover DS18B20s on the 1-Wire bus. Safe to call repeatedly.

        Only ever called from the temp reader thread (or from __init__ before
        that thread starts), so the dict swap below needs no lock.
        """
        try:
            found = {s.id: s for s in W1ThermSensor.get_available_sensors()}
        except NoSensorFoundError:
            found = {}
        except Exception as e:
            log.error("1-Wire scan failed: %s", e)
            return          # keep whatever we already had

        for sid in found:
            if sid not in self._temp_sensors:
                log.info("DS18B20 appeared: %s", sid)
        for sid in self._temp_sensors:
            if sid not in found:
                # Drop the cached reading too — a temperature that stopped
                # updating is worse than no temperature, because the control
                # loop would keep trusting it.
                log.warning("DS18B20 vanished: %s", sid)
                self._temp_cache.pop(sid, None)

        self._temp_sensors = found

    def _init_temps(self):
        self._scan_temps()
        if not self._temp_sensors:
            log.warning("No DS18B20 sensors found — will keep re-scanning "
                        "every %.0fs", TEMP_RESCAN_S)

    def _temp_reader_loop(self):
        """Daemon thread: continuously read the (slow, blocking) DS18B20s and
        cache the results so the async control loop never blocks on 1-Wire.
        Also re-scans the bus periodically so sensors that appear or drop out
        are picked up without restarting the service."""
        last_scan = time.monotonic()
        while True:
            if time.monotonic() - last_scan >= TEMP_RESCAN_S:
                last_scan = time.monotonic()
                self._scan_temps()
            for sid, sensor in list(self._temp_sensors.items()):
                try:
                    c = sensor.get_temperature()
                    self._temp_cache[sid] = c * 9.0 / 5.0 + 32.0
                except Exception as e:
                    log.error("Temp read %s failed: %s", sid, e)
            time.sleep(0.5)

    # ── Relay Control ──────────────────────────────────────────
    def set_relay(self, pin: int, active: bool):
        """Set relay state. Active-low: active=True → GPIO LOW."""
        if SIMULATE:
            return
        GPIO.output(pin, GPIO.LOW if active else GPIO.HIGH)

    def set_fan(self, speed: FanSpeed):
        if speed == FanSpeed.OFF:
            self.set_relay(PIN_BLOWER_LOW, False)
            self.set_relay(PIN_BLOWER_HI, False)
        elif speed == FanSpeed.LOW:
            self.set_relay(PIN_BLOWER_HI, False)
            self.set_relay(PIN_BLOWER_LOW, True)
        elif speed == FanSpeed.HI:
            self.set_relay(PIN_BLOWER_LOW, False)
            self.set_relay(PIN_BLOWER_HI, True)

    def set_ac(self, on: bool):
        self.set_relay(PIN_AC_CLUTCH, on)

    def set_heat_valve(self, on: bool):
        self.set_relay(PIN_HEAT_VALVE, on)

    def set_outside_air(self, on: bool):
        self.set_relay(PIN_OUTSIDE_AIR, on)

    # ── Seat Heater PWM Control ───────────────────────────────
    def set_seat_heater(self, pin: int, duty_pct: float):
        """Set seat heater duty cycle (0–100%)."""
        duty = max(0.0, min(100.0, duty_pct))
        if SIMULATE:
            return
        pwm = self._seat_pwm.get(pin)
        if pwm:
            pwm.ChangeDutyCycle(duty)

    def set_driver_seat_heat(self, duty_pct: float):
        self.set_seat_heater(PIN_SEAT_HEAT_DRIVER, duty_pct)

    def set_passenger_seat_heat(self, duty_pct: float):
        self.set_seat_heater(PIN_SEAT_HEAT_PASSENGER, duty_pct)

    # ── H-Bridge Motor Drive ──────────────────────────────────
    def drive_hbridge(self, pin_fwd: int, pin_rev: int, command: float):
        """
        Drive an H-bridge pair.
        command > 0 → forward (pin_fwd HIGH), command < 0 → reverse (pin_rev HIGH)
        command == 0 → both LOW (brake/coast)
        """
        if SIMULATE:
            return
        if command > 0:
            GPIO.output(pin_rev, GPIO.LOW)
            GPIO.output(pin_fwd, GPIO.HIGH)
        elif command < 0:
            GPIO.output(pin_fwd, GPIO.LOW)
            GPIO.output(pin_rev, GPIO.HIGH)
        else:
            GPIO.output(pin_fwd, GPIO.LOW)
            GPIO.output(pin_rev, GPIO.LOW)

    def drive_mix_flap(self, command: float):
        """Positive = toward HOT, negative = toward COLD."""
        # GPIO24 is HOT on the harness sheet and drives this pot DOWN;
        # invert=True turns that into rising position. Self-consistent, and
        # it matches the control convention of 0% cold / 100% hot.
        #
        # NOT yet confirmed against the physical door — the blend flap has a
        # broken retainer (pre-existing), so the pot may be tracking the
        # motor while the door itself does not follow. Treat blend position
        # as unverified until that is repaired.
        self.drive_hbridge(PIN_MIX_HOT, PIN_MIX_COLD, command)

    def drive_defrost_flap(self, command: float):
        # IN2 (GPIO20) drives the pot UP, but invert=True means rising
        # position is FALLING volts — more defrost. So IN1 is the forward
        # pin. This is the original pin order, and that is not a
        # coincidence: the polarity was never the bug. The bug was reading
        # the pot backwards, which made a correct drive look inverted.
        self.drive_hbridge(PIN_DEF_IN1, PIN_DEF_IN2, command)

    def drive_footwell_flap(self, command: float):
        # Same story as defrost: IN2 raises the pot, invert=True makes
        # falling volts mean "more open", so IN1 is forward.
        self.drive_hbridge(PIN_FOOT_IN1, PIN_FOOT_IN2, command)

    # ── Sensor Reading ─────────────────────────────────────────
    def read_flap_position(self, channel: int) -> float:
        """Read flap position from ADS1115. Returns 0–100%."""
        if SIMULATE:
            positions = {
                ADS_MIX_CHANNEL: self._sim_mix_pos,
                ADS_DEF_CHANNEL: self._sim_def_pos,
                ADS_FOOT_CHANNEL: self._sim_foot_pos,
            }
            return positions.get(channel, 50.0)

        if channel not in self._ads_channels:
            return -1.0

        try:
            mv = self._ads_channels[channel].voltage * 1000  # Convert V to mV
            cal = FLAP_CAL[channel]
            pct = (mv - cal["lo"]) / (cal["hi"] - cal["lo"]) * 100
            if cal["invert"]:
                pct = 100.0 - pct
            return max(0.0, min(100.0, pct))
        except Exception as e:
            log.error("ADS read CH%d failed: %s", channel, e)
            return -1.0

    def read_temp_f(self, sensor_id: str) -> Optional[float]:
        """Read DS18B20 temperature in °F."""
        if SIMULATE:
            if sensor_id == SENSOR_MIX_CHAMBER:
                return self._sim_mix_temp
            elif sensor_id == SENSOR_EXTERIOR:
                return self._sim_ext_temp
            elif sensor_id == SENSOR_INTERIOR:
                return self._sim_int_temp
            return None

        # Non-blocking: latest value from the background reader thread
        # (None until the first successful conversion).
        return self._temp_cache.get(sensor_id)

    @property
    def onewire_ok(self) -> bool:
        if SIMULATE:
            return True
        return len(self._temp_sensors) > 0

    @property
    def ads_ok(self) -> bool:
        if SIMULATE:
            return True
        return len(self._ads_channels) > 0

    def shutdown(self):
        """Safe shutdown — all outputs off."""
        log.info("Hardware shutdown — all outputs off")
        if not SIMULATE:
            for pin in [PIN_BLOWER_HI, PIN_BLOWER_LOW, PIN_AC_CLUTCH,
                        PIN_HEAT_VALVE, PIN_OUTSIDE_AIR]:
                GPIO.output(pin, GPIO.HIGH)  # Relays off
            for pin in [PIN_MIX_COLD, PIN_MIX_HOT, PIN_DEF_IN1, PIN_DEF_IN2,
                        PIN_FOOT_IN1, PIN_FOOT_IN2]:
                GPIO.output(pin, GPIO.LOW)  # Motors off
            # Stop seat heater PWM
            for pwm in self._seat_pwm.values():
                pwm.stop()
            GPIO.cleanup()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HVAC Control Logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HVACController:
    """
    Main HVAC state machine + control loops.

    Control hierarchy:
    1. Vent mode → sets flap targets (defrost, footwell)
    2. Temperature PID → computes mixing flap target based on setpoint vs duct temp
    3. Flap PIDs → drive H-bridges to hit flap targets from feedback
    4. Safety interlocks → prevent AC + heat conflict, enforce limits
    """

    def __init__(self, hw: HardwareManager):
        self.hw = hw
        self.state = HVACState()
        self._start_time = time.monotonic()
        self._load_state()
        # Which flaps are currently parked. See _settle_flap().
        self._flap_settled = {"mix": False, "def": False, "foot": False}

        # Flap position PIDs
        self.mix_pid = PIDController(
            FLAP_PID_KP, FLAP_PID_KI, FLAP_PID_KD,
            deadband=FLAP_DEADBAND, out_min=-100, out_max=100
        )
        self.def_pid = PIDController(
            FLAP_PID_KP, FLAP_PID_KI, FLAP_PID_KD,
            deadband=FLAP_DEADBAND, out_min=-100, out_max=100
        )
        self.foot_pid = PIDController(
            FLAP_PID_KP, FLAP_PID_KI, FLAP_PID_KD,
            deadband=FLAP_DEADBAND, out_min=-100, out_max=100
        )

        # Temperature control PID (output = mixing flap %)
        self.temp_pid = PIDController(
            TEMP_PID_KP, TEMP_PID_KI, TEMP_PID_KD,
            deadband=TEMP_DEADBAND, out_min=0, out_max=100
        )

        # Sensor read timing (DS18B20 is slow, don't hammer it)
        self._last_temp_read = 0

        # Flap drive watchdog (per flap): overdrive / stall protection.
        # t0 = start of no-progress driving, ref = position at t0, fault = latched.
        self._flap_wd = {n: {"t0": None, "ref": 0.0, "fault": False}
                         for n in ("mix", "def", "foot")}

    def _guard_flap(self, name, cmd, pos, now):
        """Overdrive protection for one flap. Cuts the motor when it is driven
        without the feedback making progress (stall / end-stop / lost feedback)
        and latches a fault until the flap physically moves again. Returns the
        command actually safe to apply."""
        wd = self._flap_wd[name]
        # Invalid feedback (ADS error / no channel) → never drive blind.
        if pos < 0:
            wd["t0"] = None
            wd["fault"] = True
            return 0.0
        # Settled in deadband / not commanded → healthy, reset watchdog.
        if cmd == 0:
            wd["t0"] = None
            wd["fault"] = False
            wd["ref"] = pos
            return 0.0
        # Latched fault: keep the motor off until the flap actually moves.
        if wd["fault"]:
            if abs(pos - wd["ref"]) > FLAP_PROGRESS_EPS:
                wd["fault"] = False          # unstuck — allow driving again
            else:
                return 0.0
        # Driving: start the watchdog, or reset it whenever we see progress.
        if wd["t0"] is None or abs(pos - wd["ref"]) > FLAP_PROGRESS_EPS:
            wd["t0"] = now
            wd["ref"] = pos
        elif now - wd["t0"] > FLAP_MAX_DRIVE_S:
            wd["fault"] = True
            wd["t0"] = None
            log.warning("Flap %s: no feedback progress in %.1fs while driving — "
                        "cutting motor (stall / end-stop / lost feedback)",
                        name, FLAP_MAX_DRIVE_S)
            return 0.0
        return cmd

    # ── State persistence (survives power loss) ──────────────
    _PERSIST_FIELDS = ("setpoint_f", "fan_speed", "ac_on", "heat_valve",
                       "outside_air", "vent_mode", "seat_heat_driver",
                       "seat_heat_passenger", "aux_display")

    def _load_state(self):
        """Restore last user settings from disk at startup."""
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
            for key in self._PERSIST_FIELDS:
                if key in saved:
                    setattr(self.state, key, saved[key])
            log.info("Restored saved state: setpoint=%.0f fan=%s mode=%s",
                     self.state.setpoint_f, self.state.fan_speed, self.state.vent_mode)
        except FileNotFoundError:
            log.info("No saved state file — using defaults")
        except Exception as e:
            log.warning("Could not load saved state: %s", e)

    def _save_state(self):
        """Persist current user settings to disk."""
        try:
            data = {k: getattr(self.state, k) for k in self._PERSIST_FIELDS}
            with open(STATE_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("Could not save state: %s", e)

    def apply_command(self, cmd: dict):
        """Process a command from the dashboard."""
        if "setpoint_f" in cmd:
            self.state.setpoint_f = max(60, min(90, float(cmd["setpoint_f"])))
        if "fan_speed" in cmd:
            speed = cmd["fan_speed"].upper()
            if speed in ("OFF", "LOW", "HI"):
                self.state.fan_speed = speed
        if "ac_on" in cmd:
            self.state.ac_on = bool(cmd["ac_on"])
        if "heat_valve" in cmd:
            self.state.heat_valve = bool(cmd["heat_valve"])
        if "outside_air" in cmd:
            self.state.outside_air = bool(cmd["outside_air"])
        if "vent_mode" in cmd:
            self.set_vent_mode(str(cmd["vent_mode"]).lower())
        if "vent_cycle" in cmd:
            outlet = str(cmd["vent_cycle"]).lower()
            if outlet in ("face", "foot", "defrost"):
                self.cycle_vent(outlet)
        if "seat_heat_driver" in cmd:
            self.state.seat_heat_driver = max(0, min(100, float(cmd["seat_heat_driver"])))
        if "seat_heat_passenger" in cmd:
            self.state.seat_heat_passenger = max(0, min(100, float(cmd["seat_heat_passenger"])))
        if "test_override" in cmd:
            self.state.test_override = bool(cmd["test_override"])
        if "test_interior_temp_f" in cmd:
            self.state.test_interior_temp_f = max(20, min(140, float(cmd["test_interior_temp_f"])))
        if "aux_display" in cmd:
            page = str(cmd["aux_display"]).lower()
            if page in ("clock", "gmeter"):
                self.state.aux_display = page
        if "system_view" in cmd:
            v = cmd["system_view"]
            # "toggle" so the knob does not need to know the current state.
            self.state.system_view = (not self.state.system_view
                                      if str(v).lower() == "toggle" else bool(v))
        if "main_screen" in cmd:
            screen = str(cmd["main_screen"]).lower()
            if screen in ("hvac", "brake"):
                self.state.main_screen = screen
        if "tsdash" in cmd:
            # Page the TunerStudio dash on the TSDash Pi. Nothing is stored:
            # this is a fire-and-forget keystroke, and there is no state here
            # to persist because we cannot see which dash is showing.
            move = str(cmd["tsdash"]).lower()
            if move in ("next", "prev", "cfg", "home"):
                tsdash_send("D " + move.upper())
        # Persist user settings after every command
        self._save_state()

    def _settle_flap(self, name, cmd, target, pos, pid):
        """Hysteresis latch: hold a settled flap still until it is properly off.

        Returns the command actually worth applying. Resetting the PID on
        settle matters as much as the band does — otherwise the integral
        keeps winding while the motor is off, and the next legitimate move
        starts with a wound-up term that drives straight past the target.
        """
        band = FLAP_SETTLE[name]
        err = abs(target - pos)
        if self._flap_settled[name]:
            if err <= band["start"]:
                pid.reset()
                return 0.0
            self._flap_settled[name] = False        # genuinely moved away
        elif err <= band["stop"]:
            self._flap_settled[name] = True
            pid.reset()
            return 0.0
        return cmd

    # ── Vent distribution ─────────────────────────────────────────
    def _publish_vent(self, defrost, foot):
        """Store diverter positions, derive face, and re-label the mode."""
        d = max(0.0, min(100.0, float(defrost)))
        f = max(0.0, min(100.0, float(foot)))
        self.state.defrost_level = round(d, 1)
        self.state.foot_level = round(f, 1)
        self.state.face_level = round(max(0.0, 100.0 - d - f), 1)
        # A preset is just a named point in this space. Land on one and we
        # say so; move off it and the label goes to "custom" rather than
        # lying about which mode you are in.
        self.state.vent_mode = "custom"
        for name, p in VENT_PRESETS.items():
            if abs(p["defrost"] - d) < 0.6 and abs(p["foot"] - f) < 0.6:
                self.state.vent_mode = name
                break

    def set_vent_mode(self, mode: str):
        p = VENT_PRESETS.get(mode)
        if p:
            self._publish_vent(p["defrost"], p["foot"])

    def cycle_vent(self, outlet: str):
        """Advance one outlet button by a step, wrapping at the top.

        Wrapping matters because each outlet is a single button: without it
        there is no way back to off without a second gesture, and there is
        nowhere good to put one.
        """
        d, f = self.state.defrost_level, self.state.foot_level

        def next_step(current, steps):
            for v in steps:
                if v > current + 0.6:
                    return v
            return steps[0]

        if outlet == "defrost":
            self._publish_vent(next_step(d, VENT_STEPS), f)
        elif outlet == "foot":
            self._publish_vent(d, next_step(f, VENT_STEPS))
        elif outlet == "face":
            # Face is the remainder, so asking for more of it means taking it
            # back off the diverters. Scale them PROPORTIONALLY rather than
            # zeroing: the mix you had — mostly defrost, a little foot — is
            # information you did not ask to throw away.
            target = next_step(self.state.face_level, FACE_STEPS)
            budget = 100.0 - target
            total = d + f
            if total <= 0.1:
                # Coming from all-face there is no ratio to preserve. Put it
                # all into foot: that is the outlet people actually reach for
                # second, and an arbitrary even split would be a worse guess.
                self._publish_vent(0.0, budget)
            else:
                self._publish_vent(d * budget / total, f * budget / total)

    # ── iDrive knob ───────────────────────────────────────────────
    def apply_idrive_event(self, evt: dict):
        """Translate one event from the iDrive controller.

        Events arrive as NDJSON on the UART, e.g.
            {"mode":"HVAC","action":"TEMP_UP","count":2}

        Everything routes through apply_command() so the knob is just
        another client — the touchscreen updates itself from the normal
        state broadcast and the two can never disagree. The idrive_*
        fields are display-only, for the on-screen knob mirror.
        """
        action = str(evt.get("action", "")).upper()
        mode = str(evt.get("mode", "")).lower()
        try:
            count = max(1, min(12, int(evt.get("count", 1))))
        except (TypeError, ValueError):
            count = 1

        # Accept the pre-rename names too. The ESP32 and the Pi are separate
        # deployments and can be updated hours apart, so the link must not
        # break just because one side is newer than the other.
        mode = {"media": "radio", "light": "illum"}.get(mode, mode)
        if mode in ("radio", "hvac", "illum", "gauge", "tsdash"):
            self.state.idrive_mode = mode
        self.state.idrive_action = action
        self.state.idrive_last_s = time.monotonic()

        # Rotation moves the mirror ring regardless of what it controls.
        if action.endswith(("_UP", "_BRIGHTER")) or action in ("VOL_UP",):
            self.state.idrive_detents += count
        elif action.endswith(("_DOWN", "_DIMMER")) or action in ("VOL_DOWN",):
            self.state.idrive_detents -= count

        cmd = {}
        if action == "TEMP_UP":
            cmd["setpoint_f"] = self.state.setpoint_f + count
        elif action == "TEMP_DOWN":
            cmd["setpoint_f"] = self.state.setpoint_f - count
        elif action in ("FAN_UP", "FAN_DOWN"):
            order = ["OFF", "LOW", "HI"]
            i = order.index(self.state.fan_speed) if self.state.fan_speed in order else 1
            i = max(0, min(len(order) - 1, i + (1 if action == "FAN_UP" else -1)))
            cmd["fan_speed"] = order[i]
        elif action == "HVAC_TOGGLE":
            cmd["ac_on"] = not self.state.ac_on
        elif action in ("HVAC_MODE_NEXT", "HVAC_MODE_PREV"):
            order = VENT_MODE_ORDER
            i = order.index(self.state.vent_mode) if self.state.vent_mode in order else 0
            step = 1 if action == "HVAC_MODE_NEXT" else -1
            cmd["vent_mode"] = order[(i + step) % len(order)]
        elif action == "SYSTEM_TOGGLE":
            # BACK button. Global, not a mode: the status page is read-only, so
            # the knob keeps doing whatever it was doing while you look at it.
            cmd["system_view"] = "toggle"
        elif action == "AUX_SWAP":
            # Dedicated button: swap the round screen clock <-> G-meter.
            cmd["aux_display"] = "gmeter" if self.state.aux_display == "clock" else "clock"

        # ── Interior lighting ─────────────────────────────────────
        # Sent as RELATIVE adjustments. We deliberately do not track or
        # send absolute brightness: the lighting board owns that value and
        # the round knob can change it at any time, so anything we cached
        # would be wrong the moment it did.
        elif action == "LIGHT_BRIGHTER":
            lighting_send(f"L ADJ 1 {LIGHT_STEP * count}")
        elif action == "LIGHT_DIMMER":
            lighting_send(f"L ADJ 1 {-LIGHT_STEP * count}")
        elif action == "LIGHT_SCENE_NEXT":
            lighting_send("L ADJ 5 1")
        elif action == "LIGHT_SCENE_PREV":
            lighting_send("L ADJ 5 -1")
        elif action == "LIGHT_TOGGLE":
            lighting_send("L ADJ 3 1")      # any nudge toggles the dome relay

        # ── TSDash gauge screens (OPTION button → TSDASH mode) ────
        # Exactly one keystroke per event regardless of `count`. TS Dash
        # has a short list of dash tabs, and a knob flick that fired eight
        # Ctrl+Rights would leave the driver somewhere unpredictable with
        # no way to see where they landed — the bridge types blind and
        # cannot read back which dash is showing, so overshoot is not
        # recoverable. Deliberately slower than the knob can turn.
        elif action == "TSDASH_NEXT":
            tsdash_send("D NEXT")
        elif action == "TSDASH_PREV":
            tsdash_send("D PREV")
        elif action == "TSDASH_CFG":
            tsdash_send("D CFG")
        elif action == "TSDASH_HOME":
            tsdash_send("D HOME")

        # GAUGE_* stays unbound on purpose. GAUGE is the NAV button and
        # belongs to the backup cluster (the two T-Display-S3-Long panels),
        # which has no Pi protocol yet — a different screen from TSDASH and
        # not to be conflated with it. MEDIA actions (volume/mute/track)
        # stay unbound too: the head unit is driven by IR, not by the Pi.
        if cmd:
            self.apply_command(cmd)
        else:
            self._save_state()

    def tick(self):
        """Called at CONTROL_HZ. Reads sensors, runs PIDs, drives outputs."""
        now = time.monotonic()
        self.state.uptime_s = now - self._start_time

        # ── Read sensors ──────────────────────────────────────
        # Flap positions — fast, read every tick
        self.state.mix_flap_pos = self.hw.read_flap_position(ADS_MIX_CHANNEL)
        self.state.defrost_flap_pos = self.hw.read_flap_position(ADS_DEF_CHANNEL)
        self.state.footwell_flap_pos = self.hw.read_flap_position(ADS_FOOT_CHANNEL)

        # Temperatures — slow (DS18B20 conversion time)
        if now - self._last_temp_read >= (1.0 / SENSOR_HZ):
            self._last_temp_read = now
            mix_t = self.hw.read_temp_f(SENSOR_MIX_CHAMBER)
            ext_t = self.hw.read_temp_f(SENSOR_EXTERIOR)
            int_t = self.hw.read_temp_f(SENSOR_INTERIOR)
            if mix_t is not None:
                self.state.mix_chamber_temp_f = round(mix_t, 1)
            if ext_t is not None:
                self.state.exterior_temp_f = round(ext_t, 1)
            if int_t is not None:
                self.state.interior_temp_f = round(int_t, 1)

        self.state.onewire_ok = self.hw.onewire_ok
        self.state.ads_ok = self.hw.ads_ok

        # iDrive knob goes "live" on screen briefly after any input
        self.state.idrive_active = (
            self.state.idrive_last_s > 0
            and (now - self.state.idrive_last_s) < IDRIVE_ACTIVE_S
        )

        # ── Accelerometer ─────────────────────────────────────
        # Cache read only — the sampling happens on its own thread.
        acc = self.hw.read_accel()
        if acc is None:
            self.state.accel_ok = False
            self.state.accel_axes_bad = ""
        else:
            bad = acc["bad"]
            self.state.accel_axes_bad = "".join(sorted(bad))
            # Any floating axis makes the whole reading untrustworthy: a
            # G-meter missing one axis is not a degraded G-meter, it is a
            # wrong one, and it would put the dot confidently off-centre.
            self.state.accel_ok = not bad
            g = acc["g"]
            lat = -g["x"] if ACCEL_INVERT_X else g["x"]
            lon = -g["y"] if ACCEL_INVERT_Y else g["y"]
            self.state.g_lateral = 0.0 if "x" in bad else round(lat, 3)
            self.state.g_longitudinal = 0.0 if "y" in bad else round(lon, 3)
            self.state.g_vertical = 0.0 if "z" in bad else round(g["z"], 3)

        # ── Link liveness ─────────────────────────────────────
        # idrive_active means "the knob was just touched"; idrive_online means
        # "the wire is alive". They are NOT the same thing and conflating them
        # was the worst gap here: a knob nobody has touched for an hour looked
        # exactly like a severed UART, so a status page would show green
        # straight through a real fault. The firmware heartbeats for this.
        self.state.idrive_age_s = _age_of("idrive", now)
        self.state.illum_age_s  = _age_of("illum",  now)
        self.state.tsdash_age_s = _age_of("tsdash", now)
        def _fresh(age):
            return 0 <= age < LINK_STALE_S

        # Derived every tick, never latched. An earlier version let the reader
        # thread set online=True once at connect and then only ever cleared it
        # on staleness — so the first tick, which runs before any data has
        # arrived, pinned it false for the life of the process. Both boards are
        # polled every 2 s, so freshness is the honest test for all three.
        self.state.idrive_online = _fresh(self.state.idrive_age_s)
        self.state.illum_online  = _port_up["illum"]  and _fresh(self.state.illum_age_s)
        self.state.tsdash_online = _port_up["tsdash"] and _fresh(self.state.tsdash_age_s)

        # ── iBooster (read-only CAN) ──────────────────────────
        # Tighter staleness than the serial links: 0x39D arrives at 25 Hz
        # and 0x38E at 100 Hz, so 2 s of silence is dozens of missed frames.
        self.state.booster_veh_age_s = _age_of("canveh", now)
        self.state.booster_yaw_age_s = _age_of("canyaw", now)
        self.state.booster_veh_online = 0 <= self.state.booster_veh_age_s < BOOSTER_STALE_S
        self.state.booster_yaw_online = 0 <= self.state.booster_yaw_age_s < BOOSTER_STALE_S

        with _can_lock:
            brake = dict(_brake)
            snap = [(link, cid, e["hz"], e["dlc"], e["data"], e["prev"],
                     now - e["t"]) for (link, cid), e in _can_stats.items()]

        self.state.brake_stroke_raw = brake["stroke_raw"]
        self.state.brake_sentinel = brake["sentinel"]
        self.state.brake_pos_yaw = brake["pos_yaw"]
        # Hold status at its last value when the bus goes quiet rather than
        # resetting to unknown: the fault LATCHES in the booster, and a
        # latched fault with a flaky CAN lead is still a latched fault.
        if self.state.booster_yaw_online:
            self.state.brake_status = brake["status"]
        # The sentinel is fault signalling, not travel — never convert it
        # to a fake 51 mm reading.
        if brake["stroke_raw"] < 0 or brake["sentinel"]:
            self.state.brake_stroke_mm = 0.0
        else:
            self.state.brake_stroke_mm = round(max(
                0.0, (brake["stroke_raw"] - BRAKE_STROKE_OFFSET)
                / BRAKE_STROKE_SCALE), 2)

        self.state.can_frames = [
            {"bus": link[3:], "id": f"{cid:03X}", "hz": round(hz, 1),
             "dlc": dlc, "data": data.hex(" ").upper(),
             "chg": [i for i in range(min(len(data), len(prev)))
                     if data[i] != prev[i]],
             "stale": age > BOOSTER_STALE_S}
            for link, cid, hz, dlc, data, prev, age in
            sorted(snap, key=lambda r: (r[0], r[1]))
        ]

        # ── Steering (Prius EPS) ──────────────────────────────
        # Liveness and an ID count only. steer_decoded stays False until a
        # signal on this column is actually confirmed — the screen must not
        # be able to show a confident number that nothing measured.
        self.state.steer_age_s = _age_of("cansteer", now)
        self.state.steer_online = 0 <= self.state.steer_age_s < STEER_STALE_S
        self.state.steer_ids_seen = sum(
            1 for f in self.state.can_frames if f["bus"] == "steer")

        # ── Bench-test override ───────────────────────────────
        # Force a fake cabin temp so heating can be exercised indoors.
        # Not persisted; a reboot always returns to the real sensor.
        if self.state.test_override:
            self.state.interior_temp_f = round(self.state.test_interior_temp_f, 1)

        # ── Safety interlocks ─────────────────────────────────
        # A/C and heat valve may run together on purpose: the A/C dries/cools
        # the air and the heater core reheats it (reheat / dehumidify / defrost),
        # exactly like production automotive HVAC. The blend flap sets final temp.

        # Fan must be on for AC
        if self.state.ac_on and self.state.fan_speed == "OFF":
            self.state.fan_speed = "LOW"

        # Heavy defrost forces outside air — recirculated air fogs a screen.
        # Keyed on the LEVEL, not the mode name, so it still holds when you
        # have dialled defrost up by hand and left the presets behind.
        if self.state.defrost_level >= DEFROST_FRESH_AIR_PCT:
            self.state.outside_air = True

        # ── Flap targets come straight from the diverter levels ───
        # Face needs no target because it has no flap: it is whatever these
        # two leave behind.
        self.state.defrost_flap_target = self.state.defrost_level
        self.state.footwell_flap_target = self.state.foot_level

        # ── Temperature PID → mixing flap target ──────────────
        # Closed-loop on CABIN (interior) temp: modulate the blend flap to
        # drive the interior toward the setpoint. Setpoint 90 only commands
        # HOT when the cabin is below 90; if the cabin is hotter, it cools.
        if self.state.fan_speed != "OFF" and self.state.interior_temp_f > 0:
            # PID output: 0% = full cold, 100% = full hot
            mix_target = self.temp_pid.update(
                self.state.setpoint_f, self.state.interior_temp_f
            )
            self.state.mix_flap_target = max(0, min(100, mix_target))
        else:
            self.temp_pid.reset()
            self.state.mix_flap_target = 50  # Neutral when off

        self.state.control_active = self.state.fan_speed != "OFF"

        # ── Drive relay outputs ───────────────────────────────
        self.hw.set_fan(FanSpeed(self.state.fan_speed))
        self.hw.set_ac(self.state.ac_on)
        self.hw.set_heat_valve(self.state.heat_valve)
        self.hw.set_outside_air(self.state.outside_air)

        # ── Drive seat heater PWM outputs ─────────────────────
        self.hw.set_driver_seat_heat(self.state.seat_heat_driver)
        self.hw.set_passenger_seat_heat(self.state.seat_heat_passenger)

        # ── Flap PID loops → H-bridge commands ────────────────
        if self.state.control_active:
            mix_cmd = self.mix_pid.update(self.state.mix_flap_target, self.state.mix_flap_pos)
            def_cmd = self.def_pid.update(self.state.defrost_flap_target, self.state.defrost_flap_pos)
            foot_cmd = self.foot_pid.update(self.state.footwell_flap_target, self.state.footwell_flap_pos)
            # Settle first, stall-guard second: a flap held still by the
            # hysteresis latch is not "driven without progress", and feeding
            # it to the watchdog would eventually latch a false fault.
            # Held flaps: never driven, PID reset so nothing winds up, and
            # kept OUT of the stall watchdog below — a flap that is being
            # deliberately not driven is not "driven without progress", and
            # feeding it there would latch a fault that means nothing.
            mix_cmd = self._settle_flap("mix", mix_cmd,
                self.state.mix_flap_target, self.state.mix_flap_pos, self.mix_pid)
            def_cmd = self._settle_flap("def", def_cmd,
                self.state.defrost_flap_target, self.state.defrost_flap_pos, self.def_pid)
            foot_cmd = self._settle_flap("foot", foot_cmd,
                self.state.footwell_flap_target, self.state.footwell_flap_pos, self.foot_pid)
            # Overdrive / stall protection — cut a motor that isn't making progress
            mix_cmd = self._guard_flap("mix", mix_cmd, self.state.mix_flap_pos, now)
            def_cmd = self._guard_flap("def", def_cmd, self.state.defrost_flap_pos, now)
            foot_cmd = self._guard_flap("foot", foot_cmd, self.state.footwell_flap_pos, now)
        else:
            mix_cmd = def_cmd = foot_cmd = 0
            self.mix_pid.reset()
            self.def_pid.reset()
            self.foot_pid.reset()
            # System off → clear watchdogs and any latched faults
            for wd in self._flap_wd.values():
                wd["t0"] = None
                wd["fault"] = False

        # Publish flap fault status for the dashboard
        self.state.mix_flap_fault = self._flap_wd["mix"]["fault"]
        self.state.defrost_flap_fault = self._flap_wd["def"]["fault"]
        self.state.footwell_flap_fault = self._flap_wd["foot"]["fault"]

        if "mix" in FLAP_HELD:
            mix_cmd = 0.0
            self.mix_pid.reset()
            self.temp_pid.reset()
            # Park the target on the actual position. Leaving it at whatever
            # the temperature PID wanted would show the dashboard a standing
            # error the controller has no intention of correcting, which reads
            # as a fault rather than as a decision.
            self.state.mix_flap_target = self.state.mix_flap_pos
            self._flap_wd["mix"]["fault"] = False
        if "def" in FLAP_HELD:
            def_cmd = 0.0
            self.def_pid.reset()
            self.state.defrost_flap_target = self.state.defrost_flap_pos
            self._flap_wd["def"]["fault"] = False
        if "foot" in FLAP_HELD:
            foot_cmd = 0.0
            self.foot_pid.reset()
            self.state.footwell_flap_target = self.state.footwell_flap_pos
            self._flap_wd["foot"]["fault"] = False
        self.state.flaps_held = " ".join(sorted(FLAP_HELD))

        self.hw.drive_mix_flap(mix_cmd)
        self.hw.drive_defrost_flap(def_cmd)
        self.hw.drive_footwell_flap(foot_cmd)

        # ── Simulation: fake flap movement ────────────────────
        if SIMULATE:
            rate = 2.0  # % per tick
            self.hw._sim_mix_pos += max(-rate, min(rate, mix_cmd * 0.02))
            self.hw._sim_mix_pos = max(0, min(100, self.hw._sim_mix_pos))
            self.hw._sim_def_pos += max(-rate, min(rate, def_cmd * 0.02))
            self.hw._sim_def_pos = max(0, min(100, self.hw._sim_def_pos))
            self.hw._sim_foot_pos += max(-rate, min(rate, foot_cmd * 0.02))
            self.hw._sim_foot_pos = max(0, min(100, self.hw._sim_foot_pos))
            # Duct temp = blend flap position between a cold and a hot source
            # (heat valve supplies the hot side, A/C the cold side).
            hot = 160.0 if self.state.heat_valve else 90.0
            cold = 40.0 if self.state.ac_on else self.hw._sim_ext_temp
            duct_target = cold + (hot - cold) * (self.hw._sim_mix_pos / 100.0)
            self.hw._sim_mix_temp += (duct_target - self.hw._sim_mix_temp) * 0.05
            # Cabin drifts toward the duct air temperature (what the PID reads)
            self.hw._sim_int_temp += (self.hw._sim_mix_temp - self.hw._sim_int_temp) * 0.02


# ── iBooster CAN readers ───────────────────────────────────────
# One daemon thread per bus, raw AF_CAN sockets — the kernel binds the
# CANable adapters natively, so this needs no libraries at all. recv()
# only; there is no send path in this process and none may be added.
#
# Decoded values and per-ID stats land in module globals under _can_lock,
# copied into state by tick(). Same shape as the serial reader threads.

_can_lock = threading.Lock()
_can_stats = {}   # (bus, can_id) -> {"hz","dlc","data","prev","t"}
_brake = {"stroke_raw": -1, "status": 0, "pos_yaw": -1, "sentinel": False}

_CAN_SFF_MASK = 0x000007FF
_CAN_EFF_FLAG = 0x80000000
_CAN_EFF_MASK = 0x1FFFFFFF
_CAN_ERR_FLAG = 0x20000000


def can_reader_loop(link: str):
    """Read one CAN bus forever. link is a key of CAN_IFACES.

    Identical for every bus: collect per-ID stats for the raw view, and for
    the two booster buses additionally decode the signals in DECODE.md. The
    steering bus has no decode because nothing on it is known — it collects
    raw stats only, which is exactly what a discovery screen needs.

    A missing interface is normal, not an error: can-steer does not exist
    until a third adapter is fitted. Log once, retry forever, never let it
    take the process down.
    """
    import socket as sk
    import struct as st
    iface = CAN_IFACES[link]
    complained = False
    while True:
        try:
            s = sk.socket(sk.PF_CAN, sk.SOCK_RAW, sk.CAN_RAW)
            s.bind((iface,))
            s.settimeout(1.0)
            complained = False
            log.info("CAN: %s up on %s", link, iface)
            while True:
                try:
                    frame = s.recv(16)
                except (sk.timeout, TimeoutError):
                    continue
                now = time.monotonic()
                can_id, dlc = st.unpack("=IB3x", frame[:8])
                if can_id & _CAN_ERR_FLAG:
                    continue
                mask = _CAN_EFF_MASK if can_id & _CAN_EFF_FLAG else _CAN_SFF_MASK
                cid = can_id & mask
                data = frame[8:8 + min(dlc, 8)]
                _mark_rx(link)

                with _can_lock:
                    ent = _can_stats.get((link, cid))
                    if ent is None:
                        _can_stats[(link, cid)] = {"hz": 0.0, "dlc": dlc,
                                                   "data": data, "prev": data,
                                                   "t": now}
                    else:
                        dt = now - ent["t"]
                        if dt > 1e-4:
                            # EMA so the displayed rate is steady, not jittery
                            ent["hz"] = 0.9 * ent["hz"] + 0.1 * (1.0 / dt)
                        ent["prev"], ent["data"] = ent["data"], data
                        ent["dlc"], ent["t"] = dlc, now

                    if cid == 0x39D and len(data) >= 4:
                        # Reject frames whose additive checksum fails rather
                        # than showing a corrupt stroke as a real one.
                        if ((data[1] + data[2] + data[3] + 0xA0) & 0xFF) == data[0]:
                            raw = data[2] | (data[3] << 8)
                            _brake["stroke_raw"] = raw
                            _brake["sentinel"] = raw > BRAKE_STROKE_SENTINEL
                    elif cid == 0x38E and len(data) >= 5:
                        _brake["status"] = data[4] >> 4
                        _brake["pos_yaw"] = data[3] | ((data[4] & 0x0F) << 8)
        except OSError as e:
            if not complained:
                log.info("CAN: %s (%s) unavailable: %s — retrying", link, iface, e)
                complained = True
            try:
                s.close()
            except Exception:
                pass
            time.sleep(3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI + WebSocket Server
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="944S HVAC Controller")

# Global instances
hw = HardwareManager()
controller = HVACController(hw)
connected_clients = set()


# ── iDrive controller link ─────────────────────────────────────
# The ESP32 in the HVAC enclosure reads the BMW knob off CAN and writes
# newline-delimited JSON here. Runs in a daemon thread because pyserial
# is blocking.
#
# Every failure path degrades quietly: no pyserial, no port, unplugged
# cable, garbage bytes — all logged once and then retried or skipped.
# The knob is a convenience; climate control must never depend on it.
IDRIVE_PORT = "/dev/serial0"
IDRIVE_BAUD = 115200

# A link is "online" if it has said anything at all within this window. The
# iDrive firmware heartbeats every 2 s, the lighting board and the bridge are
# polled at the same rate, so measured age tops out just under 2 s and this is
# five missed messages rather than one. Deliberately generous: a false red is
# as bad as a false green, and nothing here needs sub-second fault detection.
# The cost of the margin is that a genuine dead link takes this long to show.
LINK_STALE_S = 10.0

# Monotonic stamp of the last line received from each link. Written by the
# reader threads, read by tick(). Plain floats: assignment is atomic under the
# GIL and a torn read here would only ever be one tick stale.
_last_rx = {"idrive": 0.0, "illum": 0.0, "tsdash": 0.0,
            "canveh": 0.0, "canyaw": 0.0, "cansteer": 0.0}

# Whether the reader thread currently holds the port open. Separate from
# freshness on purpose: an open port that has gone quiet is a different fault
# from a port that will not open, and the status page says which.
_port_up = {"illum": False, "tsdash": False}


def _mark_rx(link: str):
    """Note that a link just proved it is alive."""
    _last_rx[link] = time.monotonic()


def _age_of(link: str, now: float) -> float:
    """Seconds since this link last spoke, or -1 if it never has.

    Clamped at zero. tick() samples `now` once at the top and then spends
    real time reading sensors, so a reader thread can stamp _last_rx with a
    LATER timestamp before we get here — giving a small negative age. The
    freshness test is `0 <= age < LINK_STALE_S`, so that negative value
    failed the lower bound and flashed the link offline for one frame,
    roughly once per poll cycle. Measured at -0.01 to -0.03 s.
    """
    t = _last_rx[link]
    if t <= 0:
        return -1.0
    return max(0.0, now - t)

# ── Interior lighting board ────────────────────────────────────
# ESP32 output board on USB (stable name from the udev rule). We send
# RELATIVE commands only — the board owns the real brightness and reports
# it back, so this end never has to guess and can never drift from the
# round knob. Protocol lives in the lighting repo's pwm_controller.ino.
LIGHTING_PORT = "/dev/lighting"
LIGHTING_BAUD = 115200
LIGHT_STEP    = 8          # brightness units per knob detent (0-255 range)

_lighting_port = None                    # serial.Serial when the link is up
_lighting_lock = threading.Lock()

def lighting_send(line: str):
    """Send one command line to the lighting board, if it is connected."""
    with _lighting_lock:
        port = _lighting_port
    if port is None:
        log.debug("lighting: %s dropped — link down", line)
        return
    try:
        port.write((line + "\n").encode())
    except Exception as e:
        log.warning("lighting: write failed: %s", e)


def lighting_reader_loop():
    """Read state reports from the lighting board and mirror them."""
    global _lighting_port
    try:
        import serial
    except ImportError:
        log.warning("lighting link disabled — pyserial not installed")
        return

    complained = False
    while True:
        try:
            port = serial.Serial(LIGHTING_PORT, LIGHTING_BAUD, timeout=1)
            with _lighting_lock:
                _lighting_port = port
            _port_up["illum"] = True
            complained = False
            log.info("lighting link up on %s", LIGHTING_PORT)
            port.write(b"L GET\n")        # ask for current state on connect
            last_poll = time.monotonic()

            # readline(), never `for line in port` — iteration ends the
            # moment a read times out, which idle guarantees.
            while True:
                # Poll on idle, exactly as the bridge does. This board only
                # speaks when something changes, so without it a healthy but
                # untouched link ages out and the status page shows a red that
                # is not real — the same lie as a false green, just louder.
                now = time.monotonic()
                if now - last_poll >= 2.0:
                    last_poll = now
                    port.write(b"L GET\n")
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                # The board shares this port with its own diagnostic prints;
                # only JSON objects are protocol.
                if not line.startswith("{"):
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("src") != "illum":
                    continue
                _mark_rx("illum")
                st = controller.state
                try:
                    st.illum_ch1   = int(evt.get("ch1", st.illum_ch1))
                    st.illum_ch2   = int(evt.get("ch2", st.illum_ch2))
                    st.illum_color = int(evt.get("color", st.illum_color))
                    st.illum_relay = bool(int(evt.get("relay", st.illum_relay)))
                    st.illum_night = bool(int(evt.get("night", st.illum_night)))
                except (TypeError, ValueError):
                    log.debug("lighting: unparseable report %r", line[:80])
        except Exception as e:
            with _lighting_lock:
                _lighting_port = None
            _port_up["illum"] = False
            if not complained:
                log.warning("lighting link unavailable (%s): %s — retrying",
                            LIGHTING_PORT, e)
                complained = True
            time.sleep(5)
# ── TSDash bridge board ────────────────────────────────────────
# A spare ESP32-S3 with two USB ports: its UART port is on our hub (this
# link), and its native USB port is plugged into the TSDash Pi, where it
# enumerates as a plain HID keyboard. TS Dash has documented shortcuts —
# Ctrl+Right / Ctrl+Left move between dashes — so the bridge just types
# them. The TSDash Pi needs nothing installed on it at all, which is the
# whole reason for this route: it has no SSH and no network in the car.
#
# Note this appears as ttyUSB* (a CH340/CP2102 bridge chip), not ttyACM*
# like the other three boards, which are all native-USB CDC.
# Protocol lives in the idrive-controller repo's dash_bridge.ino.
TSDASH_PORT = "/dev/tsdash"
TSDASH_BAUD = 115200

# The bridge is the ONE board here that udev cannot pin by MAC. We reach it
# through its UART port, where the host enumerates a CH340 — a separate
# chip with its own descriptor, no knowledge of the ESP32's MAC, and (on
# this unit, checked 2026-07-31) no serial number of its own either. So
# /dev/tsdash is pinned to a physical hub port and follows the SOCKET, not
# the board: move the cable and the symlink points at whatever is there now.
#
# The firmware therefore reports its MAC in every status line, and we check
# it. This is not paranoia — the bridge is 3C:DC:75:40:0B:D8 and the
# lighting board is 3C:DC:75:40:0B:F0, same batch, differing in the last
# byte. Exactly the trap already documented for the two gauge panels.
TSDASH_MAC = "3C:DC:75:40:0B:D8"

_tsdash_port = None                      # serial.Serial when the link is up
_tsdash_lock = threading.Lock()


def tsdash_send(cmd: str):
    """Send one command to the TSDash bridge, if it is connected.

    Relative moves only — NEXT and PREV, never "go to dash 3". The bridge
    types blind into a Pi we cannot query, and the TSDash screen can also
    be swiped by hand, so any dash index cached here would be wrong the
    moment anyone touched it. Same reasoning as the lighting board's
    L ADJ: the device that owns the state stays the owner.
    """
    with _tsdash_lock:
        port = _tsdash_port
    if port is None:
        log.debug("tsdash: %s dropped — link down", cmd)
        return
    try:
        port.write((cmd + "\n").encode())
        controller.state.tsdash_last = cmd
    except Exception as e:
        log.warning("tsdash: write failed: %s", e)


def tsdash_reader_loop():
    """Hold the bridge port open and mirror its status reports."""
    global _tsdash_port
    try:
        import serial
    except ImportError:
        log.warning("tsdash link disabled — pyserial not installed")
        return

    complained = False
    while True:
        try:
            port = serial.Serial(TSDASH_PORT, TSDASH_BAUD, timeout=1)
            with _tsdash_lock:
                _tsdash_port = port
            _port_up["tsdash"] = True
            complained = False
            log.info("tsdash link up on %s", TSDASH_PORT)
            port.write(b"D PING\n")       # prove the far end answers
            last_poll = time.monotonic()

            # readline(), never `for line in port` — same trap as the
            # lighting loop: iteration ends on the first read timeout,
            # which an idle knob guarantees.
            while True:
                # Poll on idle. Without this the bridge only speaks when spoken
                # to, so a dead board and a quiet one look identical and the age
                # column on the status page would be meaningless.
                now = time.monotonic()
                if now - last_poll >= 2.0:
                    last_poll = now
                    port.write(b"D GET\n")
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                # The bridge prints a banner on boot; only JSON is protocol.
                if not line.startswith("{"):
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("src") != "dash":
                    continue
                _mark_rx("tsdash")

                # init and usb split the failure in half and the status page is
                # built on the distinction: init:0 is a firmware or build fault,
                # init:1 with usb:0 is a cable, port or host fault. Logging them
                # and throwing them away meant the screen could only ever say
                # "something is wrong".
                controller.state.tsdash_init = bool(int(evt.get("init", 0)))
                controller.state.tsdash_usb  = bool(int(evt.get("usb", 0)))

                # Identity check. Warn loudly but keep working: a wrong
                # board will not understand "D NEXT" anyway, so the failure
                # is inert, and refusing to run would turn any future
                # firmware change into a dead feature. The point is that a
                # moved cable leaves a trace instead of being silent.
                mac = str(evt.get("mac", ""))
                if mac and mac != controller.state.tsdash_mac:
                    controller.state.tsdash_mac = mac
                    if mac != TSDASH_MAC:
                        log.warning(
                            "tsdash: %s is board %s, expected %s — /dev/tsdash "
                            "is pinned to a hub PORT, so a moved cable points "
                            "it at a different board", TSDASH_PORT, mac, TSDASH_MAC)
                    else:
                        log.info("tsdash: board %s confirmed", mac)

                # usb=0 means the bridge is powered and listening to us but
                # the TSDash Pi has not enumerated it — keystrokes go
                # nowhere. Worth a log line; not worth refusing to send.
                if not int(evt.get("usb", 1)):
                    log.debug("tsdash: bridge up but TSDash Pi not enumerated")
        except Exception as e:
            with _tsdash_lock:
                _tsdash_port = None
            _port_up["tsdash"] = False
            if not complained:
                log.warning("tsdash link unavailable (%s): %s — retrying",
                            TSDASH_PORT, e)
                complained = True
            time.sleep(5)


# IDRIVE_ACTIVE_S lives with the other loop constants near the top.


def idrive_reader_loop():
    """Read iDrive events off the UART and feed them to the controller."""
    try:
        import serial
    except ImportError:
        log.warning("iDrive link disabled — pyserial not installed "
                    "(pip install pyserial --break-system-packages)")
        return

    complained = False
    while True:
        try:
            port = serial.Serial(IDRIVE_PORT, IDRIVE_BAUD, timeout=1)
            log.info("iDrive link up on %s", IDRIVE_PORT)
            complained = False
            # Explicit readline() loop, NOT `for raw in port`. Iterating a
            # Serial stops as soon as readline() returns empty, which the
            # 1s timeout guarantees every time the knob is idle — the outer
            # loop would then reopen the port and log "link up" once per
            # second forever, without ever reading an event.
            while True:
                raw = port.readline()
                if not raw:
                    continue            # read timeout, nothing waiting
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    log.debug("iDrive: bad line %r", line[:80])
                    continue
                # Any well-formed line proves the wire, heartbeat or not.
                _mark_rx("idrive")
                # Heartbeats carry no action. They must NOT reach
                # apply_idrive_event() — that would light idrive_active every
                # 2 s and leave the on-screen knob mirror permanently awake.
                if evt.get("hb"):
                    continue
                try:
                    controller.apply_idrive_event(evt)
                except Exception as e:
                    log.error("iDrive: failed to apply %s: %s", evt, e)
        except Exception as e:
            if not complained:
                log.warning("iDrive link unavailable (%s): %s — retrying", IDRIVE_PORT, e)
                complained = True
            time.sleep(5)


@app.on_event("startup")
async def startup():
    """Start the background control loop."""
    asyncio.create_task(control_loop())
    threading.Thread(target=idrive_reader_loop, daemon=True,
                     name="idrive-reader").start()
    for _link in CAN_IFACES:
        threading.Thread(target=can_reader_loop, args=(_link,), daemon=True,
                         name=f"can-{_link}-reader").start()
    threading.Thread(target=lighting_reader_loop, daemon=True,
                     name="lighting-reader").start()
    threading.Thread(target=tsdash_reader_loop, daemon=True,
                     name="tsdash-reader").start()
    log.info("HVAC controller started — %s mode", "SIMULATION" if SIMULATE else "HARDWARE")


@app.on_event("shutdown")
async def shutdown():
    hw.shutdown()


async def control_loop():
    """Background task: runs PID control and broadcasts state to all clients."""
    global connected_clients
    interval = 1.0 / CONTROL_HZ
    while True:
        try:
            controller.tick()

            # Broadcast state to all connected dashboards
            state_json = controller.state.to_json()
            dead = set()
            for ws in connected_clients:
                try:
                    await ws.send_text(state_json)
                except Exception:
                    dead.add(ws)
            connected_clients -= dead

        except Exception as e:
            log.error("Control loop error: %s", e)

        await asyncio.sleep(interval)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Dashboard WebSocket — receives commands, gets state broadcasts."""
    await ws.accept()
    connected_clients.add(ws)
    log.info("Dashboard connected (%d clients)", len(connected_clients))

    try:
        while True:
            data = await ws.receive_text()
            try:
                cmd = json.loads(data)
                controller.apply_command(cmd)
                log.debug("Command: %s", cmd)
            except json.JSONDecodeError:
                log.warning("Invalid JSON from client: %s", data[:100])
    except WebSocketDisconnect:
        connected_clients.discard(ws)
        log.info("Dashboard disconnected (%d clients)", len(connected_clients))


# ── REST API for debugging / external integration ──────────────

@app.get("/api/state")
async def get_state():
    """Get current HVAC state as JSON."""
    return json.loads(controller.state.to_json())


@app.post("/api/command")
async def post_command(cmd: dict):
    """Send a command to the HVAC controller."""
    controller.apply_command(cmd)
    return {"ok": True}


# ── Serve the React dashboard as static files ─────────────────
app.mount("/", StaticFiles(directory="/home/mark/hvac/dashboard/build", html=True), name="dashboard")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
