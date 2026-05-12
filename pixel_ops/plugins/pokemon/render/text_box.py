from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pixel_ops.render.fonts import font
from pixel_ops.render.renderer import PixelRenderer

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
MENU_SHEET = ASSET_DIR / "Game Boy Advance - Pokemon FireRed _ LeafGreen - Battle Effects - HP Bars & In-battle Menu.png"

_TEXT_BOX_FRAME: Image.Image | None = None


def _load_text_box_frame(size: tuple[int, int]) -> Image.Image | None:
    global _TEXT_BOX_FRAME
    if _TEXT_BOX_FRAME is None:
        if not MENU_SHEET.exists():
            return None
        with Image.open(MENU_SHEET) as sheet:
            # Blank battle message box from the FireRed/LeafGreen interface sheet.
            _TEXT_BOX_FRAME = sheet.convert("RGB").crop((297, 56, 535, 107))
    return _TEXT_BOX_FRAME.resize(size, Image.Resampling.NEAREST)


def draw_text_box(image: Image.Image, box: tuple[int, int, int, int], text: str, pal, frame: int) -> None:
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = box
    asset = _load_text_box_frame((x1 - x0, y1 - y0))
    if asset:
        image.paste(asset, (x0, y0))
        text_fill = (248, 248, 248)
        cursor_fill = (248, 248, 248)
        text_x = x0 + 16
        text_y = y0 + 15
    else:
        PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
        text_fill = pal.ink
        cursor_fill = pal.red
        text_x = x0 + 16
        text_y = y0 + 15

    text_font = font(16)
    words = text.split()
    lines: list[str] = []
    current = ""
    max_text_width = x1 - x0 - 38
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=text_font)[2] > max_text_width:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    y = text_y
    max_lines = max(2, (y1 - y0 - 30) // 21)
    for line in lines[:max_lines]:
        draw.text((text_x, y), line, font=text_font, fill=text_fill)
        y += 21
    if frame % 20 < 10:
        cursor_y = y1 - 25
        draw.polygon([(x1 - 24, cursor_y), (x1 - 14, cursor_y + 7), (x1 - 24, cursor_y + 14)], fill=cursor_fill)
