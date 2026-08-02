#!/usr/bin/env python3
"""Check both ADS1115s — flap feedback (0x48) and accelerometer (0x49).

    sudo systemctl stop hvac-backend      # release 0x48 first
    python3 deploy/check-adc.py
    sudo systemctl start hvac-backend

Why stopping the backend matters: it reads 0x48 at 10 Hz using single-shot
conversions. Two processes doing that interleave — one starts a conversion,
the other reads it half-finished — so numbers taken while it runs are not
trustworthy. The script refuses to guess and says so instead.

Reads raw millivolts and interprets them, because "3.2%" tells you nothing
about whether a channel is connected. A floating ADC input is not zero: it
drifts, wanders with a finger nearby, and reads noise. Distinguishing
"floating" from "real signal" is most of the job here.
"""
import sys
import time

FLAP_ADDR  = 0x48
ACCEL_ADDR = 0x49

# From the harness notes: the pot dividers are excited at ~5 V.
POT_0PCT_MV = 225
POT_100PCT_MV = 4090

FLAP_CH = {0: "blend / temp mix", 1: "defrost", 2: "footwell", 3: "spare"}
# ADXL335 is ratiometric: ~half supply at zero g, ~330 mV/g at 3.3 V.
ACCEL_CH = {0: "X axis", 1: "Y axis", 2: "Z axis", 3: "spare"}


def read_all(addr):
    """Return {channel: millivolts} for one ADS1115, or None if absent."""
    import board, busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    i2c = busio.I2C(board.SCL, board.SDA)
    try:
        ads = ADS.ADS1115(i2c, address=addr)
        return {ch: AnalogIn(ads, ch).voltage * 1000.0 for ch in range(4)}
    except Exception:
        return None


def sample(addr, n=12, delay=0.08):
    """Sample repeatedly so we can talk about stability, not one lucky read."""
    runs = []
    for _ in range(n):
        r = read_all(addr)
        if r is None:
            return None
        runs.append(r)
        time.sleep(delay)
    return {ch: [r[ch] for r in runs] for ch in range(4)}


def verdict_flap(mv_list):
    lo, hi = min(mv_list), max(mv_list)
    spread, mean = hi - lo, sum(mv_list) / len(mv_list)
    pct = (mean - POT_0PCT_MV) / (POT_100PCT_MV - POT_0PCT_MV) * 100
    if spread > 150:
        return f"UNSTABLE (±{spread:.0f} mV) — floating input, or two chips on one address"
    if mean < POT_0PCT_MV * 0.6:
        return "near 0 V — disconnected, or wiper grounded"
    if mean > POT_100PCT_MV * 1.05:
        return "above the pot's top — check the 5 V excitation"
    return f"steady, reads {pct:5.1f}% of travel"


def verdict_accel(mv_list, axis, floating_ref=None):
    """Interpret one ADXL335 axis.

    floating_ref is the mean of A3, which is wired to nothing. It is the
    control: a disconnected input does not read zero, it settles at whatever
    leakage the pin sees — and every floating pin on the same chip settles at
    roughly the SAME place. So an axis sitting within a few mV of A3 is
    almost certainly not connected, however steady it looks. Without that
    check this function cheerfully reported a floating pin as "-3.22 g".
    """
    lo, hi = min(mv_list), max(mv_list)
    spread, mean = hi - lo, sum(mv_list) / len(mv_list)
    if axis == "spare":
        return f"unused — floating, ignore ({spread:.0f} mV of drift)"
    # Zero g sits near half supply; Z also carries 1 g when level.
    expect = 1980 if axis == "Z axis" else 1650
    g = (mean - expect) / 330.0
    if floating_ref is not None and abs(mean - floating_ref) < 25:
        return (f"NOT CONNECTED — sits at {mean:.0f} mV, the same place as the "
                f"unused A3 pin ({floating_ref:.0f} mV)")
    if abs(g) > 2.0:
        return (f"implausible ({g:+.1f} g sitting still) — not connected, or "
                f"wired to the wrong ADXL335 pin. Expected near {expect} mV.")
    if spread > 120:
        return f"UNSTABLE (±{spread:.0f} mV) — check this axis's wire"
    if mean < 200:
        return "near 0 V — ADXL335 not powered, or output not connected"
    return f"steady — {g:+.2f} g from the {expect} mV zero point"


def main():
    print("── I2C bus ──")
    try:
        import smbus2 as smb
    except ImportError:
        try:
            import smbus as smb
        except ImportError:
            print("  no smbus module; skipping the scan")
            smb = None
    present = []
    if smb:
        bus = smb.SMBus(1)
        for a in range(0x03, 0x78):
            try:
                bus.read_byte(a)
                present.append(a)
            except Exception:
                pass
        names = {0x48: "ADS1115 #1 — flap feedback",
                 0x49: "ADS1115 #2 — accelerometer",
                 0x4a: "ADS1115, ADDR strapped to SDA",
                 0x4b: "ADS1115, ADDR strapped to SCL",
                 0x57: "AT24C32 EEPROM — normal, it rides on the DS3231 module",
                 0x68: "DS3231 RTC"}
        for a in present:
            print(f"  {hex(a)}  {names.get(a, 'unrecognised device')}")
        if not present:
            print("  nothing responded — check SDA/SCL and power")

    if ACCEL_ADDR not in present and FLAP_ADDR in present:
        others = [a for a in present if a in (0x4a, 0x4b)]
        print()
        print("  !! 0x49 is missing.")
        if others:
            print("     But something answered at", ", ".join(hex(a) for a in others))
            print("     — that is an ADS1115 with ADDR strapped to SDA or SCL")
            print("     instead of VDD. Move the strap to VDD for 0x49.")
        else:
            print("     Nothing answered at 0x49, 0x4A or 0x4B either, so the")
            print("     second board is not talking on this bus AT ALL. That is")
            print("     a power or SDA/SCL problem, not an address problem —")
            print("     a chip with the wrong ADDR strap still answers, just at")
            print("     the wrong address, and none of them are in use here.")
            print()
            print("     Check, in this order: VDD and GND at the board, then SDA")
            print("     and SCL continuity back to the Pi, then the ADDR strap.")

    # A3 is the unused channel on the flap board. It is the control: if two
    # chips were sharing 0x48, every read would be the bitwise AND of both and
    # ALL FOUR channels would be corrupted. A3 sitting still while A0-A2 wander
    # is the signature of floating INPUT leads, not of bus contention.
    for addr, chmap, verdict, label in (
        (FLAP_ADDR, FLAP_CH, verdict_flap, "FLAP FEEDBACK"),
        (ACCEL_ADDR, ACCEL_CH, verdict_accel, "ACCELEROMETER"),
    ):
        print(f"\n── {label} @ {hex(addr)} ──")
        data = sample(addr)
        if data is None:
            print("  not responding")
            continue
        ref = sum(data[3]) / len(data[3])   # A3 is unused on both boards
        for ch in range(4):
            mv = data[ch]
            mean = sum(mv) / len(mv)
            v = (verdict(mv, chmap[ch], ref) if verdict is verdict_accel
                 else verdict(mv))
            print(f"  A{ch} {chmap[ch]:<18} {mean:7.1f} mV   {v}")


if __name__ == "__main__":
    sys.exit(main())
