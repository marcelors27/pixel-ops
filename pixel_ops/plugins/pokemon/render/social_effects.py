from __future__ import annotations

from PIL import Image, ImageDraw

from pixel_ops.plugins.pokemon.game.social_weather import WorldMoodState


MOOD_TINTS = {
    "tense": ((48, 40, 88), 0.22),
    "charged": ((224, 104, 48), 0.13),
    "busy": ((248, 192, 64), 0.10),
    "celebrating": ((248, 196, 88), 0.12),
    "focused": ((88, 72, 160), 0.12),
    "reflective": ((176, 96, 64), 0.10),
    "restorative": ((104, 184, 152), 0.10),
    "calm": ((80, 144, 104), 0.06),
}


def draw_social_world_effects(
    img: Image.Image,
    box: tuple[int, int, int, int],
    state: WorldMoodState,
    frame: int,
) -> None:
    color, alpha = MOOD_TINTS.get(state.mood, ((96, 120, 160), 0.08))
    if state.intensity > 0:
        _blend_region(img, box, color, min(0.28, alpha * max(0.35, state.intensity)))

    draw = ImageDraw.Draw(img)
    if "crowd" in state.particles:
        _draw_crowd(draw, box, frame, state.intensity)
    if "sparks" in state.particles:
        _draw_sparks(draw, box, frame)
    if "lanterns" in state.particles:
        _draw_lanterns(draw, box, frame)
    if "embers" in state.particles:
        _draw_embers(draw, box, frame)
    if "glyphs" in state.particles:
        _draw_glyphs(draw, box, frame)


def _blend_region(img: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int], alpha: float) -> None:
    region = img.crop(box)
    tinted = Image.blend(region, Image.new("RGB", region.size, color), alpha)
    img.paste(tinted, box)


def _draw_crowd(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], frame: int, intensity: float) -> None:
    x0, y0, x1, y1 = box
    count = 3 + int(5 * min(1.0, intensity))
    base_y = y1 - 30
    for index in range(count):
        x = x0 + 18 + index * 36 + ((frame // 8 + index) % 2)
        if x >= x1 - 12:
            break
        y = base_y - (index % 3) * 9
        color = ((56, 72, 96), (72, 104, 112), (96, 80, 120))[index % 3]
        draw.rectangle((x, y + 5, x + 5, y + 12), fill=color)
        draw.rectangle((x + 1, y, x + 4, y + 4), fill=(232, 184, 136))


def _draw_sparks(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], frame: int) -> None:
    x0, y0, x1, y1 = box
    for index in range(9):
        x = x0 + 22 + ((index * 37 + frame * 3) % max(1, x1 - x0 - 44))
        y = y0 + 22 + ((index * 29 + frame * 5) % max(1, y1 - y0 - 58))
        if (frame + index) % 3 == 0:
            draw.line((x - 2, y, x + 2, y), fill=(248, 224, 96))
            draw.line((x, y - 2, x, y + 2), fill=(248, 224, 96))


def _draw_lanterns(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], frame: int) -> None:
    x0, y0, x1, _ = box
    glow = (248, 204, 96) if frame % 20 < 12 else (224, 160, 72)
    for x in range(x0 + 28, x1, 58):
        y = y0 + 26 + ((x // 58) % 2) * 14
        draw.line((x, y - 10, x, y - 1), fill=(88, 72, 72))
        draw.rectangle((x - 3, y, x + 3, y + 5), fill=glow, outline=(120, 80, 56))


def _draw_embers(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], frame: int) -> None:
    x0, y0, x1, y1 = box
    for index in range(8):
        x = x0 + 28 + (index * 31) % max(1, x1 - x0 - 56)
        y = y1 - 18 - ((frame + index * 9) % 54)
        draw.point((x, y), fill=(248, 136, 64))
        draw.point((x + 1, y), fill=(248, 200, 88))


def _draw_glyphs(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], frame: int) -> None:
    x0, y0, x1, _ = box
    color = (184, 176, 232) if frame % 24 < 12 else (128, 120, 184)
    for x in range(x0 + 36, x1 - 24, 72):
        y = y0 + 36 + ((x + frame) % 18)
        draw.rectangle((x, y, x + 7, y + 7), outline=color)
        draw.line((x + 2, y + 4, x + 5, y + 4), fill=color)
