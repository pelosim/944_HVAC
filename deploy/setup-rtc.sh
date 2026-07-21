#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Provision a DS3231 real-time clock on the 944 HVAC Pi.
#
# WIRING (DS3231 module -> Pi 40-pin header; shares the I2C bus with the
# ADS1115, so tap the same four lines):
#   VCC -> 3V3   (pin 1)      << use 3.3V, not 5V
#   GND -> GND   (pin 6 or 9)
#   SDA -> GPIO2 (pin 3)      << same line as ADS1115 SDA
#   SCL -> GPIO3 (pin 5)      << same line as ADS1115 SCL
#   (SQW/32K pins: leave unconnected)
#
# Cheap "ZS-042" modules have a charging circuit for a rechargeable LIR2032.
# If you fit a non-rechargeable CR2032, that's fine for years — just don't
# expect it to "charge"; (optional) remove resistor R5/diode to be safe.
#
# RUN THIS AFTER the module is wired:   bash ~/hvac/deploy/setup-rtc.sh
# Then reboot, then run:                sudo hwclock -w   (seed RTC from NTP)
# Idempotent — safe to re-run.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
CFG=/boot/firmware/config.txt

echo "==> 1. Checking the DS3231 is on the bus (expect 0x68)..."
if sudo i2cdetect -y 1 | grep -qE '(^60:.* 68| 68 | UU)'; then
  echo "    DS3231 detected."
else
  echo "!!  DS3231 NOT found at 0x68. Check 3V3/GND/SDA(GPIO2)/SCL(GPIO3) and re-run."
  sudo i2cdetect -y 1
  exit 1
fi

echo "==> 2. Adding device-tree overlay (idempotent)..."
if ! grep -q '^dtoverlay=i2c-rtc,ds3231' "$CFG"; then
  echo 'dtoverlay=i2c-rtc,ds3231' | sudo tee -a "$CFG" >/dev/null
  echo "    overlay added."
else
  echo "    overlay already present."
fi

echo "==> 3. Disabling fake-hwclock (it would fight the real RTC)..."
sudo systemctl disable --now fake-hwclock 2>/dev/null || true
sudo apt-get -y remove fake-hwclock >/dev/null 2>&1 || true

echo ""
echo "==> Done. Now:"
echo "    1) sudo reboot"
echo "    2) after reboot, while still online (NTP synced):  sudo hwclock -w"
echo "    3) verify:  ls /dev/rtc*   &&   sudo hwclock -r"
echo "    After that the Pi keeps accurate time with no network."
