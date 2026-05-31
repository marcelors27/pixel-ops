from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image


@dataclass(frozen=True)
class MapArea:
    area_id: str
    source_path: Path
    map_key: str
    crop_box: tuple[int, int, int, int]
    source_bounds: tuple[int, int, int, int]
    route: tuple[tuple[int, int], ...]
    environment: str = "outdoor"
    sheltered: bool = False
    location_kind: str = "outdoor"


class MapRouteManager:
    def __init__(
        self,
        maps_dir: Path,
        viewport_size: tuple[int, int],
        switch_seconds: int = 60,
        seed: int = 251,
        allowed_map_keys: Iterable[str] | None = None,
        walkable_source_rects: dict[str,
                                    Iterable[tuple[int, int, int, int]]] | None = None,
        min_walkable_coverage: float = 0.4,
    ):
        self.maps_dir = maps_dir
        self.viewport_size = viewport_size
        self.switch_seconds = switch_seconds
        self.seed = seed
        self.rng = random.Random(seed)
        self.walkable_source_rects = {
            key: tuple(rects)
            for key, rects in (walkable_source_rects or {}).items()
            if key and rects
        }
        raw_allowed_keys = allowed_map_keys
        if raw_allowed_keys is None and self.walkable_source_rects:
            raw_allowed_keys = self.walkable_source_rects.keys()
        self.allowed_map_keys = {
            key for key in raw_allowed_keys if key} if raw_allowed_keys is not None else None
        self.min_walkable_coverage = max(0.0, min(1.0, min_walkable_coverage))
        self.areas = self._load_areas()
        self._background_cache: dict[tuple[str, str], Image.Image] = {}

    def area_for_timestamp(self, timestamp: float) -> MapArea | None:
        if not self.areas:
            return None
        areas = self._filtered_areas_for_mock() or self.areas
        bucket = int(timestamp // max(1, self.switch_seconds))
        groups = self._areas_by_map_key(areas)
        map_keys = list(groups)
        map_key = map_keys[(bucket + self.seed) % len(map_keys)]
        candidates = groups[map_key]
        if len(candidates) == 1:
            return candidates[0]
        rng = random.Random(bucket + self.seed)
        return candidates[rng.randrange(len(candidates))]

    @staticmethod
    def _areas_by_map_key(areas: list[MapArea]) -> dict[str, list[MapArea]]:
        groups: dict[str, list[MapArea]] = {}
        for area in areas:
            groups.setdefault(area.map_key, []).append(area)
        return groups

    def _filtered_areas_for_mock(self) -> list[MapArea]:
        environment = os.environ.get(
            "PIXEL_OPS_MAP_MOCK_ENVIRONMENT", "").strip().lower()
        if not environment:
            return []
        if environment == "sheltered":
            return [area for area in self.areas if area.sheltered]
        if environment == "unsheltered":
            return [area for area in self.areas if not area.sheltered]
        return [area for area in self.areas if area.environment == environment]

    def background_for_area(self, area: MapArea, phase: str, tint) -> Image.Image:
        key = (area.area_id, phase)
        cached = self._background_cache.get(key)
        if cached is not None:
            return cached
        with Image.open(area.source_path) as source:
            crop = source.convert("RGB").crop(area.crop_box)
        crop = self._black_out_light_border(crop)
        background = Image.new("RGB", self.viewport_size, (0, 0, 0))
        background.paste(crop, ((
            self.viewport_size[0] - crop.width) // 2, (self.viewport_size[1] - crop.height) // 2))
        if tint:
            background = tint(background)
        self._background_cache[key] = background
        return background

    def position_on_route(self, area: MapArea, frame: int, speed_px_per_frame: float = 1.25) -> tuple[int, int]:
        position, _ = self.pose_on_route(area, frame, speed_px_per_frame)
        return position

    def pose_on_route(
        self,
        area: MapArea,
        frame: int,
        speed_px_per_frame: float = 1.25,
    ) -> tuple[tuple[int, int], str]:
        route = area.route
        if len(route) < 2:
            return (route[0] if route else (120, 292)), "down"
        segments = []
        total = 0.0
        for start, end in zip(route, route[1:]):
            length = ((end[0] - start[0]) ** 2 +
                      (end[1] - start[1]) ** 2) ** 0.5
            segments.append((start, end, length))
            total += length
        if total <= 0:
            return route[0], "down"
        distance = (frame * speed_px_per_frame) % (total * 2)
        reverse = False
        if distance > total:
            distance = (total * 2) - distance
            reverse = True
        for start, end, length in segments:
            if distance > length:
                distance -= length
                continue
            t = distance / max(1.0, length)
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            if reverse:
                dx = -dx
                dy = -dy
            direction = self._direction_for_delta(dx, dy)
            return (
                int(start[0] + (end[0] - start[0]) * t),
                int(start[1] + (end[1] - start[1]) * t),
            ), direction
        return route[-1], "down"

    @staticmethod
    def _direction_for_delta(dx: int, dy: int) -> str:
        if abs(dx) >= abs(dy):
            return "right" if dx >= 0 else "left"
        return "down" if dy >= 0 else "up"

    def _load_areas(self) -> list[MapArea]:
        paths = sorted(self.maps_dir.glob("**/*.png"))
        areas: list[MapArea] = []
        for path in paths:
            if self.allowed_map_keys is not None and path.stem not in self.allowed_map_keys:
                continue
            with Image.open(path) as image:
                source = image.convert("RGB")
                bounds = self._main_map_bounds(source)
                width = bounds[2] - bounds[0]
                height = bounds[3] - bounds[1]
            crop_w, crop_h = self._crop_size(width, height)
            centers = self._centers_for_map(
                path.stem, width, height, crop_w, crop_h, bounds)
            candidates: list[tuple[float, MapArea]] = []
            for index, center in enumerate(centers):
                local_box = self._crop_box(
                    width, height, crop_w, crop_h, center)
                box = (
                    bounds[0] + local_box[0],
                    bounds[1] + local_box[1],
                    bounds[0] + local_box[2],
                    bounds[1] + local_box[3],
                )
                area_id = f"{path.stem}:{index}"
                coverage = self._walkable_coverage(path.stem, box)
                if self.walkable_source_rects and coverage < self.min_walkable_coverage:
                    continue
                route = self._route_for_crop(source.crop(
                    box)) or self._route_for_source_rects(path.stem, box)
                if route:
                    environment, sheltered, location_kind = self._classify_area(
                        path)
                    candidates.append(
                        (
                            coverage,
                            MapArea(
                                area_id,
                                path,
                                path.stem,
                                box,
                                bounds,
                                route,
                                environment=environment,
                                sheltered=sheltered,
                                location_kind=location_kind,
                            ),
                        )
                    )
            candidates.sort(key=lambda item: item[0], reverse=True)
            areas.extend(area for _, area in candidates)
        return areas

    @staticmethod
    def _classify_area(path: Path) -> tuple[str, bool, str]:
        stem = path.stem
        parent = path.parent.name
        if parent == "nature":
            if "altering-cave" in stem:
                return "cave", True, "cave"
            if stem.endswith("__map-02"):
                return "indoor", True, "interior"
            return "outdoor", False, "nature"

        if "__map-01" in stem:
            return "outdoor", False, "town"

        return "indoor", True, MapRouteManager._indoor_kind(stem)

    @staticmethod
    def _indoor_kind(stem: str) -> str:
        if "__map-03" in stem or "__map-04" in stem:
            return "pokemon_center"
        if "pewter-city__map-05" in stem or "vermilion-city__map-02" in stem or "viridian-city__map-02" in stem:
            return "gym"
        if "pewter-city__map-06" in stem or "pewter-city__map-07" in stem:
            return "museum"
        if "__map-02" in stem:
            return "shop"
        return "house"

    def _main_map_bounds(self, image: Image.Image) -> tuple[int, int, int, int]:
        width, height = image.size
        left, top, right, bottom = 0, 0, width, height

        # Original Spriters Resource sheets have a white frame/header around the maps.
        # Clean split maps do not, so only apply header trimming when the outer border is mostly light.
        border_sample = []
        if height > 20:
            border_sample.extend(image.getpixel((x, 0))
                                 for x in range(0, width, max(1, width // 80)))
            border_sample.extend(image.getpixel((x, height - 1))
                                 for x in range(0, width, max(1, width // 80)))
            border_sample.extend(image.getpixel((0, y))
                                 for y in range(0, height, max(1, height // 80)))
            border_sample.extend(image.getpixel((width - 1, y))
                                 for y in range(0, height, max(1, height // 80)))
        has_light_border = bool(border_sample) and sum(
            1 for pixel in border_sample if self._is_light(pixel)) > len(border_sample) * 0.7
        header_sample = [image.getpixel((x, 8)) for x in range(
            0, width, max(1, width // 80))] if has_light_border else []
        if header_sample and sum(1 for pixel in header_sample if self._is_light(pixel)) > len(header_sample) * 0.5:
            top = min(18, height - 1)
        for y in range(top, min(40, height)):
            row = [image.getpixel((x, y))
                   for x in range(0, width, max(1, width // 80))]
            non_light = sum(1 for pixel in row if not self._is_light(pixel))
            if non_light > len(row) * 0.55:
                top = y
                break

        # If the sheet has interiors/legend panels on the right, keep the main outdoor map.
        gap_start = None
        for x in range(max(220, width // 4), width):
            sample = [image.getpixel((x, y)) for y in range(
                top, height, max(1, (height - top) // 80))]
            light = sum(1 for pixel in sample if self._is_light(pixel))
            if light > len(sample) * 0.92:
                if gap_start is None:
                    gap_start = x
            elif gap_start is not None and x - gap_start > 10:
                right = gap_start
                break
            else:
                gap_start = None
        if gap_start is not None and width - gap_start > 80:
            right = gap_start

        # Trim fully light margins left after choosing the main panel.
        for x in range(0, right):
            sample = [image.getpixel((x, y)) for y in range(
                top, height, max(1, (height - top) // 80))]
            if sum(1 for pixel in sample if not self._is_light(pixel)) > len(sample) * 0.2:
                left = x
                break

        return left, top, max(left + 1, right), bottom

    @staticmethod
    def _is_light(pixel: tuple[int, int, int]) -> bool:
        r, g, b = pixel
        return r > 238 and g > 238 and b > 238

    def _black_out_light_border(self, image: Image.Image) -> Image.Image:
        cleaned = image.copy()
        pixels = cleaned.load()
        width, height = cleaned.size
        stack: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()

        for x in range(width):
            stack.append((x, 0))
            stack.append((x, height - 1))
        for y in range(height):
            stack.append((0, y))
            stack.append((width - 1, y))

        while stack:
            x, y = stack.pop()
            if (x, y) in seen:
                continue
            seen.add((x, y))
            if not self._is_light(pixels[x, y]):
                continue
            pixels[x, y] = (0, 0, 0)
            if x > 0:
                stack.append((x - 1, y))
            if x < width - 1:
                stack.append((x + 1, y))
            if y > 0:
                stack.append((x, y - 1))
            if y < height - 1:
                stack.append((x, y + 1))
        return cleaned

    def _crop_size(self, width: int, height: int) -> tuple[int, int]:
        view_w, view_h = self.viewport_size
        return max(1, min(width, view_w)), max(1, min(height, view_h))

    def _centers_for_map(
        self,
        map_key: str,
        width: int,
        height: int,
        crop_w: int,
        crop_h: int,
        source_bounds: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> list[tuple[int, int]]:
        xs = [width // 2]
        ys = [height // 2]
        if width > crop_w * 1.35:
            xs = [crop_w // 2, width // 2, width - crop_w // 2]
        if height > crop_h * 1.35:
            ys = [crop_h // 2, height // 2, height - crop_h // 2]
        centers = [(x, y) for y in ys for x in xs]
        bounds_x0, bounds_y0, _, _ = source_bounds
        for x0, y0, x1, y1 in self.walkable_source_rects.get(map_key, ()):
            cx = (x0 + x1) // 2 - bounds_x0
            cy = (y0 + y1) // 2 - bounds_y0
            centers.append((cx, cy))
            centers.append((max(0, x0 - bounds_x0 + crop_w // 2), cy))
            centers.append((min(width, x1 - bounds_x0 - crop_w // 2), cy))
            centers.append((cx, max(0, y0 - bounds_y0 + crop_h // 2)))
            centers.append((cx, min(height, y1 - bounds_y0 - crop_h // 2)))
        unique: list[tuple[int, int]] = []
        seen = set()
        for center in centers:
            box = self._crop_box(width, height, crop_w, crop_h, center)
            key = (box[0], box[1])
            if key in seen:
                continue
            seen.add(key)
            unique.append(center)
        return unique

    def _walkable_coverage(self, map_key: str, box: tuple[int, int, int, int]) -> float:
        rects = self.walkable_source_rects.get(map_key, ())
        if not rects:
            return 1.0
        box_area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        clipped = []
        for x0, y0, x1, y1 in rects:
            ix0 = max(x0, box[0])
            iy0 = max(y0, box[1])
            ix1 = min(x1, box[2])
            iy1 = min(y1, box[3])
            if ix1 > ix0 and iy1 > iy0:
                clipped.append((ix0, iy0, ix1, iy1))
        return min(1.0, self._rect_union_area(clipped) / box_area)

    @staticmethod
    def _rect_union_area(rects: Iterable[tuple[int, int, int, int]]) -> int:
        rect_list = list(rects)
        if not rect_list:
            return 0
        xs = sorted({x for x0, _, x1, _ in rect_list for x in (x0, x1)})
        total = 0
        for left, right in zip(xs, xs[1:]):
            if right <= left:
                continue
            intervals = [(y0, y1) for x0, y0, x1,
                         y1 in rect_list if x0 < right and x1 > left]
            if not intervals:
                continue
            intervals.sort()
            merged = 0
            current_start, current_end = intervals[0]
            for start, end in intervals[1:]:
                if start > current_end:
                    merged += current_end - current_start
                    current_start, current_end = start, end
                else:
                    current_end = max(current_end, end)
            merged += current_end - current_start
            total += (right - left) * merged
        return total

    @staticmethod
    def _crop_box(
        width: int,
        height: int,
        crop_w: int,
        crop_h: int,
        center: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        left = min(max(0, center[0] - crop_w // 2), max(0, width - crop_w))
        top = min(max(0, center[1] - crop_h // 2), max(0, height - crop_h))
        return left, top, left + crop_w, top + crop_h

    def _route_for_view(self, index: int, total: int) -> tuple[tuple[int, int], ...]:
        width, height = self.viewport_size
        lower = int(height * 0.73)
        middle = int(height * 0.58)
        upper = int(height * 0.43)
        margin = 28
        variant = index % 3
        if variant == 0:
            return ((margin, lower), (width - margin, lower))
        if variant == 1:
            return ((margin, middle), (width - margin, middle), (width - margin, lower), (margin, lower))
        return ((margin, upper), (width - margin, upper), (width - margin, middle), (margin, middle))

    def _route_for_crop(self, image: Image.Image) -> tuple[tuple[int, int], ...]:
        width, height = image.size
        offset_x = (self.viewport_size[0] - width) // 2
        offset_y = (self.viewport_size[1] - height) // 2
        walkable = self._walkable_mask(image)
        best: tuple[float, int, int, int] | None = None
        for y in range(12, max(13, height - 44)):
            run_start = None
            for x in range(4, width - 34):
                can_walk = walkable(x, y)
                if can_walk and run_start is None:
                    run_start = x
                if (not can_walk or x == width - 35) and run_start is not None:
                    run_end = x if not can_walk else x + 1
                    run_len = run_end - run_start
                    preferred_y = height * 0.68
                    score = run_len - abs(y - preferred_y) * 0.35
                    if run_len > 72 and (best is None or score > best[0]):
                        best = (score, y, run_start, run_end)
                    run_start = None
        if best is None:
            return ()
        _, y, start, end = best
        start = min(max(4, start + 8), width - 40)
        end = max(min(width - 40, end - 8), start + 48)
        route = self._route_with_vertical_segments(
            image, start, end, y, walkable)
        route = tuple(point for point in route if walkable(point[0], point[1]))
        if len(route) < 2:
            return ()
        return tuple((x + offset_x, y + offset_y) for x, y in route)

    def _route_for_source_rects(
        self,
        map_key: str,
        crop_box: tuple[int, int, int, int],
    ) -> tuple[tuple[int, int], ...]:
        rects = self.walkable_source_rects.get(map_key, ())
        if not rects:
            return ()
        crop_x0, crop_y0, crop_x1, crop_y1 = crop_box
        best: tuple[int, tuple[int, int, int, int]] | None = None
        for rect_x0, rect_y0, rect_x1, rect_y1 in rects:
            ix0 = max(rect_x0, crop_x0)
            iy0 = max(rect_y0, crop_y0)
            ix1 = min(rect_x1, crop_x1)
            iy1 = min(rect_y1, crop_y1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            area = (ix1 - ix0) * (iy1 - iy0)
            if best is None or area > best[0]:
                best = (area, (ix0, iy0, ix1, iy1))
        if best is None:
            return ()

        _, (ix0, iy0, ix1, iy1) = best
        crop_w = crop_x1 - crop_x0
        crop_h = crop_y1 - crop_y0
        offset_x = (self.viewport_size[0] - crop_w) // 2
        offset_y = (self.viewport_size[1] - crop_h) // 2
        sx0 = ix0 - crop_x0 + offset_x
        sy0 = iy0 - crop_y0 + offset_y
        sx1 = ix1 - crop_x0 + offset_x
        sy1 = iy1 - crop_y0 + offset_y
        if sx1 - sx0 >= sy1 - sy0:
            y = max(sy0 + 1, min(sy1 - 1, sy0 + int((sy1 - sy0) * 0.68)))
            return (sx0 + 1, y), (max(sx0 + 2, sx1 - 1), y)
        x = max(sx0 + 1, min(sx1 - 1, (sx0 + sx1) // 2))
        return (x, sy0 + 1), (x, max(sy0 + 2, sy1 - 1))

    def _route_with_vertical_segments(
        self,
        image: Image.Image,
        start: int,
        end: int,
        y: int,
        walkable: Callable[[int, int], bool],
    ) -> tuple[tuple[int, int], ...]:
        candidates = [start + (end - start) // 3, start +
                      (end - start) * 2 // 3, (start + end) // 2]
        for x in candidates:
            up = self._vertical_reach(image, x, y, -1, walkable)
            down = self._vertical_reach(image, x, y, 1, walkable)
            if y - up > 42:
                upper_run = self._horizontal_run_containing(
                    image, up, x, walkable)
                if upper_run:
                    upper_end = upper_run[1] if abs(
                        upper_run[1] - x) >= abs(x - upper_run[0]) else upper_run[0]
                    return ((start, y), (x, y), (x, up), (upper_end, up))
            if down - y > 42:
                lower_run = self._horizontal_run_containing(
                    image, down, x, walkable)
                if lower_run:
                    lower_end = lower_run[1] if abs(
                        lower_run[1] - x) >= abs(x - lower_run[0]) else lower_run[0]
                    return ((start, y), (x, y), (x, down), (lower_end, down))
        return ((start, y), (end, y))

    def _vertical_reach(
        self,
        image: Image.Image,
        x: int,
        y: int,
        direction: int,
        walkable: Callable[[int, int], bool],
    ) -> int:
        current = y
        while 16 <= current + direction < image.height - 16:
            next_y = current + direction
            if not walkable(x, next_y):
                break
            current = next_y
        return current

    def _horizontal_run_containing(
        self,
        image: Image.Image,
        y: int,
        x: int,
        walkable: Callable[[int, int], bool],
    ) -> tuple[int, int] | None:
        left = x
        right = x
        while left - 1 >= 4 and walkable(left - 1, y):
            left -= 1
        while right + 1 < image.width - 34 and walkable(right + 1, y):
            right += 1
        if right - left < 56:
            return None
        return min(max(4, left + 8), image.width - 40), max(min(image.width - 40, right - 8), left + 16)

    def _walkable_mask(self, image: Image.Image) -> Callable[[int, int], bool]:
        import numpy as np

        width, height = image.size
        max_y = max(0, height - 43)
        max_x = max(0, width - 27)
        rows = np.zeros((height, width), dtype=bool)
        if max_y and max_x:
            pixels = np.asarray(image.convert("RGB"))
            r = pixels[:, :, 0].astype(np.int16)
            g = pixels[:, :, 1].astype(np.int16)
            b = pixels[:, :, 2].astype(np.int16)
            pixel_walkable = (
                (b <= r + 22)
                & (b <= g + 18)
                & ((r >= 35) | (g >= 45) | (b >= 55))
                & (
                    ((g >= r - 12) & (g >= b - 8) & (g > 70))
                    | ((r > 120) & (g > 95) & (b < 185))
                    | ((np.abs(r - g) < 28) & (np.abs(g - b) < 28) & (r > 95) & (r < 220))
                )
            )
            count = np.zeros((max_y, max_x), dtype=np.uint8)
            for x_offset in (12, 19, 26):
                for y_offset in (36, 38, 40, 42):
                    count += pixel_walkable[y_offset: y_offset +
                                            max_y, x_offset: x_offset + max_x]
            rows[:max_y, :max_x] = count >= 10

        def walkable(x: int, y: int) -> bool:
            return 0 <= y < height and 0 <= x < width and bool(rows[y][x])

        return walkable

    def _feet_are_walkable(self, image: Image.Image, x: int, y: int) -> bool:
        # x/y is the Ash sprite top-left route position in map viewport coordinates.
        foot_y = y + 38
        left_x = x + 12
        right_x = x + 26
        if foot_y >= image.height or right_x >= image.width or left_x < 0:
            return False
        samples = [
            image.getpixel((min(max(0, px), image.width - 1),
                           min(max(0, foot_y + dy), image.height - 1)))
            for px in (left_x, (left_x + right_x) // 2, right_x)
            for dy in (-2, 0, 2, 4)
        ]
        return sum(1 for pixel in samples if self._is_walkable(pixel)) >= 10

    @staticmethod
    def _is_walkable(pixel: tuple[int, int, int]) -> bool:
        r, g, b = pixel
        if b > r + 22 and b > g + 18:
            return False
        if r < 35 and g < 45 and b < 55:
            return False
        if g >= r - 12 and g >= b - 8 and g > 70:
            return True
        if r > 120 and g > 95 and b < 185:
            return True
        if abs(r - g) < 28 and abs(g - b) < 28 and 95 < r < 220:
            return True
        return False
