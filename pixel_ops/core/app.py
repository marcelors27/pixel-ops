from __future__ import annotations

from datetime import datetime

from PIL import Image

from pixel_ops.core.game import GameEngine
from pixel_ops.events.base import EventSource
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.core.screens import ScreenRotationController


class PixelOpsApp:
    """Hardware-neutral event pump for a selected game engine."""

    def __init__(self, engine: GameEngine, event_sources: list[EventSource] | None = None, screens: ScreenRotationController | None = None):
        self.engine = engine
        self.engines: dict[str, GameEngine] = {engine.name: engine}
        self.default_engine_name = engine.name
        self.event_sources = event_sources or []
        self.screens = screens
        self._presentation_revision = -1

    def render_frame(self, now: datetime) -> Image.Image:
        for source in self.event_sources:
            for event in source.poll(now):
                for engine in self.engines.values():
                    engine.consume(event)
        for engine in self.engines.values():
            engine.consume(PixelOpsEvent.tick(now))
        if self.screens is not None:
            self.screens.advance(now)
            status = self.screens.status(now)
            if status["revision"] != self._presentation_revision:
                presentation = self.screens.presentation
                self.engine = self.engines.get(presentation.plugin, self.engines[self.default_engine_name])
                self.engine.set_presentation(presentation.layout, presentation.layout_theme)
                self._presentation_revision = status["revision"]
        return self.engine.render()

    def add_engine(self, engine: GameEngine) -> None:
        self.engines[engine.name] = engine

    def close(self) -> None:
        for engine in self.engines.values():
            engine.close()
