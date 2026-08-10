# 944S HVAC — Flap Calibration

How the three flap actuators are measured, what the current numbers are, and
the one thing still unverified. Current as of 2026-08-06.

---

## What the feedback actually is

Each actuator has a potentiometer **inside the actuator**, on ~5 V excitation,
read by the ADS1115 at `0x48`. This matters more than it sounds:

- The pot tracks the **actuator**, not the door. It cannot see a linkage that
  has slipped, bent, or come off. A perfectly healthy-looking sweep proves the
  motor moved, not that the flap did.
- Because it is inside the actuator, its end stops are the actuator's own and
  are **repeatable**. They do not shift when the door or linkage is worked on,
  which makes them a usable datum for setting a door against.
- The ADS must run at **gain 2/3** (±6.144 V). At gain 1 a 5 V pot clips, and
  roughly a volt of travel disappears silently.

| Channel | Flap | H-bridge pins (BCM) |
|---------|------|--------------------|
| A0 | blend / mix | 23 = COLD, 24 = HOT |
| A1 | defrost | 16 / 20 |
| A2 | footwell | 12 / 21 |

---

## The tool

`deploy/flap-pulse.py`. **The backend must be stopped** — both would drive the
same pins and read the same ADC.

```bash
sudo systemctl stop hvac-backend
cd ~/hvac

python3 deploy/flap-pulse.py check              # read all three, no motion
python3 deploy/flap-pulse.py pulse blend in1    # one nudge, default 120 ms
python3 deploy/flap-pulse.py sweep blend        # drive to both actuator stops
python3 deploy/flap-pulse.py sweep blend --gentle   # stop at first sign of binding

sudo systemctl start hvac-backend
```

It refuses to run if a channel reads outside 40–5300 mV, caps pulse width at
400 ms, stops after 3 no-progress pulses, and commands every motor off on
Ctrl-C.

### Which sweep to use

| Situation | Command | Why |
|-----------|---------|-----|
| Actuator arm **off** the door | `sweep` | Reaches the real hard stops. The pot is inside the actuator, so stalling briefly against its own stops is what it is built to do. |
| Any linkage **in the load path** | `sweep --gentle` | Stops when a pulse delivers under 35% of the travel it had been managing — that is the flap loading up, and it happens well before a stall. Backs off 120 mV. |

`--gentle` **cannot tell a door binding from an actuator hard stop** — travel
falls to zero either way, and it reports "BINDING" for both. The numbers tell
you which: if it stops within a few tens of mV of the known free stops, it
found the actuator; if it stops well short, the door is the limit.

---

## Fitting a linkage against a known datum

This is the procedure that fixed blend. The failure it replaced was setting the
door by hand to an *assumed* mid position — the actuator was not actually at
mid, so every measured millivolt mapped to the wrong physical place. The
numbers were self-consistent and completely wrong, which is the worst kind:
nothing in the data looks off.

1. Disconnect the arm from the door.
2. `sweep` the free actuator. Record both stops.
3. The flap is now parked on the stop it finished at — a measured datum.
4. Set the door to the position that matches that stop, and fit the linkage.
5. `sweep --gentle` with the linkage on. Compare travel against the free range.
6. If the door reaches the actuator's stops, calibrate 60 mV inside each
   measured end. If the door binds first, calibrate inside the **binding**
   points, not the actuator's.

---

## Current measured values

### Blend — 2026-08-06, permanent linkage

| | mV |
|---|---|
| Actuator free, in2 stop | 111 |
| Actuator free, in1 stop | 4907 |
| Free travel | 4788 |
| Door on permanent linkage, in2 | 125 |
| Door on permanent linkage, in1 | 4879 (peaked 4896) |
| Door travel | 4754 |
| **Lost to linkage** | **34 mV (0.7%)** |

The door is no longer what limits travel. The temporary linkage it replaced
cost 108 mV; this one costs 34. Backend calibration went back to the standard
60 mV margin from the doubled 120 mV the temporary linkage warranted:

```python
ADS_MIX_CHANNEL:  {"lo":  185, "hi": 4819, "invert": True}
```

Verified live: with the hold lifted, the PID drove the full span from 125 mV
and settled at 1.1% against a 0% target — inside the 3.0% `FLAP_SETTLE` stop
band, no overdrive fault, parked ≈4765 mV, which is 52 mV short of the limit
and 112 mV short of the door's stop. It is not leaning on anything.

### Defrost and footwell

Confirmed against the physical flaps 2026-08-02: defrost read 0% while fully
**open**, footwell read 100% while fully **closed**. Both inverted, so on all
three flaps **100% means "more"** — full hot, full defrost, foot open.

```python
ADS_DEF_CHANNEL:  {"lo":  417, "hi": 4971, "invert": True}
ADS_FOOT_CHANNEL: {"lo":  258, "hi": 4956, "invert": True}
```

---

## OPEN: blend direction is unverified

`invert: True` says raw-low (the GPIO24 / in2 end) is HOT and publishes as
100%. That follows the `in1=COLD, in2=HOT` record in `flap-pulse.py`, but **the
door is not visible with the dash in** and could not be confirmed by eye.

The span and the linearity are measured and trustworthy. Only the **sense** is
inherited.

**To settle it:** run the engine to temperature, command full heat, and feel
the duct. If it blows cold, change `invert` to `False` in `ADS_MIX_CHANNEL` and
change nothing else — the limits describe travel, not direction, so they hold
either way.

Expect the loop to look perfectly healthy while doing the wrong thing. The
feedback is self-consistent, so the dashboard will show it hitting target
exactly; duct temperature is the only thing that will tell you.

---

## Non-uniform plant gain

Blend does not move at a constant rate. Above ~3000 mV it manages ~115 mV per
pulse; below it, ~200 mV — a ~1.7× difference, consistent in **both**
directions, so it is geometry or a spring load rather than directional
friction. The blend PID has correspondingly less authority approaching full
cold. Not a problem while it settles cleanly, but it is the first place to look
if it ever gets sluggish at that end.

(Do not compare pulse sizes between a `sweep` and a `--gentle` run — 120 ms
versus 100 ms.)

---

## Protections in the backend

| Constant | Value | What it does |
|----------|-------|-------------|
| `FLAP_MAX_DRIVE_S` | 8.0 s | Driving this long without feedback advancing cuts the motor — stall, end stop, or lost feedback |
| `FLAP_PROGRESS_EPS` | 1.5% | Movement below this does not count as progress |
| `FLAP_SETTLE` | mix 3/7%, others 4/10% | Hysteresis: stop inside the first number, do not re-engage until outside the second. Stops the chatter |
| `FLAP_HELD` | `set()` | Flaps the controller must not drive. Empty — blend's hold was lifted 2026-08-06 |

`FLAP_HELD` is deliberately code-level, not a runtime toggle: re-enabling a
flap should be a decision someone makes on purpose with the reason in front of
them, not something a stray command can undo.
