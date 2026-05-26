from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pixel_ops.render.fonts import font
from pixel_ops.render.renderer import PixelRenderer

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
MENU_SHEET = ASSET_DIR / "Game Boy Advance - Pokemon FireRed _ LeafGreen - Battle Effects - HP Bars & In-battle Menu.png"
TEXT_BOX_TEXT_TOP_PADDING = 14
TEXT_BOX_LINE_HEIGHT = 18
TEXT_BOX_BOTTOM_PADDING = 18
TEXT_BOX_CURSOR_HEIGHT = 14

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
        text_x = x0 + 12
        text_y = y0 + TEXT_BOX_TEXT_TOP_PADDING
    else:
        PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
        text_fill = pal.ink
        cursor_fill = pal.red
        text_x = x0 + 12
        text_y = y0 + TEXT_BOX_TEXT_TOP_PADDING

    text_font = font(14)
    max_text_width = x1 - text_x - 26
    lines = wrap_text_lines(draw, text, text_font, max_text_width)

    y = text_y
    max_lines = text_box_visible_lines((x0, y0, x1, y1), text, text_y=text_y)
    visible_lines = _scroll_lines(lines, max_lines, frame)
    for line in visible_lines:
        draw.text((text_x, y), line, font=text_font, fill=text_fill)
        y += TEXT_BOX_LINE_HEIGHT
    if frame % 20 < 10:
        cursor_y = min(y1 - TEXT_BOX_CURSOR_HEIGHT - 4, y + 1)
        cursor_y = max(y0 + TEXT_BOX_TEXT_TOP_PADDING, cursor_y)
        draw.polygon([(x1 - 24, cursor_y), (x1 - 14, cursor_y + 7), (x1 - 24, cursor_y + 14)], fill=cursor_fill)


def _scroll_lines(lines: list[str], max_lines: int, frame: int) -> list[str]:
    start = scroll_line_start(lines, max_lines, frame)
    return lines[start : start + max_lines]


def scroll_line_start(lines: list[str], max_lines: int, frame: int) -> int:
    if len(lines) <= max_lines:
        return 0
    hold_frames = 8
    step_frames = 8
    cycle = hold_frames + (len(lines) - max_lines) * step_frames + hold_frames
    position = frame % max(1, cycle)
    if position < hold_frames:
        return 0
    return min(len(lines) - max_lines, (position - hold_frames) // step_frames + 1)


def wrap_text_lines(draw: ImageDraw.ImageDraw, text: str, text_font, max_text_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        current = ""
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
    return lines


def text_box_visible_lines(box: tuple[int, int, int, int], text: str, text_y: int | None = None) -> int:
    _, y0, _, y1 = box
    first_line_y = text_y if text_y is not None else y0 + TEXT_BOX_TEXT_TOP_PADDING
    available_height = max(0, y1 - first_line_y - TEXT_BOX_BOTTOM_PADDING)
    return max(1, available_height // TEXT_BOX_LINE_HEIGHT)
