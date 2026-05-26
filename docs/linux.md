# Linux Setup

Pixel OPs supports Linux first for `preview`, `gif`, and `window` outputs. USB display output also works through PyUSB/libusb when the device is visible and the user has permission to claim it.

## System Packages

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev libusb-1.0-0 libsdl2-2.0-0
```

Optional packages for richer PC stats and hardware discovery:

```bash
sudo apt install usbutils pciutils lm-sensors
sudo sensors-detect
```

NVIDIA GPU name detection uses `nvidia-smi` when available.

## Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the local Linux compatibility check:

```bash
python scripts/linux_check.py
```

## Output Tests

Start with file output:

```bash
python pixel_ops/main.py --plugin pokemon --output preview --offline
```

Then test a desktop window under X11 or Wayland:

```bash
python pixel_ops/main.py --plugin pokemon --output window --forever --offline
```

For headless preview generation, use `preview` or `gif`; `window` requires a graphical session.

## TURZX USB Display

Find the display:

```bash
lsusb
```

The current backend expects:

```text
1a86:5722
```

If the device appears but Pixel OPs cannot claim it, add a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-pixel-ops-turzx.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", ATTR{idProduct}=="5722", MODE="0666", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and reconnect the display, then run:

```bash
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

## PC Stats Notes

The `pc_stats` integration uses `psutil` for CPU, RAM, disk, battery, processes, uptime, and load. On Linux it also reads temperatures from `/sys/class/thermal` and `/sys/class/hwmon` when available.

GPU name detection uses `nvidia-smi` first, then `lspci`. GPU utilization and some temperatures are hardware/vendor-specific and may render as `-` when unavailable.
