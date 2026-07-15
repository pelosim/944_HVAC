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

# --- Analog Scaling ---
ADC_MV_MIN = 225     # mV at 0% position
ADC_MV_MAX = 4090    # mV at 100% position

# --- PID Tuning ---
# These are starting points — tune on the car
FLAP_PID_KP = 2.0    # Proportional gain
FLAP_PID_KI = 0.5    # Integral gain
FLAP_PID_KD = 0.1    # Derivative gain
FLAP_DEADBAND = 2.0  # % — don't drive motor within this band of setpoint

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
    vent_mode: str = "face"

    # Sensor readings
    mix_chamber_temp_f: float = 0.0
    exterior_temp_f: float = 0.0

    # Flap positions (0–100%)
    mix_flap_pos: float = 50.0
    defrost_flap_pos: float = 0.0
    footwell_flap_pos: float = 0.0

    # Flap setpoints (computed by mode logic)
    mix_flap_target: float = 50.0
    defrost_flap_target: float = 0.0
    footwell_flap_target: float = 0.0

    # System status
    control_active: bool = False
    onewire_ok: bool = False
    ads_ok: bool = False
    uptime_s: float = 0.0

    # Seat heaters (0–100% duty cycle)
    seat_heat_driver: float = 0.0
    seat_heat_passenger: float = 0.0

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

        if not SIMULATE:
            self._init_gpio()
            self._init_ads()
            self._init_temps()
        else:
            log.info("SIMULATION: Hardware stubs active")
            self._sim_mix_pos = 50.0
            self._sim_def_pos = 0.0
            self._sim_foot_pos = 0.0
            self._sim_mix_temp = 68.0
            self._sim_ext_temp = 47.0

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
            ads.gain = 1  # ±4.096V range
            self._ads_channels = {
                ADS_MIX_CHANNEL:  AnalogIn(ads, 0),
                ADS_DEF_CHANNEL:  AnalogIn(ads, 1),
                ADS_FOOT_CHANNEL: AnalogIn(ads, 2),
            }
            log.info("ADS1115 initialized at 0x%02X", ADS_I2C_ADDR)
        except Exception as e:
            log.error("ADS1115 init failed: %s", e)

    def _init_temps(self):
        try:
            for sensor in W1ThermSensor.get_available_sensors():
                self._temp_sensors[sensor.id] = sensor
                log.info("Found DS18B20: %s", sensor.id)
        except NoSensorFoundError:
            log.warning("No DS18B20 sensors found")
        except Exception as e:
            log.error("1-Wire init failed: %s", e)

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
        self.drive_hbridge(PIN_MIX_HOT, PIN_MIX_COLD, command)

    def drive_defrost_flap(self, command: float):
        self.drive_hbridge(PIN_DEF_IN1, PIN_DEF_IN2, command)

    def drive_footwell_flap(self, command: float):
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
            pct = (mv - ADC_MV_MIN) / (ADC_MV_MAX - ADC_MV_MIN) * 100
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
            return None

        sensor = self._temp_sensors.get(sensor_id)
        if sensor is None:
            return None
        try:
            c = sensor.get_temperature()
            return c * 9.0 / 5.0 + 32.0
        except Exception as e:
            log.error("Temp read %s failed: %s", sensor_id, e)
            return None

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

    # ── State persistence (survives power loss) ──────────────
    _PERSIST_FIELDS = ("setpoint_f", "fan_speed", "ac_on", "heat_valve",
                       "outside_air", "vent_mode", "seat_heat_driver",
                       "seat_heat_passenger")

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
            mode = cmd["vent_mode"].lower()
            if mode in ("face", "bilevel", "feet", "defrost"):
                self.state.vent_mode = mode
        if "seat_heat_driver" in cmd:
            self.state.seat_heat_driver = max(0, min(100, float(cmd["seat_heat_driver"])))
        if "seat_heat_passenger" in cmd:
            self.state.seat_heat_passenger = max(0, min(100, float(cmd["seat_heat_passenger"])))
        # Persist user settings after every command
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
            if mix_t is not None:
                self.state.mix_chamber_temp_f = round(mix_t, 1)
            if ext_t is not None:
                self.state.exterior_temp_f = round(ext_t, 1)

        self.state.onewire_ok = self.hw.onewire_ok
        self.state.ads_ok = self.hw.ads_ok

        # ── Safety interlocks ─────────────────────────────────
        # Don't run AC and heat valve simultaneously (compressor load + wasted energy)
        if self.state.ac_on and self.state.heat_valve:
            # AC takes priority in conflict
            self.state.heat_valve = False

        # Fan must be on for AC
        if self.state.ac_on and self.state.fan_speed == "OFF":
            self.state.fan_speed = "LOW"

        # Defrost mode forces outside air (prevents fogging)
        if self.state.vent_mode == "defrost":
            self.state.outside_air = True

        # ── Compute flap targets from vent mode ───────────────
        mode_targets = {
            "face":    {"defrost": 0,   "footwell": 0},
            "bilevel": {"defrost": 0,   "footwell": 100},
            "feet":    {"defrost": 0,   "footwell": 100},
            "defrost": {"defrost": 100, "footwell": 0},
        }
        targets = mode_targets.get(self.state.vent_mode, mode_targets["face"])
        self.state.defrost_flap_target = targets["defrost"]
        self.state.footwell_flap_target = targets["footwell"]

        # ── Temperature PID → mixing flap target ──────────────
        if self.state.fan_speed != "OFF" and self.state.mix_chamber_temp_f > 0:
            # PID output: 0% = full cold, 100% = full hot
            mix_target = self.temp_pid.update(
                self.state.setpoint_f, self.state.mix_chamber_temp_f
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
        else:
            mix_cmd = def_cmd = foot_cmd = 0
            self.mix_pid.reset()
            self.def_pid.reset()
            self.foot_pid.reset()

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
            # Simulate duct temp response
            if self.state.heat_valve:
                self.hw._sim_mix_temp += 0.05
            elif self.state.ac_on:
                self.hw._sim_mix_temp -= 0.03
            else:
                self.hw._sim_mix_temp += (self.hw._sim_ext_temp - self.hw._sim_mix_temp) * 0.002


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


@app.on_event("startup")
async def startup():
    """Start the background control loop."""
    asyncio.create_task(control_loop())
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
