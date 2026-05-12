from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass
class AnimationClock:
    frame: int = 0

    def tick(self) -> int:
        self.frame += 1
        return self.frame


@dataclass(frozen=True)
class SpriteAnimation:
    frames: tuple[Image.Image, ...]
    fps: int = 6
    loop: bool = True

    def frame_at(self, scene_frame: int, scene_fps: int) -> Image.Image:
        if not self.frames:
            raise ValueError("SpriteAnimation requires at least one frame")

        index = int(scene_frame * max(1, self.fps) / max(1, scene_fps))
        if self.loop:
            index %= len(self.frames)
        else:
            index = min(index, len(self.frames) - 1)
        return self.frames[index]

    @property
    def first_frame(self) -> Image.Image:
        if not self.frames:
            raise ValueError("SpriteAnimation requires at least one frame")
        return self.frames[0]
