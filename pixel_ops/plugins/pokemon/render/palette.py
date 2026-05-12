DAY = {
    "bg": (112, 184, 240),
    "ground": (88, 168, 88),
    "panel": (248, 248, 224),
    "panel_shadow": (72, 88, 112),
    "ink": (32, 40, 56),
    "blue": (48, 104, 184),
    "red": (216, 56, 56),
    "yellow": (248, 200, 48),
    "green": (72, 184, 96),
}

EVENING = {**DAY, "bg": (224, 144, 104), "ground": (96, 144, 80), "panel": (248, 232, 200)}
NIGHT = {**DAY, "bg": (24, 40, 88), "ground": (48, 96, 72), "panel": (216, 224, 240), "ink": (16, 24, 40)}
DAWN = {**DAY, "bg": (96, 104, 168), "ground": (64, 120, 88), "panel": (232, 224, 216)}


def palette_for_hour(hour: int) -> dict[str, tuple[int, int, int]]:
    if 6 <= hour < 12:
        return DAY
    if 12 <= hour < 18:
        return DAY
    if 18 <= hour < 22:
        return EVENING
    if 4 <= hour < 6:
        return DAWN
    return NIGHT
