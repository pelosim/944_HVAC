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

The pot is inside the actuator, so those stops are the actuator's own and
the numbers a sweep produces are repeatable: they do not shift if the door
or its linkage is worked on. The same fact means position is ACTUATOR
position, not DOOR position — a detached linkage reads perfectly normal.

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
# lo/hi are the measured end stops, 2026-08-02, taken with `sweep` at gain
# 2/3. "up" names the input that drives the pot UP in mV — note blend is
# wired opposite to the other two, which is why there is a column for it
# rather than one global rule.
FLAPS = {
    # lo/hi stay the ACTUATOR's free range so "% of travel" means the same
    # thing every time. Re-confirmed 2026-08-06 with the arm off: 111/4907.
    # On the PERMANENT linkage the door now reaches 125/4879, within ~14 mV of
    # those stops — it is no longer what limits travel. (The temporary linkage
    # it replaced bound at 173/4853.) The backend is calibrated to the door.
    "blend":    {"in1": 23, "in2": 24, "ch": 0, "lo": 120, "hi": 4908,
                 "up": "in1", "note": "in1=COLD, in2=HOT (sense UNVERIFIED) · door 125-4879"},
    "defrost":  {"in1": 16, "in2": 20, "ch": 1, "lo": 357, "hi": 5031,
                 "up": "in2", "note": ""},
    "footwell": {"in1": 12, "in2": 21, "ch": 2, "lo": 198, "hi": 5016,
                 "up": "in2", "note": ""},
}


def pct_of_travel(name, mv):
    """Where this flap sits between its OWN measured end stops."""
    f = FLAPS[name]
    return (mv - f["lo"]) / (f["hi"] - f["lo"]) * 100.0

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

# ── Gentle mode, for a flap on a temporary or suspect linkage ────
# The normal sweep drives until three pulses deliver no travel at all. That
# means the motor stalls against the stop for up to ~600 ms, which is fine
# when the pot is inside the actuator and the actuator is what it is pushing
# against — but NOT fine when a temporary linkage is in the load path.
#
# Gentle mode never reaches a stop. It watches travel-per-pulse and stops as
# soon as a pulse delivers markedly less than the flap has been managing:
# that is the flap loading up against something, and it happens BEFORE the
# force gets anywhere near a stall. Shorter pulses too, so there is less
# energy in each one and the onset is caught finer.
GENTLE_MS        = 100     # motor on-time per pulse in gentle mode
GENTLE_FRAC      = 0.35    # a pulse under this fraction of typical travel = binding
GENTLE_MIN_FREE  = 4       # pulses of free motion needed before judging
GENTLE_MARGIN_MV = 120     # back off this far from where binding began

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
        pct = pct_of_travel(name, mv)
        bar = "#" * int(round(max(0, min(100, pct)) / 5)).__int__()
        print(f"  {name:9} A{f['ch']}  {mv:7.1f} mV  {pct:6.1f}% of travel  "
              f"|{bar:<20}|  {verdict}")
        if f["note"]:
            print(f"            {f['note']}")
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


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0.0


def cmd_sweep(args, chans):
    f = FLAPS[args.flap]
    mv = read_mv(chans, f["ch"])
    if assess(mv) != "plausible":
        print(f"  refusing: {args.flap} feedback reads {mv:.0f} mV — {assess(mv)}")
        return 1

    ms = GENTLE_MS if args.gentle else args.ms
    if args.gentle:
        print(f"── GENTLY sweeping {args.flap} ── {ms} ms pulses, stopping at the "
              f"first sign of binding rather than at a stop")
        print(f"   (a pulse under {GENTLE_FRAC:.0%} of typical travel ends that "
              f"direction; nothing is driven into a hard stop)")
    else:
        print(f"── sweeping {args.flap} ── pulses of {ms} ms, "
              f"stopping after {MAX_STALL_PULSES} with no travel")
    # In gentle mode ONE dead pulse ends the direction. The binding detector
    # needs GENTLE_MIN_FREE samples before it can judge, so a flap that starts
    # near a stop would reach that stop before the detector ever engaged — and
    # then sit on it for three pulses under the normal rule. One is the safe
    # backstop whether or not the median got established.
    max_stalls = 1 if args.gentle else MAX_STALL_PULSES
    ends = {}
    bound = {}
    for direction in ("in1", "in2"):
        stalls = 0
        pulses = 0
        travels = []
        last = read_mv(chans, f["ch"])
        bound[direction] = False
        print(f"\n  {direction}: from {last:.0f} mV")
        while stalls < max_stalls and pulses < MAX_PULSES:
            b, a, d = pulse(args.flap, direction, ms, chans)
            pulses += 1
            if assess(a) != "plausible":
                print(f"    {a:7.1f} mV  !! left the sane band — stopping")
                break

            if args.gentle and len(travels) >= GENTLE_MIN_FREE:
                typical = _median(travels)
                if typical > 0 and abs(d) < typical * GENTLE_FRAC:
                    print(f"    {a:7.1f} mV  ({d:+5.0f})  BINDING — travel fell to "
                          f"{abs(d)/typical:.0%} of the {typical:.0f} mV it had been "
                          f"managing. Stopping here, short of any stop.")
                    bound[direction] = True
                    last = a
                    break

            if abs(d) < NO_PROGRESS_MV:
                stalls += 1
                print(f"    {a:7.1f} mV  ({d:+5.0f})  no travel [{stalls}/{max_stalls}]")
            else:
                stalls = 0
                travels.append(abs(d))
                print(f"    {a:7.1f} mV  ({d:+5.0f})")
            last = a
        ends[direction] = last
        why = "binding began" if bound[direction] else "end stop"
        print(f"    {why} for {direction}: {last:.0f} mV after {pulses} pulses")

    lo_dir = min(ends, key=lambda k: ends[k])
    hi_dir = max(ends, key=lambda k: ends[k])
    lo, hi = ends[lo_dir], ends[hi_dir]
    margin = GENTLE_MARGIN_MV if args.gentle else EDGE_MARGIN_MV
    print(f"\n── {args.flap} calibration ──")
    print(f"  {lo_dir} drives DOWN in mV, reached {lo:.0f} mV"
          f"{'  (binding)' if bound.get(lo_dir) else ''}")
    print(f"  {hi_dir} drives UP   in mV, reached {hi:.0f} mV"
          f"{'  (binding)' if bound.get(hi_dir) else ''}")
    print(f"  travel found: {hi - lo:.0f} mV")
    known = FLAPS[args.flap]
    print(f"  actuator's own range (free): {known['lo']:.0f} - {known['hi']:.0f} mV"
          f"  = {known['hi'] - known['lo']:.0f} mV")
    lost = (known["hi"] - known["lo"]) - (hi - lo)
    if lost > 150:
        print(f"  ** the linkage restricts travel by {lost:.0f} mV "
              f"({lost / (known['hi'] - known['lo']):.0%}) — the DOOR stops before "
              f"the actuator does. Calibrating to the actuator would drive the")
        print(f"     linkage into its stops on every full-travel command.")
    if hi - lo < 500:
        print("  !! that is a very small span — feedback may not be tracking the flap")
    print(f"  suggested limits, {margin} mV inside each end:")
    print(f"    0% = {lo + margin:.0f} mV     100% = {hi - margin:.0f} mV")
    # Deliberately does NOT print what the backend currently uses. The old
    # version claimed one global ADC_MV_MIN/MAX pair for all three flaps; that
    # had not been true since per-flap FLAP_CAL went in, and a tool that states
    # a stale calibration as fact is worse than one that says nothing.
    print(f"  put these in FLAP_CAL[{args.flap}] in hvac_backend.py "
          f"(see docs/FLAP_CALIBRATION.md)")
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
    s.add_argument("--gentle", action="store_true",
                   help="stop at the onset of binding, never at a stop — use "
                        "this for a flap on a temporary or suspect linkage")
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
