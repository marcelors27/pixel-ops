from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from PIL import Image

PLUGIN_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = PLUGIN_DIR / "assets/maps/firered_leafgreen"
DEFAULT_OUTPUT_DIR = PLUGIN_DIR / "assets/maps/firered_leafgreen_clean"


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def is_background(pixel_array: np.ndarray) -> np.ndarray:
    return (pixel_array[:, :, 0] > 245) & (pixel_array[:, :, 1] > 245) & (pixel_array[:, :, 2] > 245)


def connected_components(mask: np.ndarray) -> Iterable[tuple[int, int, int, int, int]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    for y in range(height):
        candidates = np.where(mask[y] & ~seen[y])[0]
        for start_x in candidates:
            if seen[y, start_x] or not mask[y, start_x]:
                continue
            stack = [(int(start_x), y)]
            seen[y, start_x] = True
            min_x = max_x = int(start_x)
            min_y = max_y = y
            pixels = 0

            while stack:
                x, current_y = stack.pop()
                pixels += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)
                for next_x, next_y in ((x + 1, current_y), (x - 1, current_y), (x, current_y + 1), (x, current_y - 1)):
                    if 0 <= next_x < width and 0 <= next_y < height and mask[next_y, next_x] and not seen[next_y, next_x]:
                        seen[next_y, next_x] = True
                        stack.append((next_x, next_y))

            yield min_x, min_y, max_x + 1, max_y + 1, pixels


def component_is_map(component: tuple[int, int, int, int, int], image_size: tuple[int, int]) -> bool:
    x0, y0, x1, y1, pixels = component
    width = x1 - x0
    height = y1 - y0
    image_width, image_height = image_size
    if width < 96 or height < 96:
        return False
    density = pixels / max(1, width * height)
    if density < 0.18:
        return False
    # Large source sheets often have a thin non-white frame around the whole sheet.
    if x0 <= 2 and y0 <= 2 and x1 >= image_width - 2 and y1 >= image_height - 2 and density < 0.2:
        return False
    return True


def split_sheet(path: Path, source_dir: Path, output_dir: Path) -> list[Path]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        pixels = np.array(rgb)

    mask = ~is_background(pixels)
    components = [
        component
        for component in connected_components(mask)
        if component_is_map(component, rgb.size)
    ]
    components.sort(key=lambda item: (item[1], item[0]))

    relative_parent = path.parent.relative_to(source_dir)
    target_dir = output_dir / relative_parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(path.stem)
    written: list[Path] = []
    for index, (x0, y0, x1, y1, _pixels) in enumerate(components, start=1):
        crop = rgb.crop((x0, y0, x1, y1))
        suffix = f"map-{index:02d}" if len(components) > 1 else "map"
        target = target_dir / f"{stem}__{suffix}.png"
        crop.save(target)
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Split Pokemon map sheets into individual map PNGs.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    source_dir = args.source_dir
    output_dir = args.output_dir
    for sheet in sorted(source_dir.glob("**/*.png")):
        if output_dir in sheet.parents:
            continue
        written = split_sheet(sheet, source_dir, output_dir)
        print(f"{sheet.relative_to(source_dir)} -> {len(written)} map(s)")
        for path in written:
            print(f"  {path.relative_to(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
