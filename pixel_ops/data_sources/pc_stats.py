from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


DEFAULT_FIELDS = ("cpu", "ram", "top_ram_app", "temperature", "gpu", "disk", "uptime")


@dataclass(frozen=True)
class PCMetric:
    key: str
    label: str
    value: str
    status: str = "ok"


@dataclass(frozen=True)
class PCStatsSnapshot:
    metrics: tuple[PCMetric, ...]
    observed_at: datetime


class PCStatsSource:
    def __init__(
        self,
        enabled: bool = True,
        fields: list[str] | tuple[str, ...] = DEFAULT_FIELDS,
        poll_seconds: int = 5,
        top_process_count: int = 1,
        disk_path: str = "/",
    ):
        self.enabled = enabled
        self.fields = tuple(str(field) for field in fields if str(field).strip()) or DEFAULT_FIELDS
        self.poll_seconds = max(1, int(poll_seconds))
        self.top_process_count = max(1, int(top_process_count))
        self.disk_path = _normalize_disk_path(disk_path or "/")
        self._last_poll_at: datetime | None = None
        self._snapshot: PCStatsSnapshot | None = None

    def current(self, now: datetime | None = None) -> PCStatsSnapshot | None:
        if not self.enabled:
            return None
        base_now = now or datetime.now().astimezone()
        if self._last_poll_at and (base_now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = base_now
        self._snapshot = PCStatsSnapshot(metrics=tuple(self._metric_for(field) for field in self.fields), observed_at=base_now)
        return self._snapshot

    def _metric_for(self, field: str) -> PCMetric:
        handlers = {
            "cpu": self._cpu_metric,
            "ram": self._ram_metric,
            "memory": self._ram_metric,
            "top_ram_app": self._top_ram_app_metric,
            "top_memory_app": self._top_ram_app_metric,
            "temperature": self._temperature_metric,
            "temp": self._temperature_metric,
            "gpu": self._gpu_metric,
            "disk": self._disk_metric,
            "uptime": self._uptime_metric,
            "battery": self._battery_metric,
            "load": self._load_metric,
        }
        handler = handlers.get(field)
        if handler is None:
            return PCMetric(field, field.upper()[:8], "-", "unknown")
        try:
            return handler()
        except (OSError, PermissionError):
            return PCMetric(field, field.upper()[:8], "-", "unknown")

    def _cpu_metric(self) -> PCMetric:
        if psutil is not None:
            value = float(psutil.cpu_percent(interval=None))
            return PCMetric("cpu", "CPU", f"{value:.0f}%", _percent_status(value))
        load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
        if load is None:
            return PCMetric("cpu", "CPU", "-", "unknown")
        cores = max(1, os.cpu_count() or 1)
        pct = min(100.0, load / cores * 100.0)
        return PCMetric("cpu", "CPU", f"{pct:.0f}%", _percent_status(pct))

    def _ram_metric(self) -> PCMetric:
        if psutil is not None:
            memory = psutil.virtual_memory()
            return PCMetric("ram", "RAM", f"{memory.percent:.0f}%", _percent_status(float(memory.percent)))
        return PCMetric("ram", "RAM", "-", "unknown")

    def _top_ram_app_metric(self) -> PCMetric:
        if psutil is not None:
            best = None
            try:
                processes = psutil.process_iter(("name", "memory_info"))
                for proc in processes:
                    try:
                        rss = int(proc.info["memory_info"].rss)
                        name = str(proc.info.get("name") or proc.pid)
                    except (psutil.Error, AttributeError, TypeError, PermissionError):
                        continue
                    if best is None or rss > best[0]:
                        best = (rss, name)
            except (psutil.Error, PermissionError):
                best = None
        if best:
            return PCMetric("top_ram_app", "TOP", f"{_short_name(best[1])} {_bytes_label(best[0])}")
        if platform.system() == "Windows":
            best = _windows_top_ram_process()
            if best:
                return PCMetric("top_ram_app", "TOP", f"{_short_name(best[1])} {_bytes_label(best[0])}")
        line = _run_command(("ps", "-axo", "rss=,comm="))
        if not line:
            return PCMetric("top_ram_app", "TOP", "-", "unknown")
        best = None
        for raw in line.splitlines():
            parts = raw.strip().split(None, 1)
            if len(parts) != 2:
                continue
            try:
                rss = int(parts[0]) * 1024
            except ValueError:
                continue
            name = os.path.basename(parts[1])
            if best is None or rss > best[0]:
                best = (rss, name)
        return PCMetric("top_ram_app", "TOP", f"{_short_name(best[1])} {_bytes_label(best[0])}") if best else PCMetric("top_ram_app", "TOP", "-", "unknown")

    def _temperature_metric(self) -> PCMetric:
        if psutil is not None and hasattr(psutil, "sensors_temperatures"):
            try:
                readings = psutil.sensors_temperatures(fahrenheit=False)
            except (OSError, AttributeError):
                readings = {}
            temps = [float(item.current) for values in readings.values() for item in values if item.current is not None]
            if temps:
                temp = max(temps)
                return PCMetric("temperature", "TEMP", f"{temp:.0f}C", "warn" if temp >= 80 else "ok")
        if platform.system() == "Linux":
            temp = _linux_temperature_c()
            if temp is not None:
                return PCMetric("temperature", "TEMP", f"{temp:.0f}C", "warn" if temp >= 80 else "ok")
        if platform.system() == "Windows":
            temp = _windows_temperature_c()
            if temp is not None:
                return PCMetric("temperature", "TEMP", f"{temp:.0f}C", "warn" if temp >= 80 else "ok")
        return PCMetric("temperature", "TEMP", "-", "unknown")

    def _gpu_metric(self) -> PCMetric:
        if platform.system() == "Darwin" and shutil.which("system_profiler"):
            output = _run_command(("system_profiler", "SPDisplaysDataType"))
            for raw in output.splitlines():
                line = raw.strip()
                if line.startswith("Chipset Model:"):
                    return PCMetric("gpu", "GPU", _short_name(line.split(":", 1)[1].strip(), 14))
        if platform.system() == "Linux":
            if shutil.which("nvidia-smi"):
                output = _run_command(("nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"))
                name = next((line.strip() for line in output.splitlines() if line.strip()), "")
                if name:
                    return PCMetric("gpu", "GPU", _short_name(name, 14))
            if shutil.which("lspci"):
                output = _run_command(("lspci",))
                for raw in output.splitlines():
                    if any(marker in raw for marker in (" VGA ", " 3D ", " Display ")):
                        name = raw.split(":", 2)[-1].strip()
                        return PCMetric("gpu", "GPU", _short_name(name, 14))
        if platform.system() == "Windows":
            name = _windows_gpu_name()
            if name:
                return PCMetric("gpu", "GPU", _short_name(name, 14))
        return PCMetric("gpu", "GPU", "-", "unknown")

    def _disk_metric(self) -> PCMetric:
        if psutil is not None:
            try:
                usage = psutil.disk_usage(self.disk_path)
            except OSError:
                return PCMetric("disk", "DISK", "-", "unknown")
            return PCMetric("disk", "DISK", f"{usage.percent:.0f}%", _percent_status(float(usage.percent)))
        usage = shutil.disk_usage(self.disk_path)
        pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
        return PCMetric("disk", "DISK", f"{pct:.0f}%", _percent_status(pct))

    def _uptime_metric(self) -> PCMetric:
        if psutil is not None:
            seconds = max(0, int(time.time() - psutil.boot_time()))
            return PCMetric("uptime", "UP", _duration_label(seconds))
        return PCMetric("uptime", "UP", "-", "unknown")

    def _battery_metric(self) -> PCMetric:
        if psutil is not None and hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery is not None:
                suffix = "+" if battery.power_plugged else ""
                return PCMetric("battery", "BATT", f"{battery.percent:.0f}%{suffix}", "warn" if battery.percent <= 20 and not battery.power_plugged else "ok")
        return PCMetric("battery", "BATT", "-", "unknown")

    def _load_metric(self) -> PCMetric:
        if not hasattr(os, "getloadavg"):
            return PCMetric("load", "LOAD", "-", "unknown")
        load = os.getloadavg()[0]
        return PCMetric("load", "LOAD", f"{load:.1f}")


def _run_command(cmd: tuple[str, ...]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=1.5)
    except (OSError, subprocess.SubprocessError):
        return ""


def _normalize_disk_path(path: str) -> str:
    if platform.system() == "Windows" and path in ("", "/"):
        return os.environ.get("SystemDrive", "C:") + "\\"
    return path


def _linux_temperature_c(root: Path = Path("/sys")) -> float | None:
    paths = [
        *root.glob("class/thermal/thermal_zone*/temp"),
        *root.glob("class/hwmon/hwmon*/temp*_input"),
    ]
    temps: list[float] = []
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            value = float(raw)
        except (OSError, ValueError):
            continue
        temp = value / 1000.0 if value > 1000 else value
        if 0 < temp < 130:
            temps.append(temp)
    return max(temps) if temps else None


def _windows_temperature_c() -> float | None:
    if not shutil.which("powershell"):
        return None
    output = _run_command(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | Select-Object -First 1 -ExpandProperty CurrentTemperature)",
        )
    )
    for raw in output.splitlines():
        try:
            kelvin_tenths = float(raw.strip())
        except ValueError:
            continue
        celsius = kelvin_tenths / 10.0 - 273.15
        if 0 < celsius < 130:
            return celsius
    return None


def _windows_gpu_name() -> str:
    if shutil.which("powershell"):
        output = _run_command(
            (
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)",
            )
        )
        name = next((line.strip() for line in output.splitlines() if line.strip()), "")
        if name:
            return name
    if shutil.which("wmic"):
        output = _run_command(("wmic", "path", "win32_VideoController", "get", "name"))
        names = [line.strip() for line in output.splitlines() if line.strip() and line.strip().lower() != "name"]
        return names[0] if names else ""
    return ""


def _windows_top_ram_process() -> tuple[int, str] | None:
    output = _run_command(("tasklist", "/fo", "csv", "/nh"))
    return _parse_tasklist_top_memory(output)


def _parse_tasklist_top_memory(output: str) -> tuple[int, str] | None:
    best: tuple[int, str] | None = None
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 5:
            continue
        name = row[0]
        mem_raw = row[4].replace(",", "").replace(".", "").replace("K", "").replace("k", "").strip()
        try:
            rss = int(mem_raw) * 1024
        except ValueError:
            continue
        if best is None or rss > best[0]:
            best = (rss, name)
    return best


def _percent_status(value: float) -> str:
    return "critical" if value >= 90 else "warn" if value >= 75 else "ok"


def _bytes_label(value: int) -> str:
    if value >= 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024 * 1024):.1f}G"
    if value >= 1024 * 1024:
        return f"{value // (1024 * 1024)}M"
    return f"{value // 1024}K"


def _duration_label(seconds: int) -> str:
    days = seconds // 86400
    if days:
        return f"{days}d"
    hours = seconds // 3600
    if hours:
        return f"{hours}h"
    minutes = seconds // 60
    return f"{minutes}m"


def _short_name(value: str, limit: int = 10) -> str:
    clean = value.strip() or "-"
    return clean if len(clean) <= limit else clean[: max(1, limit - 1)] + "."
