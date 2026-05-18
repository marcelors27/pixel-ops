#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pixel_ops.data_sources.calendar import next_ics_event, next_mock_event
from pixel_ops.config_loader import ConfigWatcher, load_config_prefer_json
from pixel_ops.events.mock_events import MockEventSource
from pixel_ops.integration_plugins.base import IntegrationContext
from pixel_ops.integration_plugins.registry import build_integration_runtime
from pixel_ops.outputs import GifOutput, PreviewOutput, TURZXOutput, WindowOutput
from pixel_ops.outputs.base import DisplayOutput
from pixel_ops.plugins.ai.plugin import build_ai_plugin
from pixel_ops.plugins.registry import available_plugins, get_plugin
from pixel_ops.render.splash import render_splash, splash_frame_count, splash_seconds

APP_DIR = Path(__file__).resolve().parent


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
    runtime_config = load_runtime_config()
    display_cfg = load_config(APP_DIR / "config/display.json")["display"]
    people_cfg = load_config(APP_DIR / "config/people.json")["people"]
    plugin_cfg = plugin.load_config(plugin_dir, load_config)
    config_watcher = ConfigWatcher(
        lambda: [
            APP_DIR / "config/display.json",
            APP_DIR / "config/people.json",
            APP_DIR / "config/integrations.json",
            plugin_dir / "game.json",
            plugin_dir / "pokemon.json",
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

    def build_runtime_app():
        nonlocal integration_runtime
        current_display_cfg = load_config(APP_DIR / "config/display.json")["display"]
        current_people_cfg = load_config(APP_DIR / "config/people.json")["people"]
        current_plugin_cfg = plugin.load_config(plugin_dir, load_config)
        current_events_cfg = plugin.event_config(current_plugin_cfg)
        current_calendar_enabled = any(name in integration_runtime.loaded_plugins for name in ("ics", "google_calendar"))
        current_event_sources = [
            MockEventSource(enabled=env_bool("PIXEL_OPS_MOCK_EVENTS", bool(current_events_cfg.get("mock_events", False)))),
            *integration_runtime.event_sources,
        ]
        return plugin.build_app(
            args=args,
            root_dir=ROOT_DIR,
            display_cfg=current_display_cfg,
            config=current_plugin_cfg,
            width=width,
            height=height,
            fps=fps,
            people_config=current_people_cfg,
            next_event=lambda now: next_event(now, integration_runtime.calendar_paths, current_calendar_enabled),
            pull_request_source=integration_runtime.pull_request_source,
            weather_source=integration_runtime.weather_source,
            ai_plugin=build_ai_plugin(current_display_cfg.get("ai", {})),
            event_sources=current_event_sources,
        )

    app = build_runtime_app()

    def maybe_reload_app(current_app):
        nonlocal integration_runtime, runtime_config
        if not config_watcher.changed():
            return current_app
        try:
            next_runtime_config = load_runtime_config()
            if next_runtime_config != runtime_config:
                integration_runtime.close()
                integration_runtime = build_integration_runtime_from_config(next_runtime_config)
                runtime_config = next_runtime_config
            return build_runtime_app()
        except Exception as error:
            print(f"[pixel-ops config] hot reload failed: {type(error).__name__}: {error}", file=sys.stderr)
            return current_app

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
                app = maybe_reload_app(app)
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
            app = maybe_reload_app(app)
            now = datetime.now(ZoneInfo(primary_tz))
            output.send(app.render_frame(now))
            elapsed = time.perf_counter() - loop_started
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        integration_runtime.close()
        output.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
