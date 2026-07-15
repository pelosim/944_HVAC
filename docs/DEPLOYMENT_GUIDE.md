# 944S HVAC — Deployment Guide

## What You're Installing

This system replaces your entire Node-RED stack with two components:

| Component | What it does | Technology |
|-----------|-------------|------------|
| **Backend** (`hvac_backend.py`) | Reads sensors, drives outputs, runs PID loops | Python 3 + FastAPI |
| **Frontend** (`944_hvac_dashboard.jsx`) | Touch UI on the 1920×720 display | React (built to static HTML) |

The backend runs as a systemd service (auto-starts at boot, auto-restarts on crash).
The frontend is served by the backend and displayed in Chromium kiosk mode.

---

## Files You Downloaded from Claude

| File | Purpose | Goes where on Pi |
|------|---------|------------------|
| `hvac_backend.py` | Python backend with all IO + PID control | `/home/pi/hvac/` |
| `944_hvac_dashboard.jsx` | React dashboard component | `/home/pi/hvac/` (setup copies it into React app) |
| `App.js` | React wrapper (imports the dashboard) | `/home/pi/hvac/dashboard/src/` |
| `index.css` | Fullscreen dark-mode CSS | `/home/pi/hvac/dashboard/src/` |
| `setup.sh` | Automated install script | Run from anywhere |
| `944S_HVAC_SETUP.md` | Architecture reference | Keep for reference |

---

## Step-by-Step Deployment

### 1. Get files onto the Pi

**Option A — From your Mac via SCP** (easiest if Pi is on your network):
```bash
# Find your Pi's IP address (on the Pi, run: hostname -I)
# Then from your Mac Terminal:

scp hvac_backend.py pi@<PI_IP>:/home/pi/
scp 944_hvac_dashboard.jsx pi@<PI_IP>:/home/pi/
scp App.js pi@<PI_IP>:/home/pi/
scp index.css pi@<PI_IP>:/home/pi/
scp setup.sh pi@<PI_IP>:/home/pi/
```

**Option B — USB drive:**
1. Copy all files to a USB stick
2. Plug into the Pi
3. Mount and copy:
```bash
sudo mount /dev/sda1 /mnt
cp /mnt/hvac_backend.py /home/pi/
cp /mnt/944_hvac_dashboard.jsx /home/pi/
cp /mnt/App.js /home/pi/
cp /mnt/index.css /home/pi/
cp /mnt/setup.sh /home/pi/
sudo umount /mnt
```

**Option C — Direct download** (if Pi has internet):
Open this Claude conversation on the Pi's browser and download each file directly.

### 2. Run the setup script

SSH into the Pi or open a terminal on it:

```bash
cd /home/pi
chmod +x setup.sh
./setup.sh
```

This will take 10–20 minutes (mostly npm installing React dependencies and building). 
It handles everything: system packages, Python libraries, Node.js, React build, 
systemd service, Chromium kiosk, and display config.

### 3. Move your files into position

After setup.sh creates the project structure:

```bash
# Move backend into project directory
mv /home/pi/hvac_backend.py /home/pi/hvac/

# The dashboard component — setup.sh should have handled this,
# but if it didn't find the file:
cp /home/pi/944_hvac_dashboard.jsx /home/pi/hvac/dashboard/src/HVACDashboard.jsx

# Copy the React wrapper files
cp /home/pi/App.js /home/pi/hvac/dashboard/src/App.js
cp /home/pi/index.css /home/pi/hvac/dashboard/src/index.css

# Rebuild the React app after copying files
cd /home/pi/hvac/dashboard
npm run build
```

### 4. Test manually before enabling auto-start

```bash
cd /home/pi/hvac
python3 hvac_backend.py
```

You should see:
```
INFO:     HVAC controller started — SIMULATION mode
INFO:     Uvicorn running on http://0.0.0.0:8000
```

(It says SIMULATION if your sensors/relays aren't wired yet — that's fine.)

Open Chromium on the Pi and go to `http://localhost:8000` — you should see the dashboard.

Press `Ctrl+C` to stop the manual test.

### 5. Start the service

```bash
sudo systemctl start hvac
sudo systemctl status hvac
```

Check for errors:
```bash
journalctl -u hvac -f
```

### 6. Reboot for full auto-start test

```bash
sudo reboot
```

After reboot, the Pi should:
1. Start the HVAC backend automatically (systemd)
2. Launch Chromium in kiosk mode pointing at localhost:8000
3. Display the dashboard fullscreen on the 1920×720 display
4. Hide the mouse cursor after 0.5 seconds of inactivity
5. Never blank the screen

---

## System Dependencies Summary

Here's everything the setup script installs, in case you need to install manually:

### System Packages (apt)
```
python3-pip          Python package manager
python3-dev          Python headers (for native extensions)
python3-venv         Virtual environments (optional)
python3-smbus        I²C Python bindings
i2c-tools            i2cdetect diagnostic tool
chromium-browser     Kiosk display
unclutter            Hides mouse cursor
xdotool              X11 window management
nodejs (v20 LTS)     React build toolchain
npm                  Node package manager
```

### Python Packages (pip)
```
fastapi              Web framework + WebSocket server
uvicorn[standard]    ASGI server (runs FastAPI)
websockets           WebSocket protocol support
RPi.GPIO             Direct GPIO pin control
gpiozero             Higher-level GPIO (optional, useful for debugging)
w1thermsensor        DS18B20 temperature sensor driver
adafruit-circuitpython-ads1x15   ADS1115 16-bit ADC driver
```

### Node/React Packages (npm, inside dashboard/)
```
react                UI library
react-dom            DOM renderer
react-scripts        Build toolchain (webpack, babel, etc.)
```
(These are installed automatically by `create-react-app`)

---

## Useful Commands

```bash
# Service management
sudo systemctl start hvac        # Start
sudo systemctl stop hvac         # Stop
sudo systemctl restart hvac      # Restart
sudo systemctl status hvac       # Status
journalctl -u hvac -f            # Live logs
journalctl -u hvac --since today # Today's logs

# Quick hardware checks
i2cdetect -y 1                   # Scan I²C bus (should show 48)
ls /sys/bus/w1/devices/28-*      # List DS18B20 sensors
cat /sys/bus/w1/devices/28-000000bd3d51/temperature  # Raw temp reading

# Manual motor test (careful — this drives real hardware!)
python3 -c "
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(24, GPIO.OUT)
GPIO.output(24, GPIO.HIGH)  # Drive mixing flap HOT direction
import time; time.sleep(0.5)
GPIO.output(24, GPIO.LOW)   # Stop
GPIO.cleanup()
"

# Rebuild dashboard after code changes
cd /home/pi/hvac/dashboard
npm run build
sudo systemctl restart hvac

# Check what's using port 8000
sudo lsof -i :8000

# Kill Chromium if it's stuck
pkill chromium
```

---

## Troubleshooting

**Dashboard doesn't load after reboot:**
- Check if backend is running: `sudo systemctl status hvac`
- Check logs: `journalctl -u hvac --since today`
- Try manually: `cd /home/pi/hvac && python3 hvac_backend.py`

**"SIMULATION mode" when hardware is connected:**
- Ensure I²C is enabled: `sudo raspi-config` → Interface Options → I²C
- Ensure 1-Wire is enabled: `sudo raspi-config` → Interface Options → 1-Wire
- Reboot after enabling interfaces
- Check I²C: `i2cdetect -y 1`
- Check 1-Wire: `ls /sys/bus/w1/devices/`

**Display resolution wrong:**
- Check config: `cat /boot/firmware/config.txt | grep hdmi`
- Try `tvservice -s` to see current mode
- Some 1920×720 panels need `hdmi_timings` instead of `hdmi_cvt` — check your panel's spec sheet

**Touch not working:**
- Most USB touch panels work out of the box on Pi OS Bookworm
- Check `dmesg | grep -i touch` for detection
- If using a custom touch controller, you may need `xinput` calibration

**Node-RED conflict:**
- If Node-RED is still running, it may fight for GPIO access
- Disable it: `sudo systemctl disable nodered && sudo systemctl stop nodered`
