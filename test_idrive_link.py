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

    lighting_sent = []
    ns = {"dataclass": dataclass, "field": field, "asdict": asdict,
          "json": json, "time": time, "Optional": object,
          "lighting_send": lighting_sent.append,
          "tsdash_send": lambda *_: None,
          "log": type("L", (), {"warning": lambda *a, **k: None,
                                "info": lambda *a, **k: None,
                                "debug": lambda *a, **k: None})(),
          "_sent": lighting_sent}

    # Pull module-level CONSTANTS out of the backend rather than listing
    # them here. Hand-listing was the one drift vector left in a file whose
    # whole point is not to drift, and it had already broken: VENT_MODE_ORDER
    # was added to the backend and this file never learned about it, so
    # Test 3 died with a NameError instead of testing anything. Anything
    # ALL_CAPS and literal now arrives automatically.
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.isupper():
            try:
                ns[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                pass          # not a literal — nothing this harness needs
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
    # Hand the extracted constants back too, so tests can assert against
    # the real MAIN_SCREENS rather than a copy that would drift the same way
    # the hand-listed ones did.
    consts = {k: v for k, v in ns.items() if k.isupper()}
    return ns["HVACState"], ns["Ctl"], lighting_sent, consts


HVACState, Ctl, LIGHTING_SENT, BACKEND_CONSTS = load_from_backend()
globals().update(BACKEND_CONSTS)

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

print("\nTest 11: lighting is driven by RELATIVE commands only")
c = new(); LIGHTING_SENT.clear()
c.apply_idrive_event(evt("LIGHT_BRIGHTER", 3, mode="ILLUM"))
check(LIGHTING_SENT == ["L ADJ 1 24"], f"3 detents -> one +24 adjust, got {LIGHTING_SENT}")
LIGHTING_SENT.clear()
c.apply_idrive_event(evt("LIGHT_DIMMER", 2, mode="ILLUM"))
check(LIGHTING_SENT == ["L ADJ 1 -16"], f"dimmer sends negative, got {LIGHTING_SENT}")
LIGHTING_SENT.clear()
c.apply_idrive_event(evt("LIGHT_SCENE_NEXT", mode="ILLUM"))
c.apply_idrive_event(evt("LIGHT_SCENE_PREV", mode="ILLUM"))
c.apply_idrive_event(evt("LIGHT_TOGGLE", mode="ILLUM"))
check(LIGHTING_SENT == ["L ADJ 5 1", "L ADJ 5 -1", "L ADJ 3 1"],
      f"scene and dome map correctly, got {LIGHTING_SENT}")
check(not any(cmd.startswith("L SET") for cmd in
              ["L ADJ 1 24", "L ADJ 1 -16"]), "never sends an absolute SET")

print("\nTest 12: lighting actions never touch HVAC state")
c = new(); LIGHTING_SENT.clear()
before = (c.state.setpoint_f, c.state.fan_speed, c.state.aux_display)
for a in ("LIGHT_BRIGHTER", "LIGHT_DIMMER", "LIGHT_TOGGLE",
          "LIGHT_SCENE_NEXT", "LIGHT_SCENE_PREV"):
    c.apply_idrive_event(evt(a, mode="ILLUM"))
check(c.commands == [], "no HVAC command issued")
check((c.state.setpoint_f, c.state.fan_speed, c.state.aux_display) == before,
      "setpoint / fan / aux untouched")
check(c.state.idrive_mode == "illum", "but the mirror tracks ILLUM mode")

print("\nTest 13: the backend never caches absolute lighting brightness")
c = new(); LIGHTING_SENT.clear()
c.apply_idrive_event(evt("LIGHT_BRIGHTER", 5, mode="ILLUM"))
check(c.state.illum_ch1 == 0,
      "illum_ch1 stays at its reported value - only the board sets it")

# ── Screen cycling (BACK) and get-me-home (MENU) ──────────────────
# This pair broke in service: main_screen:"steer" was rejected by a
# validator that had never learned about the screen, so the dashboard showed
# it optimistically and snapped back 800 ms later. A cycle that silently
# refuses to reach one of its own stops is exactly the shape to test for.

print("\nTest 14: BACK cycles every screen and returns home")
c = new()
seen = []
for _ in range(len(MAIN_SCREENS) + 1):
    c.apply_idrive_event(evt("SYSTEM_TOGGLE"))
    seen.append("system" if c.state.system_view else c.state.main_screen)
check(seen[:len(MAIN_SCREENS)] == list(MAIN_SCREENS[1:]) + ["system"],
      f"walks {' -> '.join(MAIN_SCREENS[1:])} -> system, got {seen[:-1]}")
check(seen[-1] == MAIN_SCREENS[0],
      f"wraps back to {MAIN_SCREENS[0]}, got {seen[-1]}")
check(set(seen) >= set(MAIN_SCREENS),
      f"every screen reachable, missed {set(MAIN_SCREENS) - set(seen)}")

print("\nTest 15: every screen the cycle emits is one the validator accepts")
c = new()
emitted = set()
for _ in range(12):
    c.apply_idrive_event(evt("SYSTEM_TOGGLE"))
for cmd in c.commands:
    if "main_screen" in cmd:
        emitted.add(cmd["main_screen"])
check(emitted <= set(MAIN_SCREENS),
      f"cycle never names an unknown screen, emitted {sorted(emitted)}")
check(emitted == set(MAIN_SCREENS),
      f"cycle emits all of them, missing {set(MAIN_SCREENS) - emitted}")

print("\nTest 16: MENU returns the display home from anywhere")
for start in list(MAIN_SCREENS) + ["system"]:
    c = new()
    if start == "system":
        c.state.system_view = True
    else:
        c.state.main_screen = start
    c.apply_idrive_event(evt("MODE_ENTER", mode="hvac"))
    check(c.state.main_screen == "hvac" and not c.state.system_view,
          f"from {start} -> hvac")

print("\nTest 17: other mode buttons leave the screen alone")
for m in ("radio", "illum", "gauge", "tsdash"):
    c = new()
    c.state.main_screen = "brake"
    c.apply_idrive_event(evt("MODE_ENTER", mode=m))
    check(c.state.main_screen == "brake", f"{m} does not steal the screen")

print(f"\n{'ALL TESTS PASSED' if not failures else 'FAILED'} "
      f"({failures} failure{'' if failures == 1 else 's'})")
sys.exit(1 if failures else 0)
