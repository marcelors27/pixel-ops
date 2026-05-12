from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

APP_DIR = Path(__file__).resolve().parents[1]
PIXEL_FONT = APP_DIR / "assets/fonts/BoutiqueBitmap9x9/BoutiqueBitmap9x9_Bold_1.92.ttf"
MONO_FONT = APP_DIR / "assets/fonts/jetbrains-mono/JetBrainsMono-Bold.ttf"


def font(size: int) -> ImageFont.ImageFont:
    for path in (PIXEL_FONT, MONO_FONT):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()
