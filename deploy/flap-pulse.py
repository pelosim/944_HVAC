#!/usr/bin/env python3
"""Pulse-test and calibrate the flap H-bridges, without cooking a motor.

    sudo systemctl stop hvac-backend        # MANDATORY — see below
    python3 deploy/flap-pulse.py check              # read-only, no motion
    python3 deploy/flap-pulse.py pulse blend in1    # one short nudge
    python3 deploy/flap-pulse.py sweep blend        # find both end stops
    sudo systemctl start hvac-backend

The backend must be stopped. It drives these same six GPIOs from its PID
loop and polls the same ADC — two writers on one H-bridge is how you get a
motor driven two ways at once, and two readers on one ADS1115 interleave
into nonsense. The script refuses to run if it is up.

WHAT MAKES THIS SAFE

Every motion is a short pulse followed by a settle and a measurement, never
a continuous drive. The motor only ever runs for PULSE_MS at a time, and
between pulses the bridge is commanded to both-pins-LOW. Nothing here can
leave a motor energised: stop() runs from a finally block, an atexit hook,
and SIGINT/SIGTERM handlers.

A sweep stops the moment the feedback stops moving. That is the end stop —
the flap has hit its travel limit and the motor is now stalled, which is
exactly the condition that burns it. Three consecutive pulses with no
measurable movement ends the run.

BEFORE THE FIRST RUN, with the connector unplugged, ohm each pot: end to end
should read a few kOhm, and wiper to end should sweep smoothly as the flap is
moved by hand. Pins 4 and 5 are the motor; 1, 2 and 3 are the pot, wiper on
3. A pot wired where a motor belongs is destroyed the instant a bridge drives
it, and no amount of software care prevents that.
"""
import argparse
import atexit
import signal
import subprocess
import sys
import time

# ── H-bridge pins (BCM), matching hvac_backend.py ────────────────
FLAPS = {
    "blend":    {"in1": 23, "in2": 24, "ch": 0, "note": "in1=COLD, in2=HOT"},
    "defrost":  {"in1": 16, "in2": 20, "ch": 1, "note": ""},
    "footwell": {"in1": 12, "in2": 21, "ch": 2, "note": ""},
}

# ── Safety envelope ──────────────────────────────────────────────
PULSE_MS_DEFAULT = 120     # motor on-time per pulse
PULSE_MS_MAX     = 400     # refuse anything longer
SETTLE_S         = 0.35    # let the flap and the pot settle before measuring
NO_PROGRESS_MV   = 15      # movement below this is noise, not travel
MAX_STALL_PULSES = 3       # consecutive no-progress pulses before stopping
MAX_PULSES       = 60      # hard cap per sweep direction
POT_SANE_LO_MV   = 40      # outside this band the feedback is not a working pot
POT_SANE_HI_MV   = 5300    # pots run on ~5 V; measured 5046 mV at a top stop
EDGE_MARGIN_MV   = 60      # stop this far short of a known end stop

_gpio = None
_claimed = []


def stop_all():
    """Both pins LOW on every flap. Idempotent, and safe to call twice."""
    if _gpio is None:
        return
    for pin in _claimed:
        try:
            _gpio.output(pin, _gpio.LOW)
        except Exception:
            pass


def _panic(signum, frame):
    stop_all()
    print("\n!! interrupted — all motors commanded off")
    sys.exit(130)


def backend_running():
    r = subprocess.run(["systemctl", "is-active", "hvac-backend"],
                       capture_output=True, text=True)
    return r.stdout.strip() == "active"


def open_adc():
    """One ADS1115, primed. See check-adc.py for why this matters."""
    import board, busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ads = ADS.ADS1115(busio.I2C(board.SCL, board.SDA), address=0x48)
    ads.gain = 2 / 3   # ±6.144 V — 5 V pot excitation clips at gain=1
    chans = {ch: AnalogIn(ads, ch) for ch in range(4)}
    for ch in chans:
        chans[ch].voltage
    return chans


def read_mv(chans, ch, n=3):
    """Median of n reads. Double-read each: the first after a mux change can
    still carry the previous channel's conversion."""
    vals = []
    for _ in range(n):
        chans[ch].voltage
        vals.append(chans[ch].voltage * 1000.0)
        time.sleep(0.01)
    return sorted(vals)[len(vals) // 2]


def setup_gpio():
    global _gpio
    import RPi.GPIO as GPIO
    _gpio = GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for f in FLAPS.values():
        for key in ("in1", "in2"):
            GPIO.setup(f[key], GPIO.OUT, initial=GPIO.LOW)
            _claimed.append(f[key])
    stop_all()


def pulse(flap, direction, ms, chans):
    """One pulse. Returns (mv_before, mv_after, delta)."""
    f = FLAPS[flap]
    drive = f[direction]
    other = f["in2" if direction == "in1" else "in1"]
    before = read_mv(chans, f["ch"])

    _gpio.output(other, _gpio.LOW)      # never both high
    _gpio.output(drive, _gpio.HIGH)
    time.sleep(ms / 1000.0)
    _gpio.output(drive, _gpio.LOW)

    time.sleep(SETTLE_S)
    after = read_mv(chans, f["ch"])
    return before, after, after - before


def assess(mv):
    if mv < POT_SANE_LO_MV:
        return "near ground — disconnected, wiper shorted, or no pot excitation"
    if mv > 6100:
        return "above full scale — ADC is clipping"
    if mv > POT_SANE_HI_MV:
        return "above the supply — check the excitation rail"
    return "plausible"


def cmd_check(args, chans):
    print("── flap feedback (no motion) ──")
    ok = True
    for name, f in FLAPS.items():
        vals = [read_mv(chans, f["ch"]) for _ in range(6)]
        mv = sum(vals) / len(vals)
        spread = max(vals) - min(vals)
        verdict = assess(mv)
        if verdict != "plausible":
            ok = False
        note = f"  ({f['note']})" if f["note"] else ""
        print(f"  {name:9} A{f['ch']}  {mv:7.1f} mV  spread {spread:5.1f}  {verdict}{note}")
    print()
    if ok:
        print("  All three read like connected pots. A sweep is safe to attempt.")
    else:
        print("  !! At least one channel does not look like a working pot.")
        print("     Do NOT sweep that flap — a bridge driving a flap whose")
        print("     feedback is dead has nothing to tell it when to stop, and")
        print("     the stall detector here works entirely off that feedback.")
    return 0 if ok else 1


def cmd_pulse(args, chans):
    f = FLAPS[args.flap]
    mv = read_mv(chans, f["ch"])
    if assess(mv) != "plausible":
        print(f"  refusing: {args.flap} feedback reads {mv:.0f} mV — {assess(mv)}")
        return 1
    b, a, d = pulse(args.flap, args.direction, args.ms, chans)
    arrow = "up" if d > 0 else "down" if d < 0 else "no change"
    print(f"  {args.flap} {args.direction} {args.ms} ms: "
          f"{b:.0f} -> {a:.0f} mV  ({d:+.0f} mV, {arrow})")
    if abs(d) < NO_PROGRESS_MV:
        print("     no measurable travel — already at an end stop, motor not")
        print("     connected, or the pulse is too short to overcome stiction")
    return 0


def cmd_sweep(args, chans):
    f = FLAPS[args.flap]
    mv = read_mv(chans, f["ch"])
    if assess(mv) != "plausible":
        print(f"  refusing: {args.flap} feedback reads {mv:.0f} mV — {assess(mv)}")
        return 1

    print(f"── sweeping {args.flap} ── pulses of {args.ms} ms, "
          f"stopping after {MAX_STALL_PULSES} with no travel")
    ends = {}
    for direction in ("in1", "in2"):
        stalls = 0
        pulses = 0
        last = read_mv(chans, f["ch"])
        print(f"\n  {direction}: from {last:.0f} mV")
        while stalls < MAX_STALL_PULSES and pulses < MAX_PULSES:
            b, a, d = pulse(args.flap, direction, args.ms, chans)
            pulses += 1
            if assess(a) != "plausible":
                print(f"    {a:7.1f} mV  !! left the sane band — stopping")
                break
            if abs(d) < NO_PROGRESS_MV:
                stalls += 1
                print(f"    {a:7.1f} mV  ({d:+5.0f})  no travel [{stalls}/{MAX_STALL_PULSES}]")
            else:
                stalls = 0
                print(f"    {a:7.1f} mV  ({d:+5.0f})")
            last = a
        ends[direction] = last
        print(f"    end stop for {direction}: {last:.0f} mV after {pulses} pulses")

    lo_dir = min(ends, key=lambda k: ends[k])
    hi_dir = max(ends, key=lambda k: ends[k])
    lo, hi = ends[lo_dir], ends[hi_dir]
    print(f"\n── {args.flap} calibration ──")
    print(f"  {lo_dir} drives DOWN in mV, ends at {lo:.0f} mV")
    print(f"  {hi_dir} drives UP   in mV, ends at {hi:.0f} mV")
    print(f"  usable travel: {hi - lo:.0f} mV")
    if hi - lo < 500:
        print("  !! that is a very small span — feedback may not be tracking the flap")
    print(f"  suggested limits, {EDGE_MARGIN_MV} mV inside each stop:")
    print(f"    0% = {lo + EDGE_MARGIN_MV:.0f} mV     100% = {hi - EDGE_MARGIN_MV:.0f} mV")
    print("  (backend currently uses one global pair for all three flaps:")
    print("   ADC_MV_MIN=225, ADC_MV_MAX=4090)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="read feedback only, drive nothing")
    p = sub.add_parser("pulse", help="one short pulse")
    p.add_argument("flap", choices=FLAPS)
    p.add_argument("direction", choices=["in1", "in2"])
    p.add_argument("--ms", type=int, default=PULSE_MS_DEFAULT)
    s = sub.add_parser("sweep", help="find both end stops and suggest limits")
    s.add_argument("flap", choices=FLAPS)
    s.add_argument("--ms", type=int, default=PULSE_MS_DEFAULT)
    args = ap.parse_args()

    if getattr(args, "ms", 0) > PULSE_MS_MAX:
        print(f"refusing a {args.ms} ms pulse; max is {PULSE_MS_MAX} ms")
        return 2

    if backend_running():
        print("hvac-backend is running. Stop it first:")
        print("    sudo systemctl stop hvac-backend")
        print("It drives these same pins and polls the same ADC.")
        return 2

    chans = open_adc()
    if args.cmd == "check":
        return cmd_check(args, chans)

    setup_gpio()
    atexit.register(stop_all)
    signal.signal(signal.SIGINT, _panic)
    signal.signal(signal.SIGTERM, _panic)
    try:
        return cmd_pulse(args, chans) if args.cmd == "pulse" else cmd_sweep(args, chans)
    finally:
        stop_all()
        print("\n  all motors commanded off")


if __name__ == "__main__":
    sys.exit(main())
