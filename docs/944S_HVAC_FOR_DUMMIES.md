# 944S HVAC FOR DUMMIES
*The plain-English guide to your climate control system*

---

## 1. WHAT IS THIS THING?

Your HVAC system is **two programs running on the Raspberry Pi**:

**The BACKEND** (`hvac_backend.py`) — the brain. A Python program that:
- Reads your temperature sensors and flap position pots
- Fires the relays, H-bridges, and seat heater MOSFETs
- Runs the PID control loops 10 times per second
- Remembers your settings when power is lost
- Serves the touchscreen page

**The DASHBOARD** (`HVACDashboard.jsx`) — the face. The touchscreen page you see.
It doesn't control anything directly — every button press is sent to the backend,
and the backend does the actual work. That's why the HVAC keeps running even if
the screen crashes.

They talk over a **WebSocket** (a live two-way connection). The backend
broadcasts the full system state 10× per second to every connected screen —
the car's touchscreen, your Mac browser, your phone — and they all stay in sync.

```
  [Touchscreen] ←──┐
  [Mac browser] ←──┼── WebSocket ──→ [BACKEND on Pi] ──→ relays, motors,
  [Phone]       ←──┘                       │              sensors, seat heat
                                           └──→ hvac_state.json (saved settings)
```

---

## 2. WHERE EVERYTHING LIVES ON THE PI

```
/home/mark/hvac/
├── hvac_backend.py          ← THE BRAIN (Python)
├── hvac_state.json          ← Your saved settings (auto-created)
├── kiosk.sh                 ← Kiosk screen on/off script
└── dashboard/
    ├── src/
    │   ├── HVACDashboard.jsx   ← THE FACE (edit this for UI changes)
    │   ├── App.js              ← Tiny wrapper (never touch)
    │   ├── index.js            ← Startup glue (never touch)
    │   └── index.css           ← Fullscreen CSS (never touch)
    └── build/                  ← Compiled dashboard (auto-generated)
```

**Golden rule:** The dashboard the screen shows is the **build/** folder,
NOT the src/ folder. Editing src/ does nothing until you run `npm run build`.

---

## 3. DOES IT REMEMBER SETTINGS AFTER POWER LOSS?

**YES** (as of this version). Every time you touch a control, the backend
writes your settings to `/home/mark/hvac/hvac_state.json`:

- Set temperature
- Fan speed
- A/C on/off, Heat on/off
- Fresh/Recirc
- Vent mode (face/bi-level/feet/defrost)
- Both seat heater levels

When power comes back, the backend reads that file and picks up right where
you left off. Sensor readings and flap positions are NOT saved (they're live
values, re-read instantly).

To reset to factory defaults: delete the file and restart:
```bash
rm ~/hvac/hvac_state.json
```

---

## 4. HOW TO START AND STOP IT

### Start it (manual, for testing):
```bash
cd ~/hvac
python3 hvac_backend.py
```
Leave that terminal open. You'll see live log lines as things happen.

### Stop it:
Press **Ctrl+C** in that terminal.

### Start it in the background (terminal can be closed):
```bash
cd ~/hvac && python3 hvac_backend.py &
```

### Kill a background copy:
```bash
pkill -f hvac_backend
```

### View the dashboard:
- On the Pi: Chromium → `http://localhost:8000`
- From your Mac: any browser → `http://192.168.1.142:8000`
- Kiosk fullscreen on the car display: `~/hvac/kiosk.sh on` (off to exit)

---

## 5. HOW TO DEPLOY AN UPDATE

### A) Dashboard change (the screen — new buttons, colors, layout)

1. **Download** the new file from Claude on your Mac (it lands in
   `/Users/markpelosi/Downloads/`, maybe named `HVACDashboard_2.jsx` etc.)

2. **Push it to the Pi** — from a MAC terminal (prompt must NOT say 944HVACPi):
```bash
scp /Users/markpelosi/Downloads/HVACDashboard_2.jsx mark@192.168.1.142:/home/mark/hvac/dashboard/src/HVACDashboard.jsx
```
   *(The command renames it to exactly `HVACDashboard.jsx` — the name matters.)*

3. **Rebuild + restart** — SSH to the Pi:
```bash
ssh mark@192.168.1.142
cd ~/hvac/dashboard && npm run build        # takes 1-2 min
pkill -f hvac_backend                        # stop old copy if running
cd ~/hvac && python3 hvac_backend.py
```

4. **Hard-refresh** the browser: **Cmd+Shift+R** (this skips the cache —
   a normal refresh often shows the OLD screen).

### B) Backend change (the brain — new IO, logic, tuning)

1. Download from Claude, then from the Mac:
```bash
scp /Users/markpelosi/Downloads/hvac_backend.py mark@192.168.1.142:/home/mark/hvac/hvac_backend.py
```

2. Restart it (NO rebuild needed — Python isn't compiled):
```bash
ssh mark@192.168.1.142
pkill -f hvac_backend
cd ~/hvac && python3 hvac_backend.py
```

### Cheat table

| What changed | scp to | npm run build? | restart backend? |
|---|---|---|---|
| Dashboard (.jsx) | `~/hvac/dashboard/src/HVACDashboard.jsx` | **YES** | yes |
| Backend (.py) | `~/hvac/hvac_backend.py` | no | **YES** |

---

## 6. READING THE STARTUP LOG (is it healthy?)

When the backend starts, look for these lines:

| Line | Meaning |
|---|---|
| `GPIO initialized (incl. seat heater PWM @ 2 Hz)` | All output pins ready |
| `ADS1115 initialized at 0x48` | Flap feedback ADC found |
| `Found DS18B20: 000000bd3d51` | Mixing chamber temp sensor found |
| `Found DS18B20: 000000be5d11` | Outside temp sensor found |
| `Restored saved state: setpoint=72 ...` | Your settings loaded from disk |
| `HARDWARE mode` | Talking to real hardware (good!) |
| `SIMULATION mode` | Libraries missing — fake data only |
| `Uvicorn running on http://0.0.0.0:8000` | Web server is up |
| `Dashboard connected (1 clients)` | A screen just connected |

The deprecation warnings about `on_event` are harmless noise — ignore them.

---

## 7. QUICK DIAGNOSTICS

```bash
# What does the backend think is happening right now? (JSON dump)
curl -s http://localhost:8000/api/state | python3 -m json.tool

# Send a test command without touching the screen
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" -d '{"setpoint_f": 75}'

# Is the ADS1115 on the I²C bus? (should show 48)
i2cdetect -y 1

# What temp sensors does the Pi see?
ls /sys/bus/w1/devices/

# Raw temperature read (divide by 1000 = °C)
cat /sys/bus/w1/devices/28-000000bd3d51/temperature

# Is the backend running?
pgrep -af hvac_backend

# Is something else hogging port 8000?
sudo lsof -i :8000
```

---

## 8. WHEN THINGS GO WRONG

| Symptom | Likely cause | Fix |
|---|---|---|
| Screen shows old design after update | Browser cache | **Cmd+Shift+R** hard refresh |
| Screen shows old design even after hard refresh | Forgot to rebuild | `cd ~/hvac/dashboard && npm run build`, restart backend |
| `{"detail":"Not Found"}` in browser | Dashboard not built or mount path wrong | Rebuild; check `app.mount` line has `/home/mark/hvac/dashboard/build` |
| Temps read 0 | Sensor ID mismatch or wiring | `ls /sys/bus/w1/devices/` and compare IDs to backend constants (no `28-` prefix in the code!) |
| `A PWM object already exists` on start | Old backend copy still running | `pkill -f hvac_backend`, then start again |
| `address already in use` port 8000 | Same as above | `pkill -f hvac_backend` |
| LINK lamp dark on dashboard | Backend not running or crashed | Check terminal / restart backend |
| Flap % values frozen | ADS1115 wiring / I²C | `i2cdetect -y 1` should show 48 |
| Everything says SIMULATION | Python libs missing | Reinstall: `pip install RPi.GPIO w1thermsensor adafruit-circuitpython-ads1x15 --break-system-packages` |
| scp says "No such file or directory" | You ran it on the Pi | Type `exit` first — scp runs from the MAC |

---

## 9. THE GPIO MAP (what wire does what)

| BCM pin | Job | Type |
|---|---|---|
| 4  | DS18B20 temp sensors (both) | 1-Wire bus |
| 5  | Blower HI relay | active-LOW relay |
| 6  | Blower LOW relay | active-LOW relay |
| 12 | Footwell flap H-bridge IN1 | active-HIGH |
| 13 | **Driver seat heat PWM** | 2 Hz PWM → MOSFET |
| 16 | Defrost flap H-bridge IN1 | active-HIGH |
| 18 | A/C clutch to MS3 (RLY1) | active-LOW relay |
| 19 | Heat valve solenoid (RLY2) | active-LOW relay |
| 20 | Defrost flap H-bridge IN2 | active-HIGH |
| 21 | Footwell flap H-bridge IN2 | active-HIGH |
| 23 | Mixing flap H-bridge IN1 (COLD) | active-HIGH |
| 24 | Mixing flap H-bridge IN2 (HOT) | active-HIGH |
| 25 | **Passenger seat heat PWM** | 2 Hz PWM → MOSFET |
| 26 | Outside air solenoid (RLY3) | active-LOW relay |
| SDA/SCL | ADS1115 flap feedback @ 0x48 | I²C |

ADS1115 channels: CH0 = mixing flap, CH1 = defrost flap, CH2 = footwell flap,
CH3 = spare. Scaling: 225 mV = 0%, 4090 mV = 100%.

---

## 10. MAKING IT START AUTOMATICALLY AT BOOT (when ready for the car)

Right now you start it by hand — good for bench testing. When it goes in the
car, enable the systemd service so it survives every ignition cycle:

```bash
sudo systemctl enable hvac     # start at every boot
sudo systemctl start hvac      # start right now
journalctl -u hvac -f          # watch live logs
```

And turn the touchscreen kiosk back on:
```bash
~/hvac/kiosk.sh on
```

From then on: key on → Pi boots → backend starts → settings restored from
hvac_state.json → kiosk opens the dashboard. No keyboard needed, ever.
