from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

APP_DIR = Path(__file__).resolve().parents[1]
PIXEL_FONT = APP_DIR / "assets/fonts/BoutiqueBitmap9x9/BoutiqueBitmap9x9_Bold_1.92.ttf"
MONO_FONT = APP_DIR / "assets/fonts/jetbrains-mono/JetBrainsMono-Bold.ttf"
FONT_AWESOME_SOLID = APP_DIR / "assets/fonts/fontawesome/fa-solid-900.ttf"


def font(size: int) -> ImageFont.ImageFont:
    for path in (PIXEL_FONT, MONO_FONT):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def icon_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_AWESOME_SOLID), size)
    except OSError:
        return font(size)
