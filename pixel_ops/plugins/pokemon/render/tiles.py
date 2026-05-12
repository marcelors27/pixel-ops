from __future__ import annotations

from PIL import Image, ImageDraw

from pixel_ops.plugins.pokemon.game.day_night import DayNightPalette


TILE = 16


def _tile(fill: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (TILE, TILE), fill)


def make_tile(name: str, pal: DayNightPalette) -> Image.Image:
    img = _tile(pal.grass)
    draw = ImageDraw.Draw(img)
    if name == "grass":
        img.paste(pal.grass, (0, 0, TILE, TILE))
        for x, y in ((2, 12), (6, 7), (11, 11), (14, 5)):
            draw.line((x, y, x + 2, y - 4), fill=pal.grass_dark)
    elif name == "tall_grass":
        img.paste(pal.grass, (0, 0, TILE, TILE))
        for x in range(1, TILE, 4):
            draw.line((x, 14, x + 2, 7), fill=pal.grass_dark)
            draw.line((x + 2, 14, x, 9), fill=pal.light)
    elif name == "path":
        img.paste(pal.path, (0, 0, TILE, TILE))
        for x in range(0, TILE, 4):
            draw.point((x, 4), fill=pal.path_dark)
            draw.point((x + 1, 11), fill=pal.path_dark)
    elif name == "pavement":
        img.paste((168, 168, 176), (0, 0, TILE, TILE))
        draw.line((0, 0, 15, 0), fill=(112, 112, 128))
        draw.line((0, 8, 15, 8), fill=(128, 128, 144))
        draw.line((8, 0, 8, 15), fill=(128, 128, 144))
    elif name == "water":
        img.paste(pal.water, (0, 0, TILE, TILE))
        draw.arc((0, 4, 10, 12), 0, 180, fill=(152, 216, 248))
        draw.arc((7, 1, 17, 9), 0, 180, fill=(152, 216, 248))
    return img


def draw_tree(draw: ImageDraw.ImageDraw, x: int, y: int, pal: DayNightPalette) -> None:
    draw.rectangle((x + 13, y + 25, x + 20, y + 40), fill=(104, 72, 48))
    draw.rectangle((x + 4, y + 13, x + 29, y + 30), fill=pal.tree_dark)
    draw.rectangle((x + 8, y + 5, x + 25, y + 22), fill=pal.tree)
    draw.rectangle((x + 1, y + 20, x + 32, y + 28), fill=pal.tree)


def draw_house(draw: ImageDraw.ImageDraw, x: int, y: int, pal: DayNightPalette, center: bool = False) -> None:
    roof = (232, 64, 72) if center else pal.roof
    draw.rectangle((x + 8, y + 16, x + 58, y + 50), fill=pal.wall, outline=pal.ink)
    draw.polygon([(x, y + 18), (x + 33, y), (x + 66, y + 18)], fill=roof, outline=pal.ink)
    draw.rectangle((x + 28, y + 31, x + 39, y + 50), fill=(96, 72, 56), outline=pal.ink)
    draw.rectangle((x + 13, y + 25, x + 24, y + 35), fill=pal.water, outline=pal.ink)
    if center:
        draw.rectangle((x + 24, y + 17, x + 42, y + 27), fill=(248, 248, 248), outline=pal.ink)
        draw.rectangle((x + 31, y + 19, x + 35, y + 25), fill=pal.red)
        draw.rectangle((x + 28, y + 21, x + 38, y + 23), fill=pal.red)


def draw_lamp(draw: ImageDraw.ImageDraw, x: int, y: int, pal: DayNightPalette) -> None:
    draw.rectangle((x + 6, y + 14, x + 8, y + 38), fill=pal.ink)
    draw.rectangle((x + 2, y + 8, x + 12, y + 16), fill=pal.light, outline=pal.ink)
    if pal.phase == "night":
        draw.ellipse((x - 7, y - 1, x + 21, y + 27), outline=pal.light)
