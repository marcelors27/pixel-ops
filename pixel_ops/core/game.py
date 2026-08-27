from __future__ import annotations

from typing import Protocol

from PIL import Image

from pixel_ops.events.base import WorkEvent
from pixel_ops.events.platform import PixelOpsEvent


class GameEngine(Protocol):
    """A replaceable visual world that owns its projections and rendering."""

    name: str

    def consume(self, event: PixelOpsEvent | WorkEvent) -> None: ...

    def render(self) -> Image.Image: ...

    def set_presentation(self, layout: dict, layout_theme: str) -> None: ...

    def close(self) -> None: ...
