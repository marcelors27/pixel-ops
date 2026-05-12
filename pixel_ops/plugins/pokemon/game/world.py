from __future__ import annotations

from dataclasses import dataclass


BIOMES = ("town", "route", "grass", "village", "center")


@dataclass
class World:
    speed_px: float = 1.4
    scroll_x: float = 0.0
    biome_index: int = 0
    frames_in_biome: int = 0
    biome_duration_frames: int = 180

    def tick(self, moving: bool = True) -> None:
        if moving:
            self.scroll_x += self.speed_px
        self.frames_in_biome += 1
        if self.frames_in_biome >= self.biome_duration_frames:
            self.frames_in_biome = 0
            self.biome_index = (self.biome_index + 1) % len(BIOMES)

    @property
    def biome(self) -> str:
        return BIOMES[self.biome_index]
