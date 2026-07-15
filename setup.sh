#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 944S HVAC Controller — Raspberry Pi 4 Setup Script
# ═══════════════════════════════════════════════════════════════
#
# Run this on a fresh Raspberry Pi OS (Bookworm, 64-bit recommended)
#   chmod +x setup.sh
#   ./setup.sh
#
# What this does:
#   1. Enables I²C and 1-Wire interfaces
#   2. Installs system packages (Node.js 20, Python deps, Chromium)
#   3. Installs Python libraries (FastAPI, GPIO, sensor drivers)
#   4. Builds the React dashboard
#   5. Creates a systemd service for auto-start
#   6. Configures Chromium kiosk mode
#   7. Configures display for 1920×720
#
# Prerequisites:
#   - Raspberry Pi 4 running Raspberry Pi OS Bookworm (64-bit)
#   - Internet connection (for package downloads)
#   - Your 1920×720 display connected via HDMI
#
# ═══════════════════════════════════════════════════════════════

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log() { echo -e "${CYAN}[HVAC]${NC} $1"; }
ok()  { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }

PROJECT_DIR="/home/$USER/hvac"
DASHBOARD_DIR="$PROJECT_DIR/dashboard"

# ─── Check we're on a Pi ──────────────────────────────────────
if [ ! -f /proc/device-tree/model ]; then
    err "This doesn't appear to be a Raspberry Pi. Aborting."
    exit 1
fi
log "Detected: $(cat /proc/device-tree/model)"

# ─── Step 1: Enable hardware interfaces ───────────────────────
log "Step 1/7: Enabling I²C and 1-Wire interfaces..."

# Enable I²C
if ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null; then
    sudo raspi-config nonint do_i2c 0
    ok "I²C enabled"
else
    ok "I²C already enabled"
fi

# Enable 1-Wire
if ! grep -q "^dtoverlay=w1-gpio" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtoverlay=w1-gpio" /boot/config.txt 2>/dev/null; then
    sudo raspi-config nonint do_onewire 0
    ok "1-Wire enabled"
else
    ok "1-Wire already enabled"
fi

# ─── Step 2: System packages ──────────────────────────────────
log "Step 2/7: Installing system packages..."

sudo apt update
sudo apt install -y \
    python3-pip \
    python3-dev \
    python3-venv \
    python3-smbus \
    i2c-tools \
    chromium-browser \
    unclutter \
    xdotool \
    git

# Install Node.js 20 LTS (Pi OS Bookworm ships Node 18, but 20 is better for React)
if ! command -v node &> /dev/null || [[ $(node -v | cut -d. -f1 | tr -d 'v') -lt 18 ]]; then
    log "Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
    ok "Node.js $(node -v) installed"
else
    ok "Node.js $(node -v) already installed"
fi

ok "System packages installed"

# ─── Step 3: Python libraries ─────────────────────────────────
log "Step 3/7: Installing Python libraries..."

# Core web framework
pip install --break-system-packages \
    fastapi \
    "uvicorn[standard]" \
    websockets

# GPIO control
pip install --break-system-packages \
    RPi.GPIO \
    gpiozero

# DS18B20 temperature sensors (1-Wire)
pip install --break-system-packages \
    w1thermsensor

# ADS1115 16-bit ADC (I²C) — Adafruit CircuitPython driver
pip install --break-system-packages \
    adafruit-circuitpython-ads1x15

ok "Python libraries installed"

# ─── Verify I²C and 1-Wire ────────────────────────────────────
log "Verifying hardware interfaces..."

if i2cdetect -y 1 2>/dev/null | grep -q "48"; then
    ok "ADS1115 detected at 0x48 on I²C bus 1"
else
    echo -e "${RED}[WARN]${NC} ADS1115 not detected at 0x48 — check wiring (will work in simulation mode)"
fi

if ls /sys/bus/w1/devices/28-* 2>/dev/null; then
    ok "DS18B20 sensor(s) found on 1-Wire bus"
else
    echo -e "${RED}[WARN]${NC} No DS18B20 sensors found — check wiring (will work in simulation mode)"
fi

# ─── Step 4: Create project structure ─────────────────────────
log "Step 4/7: Setting up project structure..."

mkdir -p "$PROJECT_DIR"
mkdir -p "$DASHBOARD_DIR"

# Copy backend if not already there
if [ ! -f "$PROJECT_DIR/hvac_backend.py" ]; then
    log "NOTE: Copy hvac_backend.py to $PROJECT_DIR/"
fi

ok "Project directory: $PROJECT_DIR"

# ─── Step 5: Build React dashboard ────────────────────────────
log "Step 5/7: Building React dashboard..."

cd "$DASHBOARD_DIR"

# Initialize React app if not already created
if [ ! -f "package.json" ]; then
    npx create-react-app . --template default
    ok "React app scaffolded"
fi

# Copy dashboard component (user should have placed 944_hvac_dashboard.jsx here)
if [ -f "$PROJECT_DIR/944_hvac_dashboard.jsx" ]; then
    cp "$PROJECT_DIR/944_hvac_dashboard.jsx" "$DASHBOARD_DIR/src/HVACDashboard.jsx"
    ok "Dashboard component copied"
fi

# Create the App.js wrapper that imports the dashboard
cat > "$DASHBOARD_DIR/src/App.js" << 'APPEOF'
import HVACDashboard from './HVACDashboard';

function App() {
  return <HVACDashboard />;
}

export default App;
APPEOF

# Create index.css with full-screen dark background
cat > "$DASHBOARD_DIR/src/index.css" << 'CSSEOF'
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html, body, #root {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #06090f;
  -webkit-user-select: none;
  user-select: none;
  cursor: default;
}
/* Hide scrollbars */
::-webkit-scrollbar { display: none; }
/* Prevent text selection on touch */
* { -webkit-tap-highlight-color: transparent; }
CSSEOF

# Build production bundle
log "Building production bundle (this takes a few minutes on Pi)..."
npm run build

ok "React dashboard built → $DASHBOARD_DIR/build/"

# ─── Step 6: Enable static file serving in backend ────────────
log "Step 6/7: Configuring backend to serve dashboard..."

# Uncomment the static files mount line in hvac_backend.py
if [ -f "$PROJECT_DIR/hvac_backend.py" ]; then
    sed -i 's|^# app.mount("/"|app.mount("/"|' "$PROJECT_DIR/hvac_backend.py"
    # Update the path to match our directory structure
    sed -i "s|directory=\"dashboard/build\"|directory=\"$DASHBOARD_DIR/build\"|" "$PROJECT_DIR/hvac_backend.py"
    ok "Backend configured to serve dashboard"
fi

# ─── Step 7: Systemd service + Chromium kiosk ─────────────────
log "Step 7/7: Setting up auto-start..."

# Create systemd service for the HVAC backend
sudo tee /etc/systemd/system/hvac.service > /dev/null << EOF
[Unit]
Description=944S HVAC Controller
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/hvac_backend.py
Restart=always
RestartSec=3
WatchdogSec=30

# Ensure GPIO access
SupplementaryGroups=gpio i2c

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hvac

# Hardening
ProtectSystem=strict
ReadWritePaths=$PROJECT_DIR
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hvac
ok "Systemd service created and enabled"

# Create Chromium kiosk autostart
mkdir -p "/home/$USER/.config/autostart"
cat > "/home/$USER/.config/autostart/hvac-kiosk.desktop" << EOF
[Desktop Entry]
Type=Application
Name=944S HVAC Dashboard
Comment=Launch HVAC dashboard in kiosk mode
Exec=bash -c 'sleep 5 && chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-translate --no-first-run --fast --fast-start --disable-features=TranslateUI --disable-session-crashed-bubble --check-for-update-interval=31536000 --window-size=1920,720 --window-position=0,0 --autoplay-policy=no-user-gesture-required http://localhost:8000'
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

ok "Chromium kiosk autostart created"

# Create a helper script to hide the mouse cursor
cat > "/home/$USER/.config/autostart/hide-cursor.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Hide Cursor
Exec=unclutter -idle 0.5 -root
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

ok "Mouse cursor auto-hide configured"

# ─── Display configuration for 1920×720 ───────────────────────
log "Configuring display for 1920×720..."

# Determine which config file to use (Bookworm uses /boot/firmware/)
if [ -d /boot/firmware ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

# Add custom HDMI mode if not already present
if ! grep -q "hdmi_cvt=1920 720" "$BOOT_CONFIG"; then
    sudo tee -a "$BOOT_CONFIG" > /dev/null << 'HDMIEOF'

# ── 944S HVAC Display (1920×720 ultrawide) ──
hdmi_group=2
hdmi_mode=87
hdmi_cvt=1920 720 60 3 0 0 0
hdmi_drive=2
disable_overscan=1
HDMIEOF
    ok "HDMI configured for 1920×720"
else
    ok "HDMI already configured for 1920×720"
fi

# Disable screen blanking / power save
sudo raspi-config nonint do_blanking 1 2>/dev/null || true
# Also via xset in autostart
cat > "/home/$USER/.config/autostart/disable-screensaver.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Disable Screensaver
Exec=bash -c 'xset s off && xset -dpms && xset s noblank'
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

ok "Screen blanking disabled"

# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  944S HVAC Controller — Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Project directory:  $PROJECT_DIR"
echo "  Dashboard build:    $DASHBOARD_DIR/build/"
echo "  Backend:            $PROJECT_DIR/hvac_backend.py"
echo ""
echo "  Next steps:"
echo "  1. Copy your files into $PROJECT_DIR/:"
echo "     - hvac_backend.py"
echo "     - 944_hvac_dashboard.jsx"
echo ""
echo "  2. Test the backend manually:"
echo "     cd $PROJECT_DIR && python3 hvac_backend.py"
echo "     → Open http://localhost:8000 in a browser"
echo ""
echo "  3. Start the service:"
echo "     sudo systemctl start hvac"
echo "     sudo systemctl status hvac"
echo "     journalctl -u hvac -f    (live logs)"
echo ""
echo "  4. Reboot to test full auto-start:"
echo "     sudo reboot"
echo ""
echo "  5. After reboot, the dashboard should appear"
echo "     automatically on the 1920×720 display."
echo ""
echo -e "  ${RED}NOTE: A reboot is required for I²C, 1-Wire,${NC}"
echo -e "  ${RED}and display changes to take effect.${NC}"
echo ""
