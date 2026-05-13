from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageSequence
import yaml

from pixel_ops.render.animation import SpriteAnimation

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
POKEBALL_SHEET = ASSET_DIR / "Game Boy Advance - Pokemon FireRed _ LeafGreen - Battle Effects - Poke Balls.png"
PLAYER_SHEET = ASSET_DIR / "Game Boy Advance - Pokemon FireRed _ LeafGreen - Playable Characters - Player Sprites.png"
POKEBALL_TRANSPARENT = (255, 166, 166)
PLAYER_TRANSPARENT = (255, 127, 39)
_POKEBALL_FRAMES: list[Image.Image] | None = None
_BATTLE_ASH_FRAMES: list[Image.Image] | None = None


def scale_sprite(sprite: Image.Image, scale: int = 3) -> Image.Image:
    return sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)


def ash_frame(step: int) -> Image.Image:
    img = Image.new("RGBA", (16, 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cap = (220, 48, 48, 255)
    skin = (248, 184, 136, 255)
    blue = (48, 96, 192, 255)
    dark = (32, 40, 56, 255)
    shoe = (64, 56, 48, 255)
    d.rectangle((4, 1, 11, 3), fill=cap)
    d.rectangle((6, 4, 10, 7), fill=skin)
    d.point((10, 5), fill=dark)
    d.rectangle((5, 8, 11, 13), fill=blue)
    d.rectangle((3, 9, 5, 12), fill=skin)
    d.rectangle((11, 9, 13, 12), fill=skin)
    if step % 2 == 0:
        d.rectangle((5, 14, 7, 18), fill=dark)
        d.rectangle((10, 14, 12, 17), fill=dark)
        d.rectangle((4, 18, 7, 19), fill=shoe)
        d.rectangle((10, 17, 13, 18), fill=shoe)
    else:
        d.rectangle((4, 14, 6, 17), fill=dark)
        d.rectangle((9, 14, 11, 18), fill=dark)
        d.rectangle((3, 17, 6, 18), fill=shoe)
        d.rectangle((9, 18, 12, 19), fill=shoe)
    return img


def ash_direction_frame(direction: str, step: int) -> Image.Image:
    if direction in ("right", "left"):
        frame = ash_frame(step)
        if direction == "left":
            return frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return frame

    img = Image.new("RGBA", (16, 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cap = (220, 48, 48, 255)
    skin = (248, 184, 136, 255)
    blue = (48, 96, 192, 255)
    dark = (32, 40, 56, 255)
    shoe = (64, 56, 48, 255)
    if direction == "up":
        d.rectangle((4, 1, 11, 5), fill=cap)
        d.rectangle((5, 6, 11, 13), fill=blue)
        d.rectangle((3, 8, 5, 12), fill=skin)
        d.rectangle((11, 8, 13, 12), fill=skin)
    else:
        d.rectangle((4, 1, 11, 4), fill=cap)
        d.rectangle((5, 5, 11, 8), fill=skin)
        d.point((6, 6), fill=dark)
        d.point((10, 6), fill=dark)
        d.rectangle((5, 9, 11, 14), fill=blue)
        d.rectangle((3, 9, 5, 13), fill=skin)
        d.rectangle((11, 9, 13, 13), fill=skin)
    if step % 2 == 0:
        d.rectangle((5, 14, 7, 18), fill=dark)
        d.rectangle((10, 14, 12, 18), fill=dark)
        d.rectangle((4, 18, 7, 19), fill=shoe)
        d.rectangle((10, 18, 13, 19), fill=shoe)
    else:
        d.rectangle((4, 14, 6, 18), fill=dark)
        d.rectangle((9, 14, 11, 18), fill=dark)
        d.rectangle((3, 18, 6, 19), fill=shoe)
        d.rectangle((9, 18, 12, 19), fill=shoe)
    return img


@dataclass(frozen=True)
class SpriteSheetSpec:
    path: Path
    frame_width: int
    frame_height: int
    margin: int = 0
    spacing: int = 0
    transparent_color: tuple[int, int, int] | None = None


def _transparent_color(value: Any) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError("transparent_color must be a list like [r, g, b]")
    return int(value[0]), int(value[1]), int(value[2])


def _apply_transparency(frame: Image.Image, color: tuple[int, int, int] | None) -> Image.Image:
    rgba = frame.convert("RGBA")
    if color is None:
        return rgba

    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            if a and (r, g, b) == color:
                pixels[x, y] = (r, g, b, 0)
    return rgba


def load_spritesheet_frames(spec: SpriteSheetSpec) -> list[Image.Image]:
    with Image.open(spec.path) as image:
        sheet = image.convert("RGBA")

    frames: list[Image.Image] = []
    y = spec.margin
    while y + spec.frame_height <= sheet.height:
        x = spec.margin
        while x + spec.frame_width <= sheet.width:
            box = (x, y, x + spec.frame_width, y + spec.frame_height)
            frames.append(_apply_transparency(sheet.crop(box), spec.transparent_color))
            x += spec.frame_width + spec.spacing
        y += spec.frame_height + spec.spacing
    return frames


def load_spritesheet_animation(
    spec: SpriteSheetSpec,
    frame_indexes: list[int] | None = None,
    boxes: list[list[int]] | None = None,
    fps: int = 6,
    scale: int = 3,
    flip_x: bool = False,
    loop: bool = True,
) -> SpriteAnimation:
    if boxes:
        with Image.open(spec.path) as image:
            sheet = image.convert("RGBA")
        selected = [
            _apply_transparency(sheet.crop((int(x), int(y), int(x) + int(w), int(y) + int(h))), spec.transparent_color)
            for x, y, w, h in boxes
        ]
    else:
        frames = load_spritesheet_frames(spec)
        if frame_indexes is None:
            selected = frames
        else:
            selected = [frames[index] for index in frame_indexes if 0 <= index < len(frames)]
    if not selected:
        raise ValueError(f"No frames selected from {spec.path}")
    if flip_x:
        selected = [frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in selected]
    if scale != 1:
        selected = [scale_sprite(frame, scale) for frame in selected]
    return SpriteAnimation(tuple(selected), fps=fps, loop=loop)


class AshSpriteSet:
    def __init__(self, asset_dir: Path, scene_fps: int = 12, require_local: bool = False):
        self.asset_dir = asset_dir
        self.scene_fps = scene_fps
        self.animations: dict[str, SpriteAnimation] = {}
        self.scale = 3
        self.using_fallback = False
        self.require_local = require_local
        self._load()

    def _load(self) -> None:
        manifest = self.asset_dir / "manifest.yaml"
        if manifest.exists():
            self._load_manifest(manifest)
        else:
            self._load_convention_files()

        if "walk_right" not in self.animations:
            if self.require_local:
                raise FileNotFoundError(
                    f"No Ash spritesheet found in {self.asset_dir}. "
                    "Add manifest.yaml or walk_right.png/idle.png/catch.png."
                )
            self.using_fallback = True
            self.animations["walk_right"] = SpriteAnimation(
                (scale_sprite(ash_frame(0), self.scale), scale_sprite(ash_frame(1), self.scale)),
                fps=4,
            )
        if "idle" not in self.animations:
            self.animations["idle"] = SpriteAnimation((self.animations["walk_right"].first_frame,), fps=1)
        if "catch" not in self.animations:
            self.animations["catch"] = self.animations["walk_right"]
        self._ensure_directional_animations()

    def _ensure_directional_animations(self) -> None:
        walk_right = self.animations["walk_right"]
        if "walk_left" not in self.animations:
            self.animations["walk_left"] = SpriteAnimation(
                tuple(frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in walk_right.frames),
                fps=walk_right.fps,
                loop=walk_right.loop,
            )
        for direction in ("up", "down"):
            key = f"walk_{direction}"
            if key not in self.animations:
                self.animations[key] = SpriteAnimation(
                    tuple(scale_sprite(ash_direction_frame(direction, step), self.scale) for step in range(4)),
                    fps=walk_right.fps,
                )
        for direction in ("left", "up", "down"):
            idle_key = f"idle_{direction}"
            walk_key = f"walk_{direction}"
            if idle_key not in self.animations:
                self.animations[idle_key] = SpriteAnimation((self.animations[walk_key].first_frame,), fps=1)
        if "idle_right" not in self.animations:
            self.animations["idle_right"] = self.animations["idle"]

    def _load_manifest(self, manifest: Path) -> None:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        self.scale = int(data.get("scale", self.scale))
        default_frame_width = int(data.get("frame_width", 16))
        default_frame_height = int(data.get("frame_height", 20))
        default_margin = int(data.get("margin", 0))
        default_spacing = int(data.get("spacing", 0))
        default_transparent = _transparent_color(data.get("transparent_color"))

        for name, animation in (data.get("animations") or {}).items():
            file_name = animation["file"]
            spec = SpriteSheetSpec(
                path=self.asset_dir / file_name,
                frame_width=int(animation.get("frame_width", default_frame_width)),
                frame_height=int(animation.get("frame_height", default_frame_height)),
                margin=int(animation.get("margin", default_margin)),
                spacing=int(animation.get("spacing", default_spacing)),
                transparent_color=_transparent_color(animation.get("transparent_color")) or default_transparent,
            )
            self.animations[name] = load_spritesheet_animation(
                spec,
                frame_indexes=animation.get("frames"),
                boxes=animation.get("boxes"),
                fps=int(animation.get("fps", 6)),
                scale=int(animation.get("scale", self.scale)),
                flip_x=bool(animation.get("flip_x", False)),
                loop=bool(animation.get("loop", True)),
            )

    def _load_convention_files(self) -> None:
        for name, fps in (("walk_right", 6), ("idle", 2), ("catch", 8)):
            path = self.asset_dir / f"{name}.png"
            if not path.exists():
                continue
            with Image.open(path) as image:
                width, height = image.size
            frame_width = height if width % height == 0 else width
            spec = SpriteSheetSpec(path=path, frame_width=frame_width, frame_height=height)
            self.animations[name] = load_spritesheet_animation(spec, fps=fps, scale=self.scale)

    def frame(self, name: str, scene_frame: int) -> Image.Image:
        animation = self.animations.get(name) or self.animations["walk_right"]
        return animation.frame_at(scene_frame, self.scene_fps)


def pokemon_blob(number: int, step: int) -> Image.Image:
    img = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    colors = [
        (248, 208, 64, 255), (96, 200, 120, 255), (96, 160, 232, 255),
        (232, 104, 88, 255), (184, 120, 224, 255), (216, 160, 80, 255),
    ]
    body = colors[number % len(colors)]
    y = 1 if step % 2 else 0
    d.ellipse((3, 4 + y, 15, 16 + y), fill=body, outline=(32, 40, 56, 255))
    d.ellipse((6, 1 + y, 12, 8 + y), fill=body, outline=(32, 40, 56, 255))
    d.point((8, 4 + y), fill=(0, 0, 0, 255))
    d.point((11, 4 + y), fill=(0, 0, 0, 255))
    if number == 25:
        d.polygon([(4, 3 + y), (1, 0 + y), (5, 5 + y)], fill=body, outline=(32, 40, 56, 255))
        d.polygon([(13, 3 + y), (17, 0 + y), (12, 5 + y)], fill=body, outline=(32, 40, 56, 255))
    return img


def pokeball(step: int) -> Image.Image:
    frames = _load_pokeball_frames()
    if frames:
        return frames[step % len(frames)]

    img = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    offset = 1 if step % 2 else 0
    d.ellipse((1, 1 + offset, 12, 12 + offset), fill=(248, 248, 248, 255), outline=(32, 40, 56, 255))
    d.pieslice((1, 1 + offset, 12, 12 + offset), 180, 360, fill=(224, 48, 48, 255))
    d.line((1, 7 + offset, 12, 7 + offset), fill=(32, 40, 56, 255))
    d.ellipse((5, 5 + offset, 8, 8 + offset), fill=(248, 248, 248, 255), outline=(32, 40, 56, 255))
    return img


def battle_ash_frame(step: int) -> Image.Image:
    frames = _load_battle_ash_frames()
    if frames:
        return frames[min(step, len(frames) - 1)]
    return scale_sprite(ash_frame(step), 3)


def _load_battle_ash_frames() -> list[Image.Image]:
    global _BATTLE_ASH_FRAMES
    if _BATTLE_ASH_FRAMES is not None:
        return _BATTLE_ASH_FRAMES
    _BATTLE_ASH_FRAMES = []
    if not PLAYER_SHEET.exists():
        return _BATTLE_ASH_FRAMES

    boxes = [
        (8, 225, 72, 280),
        (73, 225, 137, 280),
        (139, 225, 202, 280),
        (205, 225, 267, 280),
        (269, 225, 332, 280),
    ]
    with Image.open(PLAYER_SHEET) as image:
        sheet = image.convert("RGBA")
    for box in boxes:
        frame = _apply_transparency(sheet.crop(box), PLAYER_TRANSPARENT)
        if frame.getbbox():
            _BATTLE_ASH_FRAMES.append(frame)
    return _BATTLE_ASH_FRAMES


def _load_pokeball_frames() -> list[Image.Image]:
    global _POKEBALL_FRAMES
    if _POKEBALL_FRAMES is not None:
        return _POKEBALL_FRAMES
    _POKEBALL_FRAMES = []
    if not POKEBALL_SHEET.exists():
        return _POKEBALL_FRAMES

    with Image.open(POKEBALL_SHEET) as image:
        sheet = image.convert("RGBA")
    frame = _apply_transparency(sheet.crop((32, 18, 48, 34)), POKEBALL_TRANSPARENT)
    if frame.getbbox():
        _POKEBALL_FRAMES.append(frame)
    return _POKEBALL_FRAMES


class PokemonSpriteStore:
    def __init__(self):
        self._frames: dict[Path, list[Image.Image]] = {}

    def sprite_for(self, path: Path | None, number: int, step: int, scale: int = 2, loop: bool = True) -> Image.Image:
        if path is None or not path.exists():
            return scale_sprite(pokemon_blob(number, step), scale)

        frames = self._frames.get(path)
        if frames is None:
            try:
                with Image.open(path) as image:
                    frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(image)]
                    frames = [frame for frame in frames if frame.getbbox()]
            except OSError:
                frames = [pokemon_blob(number, step)]
            if not frames:
                frames = [pokemon_blob(number, step)]
            self._frames[path] = frames

        frame_index = step // 6
        if loop:
            frame_index %= len(frames)
        else:
            frame_index = min(frame_index, len(frames) - 1)
        frame = frames[frame_index]
        return scale_sprite(frame, scale)
