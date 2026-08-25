from __future__ import annotations

from datetime import datetime

from PIL import Image

from pixel_ops.core.game import GameEngine
from pixel_ops.events.base import EventSource
from pixel_ops.events.platform import PixelOpsEvent


class PixelOpsApp:
    """Hardware-neutral event pump for a selected game engine."""

    def __init__(self, engine: GameEngine, event_sources: list[EventSource] | None = None):
        self.engine = engine
        self.event_sources = event_sources or []

    def render_frame(self, now: datetime) -> Image.Image:
        for source in self.event_sources:
            for event in source.poll(now):
                self.engine.consume(event)
        self.engine.consume(PixelOpsEvent.tick(now))
        return self.engine.render()

    def close(self) -> None:
        self.engine.close()
