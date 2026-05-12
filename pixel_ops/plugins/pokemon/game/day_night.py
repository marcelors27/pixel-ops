from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DayNightPalette:
    phase: str
    sky_top: tuple[int, int, int]
    sky_bottom: tuple[int, int, int]
    grass: tuple[int, int, int]
    grass_dark: tuple[int, int, int]
    path: tuple[int, int, int]
    path_dark: tuple[int, int, int]
    roof: tuple[int, int, int]
    wall: tuple[int, int, int]
    tree: tuple[int, int, int]
    tree_dark: tuple[int, int, int]
    water: tuple[int, int, int]
    light: tuple[int, int, int]
    panel: tuple[int, int, int]
    panel_shadow: tuple[int, int, int]
    ink: tuple[int, int, int]
    red: tuple[int, int, int]
    yellow: tuple[int, int, int]
    green: tuple[int, int, int]
    blue: tuple[int, int, int]


MORNING = DayNightPalette(
    "morning", (128, 190, 238), (184, 220, 248), (88, 176, 88), (56, 128, 72),
    (216, 192, 128), (176, 152, 104), (216, 72, 72), (240, 224, 176),
    (64, 152, 80), (40, 104, 64), (72, 152, 216), (255, 232, 128),
    (248, 248, 224), (72, 88, 112), (32, 40, 56), (216, 56, 56),
    (248, 200, 48), (72, 184, 96), (48, 104, 184),
)
AFTERNOON = DayNightPalette(
    "afternoon", (230, 156, 96), (248, 204, 136), (96, 156, 72), (64, 112, 64),
    (224, 176, 104), (176, 132, 88), (200, 64, 64), (240, 216, 168),
    (72, 136, 72), (48, 96, 56), (64, 128, 184), (255, 224, 104),
    (248, 232, 200), (88, 80, 96), (32, 40, 56), (216, 56, 56),
    (248, 200, 48), (72, 168, 88), (64, 104, 168),
)
NIGHT = DayNightPalette(
    "night", (18, 28, 64), (44, 56, 104), (40, 88, 72), (24, 56, 56),
    (112, 104, 104), (72, 72, 88), (96, 56, 88), (128, 136, 160),
    (32, 88, 72), (16, 48, 56), (32, 72, 128), (248, 216, 96),
    (216, 224, 240), (40, 48, 80), (16, 24, 40), (216, 72, 88),
    (240, 196, 72), (80, 176, 104), (80, 120, 200),
)
DAWN = DayNightPalette(
    "dawn", (72, 88, 160), (152, 152, 208), (64, 128, 88), (40, 88, 72),
    (184, 160, 128), (128, 112, 104), (160, 72, 104), (216, 200, 184),
    (48, 112, 80), (32, 72, 64), (48, 104, 168), (248, 216, 112),
    (232, 224, 216), (64, 72, 104), (24, 32, 48), (208, 64, 88),
    (248, 200, 64), (72, 168, 104), (64, 104, 184),
)


def day_night_palette(hour: int) -> DayNightPalette:
    if 5 <= hour < 11:
        return MORNING
    if 11 <= hour < 18:
        return AFTERNOON
    if 18 <= hour < 22:
        return NIGHT
    if 4 <= hour < 5:
        return DAWN
    return NIGHT
