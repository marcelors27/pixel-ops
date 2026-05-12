from __future__ import annotations

from pathlib import Path

from PIL import Image

from pixel_ops.outputs.base import DisplayOutput


class PreviewOutput(DisplayOutput):
    """Writes preview PNG frames locally without requiring display hardware."""

    def __init__(self, output_path: Path, sequence: bool = False):
        self.output_path = output_path
        self.sequence = sequence
        self._index = 0

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, frame: Image.Image) -> None:
        path = self.output_path
        if self.sequence:
            path = self.output_path.with_name(f"{self.output_path.stem}_{self._index:04d}{self.output_path.suffix}")
        frame.save(path)
        self._index += 1

    def stop(self) -> None:
        print(self.output_path)
