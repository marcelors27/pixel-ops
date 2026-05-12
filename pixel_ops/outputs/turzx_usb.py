from __future__ import annotations

from PIL import Image

from pixel_ops.hardware import UsbBulkRevA
from pixel_ops.outputs.base import DisplayOutput


class TURZXOutput(DisplayOutput):
    """USB output for TURZX/Turing Smart Screen displays."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._backend: UsbBulkRevA | None = None

    def start(self) -> None:
        self._backend = UsbBulkRevA(width=self.width, height=self.height)

    def send(self, frame: Image.Image) -> None:
        if self._backend is None:
            raise RuntimeError("TURZXOutput.start() must be called before send().")
        self._backend.display_image(frame)

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None
