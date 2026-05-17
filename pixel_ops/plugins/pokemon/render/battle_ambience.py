from __future__ import annotations

from PIL import Image, ImageDraw

from pixel_ops.plugins.pokemon.game.social_weather import WorldMoodState


def apply_battle_ambience(background: Image.Image, state: WorldMoodState | None) -> Image.Image:
    if state is None or not state.meeting_type:
        return background
    tint = {
        "incident_call": ((32, 24, 72), 0.20),
        "one_on_one": ((96, 176, 144), 0.10),
        "retro": ((192, 104, 64), 0.12),
        "architecture": ((96, 80, 176), 0.14),
        "deploy": ((224, 104, 48), 0.13),
        "sprint_review": ((96, 96, 144), 0.11),
    }.get(state.meeting_type, ((88, 80, 144), 0.10))
    img = Image.blend(background, Image.new("RGB", background.size, tint[0]), tint[1])
    draw = ImageDraw.Draw(img)
    _draw_arena_marks(draw, img.size, state)
    return img


def _draw_arena_marks(draw: ImageDraw.ImageDraw, size: tuple[int, int], state: WorldMoodState) -> None:
    width, height = size
    color = (232, 216, 144) if state.meeting_type in ("deploy", "retro") else (184, 184, 232)
    for inset in (18, 30):
        draw.arc((inset, 18, width - inset, height - 22), 18, 162, fill=color, width=1)
    if state.meeting_type == "incident_call":
        for x in range(28, width, 54):
            draw.line((x, 26, x + 10, 36), fill=(224, 88, 96), width=1)
