from __future__ import annotations

import os

from PIL import Image

from pixel_ops.outputs.base import DisplayOutput


class WindowOutput(DisplayOutput):
    """Renders frames into a desktop window for local monitoring."""

    def __init__(self, width: int, height: int, scale: int = 2, title: str = "Pixel OPs"):
        self.width = width
        self.height = height
        self.scale = max(1, scale)
        self.title = title
        self.pygame = None
        self.screen = None
        self.closed = False

    def start(self) -> None:
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
        except ImportError as error:
            raise RuntimeError("Window output requires pygame. Install dependencies with requirements.txt.") from error

        self.pygame = pygame
        pygame.init()
        pygame.display.set_caption(self.title)
        self.screen = pygame.display.set_mode((self.width * self.scale, self.height * self.scale))

    def send(self, frame: Image.Image) -> None:
        if self.closed:
            raise RuntimeError("Window was closed.")
        if self.pygame is None or self.screen is None:
            raise RuntimeError("WindowOutput.start() must be called before send().")

        for event in self.pygame.event.get():
            if event.type == self.pygame.QUIT:
                self.closed = True
                raise RuntimeError("Window was closed.")

        display_frame = frame.convert("RGB")
        surface = self.pygame.image.frombuffer(display_frame.tobytes(), display_frame.size, "RGB")
        if self.scale != 1:
            surface = self.pygame.transform.scale(surface, (self.width * self.scale, self.height * self.scale))
        self.screen.blit(surface, (0, 0))
        self.pygame.display.flip()

    def stop(self) -> None:
        if self.pygame is not None:
            self.pygame.quit()
        self.pygame = None
        self.screen = None
