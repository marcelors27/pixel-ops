#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from PIL import Image

APP_DIR = Path(__file__).resolve().parents[1]
ASH_DIR = APP_DIR / "assets/sprites/ash"


def close_color(pixel: tuple[int, int, int, int], target: tuple[int, int, int], tolerance: int = 18) -> bool:
    r, g, b, a = pixel
    if a == 0:
        return False
    return all(abs(channel - expected) <= tolerance for channel, expected in zip((r, g, b), target))


def clean_frame(frame: Image.Image, bg_color: tuple[int, int, int]) -> Image.Image:
    rgba = frame.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            if close_color(pixels[x, y], bg_color):
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def crop_strip(
    source: Path,
    boxes: list[tuple[int, int, int, int]],
    bg_color: tuple[int, int, int],
    output: Path,
) -> None:
    sheet = Image.open(source).convert("RGBA")
    frames = [clean_frame(sheet.crop((x, y, x + w, y + h)), bg_color) for x, y, w, h in boxes]
    width = sum(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cursor = 0
    for frame in frames:
        strip.alpha_composite(frame, (cursor, height - frame.height))
        cursor += frame.width
    output.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output)


def write_manifest(output: Path, frame_width: int, frame_height: int, scale: int) -> None:
    manifest = {
        "scale": scale,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "spacing": 0,
        "margin": 0,
        "animations": {
            "walk_right": {"file": output.name, "frames": [0, 1, 2, 3], "fps": 6},
            "idle": {"file": output.name, "frames": [0], "fps": 1},
            "catch": {"file": output.name, "frames": [1, 2, 3], "fps": 8},
        },
    }
    (output.parent / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def parse_box(value: str) -> tuple[int, int, int, int]:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("box must be x,y,w,h")
    return parts[0], parts[1], parts[2], parts[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Ash/Red overworld frames from a full spritesheet.")
    parser.add_argument("source", type=Path, help="Full spritesheet PNG.")
    parser.add_argument(
        "--box",
        type=parse_box,
        action="append",
        help="Frame crop as x,y,w,h. Pass four boxes for walk animation.",
    )
    parser.add_argument("--output", type=Path, default=ASH_DIR / "ash_overworld.png")
    parser.add_argument("--frame-width", type=int, default=16)
    parser.add_argument("--frame-height", type=int, default=20)
    parser.add_argument("--x", type=int, default=6, help="Top-left x for first frame when --box is omitted.")
    parser.add_argument("--y", type=int, default=31, help="Top-left y for first frame when --box is omitted.")
    parser.add_argument("--step-x", type=int, default=12, help="Horizontal distance between frames when --box is omitted.")
    parser.add_argument("--bg-color", default="248,128,32", help="Background color to remove, as r,g,b.")
    parser.add_argument("--scale", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bg_color = tuple(int(part.strip()) for part in args.bg_color.split(","))
    if len(bg_color) != 3:
        raise SystemExit("--bg-color must be r,g,b")

    boxes = args.box
    if not boxes:
        boxes = [
            (args.x + args.step_x * index, args.y, args.frame_width, args.frame_height)
            for index in range(4)
        ]

    crop_strip(args.source, boxes, bg_color, args.output)
    write_manifest(args.output, args.frame_width, args.frame_height, args.scale)
    print(args.output)
    print(args.output.parent / "manifest.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
