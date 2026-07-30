#!/usr/bin/env python3
"""Tests for the iDrive knob link translation.

Runs anywhere — no Pi, no GPIO, no serial port. Rather than copying the
logic (which would silently drift), this pulls `HVACState` and
`apply_idrive_event` out of hvac_backend.py with `ast` and executes the
real source, so a change to the backend is reflected here immediately.

    python3 test_idrive_link.py
"""
import ast
import json
import sys
import time
from dataclasses import dataclass, field, asdict, is_dataclass
from pathlib import Path

SRC = Path(__file__).with_name("hvac_backend.py")


def load_from_backend():
    """Extract HVACState and apply_idrive_event from the real backend."""
    tree = ast.parse(SRC.read_text())
    state_src = method_src = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "HVACState":
            state_src = ast.get_source_segment(SRC.read_text(), node)
        if isinstance(node, ast.ClassDef) and node.name == "HVACController":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == "apply_idrive_event":
                    method_src = ast.get_source_segment(SRC.read_text(), sub)
    if not state_src:
        sys.exit("could not find HVACState in hvac_backend.py")
    if not method_src:
        sys.exit("could not find apply_idrive_event in hvac_backend.py")

    ns = {"dataclass": dataclass, "field": field, "asdict": asdict,
          "json": json, "time": time, "Optional": object}
    exec(state_src, ns)
    # get_source_segment returns a ClassDef without its decorators, so the
    # extracted class arrives undecorated — reapply @dataclass by hand or
    # asdict() (used by to_json) rejects the instance.
    if not is_dataclass(ns["HVACState"]):
        ns["HVACState"] = dataclass(ns["HVACState"])

    # Wrap the real method in a stand-in controller that records commands.
    body = "\n".join("    " + ln for ln in method_src.splitlines())
    exec("class Ctl:\n"
         "    def __init__(self, state):\n"
         "        self.state = state\n"
         "        self.commands = []\n"
         "        self.saves = 0\n"
         "    def apply_command(self, cmd):\n"
         "        self.commands.append(cmd)\n"
         "        for k, v in cmd.items():\n"
         "            if k == 'setpoint_f':\n"
         "                v = max(60, min(90, float(v)))\n"
         "            setattr(self.state, k, v)\n"
         "    def _save_state(self):\n"
         "        self.saves += 1\n"
         + body, ns)
    return ns["HVACState"], ns["Ctl"]


HVACState, Ctl = load_from_backend()

failures = 0


def check(ok, what):
    global failures
    print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
    if not ok:
        failures += 1


def new():
    return Ctl(HVACState())


def evt(action, count=1, mode="HVAC"):
    return {"mode": mode, "action": action, "count": count}


print("Test 1: setpoint follows detent count and clamps to 60-90")
c = new()
c.state.setpoint_f = 72.0
c.apply_idrive_event(evt("TEMP_UP", 3))
check(c.state.setpoint_f == 75.0, "TEMP_UP x3 raises 72 -> 75")
c.apply_idrive_event(evt("TEMP_DOWN", 5))
check(c.state.setpoint_f == 70.0, "TEMP_DOWN x5 lowers 75 -> 70")
for _ in range(10):
    c.apply_idrive_event(evt("TEMP_UP", 12))
check(c.state.setpoint_f == 90.0, "cannot exceed the 90F ceiling")
for _ in range(20):
    c.apply_idrive_event(evt("TEMP_DOWN", 12))
check(c.state.setpoint_f == 60.0, "cannot go below the 60F floor")

print("\nTest 2: fan steps through OFF/LOW/HI without running off the ends")
c = new()
c.state.fan_speed = "OFF"
c.apply_idrive_event(evt("FAN_UP"))
check(c.state.fan_speed == "LOW", "OFF -> LOW")
c.apply_idrive_event(evt("FAN_UP"))
check(c.state.fan_speed == "HI", "LOW -> HI")
c.apply_idrive_event(evt("FAN_UP"))
check(c.state.fan_speed == "HI", "HI stays HI, no wrap to OFF")
for _ in range(5):
    c.apply_idrive_event(evt("FAN_DOWN"))
check(c.state.fan_speed == "OFF", "walks back down and stops at OFF")

print("\nTest 3: vent mode cycles both ways")
c = new()
c.state.vent_mode = "face"
c.apply_idrive_event(evt("HVAC_MODE_NEXT"))
check(c.state.vent_mode == "bilevel", "face -> bilevel")
c.apply_idrive_event(evt("HVAC_MODE_PREV"))
check(c.state.vent_mode == "face", "and back again")
c.apply_idrive_event(evt("HVAC_MODE_PREV"))
check(c.state.vent_mode == "defrost", "wraps backwards to defrost")

print("\nTest 4: AUX_SWAP toggles the round screen")
c = new()
check(c.state.aux_display == "clock", "starts on clock")
c.apply_idrive_event(evt("AUX_SWAP", mode="RADIO"))
check(c.state.aux_display == "gmeter", "one press -> gmeter")
c.apply_idrive_event(evt("AUX_SWAP", mode="HVAC"))
check(c.state.aux_display == "clock", "press again -> clock, from any mode")

print("\nTest 5: the detent ring tracks rotation, both directions")
c = new()
c.apply_idrive_event(evt("VOL_UP", 4, mode="RADIO"))
check(c.state.idrive_detents == 4, "volume up advances the ring")
c.apply_idrive_event(evt("VOL_DOWN", 6, mode="RADIO"))
check(c.state.idrive_detents == -2, "volume down reverses it")
c.apply_idrive_event(evt("TEMP_UP", 2))
check(c.state.idrive_detents == 0, "temp up advances the same ring")
before = c.state.idrive_detents
c.apply_idrive_event(evt("MUTE", mode="RADIO"))
check(c.state.idrive_detents == before, "a press does not rotate it")

print("\nTest 6: MEDIA actions are mirrored but never command the backend")
c = new()
for a in ("VOL_UP", "VOL_DOWN", "MUTE", "NEXT", "PREV"):
    c.apply_idrive_event(evt(a, mode="RADIO"))
check(c.commands == [], "no HVAC command issued for any media action")
check(c.state.idrive_mode == "radio", "but the mirror knows the mode")
check(c.state.idrive_action == "PREV", "and the last action")

print("\nTest 7: mode is tracked, and liveness is stamped")
c = new()
t0 = time.monotonic()
c.apply_idrive_event(evt("MODE_ENTER", mode="GAUGE"))
check(c.state.idrive_mode == "gauge", "MODE_ENTER records the new mode")
check(c.state.idrive_last_s >= t0, "timestamp advances on input")
c.apply_idrive_event(evt("MODE_ENTER", mode="BOGUS"))
check(c.state.idrive_mode == "gauge", "an unknown mode is ignored, not stored")

print("\nTest 8: malformed events cannot crash or corrupt")
c = new()
c.state.setpoint_f = 72.0
for bad in ({}, {"action": None}, {"action": "TEMP_UP", "count": "banana"},
            {"action": "TEMP_UP", "count": 9999}, {"action": "NONSENSE"},
            {"mode": 12, "action": "TEMP_UP"}):
    try:
        c.apply_idrive_event(bad)
    except Exception as e:
        check(False, f"raised on {bad}: {e}")
check(60 <= c.state.setpoint_f <= 90, "setpoint stayed in range throughout")
check(True, "no malformed event raised")

print("\nTest 9: count is clamped so a garbled frame cannot slam the setpoint")
c = new()
c.state.setpoint_f = 72.0
c.apply_idrive_event({"mode": "HVAC", "action": "TEMP_UP", "count": 10000})
check(c.state.setpoint_f <= 84.0, "a huge count is capped at 12 steps")

print("\nTest 10: state still serialises for the broadcast")
c = new()
c.apply_idrive_event(evt("TEMP_UP", 2))
blob = json.loads(c.state.to_json())
for k in ("idrive_mode", "idrive_detents", "idrive_action",
          "idrive_active", "idrive_last_s"):
    check(k in blob, f"{k} present in the state broadcast")

print(f"\n{'ALL TESTS PASSED' if not failures else 'FAILED'} "
      f"({failures} failure{'' if failures == 1 else 's'})")
sys.exit(1 if failures else 0)
