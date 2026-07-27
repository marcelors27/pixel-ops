from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageOps

from pixel_ops.outputs.base import DisplayOutput


EINK_WIDTH = 250
EINK_HEIGHT = 122
EINK_ROW_BYTES = (EINK_WIDTH + 7) // 8
EINK_FRAME_BYTES = EINK_ROW_BYTES * EINK_HEIGHT


@dataclass(frozen=True)
class EInkFrame:
    payload: bytes
    digest: str


def encode_eink_frame(
    frame: Image.Image,
    *,
    width: int = EINK_WIDTH,
    height: int = EINK_HEIGHT,
    dither: bool = True,
    threshold: int = 160,
    invert: bool = False,
    accent_pattern: bool = True,
) -> EInkFrame:
    """Encode a PIL frame as row-aligned, MSB-first monochrome pixels.

    A set bit represents a black pixel. Each row is padded to a whole byte so
    the firmware can address pixels without depending on PIL's internal layout.
    """

    color = frame.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    resized = color.convert("L")
    if invert:
        resized = ImageOps.invert(resized)
    if dither:
        monochrome = resized.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        limit = max(0, min(255, int(threshold)))
        monochrome = resized.point(lambda value: 255 if value >= limit else 0, mode="1")

    pixels = monochrome.load()
    color_pixels = color.load()
    accent_mask = [
        [max(color_pixels[x, y]) - min(color_pixels[x, y]) >= 45 for x in range(width)]
        for y in range(height)
    ]
    accent_integral = [[0] * (width + 1) for _ in range(height + 1)]
    for y in range(height):
        row_total = 0
        for x in range(width):
            row_total += int(accent_mask[y][x])
            accent_integral[y + 1][x + 1] = accent_integral[y][x + 1] + row_total

    def dense_accent(x: int, y: int) -> bool:
        x0, y0 = max(0, x - 2), max(0, y - 2)
        x1, y1 = min(width, x + 3), min(height, y + 3)
        count = accent_integral[y1][x1] - accent_integral[y0][x1] - accent_integral[y1][x0] + accent_integral[y0][x0]
        return count * 5 >= (x1 - x0) * (y1 - y0) * 3

    row_bytes = (width + 7) // 8
    payload = bytearray(row_bytes * height)
    for y in range(height):
        row_offset = y * row_bytes
        for x in range(width):
            red, green, blue = color_pixels[x, y]
            is_accent = accent_pattern and accent_mask[y][x]
            is_yellow = is_accent and red >= 160 and green >= 120 and blue + 30 < min(red, green)
            if is_yellow:
                is_black = True
            elif is_accent and dense_accent(x, y):
                is_black = (x + y) % 4 < 2
            elif is_accent:
                is_black = True
            else:
                is_black = pixels[x, y] == 0
            if is_black:
                payload[row_offset + (x // 8)] |= 0x80 >> (x % 8)
    encoded = bytes(payload)
    return EInkFrame(payload=encoded, digest=hashlib.sha256(encoded).hexdigest())


class EInkHttpOutput(DisplayOutput):
    """Wi-Fi output for the Pixel OPs firmware running on a Heltec E213."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        width: int = EINK_WIDTH,
        height: int = EINK_HEIGHT,
        timeout_seconds: float = 10,
        min_frame_interval_seconds: float = 15,
        full_refresh_every: int = 10,
        dither: bool = False,
        threshold: int = 175,
        invert: bool = False,
        accent_pattern: bool = True,
        debug_frame_path: str = "",
    ):
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)
        self.width = int(width)
        self.height = int(height)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.min_frame_interval_seconds = max(0, float(min_frame_interval_seconds))
        self.full_refresh_every = max(1, int(full_refresh_every))
        self.dither = bool(dither)
        self.threshold = max(0, min(255, int(threshold)))
        self.invert = bool(invert)
        self.accent_pattern = bool(accent_pattern)
        self.debug_frame_path = str(debug_frame_path)
        self._session: requests.Session | None = None
        self._last_digest = ""
        self._last_send_at: float | None = None
        self._refresh_count = 0

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict) -> EInkHttpOutput:
        return cls(
            base_url=str(cfg.get("url") or cfg.get("base_url") or "http://pixelops-e213.local"),
            token=str(cfg.get("token") or ""),
            width=width,
            height=height,
            timeout_seconds=float(cfg.get("timeout_seconds", 10)),
            min_frame_interval_seconds=float(cfg.get("min_frame_interval_seconds", 15)),
            full_refresh_every=int(cfg.get("full_refresh_every", 10)),
            dither=bool(cfg.get("dither", False)),
            threshold=int(cfg.get("threshold", 175)),
            invert=bool(cfg.get("invert", False)),
            accent_pattern=bool(cfg.get("accent_pattern", True)),
            debug_frame_path=str(cfg.get("debug_frame_path") or ""),
        )

    def start(self) -> None:
        if not self.base_url:
            raise ValueError("E-ink output requires a non-empty URL.")
        if (self.width, self.height) != (EINK_WIDTH, EINK_HEIGHT):
            raise ValueError(f"Heltec E213 output requires {EINK_WIDTH}x{EINK_HEIGHT}, got {self.width}x{self.height}.")
        self._session = requests.Session()
        try:
            response = self._session.get(
                f"{self.base_url}/status",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            status = response.json()
            remote_size = (int(status.get("width", 0)), int(status.get("height", 0)))
            if remote_size != (self.width, self.height):
                raise RuntimeError(f"E-ink device reports {remote_size[0]}x{remote_size[1]}, expected {self.width}x{self.height}.")
        except Exception:
            self.stop()
            raise

    def send(self, frame: Image.Image) -> None:
        if self._session is None:
            raise RuntimeError("EInkHttpOutput.start() must be called before send().")

        if self.debug_frame_path:
            debug_path = Path(self.debug_frame_path)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            frame.save(debug_path)

        encoded = encode_eink_frame(
            frame,
            width=self.width,
            height=self.height,
            dither=self.dither,
            threshold=self.threshold,
            invert=self.invert,
            accent_pattern=self.accent_pattern,
        )
        if encoded.digest == self._last_digest:
            return

        now = time.monotonic()
        if self._last_send_at is not None and now - self._last_send_at < self.min_frame_interval_seconds:
            return

        refresh = "full" if self._refresh_count % self.full_refresh_every == 0 else "partial"
        headers = {
            **self._headers(),
            "Content-Type": "application/octet-stream",
            "X-Pixel-Ops-Width": str(self.width),
            "X-Pixel-Ops-Height": str(self.height),
            "X-Pixel-Ops-SHA256": encoded.digest,
            "X-Pixel-Ops-Refresh": refresh,
            "X-Pixel-Ops-Encoding": "base64",
        }
        response = self._session.post(
            f"{self.base_url}/frame",
            data=base64.b64encode(encoded.payload),
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        self._last_digest = encoded.digest
        self._last_send_at = now
        self._refresh_count += 1

    def stop(self) -> None:
        if self._session is not None:
            self._session.close()
        self._session = None
        self._last_digest = ""
        self._last_send_at = None
        self._refresh_count = 0

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}
