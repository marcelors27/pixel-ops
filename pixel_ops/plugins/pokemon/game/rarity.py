from __future__ import annotations

import random

from pixel_ops.events.base import EventPriority


RARITY_BY_PRIORITY = {
    EventPriority.LOW: ("common", "common", "medium"),
    EventPriority.MEDIUM: ("common", "medium", "medium", "high"),
    EventPriority.HIGH: ("medium", "high", "high", "critical"),
    EventPriority.CRITICAL: ("high", "critical", "critical"),
}

RARITY_POKEMON = {
    "common": (16, 19, 21, 41, 43, 46, 48, 50),
    "medium": (25, 37, 58, 63, 66, 74, 81, 92, 123),
    "high": (59, 65, 94, 95, 131, 143, 149),
    "critical": (144, 145, 146, 150, 151),
}


def rarity_for_priority(priority: EventPriority, rng: random.Random) -> str:
    options = RARITY_BY_PRIORITY.get(priority, RARITY_BY_PRIORITY[EventPriority.MEDIUM])
    return rng.choice(options)
