from __future__ import annotations

from PIL import Image

from pixel_ops.hardware import UsbBulkRevA
from pixel_ops.outputs.base import DisplayOutput


class TURZXOutput(DisplayOutput):
    """USB output for TURZX/Turing Smart Screen displays."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.vid = 0x1A86
        self.pid = 0x5722
        self.timeout_ms = 5000
        self.serial_number = ""
        self.bus: int | None = None
        self.address: int | None = None
        self._backend: UsbBulkRevA | None = None

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict):
        output = cls(width=width, height=height)
        output.vid = _parse_int(cfg.get("vid", output.vid))
        output.pid = _parse_int(cfg.get("pid", output.pid))
        output.timeout_ms = int(cfg.get("timeout_ms", output.timeout_ms))
        output.serial_number = str(cfg.get("serial_number") or "")
        # USB addresses are assigned dynamically on every reconnect. A serial
        # number is stable and must take precedence when the device exposes one.
        output.bus = None if output.serial_number else _optional_int(cfg.get("bus"))
        output.address = None if output.serial_number else _optional_int(cfg.get("address"))
        return output

    def start(self) -> None:
        self._backend = UsbBulkRevA(
            width=self.width,
            height=self.height,
            vid=self.vid,
            pid=self.pid,
            timeout_ms=self.timeout_ms,
            serial_number=self.serial_number,
            bus=self.bus,
            address=self.address,
        )

    def send(self, frame: Image.Image) -> None:
        if self._backend is None:
            raise RuntimeError("TURZXOutput.start() must be called before send().")
        self._backend.display_image(frame)

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None


def _parse_int(value) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return _parse_int(value)
