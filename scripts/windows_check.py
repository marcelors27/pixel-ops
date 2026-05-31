from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pixel_ops.data_sources.pc_stats import PCStatsSource

VENDOR_ID = 0x1A86
PRODUCT_ID = 0x5722


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("platform", platform.system() == "Windows", platform.platform()))
    for module in ("PIL", "yaml", "requests", "numpy", "pygame", "usb", "psutil", "websocket"):
        checks.append((f"python:{module}", importlib.util.find_spec(module) is not None, "importable"))
    for command in ("powershell", "tasklist", "wmic", "nvidia-smi"):
        checks.append((f"command:{command}", shutil.which(command) is not None, "optional" if command in ("wmic", "nvidia-smi") else "recommended"))

    device_id = f"{VENDOR_ID:04x}:{PRODUCT_ID:04x}"
    checks.append(("turzx-driver", importlib.util.find_spec("usb") is not None, f"{device_id}; requires WinUSB/libusb driver"))

    snapshot = PCStatsSource(fields=["cpu", "ram", "top_ram_app", "temperature", "gpu", "disk", "uptime", "battery", "load"]).current()
    metric_summary = ", ".join(f"{metric.key}={metric.value}" for metric in (snapshot.metrics if snapshot else ()))
    checks.append(("pc-stats", snapshot is not None, metric_summary or "no snapshot"))

    failed_required = False
    for name, ok, detail in checks:
        required = name.startswith("python:") or name == "platform"
        status = "OK" if ok else "WARN" if not required else "FAIL"
        print(f"{status:4} {name:18} {detail}")
        failed_required = failed_required or (required and not ok)

    print()
    print("Preview test: py pixel_ops\\main.py --plugin pokemon --output preview --offline")
    print("Window test:  py pixel_ops\\main.py --plugin pokemon --output window --forever --offline")
    print("USB test:     py pixel_ops\\main.py --plugin pokemon --output turzx --forever --offline")
    print("USB note: install WinUSB/libusb for the display with Zadig if PyUSB cannot claim it.")
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
