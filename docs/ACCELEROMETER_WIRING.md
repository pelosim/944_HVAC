# Accelerometer (G-meter) Wiring — ADXL335 + second ADS1115

Wiring and calibration for the G-meter shown on the round auxiliary screen
(`dashboard/public/gmeter.html`, selected from the dashboard's **AUX** button).

**Status:** not yet wired. The G-meter page runs on simulated lap data until
the backend broadcasts `g_lateral` / `g_longitudinal` (see *Backend hookup*).

---

## 1. Parts (both already on hand)

| Part | Notes |
|---|---|
| GY-61 / ADXL335 breakout | 3-axis **analog** accelerometer, ±3 g |
| ADS1115 breakout (2nd one) | 4-channel 16-bit I²C ADC — from the 3-pack |

### Why a second ADC

The ADXL335 outputs three **analog voltages**, and the Pi has no analog
inputs. The existing ADS1115 at `0x48` is nearly full — CH0/1/2 are the blend,
defrost and footwell flap feedbacks, leaving only CH3 — and we need three
channels. So the accelerometer gets its own ADS1115 at a different address.

> Do **not** substitute an MPU-6050. None is in inventory, and the parts above
> already do the job.

---

## 2. Set the second ADS1115 to address 0x49

The ADS1115's `ADDR` pin selects the address. The existing board ties `ADDR`
to GND (`0x48`); strap the new one to **VDD** for **`0x49`**:

| ADDR pin tied to | I²C address | Used by |
|---|---|---|
| GND | `0x48` | existing — flap feedback |
| **VDD** | **`0x49`** | **new — accelerometer** |
| SDA | `0x4A` | free |
| SCL | `0x4B` | free |

Both ADCs share the same SDA/SCL lines — that's normal for I²C. `0x68` is the
DS3231 RTC (see `deploy/setup-rtc.sh`), so there's no conflict.

---

## 3. Wiring

### ADXL335 → ADS1115 #2

| ADXL335 pin | Goes to | Notes |
|---|---|---|
| `VCC` | ADS1115 #2 `VDD` (3.3 V) | see power note below |
| `GND` | `GND` | common ground |
| `X` | ADS1115 #2 `A0` | lateral |
| `Y` | ADS1115 #2 `A1` | longitudinal |
| `Z` | ADS1115 #2 `A2` | vertical |
| `ST` | *(leave unconnected)* | self-test |

### ADS1115 #2 → Pi 40-pin header

| ADS1115 #2 pin | Pi pin | BCM |
|---|---|---|
| `VDD` | pin 1 — **3V3** | — |
| `GND` | pin 6 or 9 — GND | — |
| `SCL` | pin 5 | GPIO3 |
| `SDA` | pin 3 | GPIO2 |
| `ADDR` | → `VDD` (see §2) | — |

Tap the same SDA/SCL/3V3/GND the existing ADS1115 uses — the Freenove breakout
HAT makes this tidy.

> **VCC vs VDD — same thing.** Both are just "positive supply in". The names are
> historical (VCC = bipolar *collector*, VDD = CMOS *drain*); board vendors use
> them interchangeably. The GY-61 silkscreen says `VCC`, the ADS1115 says `VDD`,
> and both tie to the Pi's 3V3 rail.
>
> **Check your board's pin order before wiring.** GY-61 variants differ — some
> run VCC/X/Y/Z/GND, others the reverse. Reversing VCC and GND will destroy the
> sensor. Go by the silkscreen, not by position.

### ⚠ Power the ADXL335 from 3.3 V, not 5 V

The ADXL335's outputs are **ratiometric** — the zero-g point and the volts-per-g
both scale with its supply. Running the sensor and the ADC from the *same*
3.3 V rail means supply drift cancels out instead of showing up as phantom G.
The GY-61 board accepts 3–5 V (it has an onboard regulator), but feeding it
3.3 V keeps everything on one reference.

---

## 4. Mounting orientation

Mount the board **flat and square to the car** — its axes must line up with the
car's, or cornering will bleed into the braking reading and vice versa.

At rest on level ground you should see:

- **Z ≈ +1 g** (gravity, board flat)
- **X ≈ 0 g**, **Y ≈ 0 g**

Then, in the car:

| Axis | Car direction | Feeds |
|---|---|---|
| X | left ↔ right | `g_lateral` (+ = right turn) |
| Y | rear ↔ front | `g_longitudinal` (+ = acceleration) |
| Z | down ↔ up | tilt reference / sanity check |

If a readout comes out backwards, negate that axis in the backend rather than
rewiring. Which physical axis is which depends on how the board ends up
mounted — confirm with §6 before wiring it into the control code.

---

## 5. Verify the hardware

```bash
sudo i2cdetect -y 1
```

Expect **`48`** (flap ADC), **`49`** (new accelerometer ADC), and `68` if the
DS3231 RTC is fitted. If `49` is missing, the `ADDR` strap isn't on VDD.

Read the three axes:

```bash
python3 - <<'PY'
import board, busio, time
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn
ads = ADS1115(busio.I2C(board.SCL, board.SDA), address=0x49)
ch = [AnalogIn(ads, i) for i in range(3)]
for _ in range(10):
    print("X %.3f V   Y %.3f V   Z %.3f V" % tuple(c.voltage for c in ch))
    time.sleep(0.3)
PY
```

Sitting still and level, expect roughly **1.65 V** on X and Y (zero g) and
about **1.98 V** on Z (zero g + 1 g). Tilt the board and watch them swing.

---

## 6. Calibration (do this once, in the final mounting)

Datasheet typicals are ~1.65 V at zero g and ~330 mV/g at 3.3 V, but
part-to-part spread is ±10%, so measure your own. Gravity is a free, exact
1 g reference — use it.

For each axis, point it **straight down**, record the voltage, then point it
**straight up** and record again:

```
zero_v        = (v_down + v_up) / 2
volts_per_g   = (v_down - v_up) / 2        # magnitude; sign follows your axis convention
g             = (v_measured - zero_v) / volts_per_g
```

Doing all three axes gives a proper 6-point tumble calibration. Put the
resulting constants in `hvac_backend.py` next to the existing ADC scaling
(`ADC_MV_MIN` / `ADC_MV_MAX`), and keep the raw values — recalibrate if the
sensor is ever remounted.

---

## 7. Backend hookup

The G-meter page already listens for these two fields on the WebSocket and
switches from simulated data to live the moment they appear:

| Field | Meaning |
|---|---|
| `g_lateral` | + = right-hand cornering |
| `g_longitudinal` | + = acceleration, − = braking |

**Implemented 2026-08-02.** `HardwareManager._init_accel()` opens `0x49` and
`_accel_reader_loop()` samples it at 20 Hz on its own thread; `tick()` reads only
the cache. `HVACState` publishes `g_lateral`, `g_longitudinal`, `g_vertical`,
`accel_ok` and `accel_axes_bad`.

Calibration is still the datasheet typicals (`ACCEL_ZERO_MV` 1650,
`ACCEL_MV_PER_G` 330). Bench readings landed within 6 mV of both, but do the §6
tumble in the final mounting — there is currently a standing ~0.11 g lateral
offset that is either real tilt or part spread, and only calibration tells you
which. `ACCEL_INVERT_X` / `ACCEL_INVERT_Y` set the signs; confirm them in the
car, not on the bench.

> A floating ADC input does not read zero — it settles wherever leakage puts it,
> and every floating pin on the same chip settles in the same place. `A3` is wired
> to nothing and is used as the reference: an axis within 25 mV of it is treated as
> disconnected, `accel_ok` goes false, and the G-meter falls back rather than
> drawing a confident dot in the wrong place. A partly-wired accelerometer is not a
> degraded G-meter, it is a wrong one.

### ⚠ Read the accelerometer off the control loop

The DS18B20s were originally read **inline** in the async control loop, and
each blocking conversion stalled the whole event loop — the "10 Hz" loop was
really running at 0.4 Hz, which caused the long-standing dashboard button lag.
The fix was a background reader thread feeding a cache
(`HardwareManager._temp_reader_loop`).

The flap ADC reads are already inline and fast enough, but **adding three more
I²C conversions per tick doubles that traffic**. Follow the same pattern: read
the accelerometer in its own thread and have the control loop consume the
latest cached value. A G-meter also wants a faster update than 10 Hz, which the
thread gives you for free.

Also note the ADS1115 multiplexes one conversion at a time (default 128 SPS →
roughly 40 samples/s/channel across three channels). That's ample for a G
display, but it will smooth very sharp impacts — it is not a crash recorder.

---

## Related

- `deploy/setup-rtc.sh` — DS3231 RTC wiring (also on this I²C bus)
- `docs/944S_HVAC_CHEATSHEET.md` — existing ADS1115 `0x48` channel map and scaling
- `dashboard/public/gmeter.html` — the display this feeds
