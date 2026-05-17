#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pixel_ops.data_sources.calendar import next_ics_event, next_mock_event
from pixel_ops.data_sources.weather import OpenMeteoWeatherSource
from pixel_ops.events.mock_events import MockEventSource
from pixel_ops.integration_plugins.base import IntegrationContext
from pixel_ops.integration_plugins.registry import build_integration_runtime
from pixel_ops.outputs import GifOutput, PreviewOutput, TURZXOutput, WindowOutput
from pixel_ops.outputs.base import DisplayOutput
from pixel_ops.plugins.ai.plugin import build_ai_plugin
from pixel_ops.plugins.registry import available_plugins, get_plugin
from pixel_ops.render.splash import render_splash, splash_frame_count, splash_seconds

APP_DIR = Path(__file__).resolve().parent


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
    parser.add_argument("--plugin", choices=plugin_names, default="pokemon", help="Interface plugin to render.")
    parser.add_argument("--output", choices=("preview", "gif", "turzx", "window"), help="Frame output target.")
    parser.add_argument("--display", action="store_true", help="Send frames to UsbMonitor via USB bulk.")
    parser.add_argument("--window", action="store_true", help="Render frames in a desktop window.")
    parser.add_argument("--window-scale", type=int, default=2, help="Desktop window pixel scale.")
    parser.add_argument("--preview", action="store_true", help="Render a single PNG preview.")
    parser.add_argument("--gif", action="store_true", help="Render an animated GIF preview.")
    parser.add_argument("--preview-sequence", action="store_true", help="Write numbered PNG frames for preview output.")
    parser.add_argument("--seconds", type=float, default=20)
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


def selected_output(args: argparse.Namespace) -> str:
    if args.output:
        return args.output
    if args.display:
        return "turzx"
    if args.window:
        return "window"
    if args.gif:
        return "gif"
    return "preview"


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
        return PreviewOutput(root_dir / display_cfg["preview_output"], sequence=args.preview_sequence)
    if output_name == "gif":
        return GifOutput(root_dir / display_cfg["gif_output"], fps=fps)
    if output_name == "turzx":
        return TURZXOutput(width=width, height=height)
    if output_name == "window":
        return WindowOutput(width=width, height=height, scale=args.window_scale)
    raise ValueError(f"Unsupported output: {output_name}")


def main() -> int:
    args = build_parser().parse_args()
    load_env(ROOT_DIR / ".env")
    plugin = get_plugin(args.plugin)
    plugin_dir = APP_DIR / "plugins" / plugin.name
    display_cfg = load_yaml(APP_DIR / "config/display.yaml")["display"]
    people_cfg = load_yaml(APP_DIR / "config/people.yaml")["people"]
    plugin_cfg = plugin.load_config(plugin_dir, load_yaml)
    width = int(display_cfg["width"])
    height = int(display_cfg["height"])
    fps = args.fps or plugin.fps(plugin_cfg, int(display_cfg["fps"]))
    primary_tz = display_cfg["timezone_primary"]

    if plugin.maybe_handle_command(args, ROOT_DIR, plugin_cfg):
        return 0

    integration_runtime = build_integration_runtime(
        IntegrationContext(
            root_dir=ROOT_DIR,
            args=args,
            env_bool=env_bool,
            env_int=env_int,
            env_value=env_value,
            split_env_list=split_env_list,
        )
    )
    integration_runtime.start()
    events_cfg = plugin.event_config(plugin_cfg)
    event_sources = [
        MockEventSource(enabled=env_bool("PIXEL_OPS_MOCK_EVENTS", bool(events_cfg.get("mock_events", False)))),
        *integration_runtime.event_sources,
    ]
    pull_request_source = integration_runtime.pull_request_source
    weather_cfg = display_cfg.get("weather", {})
    weather_source = OpenMeteoWeatherSource(
        enabled=env_bool("PIXEL_OPS_WEATHER_ENABLED", bool(weather_cfg.get("enabled", True))),
        city=env_value("PIXEL_OPS_WEATHER_CITY", weather_cfg.get("city", "Porto Alegre")) or "Porto Alegre",
        country_code=env_value("PIXEL_OPS_WEATHER_COUNTRY", weather_cfg.get("country_code", "BR")) or "BR",
        poll_seconds=env_int("PIXEL_OPS_WEATHER_POLL_SECONDS", int(weather_cfg.get("poll_seconds", 900))),
    )
    ai_plugin = build_ai_plugin(display_cfg.get("ai", {}))
    integration_runtime.warm()
    calendar_enabled = any(name in integration_runtime.loaded_plugins for name in ("ics", "google_calendar"))

    app = plugin.build_app(
        args=args,
        root_dir=ROOT_DIR,
        display_cfg=display_cfg,
        config=plugin_cfg,
        width=width,
        height=height,
        fps=fps,
        people_config=people_cfg,
        next_event=lambda now: next_event(now, integration_runtime.calendar_paths, calendar_enabled),
        pull_request_source=pull_request_source,
        weather_source=weather_source,
        ai_plugin=ai_plugin,
        event_sources=event_sources,
    )

    output_name = selected_output(args)
    output = build_output(output_name, args, ROOT_DIR, display_cfg, width, height, fps)
    try:
        output.start()
        if output_name == "preview" and not args.preview_sequence:
            now = datetime.now(ZoneInfo(primary_tz))
            output.send(app.render_frame(now))
            return 0

        frame_delay = 1 / fps
        splash_frame = render_splash(ROOT_DIR, display_cfg, width, height)
        splash_frames = splash_frame_count(display_cfg, fps) if splash_frame else 0
        if output_name == "gif":
            started = datetime.now(ZoneInfo(primary_tz))
            total_frames = max(1, int(args.seconds * fps))
            for frame_index in range(total_frames):
                if frame_index < splash_frames:
                    output.send(splash_frame)
                else:
                    now = started + timedelta(seconds=(frame_index - splash_frames) / fps)
                    output.send(app.render_frame(now))
            return 0

        if splash_frame:
            splash_end_at = time.perf_counter() + splash_seconds(display_cfg)
            while time.perf_counter() < splash_end_at:
                loop_started = time.perf_counter()
                output.send(splash_frame)
                elapsed = time.perf_counter() - loop_started
                remaining = splash_end_at - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(frame_delay, remaining, max(0, frame_delay - elapsed)))

        end_at = None if args.forever or args.seconds <= 0 else time.perf_counter() + args.seconds
        while end_at is None or time.perf_counter() < end_at:
            loop_started = time.perf_counter()
            now = datetime.now(ZoneInfo(primary_tz))
            output.send(app.render_frame(now))
            elapsed = time.perf_counter() - loop_started
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        output.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
