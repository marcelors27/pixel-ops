from __future__ import annotations

from pathlib import Path

from PIL import Image

from pixel_ops.outputs.base import DisplayOutput


class GifOutput(DisplayOutput):
    """Collects frames and writes an animated GIF when stopped."""

    def __init__(self, output_path: Path, fps: int):
        self.output_path = output_path
        self.fps = fps
        self._frames: list[Image.Image] = []

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, frame: Image.Image) -> None:
        self._frames.append(frame.copy())

    def stop(self) -> None:
        if not self._frames:
            return
        self._frames[0].save(
            self.output_path,
            save_all=True,
            append_images=self._frames[1:],
            duration=max(1, int(1000 / self.fps)),
            loop=0,
        )
        print(self.output_path)
