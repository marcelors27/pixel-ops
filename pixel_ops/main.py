#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pixel_ops.data_sources.calendar import CalendarEvent, next_ics_event, next_mock_event, today_ics_events
from pixel_ops.config_loader import ConfigWatcher, load_config_prefer_json
from pixel_ops.core.screen_control import ScreenControlServer
from pixel_ops.events.mock_events import MockEventSource
from pixel_ops.events.observation_sources import CallableObservationSource
from pixel_ops.integration_plugins.base import IntegrationContext
from pixel_ops.integration_plugins.registry import build_integration_runtime
from pixel_ops.outputs import EInkHttpOutput, GifOutput, LcdHttpOutput, PreviewOutput, TURZXOutput, ThermalrightOutput, WindowOutput
from pixel_ops.outputs.base import CroppedOutput, DisplayOutput
from pixel_ops.plugins.ai.plugin import build_ai_plugin
from pixel_ops.plugins.registry import available_plugins, get_plugin
from pixel_ops.render.splash import render_splash, splash_frame_count, splash_seconds

APP_DIR = Path(__file__).resolve().parent


@dataclass
class RuntimeTarget:
    name: str
    display_cfg: dict
    width: int
    height: int
    output_name: str
    output: DisplayOutput
    started: bool = False
    next_start_attempt_at: float = 0.0
    last_error: str = ""


@dataclass
class RuntimeState:
    display_cfg: dict
    width: int
    height: int
    app: object
    targets: list[RuntimeTarget]


def load_config(path: Path) -> dict:
    return load_config_prefer_json(path)


def load_runtime_config() -> dict:
    path = APP_DIR / "config/integrations.json"
    return load_config(path) if path.exists() else {"integrations": {}}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
        os.environ.setdefault(key.strip(), value)
    return values


def env_bool(name: str, default: bool = False) -> bool:
    value = env_value(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(env_value(name) or str(default))
    except ValueError:
        return default


def env_value(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None:
        return value
    return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pixel OPs timezone dashboard renderer.")
    plugin_names = sorted(available_plugins())
    parser.add_argument("--plugin", choices=plugin_names, help="Interface plugin to render. Defaults to display.device.plugin.")
    parser.add_argument("--output", choices=("preview", "gif", "turzx", "thermalright", "eink", "lcd", "window"), help="Frame output target.")
    parser.add_argument("--display", action="store_true", help="Send frames to UsbMonitor via USB bulk.")
    parser.add_argument("--window", action="store_true", help="Render frames in a desktop window.")
    parser.add_argument("--window-scale", type=int, help="Desktop window pixel scale.")
    parser.add_argument("--preview", action="store_true", help="Render a single PNG preview.")
    parser.add_argument("--gif", action="store_true", help="Render an animated GIF preview.")
    parser.add_argument("--orientation", choices=("vertical", "horizontal"), help="Display layout orientation.")
    parser.add_argument("--preview-sequence", action="store_true", help="Write numbered PNG frames for preview output.")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--forever", action="store_true", help="Run display loop until Ctrl+C.")
    parser.add_argument("--fps", type=int, default=0)
    parser.add_argument("--full-frame", action="store_true", help="Send full frames instead of dirty regions.")
    parser.add_argument("--ics", type=Path, help="Optional local ICS calendar export.")
    for plugin in available_plugins().values():
        plugin.add_arguments(parser)
    return parser


def split_env_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def next_event(now: datetime, calendar_paths: list[Path], calendar_enabled: bool):
    events = []
    for path in calendar_paths:
        event = next_ics_event(path, now)
        if event:
            events.append(event)
    if events:
        return min(events, key=lambda item: item.starts_at)
    if calendar_enabled:
        return None
    return next_mock_event(now)


def today_events(now: datetime, calendar_paths: list[Path], calendar_enabled: bool) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    seen: set[tuple[str, datetime]] = set()
    for path in calendar_paths:
        for event in today_ics_events(path, now):
            key = (event.title, event.starts_at.replace(microsecond=0))
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    if events:
        return sorted(events, key=lambda item: item.starts_at)
    if calendar_enabled:
        return []
    return [next_mock_event(now)]


def selected_output(args: argparse.Namespace) -> str:
    if getattr(args, "output", None):
        return args.output
    if getattr(args, "display", False):
        return "turzx"
    if getattr(args, "window", False):
        return "window"
    if getattr(args, "gif", False):
        return "gif"
    return "preview"


def runtime_device_config(display_cfg: dict) -> dict:
    cfg = display_cfg.get("device", {})
    return cfg if isinstance(cfg, dict) else {}


def runtime_plugin_name(args: argparse.Namespace, display_cfg: dict) -> str:
    requested = getattr(args, "plugin", None)
    configured = runtime_device_config(display_cfg).get("plugin")
    name = str(requested or configured or "pokemon").strip().lower()
    return name if name in available_plugins() else "pokemon"


def runtime_orientation(args: argparse.Namespace, display_cfg: dict) -> str:
    orientation = args.orientation or display_cfg.get("orientation") or "vertical"
    orientation = str(orientation).strip().lower()
    return orientation if orientation in ("vertical", "horizontal") else "vertical"


def runtime_display_config(args: argparse.Namespace, display_cfg: dict, select_configured_display: bool = True) -> dict:
    orientation = runtime_orientation(args, display_cfg)
    profiles = display_cfg.get("orientations", {})
    profile = profiles.get(orientation, {}) if isinstance(profiles, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    active = dict(display_cfg)
    for key in ("width", "height", "layout"):
        if key in profile:
            active[key] = profile[key]
    active["orientation"] = orientation
    output_name = _runtime_output_name(args, active)
    display = _configured_display_for_output(active, output_name) if select_configured_display else None
    if display is not None:
        active = _display_runtime_config(active, display)
    return active


def runtime_display_configs(args: argparse.Namespace, display_cfg: dict) -> list[dict]:
    if _args_selects_output(args):
        return [runtime_display_config(args, display_cfg)]
    active = virtual_display_config(display_cfg)
    device_cfg = runtime_device_config(active)
    displays = device_cfg.get("displays", [])
    if not isinstance(displays, list):
        return [runtime_display_config(args, display_cfg)]
    configs = [
        _display_runtime_config(active, item)
        for item in displays
        if isinstance(item, dict)
        and bool(item.get("enabled", True))
        and _normalize_output_name(item.get("output") or item.get("target") or device_cfg.get("output") or device_cfg.get("target")) in ("thermalright", "turzx", "eink", "lcd")
    ]
    return configs or [runtime_display_config(args, display_cfg)]


def virtual_display_config(display_cfg: dict) -> dict:
    """Keep the global canvas for multi-display rendering.

    Orientation profiles describe a single presentation surface. Applying one
    before cropping virtual displays can shrink the shared frame and turn
    displays positioned outside that profile into blank crops.
    """

    active = dict(display_cfg)
    device_cfg = runtime_device_config(active)
    displays = device_cfg.get("displays", [])
    enabled = [item for item in displays if isinstance(item, dict) and bool(item.get("enabled", True))]
    if enabled:
        active["width"] = max(int(active.get("width", 1)), max(int(item.get("x", 0)) + int(item.get("width", 1)) for item in enabled))
        active["height"] = max(int(active.get("height", 1)), max(int(item.get("y", 0)) + int(item.get("height", 1)) for item in enabled))
        active["layout"] = _mark_eink_layout_regions(active.get("layout"), enabled)
    return active


def _mark_eink_layout_regions(layout, displays: list[dict]) -> dict:
    if not isinstance(layout, dict):
        return {}
    eink_displays = [
        item
        for item in displays
        if _normalize_output_name(item.get("output") or item.get("target")) == "eink"
    ]
    marked: dict = {}
    for key, raw in layout.items():
        if not isinstance(raw, dict):
            marked[key] = raw
            continue
        item = dict(raw)
        try:
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            x1 = x + max(1, int(item.get("width", 0)))
            y1 = y + max(1, int(item.get("height", 0)))
        except (TypeError, ValueError):
            marked[key] = item
            continue
        for display in eink_displays:
            dx = int(display.get("x", 0))
            dy = int(display.get("y", 0))
            dx1 = dx + max(1, int(display.get("width", 0)))
            dy1 = dy + max(1, int(display.get("height", 0)))
            if x >= dx and y >= dy and x1 <= dx1 and y1 <= dy1:
                item["monochrome"] = True
                break
        marked[key] = item
    return marked


def _display_runtime_config(display_cfg: dict, display: dict) -> dict:
    active = dict(display_cfg)
    device_cfg = dict(runtime_device_config(display_cfg))
    output_name = _normalize_output_name(display.get("output") or display.get("target") or device_cfg.get("output") or device_cfg.get("target"))
    device_cfg["target"] = output_name
    device_cfg["output"] = output_name
    if output_name == "thermalright":
        device_cfg["thermalright"] = _merged_device_config(device_cfg.get("thermalright"), display.get("thermalright"))
    elif output_name == "turzx":
        device_cfg["turzx"] = _merged_device_config(device_cfg.get("turzx"), display.get("turzx"))
    elif output_name == "eink":
        device_cfg["eink"] = _merged_device_config(device_cfg.get("eink"), display.get("eink"))
    elif output_name == "lcd":
        device_cfg["lcd"] = _merged_device_config(device_cfg.get("lcd"), display.get("lcd"))
    active["device"] = device_cfg
    if display is not None:
        rotation = _normalize_rotation(display.get("rotation", 0))
        active["width"], active["height"] = _display_region_size(output_name, rotation, display, active)
        active["display_region"] = {
            "x": int(display.get("x", 0)),
            "y": int(display.get("y", 0)),
            "width": active["width"],
            "height": active["height"],
            "rotation": rotation,
        }
        if isinstance(display.get("layout"), dict):
            active["layout"] = {
                key: ({**raw, "monochrome": True} if output_name == "eink" and isinstance(raw, dict) else raw)
                for key, raw in display["layout"].items()
            }
        elif isinstance(active.get("layout"), dict):
            active["layout"] = _layout_for_display(active["layout"], display, monochrome=output_name == "eink")
    return active


def _layout_for_display(layout: dict, display: dict, *, monochrome: bool = False) -> dict:
    try:
        dx = int(display.get("x", 0))
        dy = int(display.get("y", 0))
        dw = int(display.get("width", 320))
        dh = int(display.get("height", 480))
    except (TypeError, ValueError):
        return layout
    if dw <= 0 or dh <= 0:
        return {}

    display_x1 = dx + dw
    display_y1 = dy + dh
    scoped: dict = {}
    for key, raw in layout.items():
        if not isinstance(raw, dict):
            scoped[key] = raw
            continue
        try:
            x = int(raw.get("x", 0))
            y = int(raw.get("y", 0))
            width = int(raw.get("width", 0))
            height = int(raw.get("height", 0))
        except (TypeError, ValueError):
            continue
        x1 = x + max(1, width)
        y1 = y + max(1, height)
        ix0 = max(x, dx)
        iy0 = max(y, dy)
        ix1 = min(x1, display_x1)
        iy1 = min(y1, display_y1)
        if ix1 - ix0 < 8 or iy1 - iy0 < 8:
            continue
        item = dict(raw)
        item["x"] = ix0 - dx
        item["y"] = iy0 - dy
        item["width"] = ix1 - ix0
        item["height"] = iy1 - iy0
        if monochrome:
            item["monochrome"] = True
        scoped[key] = item
    return scoped


def runtime_output(args: argparse.Namespace, display_cfg: dict) -> str:
    return _runtime_output_name(args, display_cfg)


def _runtime_output_name(args: argparse.Namespace, display_cfg: dict) -> str:
    if _args_selects_output(args):
        return selected_output(args)
    device_cfg = runtime_device_config(display_cfg)
    output = _normalize_output_name(device_cfg.get("output") or device_cfg.get("target") or "preview")
    if output in ("preview", "gif", "turzx", "thermalright", "eink", "lcd", "window"):
        return output
    return "preview"


def _args_selects_output(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "output", None)
        or getattr(args, "display", False)
        or getattr(args, "window", False)
        or getattr(args, "gif", False)
        or getattr(args, "preview", False)
    )


def runtime_seconds(args: argparse.Namespace, display_cfg: dict) -> float:
    if args.seconds is not None:
        return float(args.seconds)
    return float(runtime_device_config(display_cfg).get("seconds", 20))


def runtime_forever(args: argparse.Namespace, display_cfg: dict) -> bool:
    if args.forever:
        return True
    return bool(runtime_device_config(display_cfg).get("forever", False))


def runtime_window_scale(args: argparse.Namespace, display_cfg: dict) -> int:
    if args.window_scale is not None:
        return max(1, int(args.window_scale))
    return max(1, int(runtime_device_config(display_cfg).get("window_scale", 2)))


def runtime_preview_sequence(args: argparse.Namespace, display_cfg: dict) -> bool:
    return bool(args.preview_sequence or runtime_device_config(display_cfg).get("preview_sequence", False))


def build_output(
    output_name: str,
    args: argparse.Namespace,
    root_dir: Path,
    display_cfg: dict,
    width: int,
    height: int,
    fps: int,
) -> DisplayOutput:
    if output_name == "preview":
        return PreviewOutput(root_dir / display_cfg["preview_output"], sequence=runtime_preview_sequence(args, display_cfg))
    if output_name == "gif":
        return GifOutput(root_dir / display_cfg["gif_output"], fps=fps)
    if output_name == "turzx":
        display = None if "display_region" in display_cfg else _configured_display_for_output(display_cfg, output_name)
        cfg = _merged_device_config(runtime_device_config(display_cfg).get("turzx"), display.get("turzx") if display else None)
        return TURZXOutput.from_config(width, height, cfg)
    if output_name == "thermalright":
        device_cfg = runtime_device_config(display_cfg)
        display = None if "display_region" in display_cfg else _configured_display_for_output(display_cfg, output_name)
        thermalright_cfg = _merged_device_config(device_cfg.get("thermalright"), display.get("thermalright") if display else None)
        if "display_region" in display_cfg:
            thermalright_cfg["image_width"] = width
            thermalright_cfg["image_height"] = height
        return _thermalright_output(thermalright_cfg, width, height)
    if output_name == "eink":
        display = None if "display_region" in display_cfg else _configured_display_for_output(display_cfg, output_name)
        eink_cfg = _merged_device_config(runtime_device_config(display_cfg).get("eink"), display.get("eink") if display else None)
        eink_cfg["layout"] = display_cfg.get("layout", {})
        eink_cfg["layout_theme"] = display_cfg.get("layout_theme", "default")
        return EInkHttpOutput.from_config(width, height, eink_cfg)
    if output_name == "lcd":
        display = None if "display_region" in display_cfg else _configured_display_for_output(display_cfg, output_name)
        lcd_cfg = _merged_device_config(runtime_device_config(display_cfg).get("lcd"), display.get("lcd") if display else None)
        return LcdHttpOutput.from_config(width, height, lcd_cfg)
    if output_name == "window":
        return WindowOutput(width=width, height=height, scale=runtime_window_scale(args, display_cfg))
    raise ValueError(f"Unsupported output: {output_name}")


def _configured_display_for_output(display_cfg: dict, output_name: str) -> dict | None:
    if output_name not in ("thermalright", "turzx", "eink", "lcd"):
        return None
    device_cfg = runtime_device_config(display_cfg)
    displays = device_cfg.get("displays", [])
    if not isinstance(displays, list):
        return None
    for item in displays:
        if not isinstance(item, dict) or not bool(item.get("enabled", True)):
            continue
        target = _normalize_output_name(item.get("output") or item.get("target") or device_cfg.get("output") or device_cfg.get("target"))
        if target == output_name:
            return item
    return None


def _thermalright_output(thermalright_cfg: dict, width: int, height: int) -> ThermalrightOutput:
    return ThermalrightOutput(
        vid=parse_hex_int(thermalright_cfg.get("vid", "0x0416")),
        pid=parse_hex_int(thermalright_cfg.get("pid", "0x5408")),
        serial_number=str(thermalright_cfg.get("serial_number") or ""),
        bus=parse_optional_int(thermalright_cfg.get("bus")),
        address=parse_optional_int(thermalright_cfg.get("address")),
        timeout_ms=int(thermalright_cfg.get("timeout_ms", 5000)),
        jpeg_quality=int(thermalright_cfg.get("jpeg_quality", 85)),
        image_width=int(thermalright_cfg.get("image_width", width)),
        image_height=int(thermalright_cfg.get("image_height", height)),
        min_frame_interval_ms=int(thermalright_cfg.get("min_frame_interval_ms", 0)),
        packet_delay_ms=int(thermalright_cfg.get("packet_delay_ms", 0)),
        packet_size=int(thermalright_cfg.get("packet_size", 4096)),
        hard_reset_on_start=bool(thermalright_cfg.get("hard_reset_on_start", True)),
        hard_reset_wait_ms=int(thermalright_cfg.get("hard_reset_wait_ms", 1500)),
        handshake_on_first_frame=bool(thermalright_cfg.get("handshake_on_first_frame", False)),
        require_handshake=bool(thermalright_cfg.get("require_handshake", True)),
        send_start_init=bool(thermalright_cfg.get("send_start_init", True)),
        read_start_ack=bool(thermalright_cfg.get("read_start_ack", True)),
        read_frame_ack=bool(thermalright_cfg.get("read_frame_ack", True)),
        start_retries=int(thermalright_cfg.get("start_retries", 0)),
        frame_retries=int(thermalright_cfg.get("frame_retries", 0)),
        debug=bool(thermalright_cfg.get("debug", False)),
    )


def _merged_device_config(base, override) -> dict:
    merged = base if isinstance(base, dict) else {}
    if isinstance(override, dict):
        return {**merged, **override}
    return dict(merged)


def _normalize_output_name(value) -> str:
    output = str(value or "preview").strip().lower()
    if output == "display":
        return "turzx"
    if output in ("e-ink", "eink_http"):
        return "eink"
    if output in ("tft", "lcd_http"):
        return "lcd"
    return output


def _normalize_rotation(value) -> int:
    try:
        rotation = int(value)
    except (TypeError, ValueError):
        return 0
    return rotation if rotation in (0, 90, 180, 270) else 0


def _display_region_size(output_name: str, rotation: int, display: dict, fallback: dict) -> tuple[int, int]:
    if output_name == "thermalright":
        width, height = 1920, 462
    elif output_name == "turzx":
        width, height = 320, 480
    elif output_name == "lcd":
        width, height = 172, 320
    else:
        width = int(display.get("width", fallback.get("width", 320)))
        height = int(display.get("height", fallback.get("height", 480)))
    if rotation in (90, 270):
        return height, width
    return width, height


def parse_hex_int(value) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    return int(text, 16) if text.startswith("0x") else int(text, 10)


def parse_optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return parse_hex_int(value)


def main() -> int:
    args = build_parser().parse_args()
    load_env(ROOT_DIR / ".env")
    runtime_config = load_runtime_config()
    raw_display_cfg = load_config(APP_DIR / "config/display.json")["display"]
    plugin = get_plugin(runtime_plugin_name(args, raw_display_cfg))
    plugin_dir = APP_DIR / "plugins" / plugin.name
    use_virtual_displays = not _args_selects_output(args)
    display_cfg = virtual_display_config(raw_display_cfg) if use_virtual_displays else runtime_display_config(args, raw_display_cfg)
    people_cfg = load_config(APP_DIR / "config/people.json")["people"]
    plugin_cfg = plugin.load_config(plugin_dir, load_config)
    config_watcher = ConfigWatcher(
        lambda: [
            APP_DIR / "config/display.json",
            APP_DIR / "config/people.json",
            APP_DIR / "config/integrations.json",
            *(APP_DIR / "plugins" / name / "game.json" for name in available_plugins()),
            APP_DIR / "plugins/pokemon/pokemon.json",
            APP_DIR / "plugins/pokemon/companions.json",
        ]
    )
    config_watcher.reset()
    width = int(display_cfg["width"])
    height = int(display_cfg["height"])
    fps = args.fps or plugin.fps(plugin_cfg, int(display_cfg["fps"]))
    primary_tz = display_cfg["timezone_primary"]

    if plugin.maybe_handle_command(args, ROOT_DIR, plugin_cfg):
        return 0

    def build_integration_runtime_from_config(current_runtime_config: dict):
        built = build_integration_runtime(
            IntegrationContext(
                root_dir=ROOT_DIR,
                args=args,
                config=current_runtime_config,
                env_bool=env_bool,
                env_int=env_int,
                env_value=env_value,
                split_env_list=split_env_list,
            )
        )
        built.start()
        built.warm()
        return built

    integration_runtime = build_integration_runtime_from_config(runtime_config)

    def build_runtime_app(current_display_cfg: dict, target_width: int, target_height: int):
        nonlocal integration_runtime
        configured_screen_plugins = {
            str(item.get("plugin") or plugin.name)
            for item in current_display_cfg.get("screens", {}).values()
            if isinstance(item, dict) and bool(item.get("enabled", True))
        }
        configured_screen_plugins.add(plugin.name)
        current_people_cfg = load_config(APP_DIR / "config/people.json")["people"]
        current_plugin_cfg = plugin.load_config(plugin_dir, load_config)
        current_events_cfg = plugin.event_config(current_plugin_cfg)
        current_calendar_enabled = any(name in integration_runtime.loaded_plugins for name in ("ics", "google_calendar"))
        calendar_cache = {
            "next_checked_at": None,
            "next_value": None,
            "today_checked_at": None,
            "today_value": [],
        }

        def cached_next_event(now):
            checked_at = calendar_cache["next_checked_at"]
            if checked_at is None or (now - checked_at).total_seconds() >= 30:
                calendar_cache["next_checked_at"] = now
                calendar_cache["next_value"] = next_event(now, integration_runtime.calendar_paths, current_calendar_enabled)
            return calendar_cache["next_value"]

        def cached_today_events(now):
            checked_at = calendar_cache["today_checked_at"]
            if checked_at is None or checked_at.date() != now.date() or (now - checked_at).total_seconds() >= 30:
                calendar_cache["today_checked_at"] = now
                calendar_cache["today_value"] = today_events(now, integration_runtime.calendar_paths, current_calendar_enabled)
            return calendar_cache["today_value"]

        current_event_sources = [
            MockEventSource(enabled=env_bool("PIXEL_OPS_MOCK_EVENTS", bool(current_events_cfg.get("mock_events", False)))),
            *integration_runtime.event_sources,
            CallableObservationSource("calendar.next_updated", "calendar", cached_next_event),
            CallableObservationSource("calendar.today_updated", "calendar", cached_today_events),
        ]

        app = plugin.build_app(
            args=args,
            root_dir=ROOT_DIR,
            display_cfg=current_display_cfg,
            config=current_plugin_cfg,
            width=target_width,
            height=target_height,
            fps=fps,
            people_config=current_people_cfg,
            ai_plugin=build_ai_plugin(current_display_cfg.get("ai", {})),
            event_sources=current_event_sources,
        )
        for engine_name in sorted(configured_screen_plugins - {plugin.name}):
            secondary_plugin = get_plugin(engine_name)
            secondary_dir = APP_DIR / "plugins" / engine_name
            secondary_config = secondary_plugin.load_config(secondary_dir, load_config)
            secondary_app = secondary_plugin.build_app(
                args=args,
                root_dir=ROOT_DIR,
                display_cfg=current_display_cfg,
                config=secondary_config,
                width=target_width,
                height=target_height,
                fps=fps,
                people_config=current_people_cfg,
                ai_plugin=None,
                event_sources=[],
            )
            app.add_engine(secondary_app.engine)
        return app

    def build_runtime_targets(current_raw_display_cfg: dict) -> list[RuntimeTarget]:
        current_display_cfgs = runtime_display_configs(args, current_raw_display_cfg)
        targets: list[RuntimeTarget] = []
        multi_display = use_virtual_displays and len(current_display_cfgs) > 1
        for current_display_cfg in current_display_cfgs:
            target_width = int(current_display_cfg["width"])
            target_height = int(current_display_cfg["height"])
            target_output_name = runtime_output(args, current_display_cfg)
            region = current_display_cfg.get("display_region", {})
            rotation = _normalize_rotation(region.get("rotation", 0))
            output_width, output_height = (target_height, target_width) if rotation in (90, 270) else (target_width, target_height)
            target_output = build_output(target_output_name, args, ROOT_DIR, current_display_cfg, output_width, output_height, fps)
            if multi_display or rotation:
                x = int(region.get("x", 0))
                y = int(region.get("y", 0))
                box = (x, y, x + target_width, y + target_height) if multi_display else (0, 0, target_width, target_height)
                target_output = CroppedOutput(target_output, box, rotation=rotation)
            target_name = str(runtime_device_config(current_display_cfg).get("output") or target_output_name)
            targets.append(RuntimeTarget(target_name, current_display_cfg, target_width, target_height, target_output_name, target_output))
        return targets

    def build_runtime_state() -> RuntimeState:
        current_raw_display_cfg = load_config(APP_DIR / "config/display.json")["display"]
        current_display_cfg = virtual_display_config(current_raw_display_cfg) if use_virtual_displays else runtime_display_config(args, current_raw_display_cfg)
        target_width = int(current_display_cfg["width"])
        target_height = int(current_display_cfg["height"])
        if use_virtual_displays:
            print(f"[pixel-ops canvas] {target_width}x{target_height} with {len(current_display_cfg.get('layout', {}))} layout regions", file=sys.stderr)
        return RuntimeState(
            display_cfg=current_display_cfg,
            width=target_width,
            height=target_height,
            app=build_runtime_app(current_display_cfg, target_width, target_height),
            targets=build_runtime_targets(current_raw_display_cfg),
        )

    runtime_state = build_runtime_state()
    control_cfg = raw_display_cfg.get("screen_control", {})
    control_cfg = control_cfg if isinstance(control_cfg, dict) else {}
    screen_control = ScreenControlServer(
        lambda: runtime_state.app.screens,
        port=int(control_cfg.get("port", 8766)),
    )
    try:
        screen_control.start()
        print(f"[pixel-ops screens] control listening on 127.0.0.1:{screen_control.port}", file=sys.stderr)
    except OSError as error:
        print(f"[pixel-ops screens] control unavailable: {error}", file=sys.stderr)

    def maybe_reload_runtime(current_state: RuntimeState):
        nonlocal integration_runtime, runtime_config
        if not config_watcher.changed():
            return current_state
        try:
            next_runtime_config = load_runtime_config()
            if next_runtime_config != runtime_config:
                integration_runtime.close()
                integration_runtime = build_integration_runtime_from_config(next_runtime_config)
                runtime_config = next_runtime_config
            for target in current_state.targets:
                if target.started:
                    target.output.stop()
            next_state = build_runtime_state()
            if current_state.app.screens is not None and next_state.app.screens is not None:
                previous_screen = current_state.app.screens.status()
                previous_id = previous_screen.get("active_screen_id")
                available_ids = {item["id"] for item in next_state.app.screens.status().get("screens", [])}
                if previous_id in available_ids:
                    next_state.app.screens.select(previous_id, pinned=previous_screen.get("mode") == "pinned")
            current_state.app.close()
            for target in next_state.targets:
                start_target(target)
            return next_state
        except Exception as error:
            print(f"[pixel-ops config] hot reload failed: {type(error).__name__}: {error}", file=sys.stderr)
            return current_state

    output_retry_mode = runtime_forever(args, display_cfg)
    output_retry_seconds = max(1.0, float(runtime_device_config(display_cfg).get("output_retry_seconds", 5)))

    def start_target(target: RuntimeTarget, retry: bool = output_retry_mode) -> bool:
        if target.started:
            return True
        now_monotonic = time.monotonic()
        if retry and now_monotonic < target.next_start_attempt_at:
            return False
        try:
            target.output.start()
            target.started = True
            target.last_error = ""
            print(f"[pixel-ops output] started {target.name}", file=sys.stderr)
            return True
        except RuntimeError as error:
            if not retry:
                raise
            message = str(error)
            if message != target.last_error:
                print(f"[pixel-ops output] {target.name} unavailable: {message}; retrying in {output_retry_seconds:.0f}s", file=sys.stderr)
                target.last_error = message
            target.next_start_attempt_at = now_monotonic + output_retry_seconds
            target.started = False
            try:
                target.output.stop()
            except Exception:
                pass
            return False

    def send_frame(target: RuntimeTarget, frame) -> None:
        if not start_target(target):
            return
        try:
            target.output.send(frame)
        except RuntimeError as error:
            if not output_retry_mode:
                raise
            print(f"[pixel-ops output] {target.name} send failed: {error}; will reconnect", file=sys.stderr)
            target.started = False
            target.next_start_attempt_at = time.monotonic() + output_retry_seconds
            try:
                target.output.stop()
            except Exception:
                pass

    try:
        for target in runtime_state.targets:
            start_target(target)
        if len(runtime_state.targets) == 1 and runtime_state.targets[0].output_name == "preview" and not runtime_preview_sequence(args, display_cfg):
            now = datetime.now(ZoneInfo(primary_tz))
            send_frame(runtime_state.targets[0], runtime_state.app.render_frame(now))
            return 0

        frame_delay = 1 / fps
        splash_frame = render_splash(ROOT_DIR, runtime_state.display_cfg, runtime_state.width, runtime_state.height)
        splash_frame_limit = splash_frame_count(runtime_state.display_cfg, fps) if splash_frame is not None else 0
        if len(runtime_state.targets) == 1 and runtime_state.targets[0].output_name == "gif":
            started = datetime.now(ZoneInfo(primary_tz))
            total_frames = max(1, int(runtime_seconds(args, display_cfg) * fps))
            for frame_index in range(total_frames):
                runtime_state = maybe_reload_runtime(runtime_state)
                target = runtime_state.targets[0]
                if splash_frame is not None and frame_index < splash_frame_count(runtime_state.display_cfg, fps):
                    send_frame(target, splash_frame)
                else:
                    target_splash_frames = splash_frame_count(runtime_state.display_cfg, fps) if splash_frame is not None else 0
                    now = started + timedelta(seconds=(frame_index - target_splash_frames) / fps)
                    send_frame(target, runtime_state.app.render_frame(now))
            return 0

        if splash_frame_limit > 0:
            splash_end_at = time.perf_counter() + splash_seconds(runtime_state.display_cfg)
            while time.perf_counter() < splash_end_at:
                loop_started = time.perf_counter()
                if splash_frame is not None:
                    for target in runtime_state.targets:
                        send_frame(target, splash_frame)
                elapsed = time.perf_counter() - loop_started
                remaining = splash_end_at - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(frame_delay, remaining, max(0, frame_delay - elapsed)))

        seconds = runtime_seconds(args, display_cfg)
        end_at = None if runtime_forever(args, display_cfg) or seconds <= 0 else time.perf_counter() + seconds
        while end_at is None or time.perf_counter() < end_at:
            loop_started = time.perf_counter()
            runtime_state = maybe_reload_runtime(runtime_state)
            now = datetime.now(ZoneInfo(primary_tz))
            frame = runtime_state.app.render_frame(now)
            for target in runtime_state.targets:
                send_frame(target, frame)
            elapsed = time.perf_counter() - loop_started
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        screen_control.close()
        integration_runtime.close()
        runtime_state.app.close()
        for target in runtime_state.targets:
            if target.started:
                target.output.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
