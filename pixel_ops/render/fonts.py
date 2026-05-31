from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from math import sqrt
from pathlib import Path

from PIL import ImageFont

APP_DIR = Path(__file__).resolve().parents[1]
PIXEL_FONT = APP_DIR / "assets/fonts/BoutiqueBitmap9x9/BoutiqueBitmap9x9_Bold_1.92.ttf"
MONO_FONT = APP_DIR / "assets/fonts/jetbrains-mono/JetBrainsMono-Bold.ttf"
FONT_AWESOME_SOLID = APP_DIR / "assets/fonts/fontawesome/fa-solid-900.ttf"
BASE_CANVAS_AREA = 320 * 480
MAX_CANVAS_FONT_SCALE = 1.25

_FONT_SCALE: ContextVar[float] = ContextVar("pixel_ops_font_scale", default=1.0)


def font(size: int) -> ImageFont.ImageFont:
    return _load_font(_scaled_font_size(size), icon=False)


def icon_font(size: int) -> ImageFont.ImageFont:
    return _load_font(_scaled_font_size(size), icon=True)


def scaled_px(value: int | float, *, minimum: int = 1) -> int:
    return max(minimum, int(round(float(value) * _FONT_SCALE.get())))


def canvas_font_scale(width: int, height: int) -> float:
    area_scale = sqrt(max(1, width * height) / BASE_CANVAS_AREA)
    return min(MAX_CANVAS_FONT_SCALE, max(1.0, area_scale))


@contextmanager
def font_scale_for_canvas(width: int, height: int) -> Iterator[None]:
    token = _FONT_SCALE.set(canvas_font_scale(width, height))
    try:
        yield
    finally:
        _FONT_SCALE.reset(token)


def _scaled_font_size(size: int) -> int:
    return max(1, int(round(size * _FONT_SCALE.get())))


@lru_cache(maxsize=96)
def _load_font(size: int, icon: bool = False) -> ImageFont.ImageFont:
    if icon:
        try:
            return ImageFont.truetype(str(FONT_AWESOME_SOLID), size)
        except OSError:
            pass
    for path in (PIXEL_FONT, MONO_FONT):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()
