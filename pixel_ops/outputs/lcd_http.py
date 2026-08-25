from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import requests
from PIL import Image

from pixel_ops.outputs.base import DisplayOutput


LCD_WIDTH = 172
LCD_HEIGHT = 320
LCD_FRAME_BYTES = LCD_WIDTH * LCD_HEIGHT * 2


@dataclass(frozen=True)
class LcdFrame:
    payload: bytes
    digest: str


def encode_lcd_frame(frame: Image.Image, *, width: int = LCD_WIDTH, height: int = LCD_HEIGHT) -> LcdFrame:
    """Resize a PIL frame and encode it as big-endian RGB565 pixels."""

    image = frame.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    payload = bytearray(width * height * 2)
    offset = 0
    for red, green, blue in image.getdata():
        pixel = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        payload[offset] = pixel >> 8
        payload[offset + 1] = pixel & 0xFF
        offset += 2
    encoded = bytes(payload)
    return LcdFrame(payload=encoded, digest=hashlib.sha256(encoded).hexdigest())


class LcdHttpOutput(DisplayOutput):
    """Color Wi-Fi output for the Waveshare ESP32-C6-LCD-1.47 firmware."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        width: int = LCD_WIDTH,
        height: int = LCD_HEIGHT,
        timeout_seconds: float = 5,
        min_frame_interval_seconds: float = 0.1,
    ):
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)
        self.width = int(width)
        self.height = int(height)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.min_frame_interval_seconds = max(0, float(min_frame_interval_seconds))
        self._session: requests.Session | None = None
        self._last_digest = ""
        self._last_sent_at = 0.0

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict) -> LcdHttpOutput:
        return cls(
            str(cfg.get("url") or "http://pixelops-lcd.local"),
            token=str(cfg.get("token") or ""),
            width=int(cfg.get("width", LCD_WIDTH)),
            height=int(cfg.get("height", LCD_HEIGHT)),
            timeout_seconds=float(cfg.get("timeout_seconds", 5)),
            min_frame_interval_seconds=float(cfg.get("min_frame_interval_seconds", 0.1)),
        )

    def start(self) -> None:
        self._session = requests.Session()
        try:
            response = self._session.get(
                f"{self.base_url}/status",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            self.stop()
            raise RuntimeError(f"LCD status check failed: {error}") from error

    def send(self, frame: Image.Image) -> None:
        if self._session is None:
            raise RuntimeError("LcdHttpOutput.start() must be called before send().")
        now = time.monotonic()
        if now - self._last_sent_at < self.min_frame_interval_seconds:
            return
        encoded = encode_lcd_frame(frame, width=self.width, height=self.height)
        if encoded.digest == self._last_digest:
            return
        try:
            response = self._session.post(
                f"{self.base_url}/frame",
                headers=self._headers(),
                files={"frame": ("frame.rgb565", encoded.payload, "application/octet-stream")},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(f"LCD frame send failed: {error}") from error
        self._last_digest = encoded.digest
        self._last_sent_at = now

    def stop(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}
