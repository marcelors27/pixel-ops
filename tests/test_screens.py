from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from pixel_ops.core.app import PixelOpsApp
from pixel_ops.core.screens import ScreenRotationController
from pixel_ops.core.screen_control import ScreenControlServer


def _config() -> dict:
    return {
        "layout": {"legacy": {"x": 0}},
        "layout_theme": "default",
        "screens": {
            "world": {"label": "World", "duration_seconds": 10, "layout": {"game": {"x": 0}}},
            "work": {"label": "Work", "duration_seconds": 20, "layout_theme": "terminal", "layout": {"tasks": {"x": 1}}},
        },
        "screen_rotation": {"enabled": True, "order": ["world", "work"], "default_duration_seconds": 30},
    }


def test_rotates_using_each_screen_duration() -> None:
    started = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    controller = ScreenRotationController(_config())
    controller.resume(started)

    assert controller.status(started)["active_screen_id"] == "world"
    assert controller.advance(started + timedelta(seconds=9)) is False
    assert controller.advance(started + timedelta(seconds=10)) is True
    assert controller.status(started + timedelta(seconds=10))["active_screen_id"] == "work"


def test_screen_can_select_a_hud_universe() -> None:
    config = _config()
    config["device"] = {"plugin": "pokemon"}
    config["screens"]["work"]["plugin"] = "spaceship"
    controller = ScreenRotationController(config)

    assert controller.presentation.plugin == "pokemon"
    controller.select("work")
    assert controller.presentation.plugin == "spaceship"
    assert controller.status()["screens"][1]["plugin"] == "spaceship"


def test_app_keeps_hud_engines_warm_and_renders_the_selected_one() -> None:
    class RecordingEngine:
        def __init__(self, name: str, color: str):
            self.name = name
            self.color = color
            self.events = []
            self.presentations = []

        def consume(self, event):
            self.events.append(event)

        def render(self):
            return Image.new("RGB", (2, 1), self.color)

        def set_presentation(self, layout, layout_theme):
            self.presentations.append((layout, layout_theme))

        def close(self):
            return None

    config = _config()
    config["device"] = {"plugin": "pokemon"}
    config["screens"]["work"]["plugin"] = "spaceship"
    controller = ScreenRotationController(config)
    pokemon = RecordingEngine("pokemon", "red")
    spaceship = RecordingEngine("spaceship", "blue")
    app = PixelOpsApp(pokemon, screens=controller)
    app.add_engine(spaceship)
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)

    controller.select("work", now=now)
    frame = app.render_frame(now)

    assert frame.getpixel((0, 0)) == (0, 0, 255)
    assert len(pokemon.events) == 1
    assert len(spaceship.events) == 1
    assert spaceship.presentations == [({"tasks": {"x": 1}}, "terminal")]


def test_manual_selection_pins_until_rotation_is_resumed() -> None:
    started = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    controller = ScreenRotationController(_config())
    controller.select("work", pinned=True, now=started)

    pinned = controller.status(started + timedelta(minutes=5))
    assert pinned["mode"] == "pinned"
    assert pinned["changes_at"] is None
    assert controller.advance(started + timedelta(minutes=5)) is False

    controller.resume(started + timedelta(minutes=5))
    resumed = controller.status(started + timedelta(minutes=5))
    assert resumed["mode"] == "automatic"
    assert resumed["remaining_ms"] == 20_000


def test_unknown_manual_screen_is_rejected() -> None:
    controller = ScreenRotationController(_config())
    with pytest.raises(KeyError):
        controller.select("missing")


def test_legacy_layout_becomes_non_rotating_default_screen() -> None:
    controller = ScreenRotationController({"layout": {"clock": {"x": 2}}, "layout_theme": "pokemon"})
    status = controller.status()

    assert status["active_screen_id"] == "default"
    assert status["changes_at"] is None
    assert controller.presentation.layout == {"clock": {"x": 2}}
    assert controller.presentation.layout_theme == "pokemon"


def test_loopback_control_selects_and_pins_a_screen() -> None:
    controller = ScreenRotationController(_config())
    server = ScreenControlServer(lambda: controller, port=0)
    server.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.port}/select",
            data=json.dumps({"screen_id": "work", "pinned": True}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            status = json.loads(response.read())
        assert status["active_screen_id"] == "work"
        assert status["mode"] == "pinned"
    finally:
        server.close()
