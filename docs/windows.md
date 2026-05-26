# Windows Setup

Pixel OPs supports Windows first for `preview`, `gif`, and `window` outputs. USB display output depends on a WinUSB/libusb-compatible driver for the TURZX/Turing display.

## System Requirements

- Python 3.9+
- Node.js 24 for Config Studio
- PowerShell
- Optional: Zadig for installing a WinUSB/libusb-compatible USB driver

## Python Environment

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the local Windows compatibility check:

```powershell
python scripts\windows_check.py
```

## Output Tests

Start with file output:

```powershell
python pixel_ops\main.py --plugin pokemon --output preview --offline
```

Then test a desktop window:

```powershell
python pixel_ops\main.py --plugin pokemon --output window --forever --offline
```

For a one-shot animated render:

```powershell
python pixel_ops\main.py --plugin pokemon --output gif --seconds 8 --offline
```

## TURZX USB Display

The current backend expects:

```text
1a86:5722
```

If PyUSB cannot find or claim the device, install a WinUSB/libusb-compatible driver for the display:

1. Install Zadig.
2. Connect the TURZX/Turing display.
3. In Zadig, enable `Options > List All Devices`.
4. Select the device with USB ID `1a86:5722`.
5. Install the `WinUSB` driver.
6. Unplug and reconnect the display.

Then run:

```powershell
python pixel_ops\main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

## PC Stats Notes

The `pc_stats` integration uses `psutil` for CPU, RAM, disk, battery, processes, and uptime.

Windows-specific fallbacks:

- top memory app can fall back to `tasklist`;
- GPU name uses PowerShell `Get-CimInstance Win32_VideoController`, with `wmic` as a fallback when available;
- temperature uses WMI thermal zones when the machine exposes them.

Many Windows desktops do not expose CPU/GPU temperature through standard WMI. In that case the metric renders as `-` instead of failing.

## Config Studio

```powershell
cd config-studio
npm install
npm run dev
```

Use the local UI to enable integrations and add/remove `pc_stats`, `weather`, `gauges`, and other layout windows.
