from __future__ import annotations

from pixel_ops.plugins.pokemon.game.social_weather import SocialWeatherSystem, WorldMoodState


class MoodEngine(SocialWeatherSystem):
    """Compatibility name for the global world mood engine."""


__all__ = ["MoodEngine", "WorldMoodState"]
