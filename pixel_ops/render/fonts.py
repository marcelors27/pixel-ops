from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from io import BytesIO
from math import sqrt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


@lru_cache(maxsize=512)
def emoji_image(value: str, height: int) -> Image.Image | None:
    target_height = max(6, _scaled_font_size(height))
    rendered = _macos_emoji_image(value) or _pillow_emoji_image(value)
    if rendered is None:
        return None
    bounds = rendered.getbbox()
    if bounds:
        rendered = rendered.crop(bounds)
    if rendered.height <= 0:
        return None
    target_width = max(1, round(rendered.width * target_height / rendered.height))
    return rendered.resize((target_width, target_height), Image.Resampling.LANCZOS)


def _macos_emoji_image(value: str) -> Image.Image | None:
    try:
        from AppKit import NSAttributedString, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSFont, NSFontAttributeName, NSImage
        from Foundation import NSMakePoint

        text = NSAttributedString.alloc().initWithString_attributes_(
            value,
            {NSFontAttributeName: NSFont.fontWithName_size_("Apple Color Emoji", 32)},
        )
        size = text.size()
        image = NSImage.alloc().initWithSize_(size)
        image.lockFocus()
        text.drawAtPoint_(NSMakePoint(0, 0))
        image.unlockFocus()
        representation = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
        data = representation.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
        return Image.open(BytesIO(bytes(data))).convert("RGBA")
    except (ImportError, OSError, TypeError, ValueError, AttributeError):
        return None


def _pillow_emoji_image(value: str) -> Image.Image | None:
    candidates = (
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "C:/Windows/Fonts/seguiemj.ttf",
    )
    for path in candidates:
        try:
            emoji_font = ImageFont.truetype(path, 20)
            bounds = emoji_font.getbbox(value)
            width = max(20, bounds[2] - bounds[0])
            canvas = Image.new("RGBA", (width + 4, 24), (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((2, 1), value, font=emoji_font, embedded_color=True)
            return canvas
        except (OSError, TypeError, ValueError):
            continue
    return None


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
