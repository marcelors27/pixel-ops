from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from pixel_ops.plugins.spaceship.engine import SpaceshipSnapshot
from pixel_ops.plugins.spaceship.persistence import AsteroidRecord
from pixel_ops.render.fonts import font, font_scale_for_canvas
from pixel_ops.render.renderer import PixelRenderer


ROOM_STEP_X = 40
ROOM_STEP_Y = 20


class SpaceshipScene:
    def __init__(self, width: int, height: int, config: dict | None = None):
        self.renderer = PixelRenderer(width, height)
        self.scene_scale = max(1.0, min(width / 480, height / 320))
        self.config = config or {}
        self.display_layout: dict = {}
        self.layout_theme = "terminal"
        self.ship_supersampling = max(1, min(4, int(self.config.get("ship_supersampling", 3))))
        requested_ship_scale = self.scene_scale * max(1.0, float(self.config.get("ship_scale", 2.0)))
        # Preserve the requested zoom whenever the viewport allows it, but avoid
        # presenting clipped hull parts on compact screens.
        self.ship_scale = min(requested_ship_scale, width / 280, height / 180)
        raw = self.config.get("palette", {})
        self.palette = {key: tuple(value) for key, value in raw.items() if isinstance(value, list) and len(value) == 3}
        self.assets = Path(__file__).parent / "assets"
        self._scaled_asset_cache: dict[tuple[int, int, int], Image.Image] = {}
        self._opened_room_cache: dict[tuple[int, ...], Image.Image] = {}
        self._doorway_position_cache: dict[tuple[int, int, int], tuple[int, int]] = {}
        self.ops_direction_frames = {
            direction: self._load_asset(f"crew/operations-officer-character/Idle/rotations/{direction}.png")
            for direction in ("south", "south-east", "east", "north-east", "north", "north-west", "west", "south-west")
        }
        self.ops_idle_frames = [self.ops_direction_frames["south"]] if self.ops_direction_frames["south"] else []
        self.ops_walk_frames = {
            direction: self._load_frames(f"crew/operations-officer-character/Idle/animations/walk/{direction}")
            for direction in self.ops_direction_frames
        }
        self.ops_working_state = {
            direction: self._load_asset(
                f"crew/operations-officer-character/working_on_computer/rotations/{direction}.png"
            )
            for direction in self.ops_direction_frames
        }
        self.ops_typing_frames = self._load_frames(
            "crew/operations-officer-character/working_on_computer/animations/typing/south"
        )
        self.engineer_idle_frames = self._load_frames("crew/maintenance-engineer-128-final/idle")
        self.engineer_action_frames = self._load_frames("crew/maintenance-engineer-128-final/actions/repair")
        iron = self._load_asset("asteroids/asteroid-iron.png")
        crystal = self._load_asset("asteroids/asteroid-crystal.png")
        cobalt = self._load_asset("asteroids/asteroid-cobalt.png")
        self.asteroid_sprites = {
            "iron": iron,
            "silicon_crystal": crystal,
            "energy_ice": crystal,
            "orbital_cobalt": cobalt,
            "amber_ore": cobalt,
            "data_fragment": crystal,
        }
        drone_idle = self._load_asset("mining/drone/idle.png")
        self.drone_frames = self._load_frames("mining/drone/work") or ([drone_idle] if drone_idle else [])
        self.progress_bar_frame = self._load_asset("hud/mining-progress-frame.png")
        self.progress_bar_fill = self._load_asset("hud/mining-progress-fill.png")
        self.bay_upgrade_module = self._load_asset("upgrades/bay-02-module.png")
        self.room_modules = {
            room: self._load_asset(f"isometric-pro/rooms/{file_name}.png")
            for room, file_name in {
                "BRIDGE": "bridge-refined", "REACTOR": "reactor-refined",
                "LAB": "lab-refined", "CARGO": "cargo-refined",
                "CREW": "cargo-refined", "ENGINEERING": "reactor-refined",
            }.items()
        }
        self.hull_modules = {
            name: self._load_asset(f"isometric-pro/hull-kit/{name}.png")
            for name in (
                "prow-east", "prow-west", "engine-east", "engine-west",
            )
        }
        self._validate_required_assets()

    def render(self, state: SpaceshipSnapshot) -> Image.Image:
        with font_scale_for_canvas(self.renderer.width, self.renderer.height):
            space = self._color("space", (5, 10, 24))
            image = self.renderer.canvas(space)
            draw = ImageDraw.Draw(image)
            self._draw_stars(draw, state)
            factor = self.ship_supersampling
            ship_layer = Image.new("RGBA", (image.width * factor, image.height * factor), (0, 0, 0, 0))
            self._draw_isometric_ship(ship_layer, ImageDraw.Draw(ship_layer), state, self.ship_scale * factor)
            ship_layer = ship_layer.resize(image.size, Image.Resampling.LANCZOS)
            alpha = ship_layer.getchannel("A")
            sharpened = ship_layer.convert("RGB").filter(ImageFilter.UnsharpMask(radius=0.65, percent=135, threshold=2))
            sharpened.putalpha(alpha)
            image.paste(sharpened, (0, 0), sharpened)
            asteroid_positions = self._draw_asteroids(image, draw, state)
            self._draw_mining_cycle(image, draw, state, asteroid_positions)
            self._draw_hud(image, draw, state)
            return self._compose_presentation(image)

    def set_presentation(self, layout: dict, layout_theme: str) -> None:
        self.display_layout = dict(layout) if isinstance(layout, dict) else {}
        self.layout_theme = str(layout_theme or "terminal")

    def _compose_presentation(self, full_frame: Image.Image) -> Image.Image:
        boxes: list[tuple[int, int, int, int]] = []
        for key, raw in self.display_layout.items():
            if not isinstance(raw, dict) or str(raw.get("kind") or key) != "spaceship_hud":
                continue
            try:
                x = int(raw.get("x", 0))
                y = int(raw.get("y", 0))
                width = int(raw.get("width", 0))
                height = int(raw.get("height", 0))
            except (TypeError, ValueError):
                continue
            x0 = max(0, min(self.renderer.width - 1, x))
            y0 = max(0, min(self.renderer.height - 1, y))
            x1 = max(x0 + 1, min(self.renderer.width, x0 + max(1, width)))
            y1 = max(y0 + 1, min(self.renderer.height, y0 + max(1, height)))
            boxes.append((x0, y0, x1, y1))
        if not boxes:
            return full_frame

        result = self.renderer.canvas(self._color("space", (5, 10, 24)))
        main_box = max(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
        lcd_source_x = max(1, full_frame.width - 172) if full_frame.width >= 1000 else full_frame.width
        main_source = full_frame.crop((0, 0, lcd_source_x, full_frame.height))
        for box in boxes:
            source = (
                main_source
                if box == main_box or lcd_source_x >= full_frame.width
                else full_frame.crop((lcd_source_x, 0, full_frame.width, full_frame.height))
            )
            target_size = (box[2] - box[0], box[3] - box[1])
            scaled = source.resize(target_size, Image.Resampling.NEAREST)
            result.paste(scaled, (box[0], box[1]))
        return result

    def _draw_isometric_ship(
        self, image: Image.Image, draw: ImageDraw.ImageDraw, state: SpaceshipSnapshot, scale: float
    ) -> None:
        rooms = _seeded_room_layout(state.profile.layout_seed)
        projected = {
            cell: (
                round((cell[0] - cell[1]) * ROOM_STEP_X * scale),
                round((cell[0] + cell[1]) * ROOM_STEP_Y * scale),
            )
            for cell in rooms
        }
        xs = [point[0] for point in projected.values()]
        ys = [point[1] for point in projected.values()]
        origin_x = image.width // 2 - (min(xs) + max(xs)) // 2 - round(64 * scale)
        origin_y = max(round(50 * scale), image.height // 2 - (min(ys) + max(ys)) // 2 - round(40 * scale))
        positions = {cell: (origin_x + point[0], origin_y + point[1]) for cell, point in projected.items()}
        self._compose_hull_modules(image, rooms, positions, scale)
        ordered_cells = sorted(rooms, key=lambda item: (sum(item), item[0]))
        self._compose_bay_upgrade(image, rooms, positions, scale, state.resources)
        action_frame = int(state.now.timestamp() * 4)
        bridge_cell = next(cell for cell, room in rooms.items() if room == "BRIDGE")
        reactor_cell = next(cell for cell, room in rooms.items() if room == "REACTOR")
        crew_height = round(20 * scale)
        ops_task = _manual_crew_task(self.config, "operations_officer")
        if ops_task == "working_on_computer":
            ops_frames = self.ops_typing_frames or [self.ops_working_state["south"]]
        else:
            ops_frames = self.ops_idle_frames
        engineer_frames = self.engineer_action_frames if _crew_is_working(state.now, 5) else self.engineer_idle_frames
        assignment_room = _crew_assignment_room(state.asteroids)
        target_cell = next(cell for cell, room in rooms.items() if room == assignment_room)
        route = _shortest_room_route(rooms, bridge_cell, target_cell)
        current_cell, next_cell, progress, working_at_target = _task_route_phase(route, state.now)
        moving = current_cell != next_cell
        active_edge = frozenset((current_cell, next_cell)) if moving else frozenset()
        door_open = _door_open_amount(progress) if moving else 0.0
        if moving:
            start = _crew_position(positions[current_cell], scale)
            end = _crew_position(positions[next_cell], scale)
            doorway = self._doorway_position_for_edge(current_cell, next_cell, rooms, positions, scale)
            ops_position = _route_via_doorway(start, doorway, end, progress)
            direction = _movement_direction(current_cell, next_cell)
            active_ops_frames = self.ops_walk_frames[direction] or [self.ops_direction_frames[direction]]
            ops_depth_cell = max((current_cell, next_cell), key=lambda cell: ordered_cells.index(cell))
        else:
            ops_position = _crew_position(positions[current_cell], scale)
            active_ops_frames = ops_frames if working_at_target else self.ops_idle_frames
            ops_depth_cell = current_cell

        for cell in ordered_cells:
            room = rooms[cell]
            module = self.room_modules.get(room)
            module = self._scaled_asset(module, max(80, round(128 * scale)), max(64, round(102 * scale)))
            module = self._room_with_doorways(module, cell, rooms, scale, active_edge, door_open)
            image.paste(module, positions[cell], module)
            if cell == reactor_cell:
                self._paste_frame(image, engineer_frames, action_frame, _crew_position(positions[cell], scale), crew_height)
            if cell == ops_depth_cell:
                self._paste_frame(image, active_ops_frames, action_frame, ops_position, round(19 * scale))

    def _room_with_doorways(
        self,
        module: Image.Image,
        cell: tuple[int, int],
        rooms: dict[tuple[int, int], str],
        scale: float,
        active_edge: frozenset[tuple[int, int]],
        open_amount: float,
    ) -> Image.Image:
        directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
        door_step = max(0, min(4, round(open_amount * 4)))
        neighbor_mask = sum(
            1 << index
            for index, (dx, dy) in enumerate(directions)
            if door_step
            and frozenset((cell, (cell[0] + dx, cell[1] + dy))) == active_edge
            and _should_cut_shared_wall(cell, (cell[0] + dx, cell[1] + dy), rooms)
        )
        key = (id(module), neighbor_mask, door_step, module.width, module.height)
        cached = self._opened_room_cache.get(key)
        if cached is not None:
            return cached

        opened = module.copy()
        alpha = opened.getchannel("A")
        mask_draw = ImageDraw.Draw(alpha)
        for dx, dy in directions:
            neighbor = (cell[0] + dx, cell[1] + dy)
            if (
                not door_step
                or frozenset((cell, neighbor)) != active_edge
                or not _should_cut_shared_wall(cell, neighbor, rooms)
            ):
                continue
            # The route and the opening must agree on one point in the actual
            # foreground wall.  Picking it from the room pixels avoids cutting
            # consoles, floor tiles, or an unconnected point inside the room.
            doorway_x, doorway_y = self._smooth_wall_doorway(module, (dx, dy), scale)
            half_width = max(1, round(6 * scale * door_step / 4))
            skew = max(1, round(3 * scale))
            top = doorway_y - round(22 * scale)
            bottom = doorway_y - round(4 * scale)
            if dx:
                opening = (
                    (doorway_x - half_width, top - skew),
                    (doorway_x + half_width, top + skew),
                    (doorway_x + half_width, bottom + skew),
                    (doorway_x - half_width, bottom - skew),
                )
            else:
                opening = (
                    (doorway_x - half_width, top + skew),
                    (doorway_x + half_width, top - skew),
                    (doorway_x + half_width, bottom - skew),
                    (doorway_x - half_width, bottom + skew),
                )
            mask_draw.polygon(opening, fill=0)
        opened.putalpha(alpha)
        opened = self._with_translucent_walls(opened, scale)
        self._opened_room_cache[key] = opened
        return opened

    @staticmethod
    def _with_translucent_walls(module: Image.Image, scale: float) -> Image.Image:
        """Fade the enclosing wall faces while preserving floors and furniture."""
        alpha = module.getchannel("A")
        wall_mask = Image.new("L", module.size, 0)
        draw = ImageDraw.Draw(wall_mask)

        def scaled(points: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
            return tuple((round(x * scale), round(y * scale)) for x, y in points)

        # Rear wall faces and the two foreground lips of the PixelLab room.
        # The mask deliberately excludes the central floor diamond.
        draw.polygon(scaled(((0, 17), (64, 0), (128, 17), (128, 58), (64, 42), (0, 58))), fill=255)
        draw.polygon(scaled(((0, 56), (64, 86), (64, 102), (0, 72))), fill=255)
        draw.polygon(scaled(((64, 86), (128, 56), (128, 72), (64, 102))), fill=255)
        faded_alpha = alpha.point(lambda value: round(value * 0.42))
        alpha.paste(faded_alpha, (0, 0), wall_mask)
        translucent = module.copy()
        translucent.putalpha(alpha)
        return translucent

    def _doorway_position_for_edge(
        self,
        start_cell: tuple[int, int],
        end_cell: tuple[int, int],
        rooms: dict[tuple[int, int], str],
        positions: dict[tuple[int, int], tuple[int, int]],
        scale: float,
    ) -> tuple[int, int]:
        foreground = max((start_cell, end_cell), key=lambda cell: (sum(cell), cell[0]))
        background = end_cell if foreground == start_cell else start_cell
        direction = (background[0] - foreground[0], background[1] - foreground[1])
        module = self._scaled_asset(
            self.room_modules[rooms[foreground]], max(80, round(128 * scale)), max(64, round(102 * scale))
        )
        local_x, local_y = self._smooth_wall_doorway(module, direction, scale)
        room_x, room_y = positions[foreground]
        return room_x + local_x - round(6 * scale), room_y + local_y - round(19 * scale)

    def _smooth_wall_doorway(
        self, module: Image.Image, direction: tuple[int, int], scale: float
    ) -> tuple[int, int]:
        key = (id(module), direction[0], direction[1])
        cached = self._doorway_position_cache.get(key)
        if cached is not None:
            return cached
        base_x = 44 if direction == (-1, 0) else 84
        slope = -0.35 if direction == (-1, 0) else 0.35
        sample_step = max(1, round(2 * scale))
        candidates = []
        for offset in range(-12, 13, 4):
            center_x = round((base_x + offset) * scale)
            center_y = round((58 + offset * slope) * scale)
            left, right = center_x - round(6 * scale), center_x + round(6 * scale)
            top, bottom = center_y - round(22 * scale), center_y - round(4 * scale)
            score = 0
            samples = 0
            previous = None
            for y in range(max(0, top), min(module.height, bottom + 1), sample_step):
                for x in range(max(0, left), min(module.width, right + 1), sample_step):
                    pixel = module.getpixel((x, y))
                    if pixel[3] < 220:
                        score += 1200
                    score += max(pixel[:3]) - min(pixel[:3])
                    if previous is not None:
                        score += sum(abs(pixel[channel] - previous[channel]) for channel in range(3))
                    previous = pixel
                    samples += 1
            candidates.append((score / max(1, samples), center_x, center_y))
        _, center_x, center_y = min(candidates)
        result = (center_x, center_y)
        self._doorway_position_cache[key] = result
        return result

    def _compose_bay_upgrade(
        self,
        image: Image.Image,
        rooms: dict[tuple[int, int], str],
        positions: dict[tuple[int, int], tuple[int, int]],
        scale: float,
        resources: dict[str, int],
    ) -> None:
        tier_size = max(1, int(self.config.get("prs_per_bay_tier", 60)))
        if _mining_bay_tier(resources, tier_size) < 2 or self.bay_upgrade_module is None:
            return
        cargo_cell = next(cell for cell, room in rooms.items() if room == "CARGO")
        cargo_x, cargo_y = positions[cargo_cell]
        centroid_x = sum(position[0] for position in positions.values()) // len(positions)
        direction = -1 if cargo_x <= centroid_x else 1
        module = self._scaled_asset(
            self.bay_upgrade_module, max(48, round(42 * scale)), max(38, round(34 * scale))
        )
        x = cargo_x + direction * round(4 * scale) - (module.width if direction < 0 else 0)
        y = cargo_y + round(48 * scale)
        x = max(0, min(image.width - module.width, x))
        y = max(0, min(image.height - module.height, y))
        image.paste(module, (x, y), module)

    def _compose_hull_modules(
        self,
        image: Image.Image,
        rooms: dict[tuple[int, int], str],
        positions: dict[tuple[int, int], tuple[int, int]],
        scale: float,
    ) -> None:
        """Compose only PixelLab-authored hull pieces around the seeded rooms."""
        center_y = round(82 * scale)
        centers = {
            cell: (position[0] + round(64 * scale), position[1] + center_y)
            for cell, position in positions.items()
        }

        bridge_cell = next(cell for cell, room in rooms.items() if room == "BRIDGE")
        bridge_x, bridge_y = centers[bridge_cell]
        centroid_x = sum(point[0] for point in centers.values()) // len(centers)
        direction = 1 if bridge_x >= centroid_x else -1
        prow = self.hull_modules.get("prow-east" if direction > 0 else "prow-west")
        if prow:
            prow = self._scaled_asset(prow, round(64 * scale), round(51 * scale))
            prow_x = bridge_x + direction * round(42 * scale) - prow.width // 2
            image.paste(prow, (prow_x, bridge_y - prow.height // 2), prow)

        rear_cells = sorted(centers, key=lambda cell: centers[cell][0] * direction)[:2]
        engine = self.hull_modules.get("engine-west" if direction > 0 else "engine-east")
        if not engine:
            return
        engine = self._scaled_asset(engine, round(40 * scale), round(32 * scale))
        for index, cell in enumerate(rear_cells):
            engine_x, engine_y = centers[cell]
            engine_x -= direction * round(43 * scale)
            engine_y += (-1 if index == 0 else 1) * round(18 * scale)
            image.paste(engine, (engine_x - engine.width // 2, engine_y - engine.height // 2), engine)

    def _draw_stars(self, draw: ImageDraw.ImageDraw, state: SpaceshipSnapshot) -> None:
        width, height = self.renderer.width, self.renderer.height
        offset = int(state.profile.distance_travelled) % max(1, width)
        for index in range(max(20, width // 18)):
            digest = hashlib.sha256(f"star:{index}".encode()).digest()
            x = (digest[0] * 17 - offset // (1 + digest[1] % 3)) % width
            y = 22 + (digest[1] * 11) % max(1, height - 44)
            tone = 110 + digest[2] % 100
            draw.point((x, y), fill=(tone, tone, min(255, tone + 25)))

    def _draw_asteroids(
        self, image: Image.Image, draw: ImageDraw.ImageDraw, state: SpaceshipSnapshot
    ) -> dict[str, tuple[int, int]]:
        width, height = self.renderer.width, self.renderer.height
        start_x = width * 4 // 5
        positions: dict[str, tuple[int, int]] = {}
        colors = {
            "iron": (126, 117, 110), "silicon_crystal": (92, 210, 218),
            "orbital_cobalt": (76, 112, 198), "energy_ice": (178, 226, 244),
            "amber_ore": (220, 150, 62), "data_fragment": (174, 102, 212),
        }
        for index, asteroid in enumerate(state.asteroids[:5]):
            digest = hashlib.sha256(asteroid.pr_key.encode()).digest()
            x = start_x + (digest[0] % max(1, width - start_x - 14))
            y = 52 + (index * 43 + digest[1]) % max(1, height - 78)
            positions[asteroid.pr_key] = (x, y)
            radius = 4 + digest[2] % 6
            color = colors.get(asteroid.material_type, (130, 130, 130))
            sprite = self.asteroid_sprites.get(asteroid.material_type)
            if sprite:
                image.paste(sprite, (x - sprite.width // 2, y - sprite.height // 2), sprite)
            else:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline=(220, 224, 220))
            if asteroid.processing_state == "refined":
                draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=(255, 236, 150))
        return positions

    def _draw_mining_cycle(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        state: SpaceshipSnapshot,
        asteroid_positions: dict[str, tuple[int, int]],
    ) -> None:
        target = _active_mining_asteroid(state.asteroids)
        if target is None or target.pr_key not in asteroid_positions or not self.drone_frames:
            return
        width, height = self.renderer.width, self.renderer.height
        dock = (round(width * 0.73), round(height * 0.64))
        asteroid = asteroid_positions[target.pr_key]
        progress = _drone_progress(target.processing_state, target.updated_at, state.now)
        if progress is None:
            return
        x = round(dock[0] + (asteroid[0] - dock[0]) * progress)
        y = round(dock[1] + (asteroid[1] - dock[1]) * progress)
        if target.processing_state == "sampling" and progress >= 0.98:
            y += round(2 * ((int(state.now.timestamp() * 2) % 3) - 1))
            draw.line((x + 5, y, asteroid[0], asteroid[1]), fill=self._color("cyan", (74, 210, 220)), width=1)
        elif target.processing_state == "certified":
            draw.rectangle((x - 2, y + 7, x + 2, y + 10), fill=self._color("amber", (242, 172, 68)))
        frame = int(state.now.timestamp() * 4)
        self._paste_frame(image, self.drone_frames, frame, (x - 14, y - 10), 22)

    def _draw_hud(self, image: Image.Image, draw: ImageDraw.ImageDraw, state: SpaceshipSnapshot) -> None:
        text = self._color("text", (226, 236, 238))
        cyan = self._color("cyan", (74, 210, 220))
        amber = self._color("amber", (242, 172, 68))
        panel = self._color("panel", (8, 20, 38))
        shadow = self._color("panel_shadow", (2, 7, 16))
        title = font(9)
        tiny = font(7)
        hours = timedelta(seconds=int(state.profile.total_active_seconds))
        raw = state.resources.get("raw_ore", 0)
        alloy = state.resources.get("refined_alloy", 0)
        tier_size = max(1, int(self.config.get("prs_per_bay_tier", 60)))
        mining_tier, tier_progress, tier_target = _mining_bay_progress(state.resources, tier_size)
        width, height = self.renderer.width, self.renderer.height
        lcd_width = 172 if width >= 1000 else 0
        main_right = width - lcd_width - 10

        status_box = (8, 8, min(390, main_right - 8), 126)
        cargo_box = (max(400, main_right - 420), 8, main_right, 126)
        ops_box = (8, max(132, height - 116), min(560, main_right - 8), height - 8)
        for box in (status_box, cargo_box, ops_box):
            PixelRenderer.draw_panel(draw, box, panel, shadow, cyan)

        draw.text((20, 18), "SHIP STATUS", font=tiny, fill=amber)
        draw.text((20, 39), state.profile.ship_name.upper(), font=title, fill=cyan)
        draw.text((20, 65), f"SECTOR {state.profile.current_sector:02d}   LEVEL {state.profile.ship_level:02d}", font=tiny, fill=text)
        draw.text((20, 87), f"ACTIVE {str(hours).split('.')[0]}   DIST {state.profile.distance_travelled:07.1f}", font=tiny, fill=text)

        cargo_x = cargo_box[0] + 12
        draw.text((cargo_x, 18), "CARGO & MINING", font=tiny, fill=amber)
        draw.text((cargo_x, 43), f"RAW ORE {raw:03d}", font=title, fill=text)
        draw.text((cargo_x + 145, 43), f"ALLOY {alloy:03d}", font=title, fill=text)
        draw.text((cargo_x, 72), f"BAY {mining_tier:02d}   NEXT UPGRADE {tier_progress:02d}/{tier_target:02d}", font=tiny, fill=cyan)

        active_targets = [item for item in state.asteroids if item.processing_state not in ("refined", "abandoned")]
        ops_x, ops_y = ops_box[0] + 12, ops_box[1] + 10
        draw.text((ops_x, ops_y), "MISSION OPS", font=tiny, fill=amber)
        draw.text((ops_x, ops_y + 24), f"TARGETS {len(active_targets):02d}   SIGNALS {len(state.observations):02d}", font=title, fill=cyan)
        if state.recent_event:
            label = _diegetic_event_label(state.recent_event.category)
            draw.text((ops_x, ops_y + 54), label, font=tiny, fill=text)
        else:
            draw.text((ops_x, ops_y + 54), "CRUISE NOMINAL / NO ACTIVE ALERT", font=tiny, fill=text)

        if lcd_width:
            lcd_box = (width - lcd_width + 8, 8, width - 8, min(height - 8, 312))
            PixelRenderer.draw_panel(draw, lcd_box, panel, shadow, cyan)
            lcd_x = lcd_box[0] + 10
            draw.text((lcd_x, 20), "STARSHIP", font=tiny, fill=amber)
            draw.text((lcd_x, 48), f"SEC {state.profile.current_sector:02d}", font=title, fill=cyan)
            draw.text((lcd_x, 82), f"LV {state.profile.ship_level:02d}", font=title, fill=text)
            draw.text((lcd_x, 116), f"ORE {raw:03d}", font=tiny, fill=text)
            draw.text((lcd_x, 140), f"ALLOY {alloy:03d}", font=tiny, fill=text)
            draw.text((lcd_x, 176), f"BAY {mining_tier:02d}", font=tiny, fill=cyan)
            draw.text((lcd_x, 204), f"{tier_progress:02d}/{tier_target:02d}", font=title, fill=amber)

    def _draw_mining_progress_bar(
        self, image: Image.Image, ratio: float, progress: int, target: int
    ) -> None:
        if self.progress_bar_frame is None or self.progress_bar_fill is None:
            return
        width, height = 132, 25
        x = max(8, self.renderer.width - width - 8)
        y = 30
        fill = self._scaled_asset(self.progress_bar_fill, width, height)
        visible_width = max(0, min(width, round(width * ratio)))
        if visible_width:
            clipped = fill.crop((0, 0, visible_width, height))
            image.paste(clipped, (x, y), clipped)
        frame = self._scaled_asset(self.progress_bar_frame, width, height)
        image.paste(frame, (x, y), frame)
        draw = ImageDraw.Draw(image)
        label = f"NEXT BAY {progress:02d}/{target:02d}"
        draw.text((x + 5, y + 8), label, font=font(7), fill=self._color("text", (226, 236, 238)))

    def _color(self, key: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
        return self.palette.get(key, fallback)

    def _validate_required_assets(self) -> None:
        missing = []
        if not self.ops_idle_frames:
            missing.append("crew/operations-officer-character/Idle/rotations/south.png")
        if not self.engineer_idle_frames:
            missing.append("crew/maintenance-engineer-128-final/idle")
        missing.extend(
            f"crew/operations-officer-character/working_on_computer/rotations/{direction}.png"
            for direction, asset in self.ops_working_state.items() if asset is None
        )
        if not self.ops_typing_frames:
            missing.append("crew/operations-officer-character/working_on_computer/animations/typing/south")
        if not self.engineer_action_frames:
            missing.append("crew/maintenance-engineer-128-final/actions/repair")
        missing.extend(
            f"crew/operations-officer-character/Idle/animations/walk/{direction}"
            for direction, frames in self.ops_walk_frames.items() if not frames
        )
        if not self.drone_frames:
            missing.append("mining/drone/work")
        if self.progress_bar_frame is None:
            missing.append("hud/mining-progress-frame.png")
        if self.progress_bar_fill is None:
            missing.append("hud/mining-progress-fill.png")
        if self.bay_upgrade_module is None:
            missing.append("upgrades/bay-02-module.png")
        missing.extend(f"crew/operations-officer-character/Idle/rotations/{name}.png" for name, asset in self.ops_direction_frames.items() if asset is None)
        missing.extend(f"isometric-pro/rooms/{name}" for name, asset in self.room_modules.items() if asset is None)
        missing.extend(f"isometric-pro/hull-kit/{name}.png" for name, asset in self.hull_modules.items() if asset is None)
        if missing:
            raise FileNotFoundError(f"Missing required Spaceship assets: {', '.join(missing)}")

    def _scaled_asset(self, asset: Image.Image, width: int, height: int) -> Image.Image:
        key = (id(asset), width, height)
        cached = self._scaled_asset_cache.get(key)
        if cached is None:
            cached = asset.resize((width, height), Image.Resampling.NEAREST)
            self._scaled_asset_cache[key] = cached
        return cached

    def _load_asset(self, relative: str) -> Image.Image | None:
        path = self.assets / relative
        if not path.exists():
            return None
        with Image.open(path) as source:
            return source.convert("RGBA")

    def _load_frames(self, relative: str) -> list[Image.Image]:
        directory = self.assets / relative
        return [self._load_asset(str(path.relative_to(self.assets))) for path in sorted(directory.glob("*.png"))]

    @staticmethod
    def _paste_frame(
        image: Image.Image, frames: list[Image.Image], frame: int, position: tuple[int, int], target_height: int
    ) -> None:
        if not frames:
            return
        sprite = frames[frame % len(frames)]
        bounds = _shared_alpha_bounds(frames)
        if bounds:
            sprite = sprite.crop(bounds)
        if sprite.height != target_height:
            width = max(1, round(sprite.width * target_height / sprite.height))
            sprite = sprite.resize((width, target_height), Image.Resampling.NEAREST)
        image.paste(sprite, position, sprite)


def _shared_alpha_bounds(frames: list[Image.Image]) -> tuple[int, int, int, int] | None:
    """Use one crop for an animation so pose changes never alter sprite scale."""
    bounds = [frame.getchannel("A").getbbox() for frame in frames if frame.mode == "RGBA"]
    visible = [bound for bound in bounds if bound]
    if not visible:
        return None
    return (
        min(bound[0] for bound in visible),
        min(bound[1] for bound in visible),
        max(bound[2] for bound in visible),
        max(bound[3] for bound in visible),
    )


def _diegetic_event_label(category) -> str:
    labels = {
        "pull_request": "ASTEROID DETECTED",
        "review_requested": "MINERAL SAMPLING",
        "pr_approved": "SAMPLE CERTIFIED",
        "merge": "CARGO REFINED",
        "pr_closed": "TARGET ABANDONED",
        "build_broken": "REFINERY UNSTABLE",
        "deploy_started": "JUMP PREPARATION",
        "deploy_completed": "JUMP COMPLETE",
    }
    return labels.get(getattr(category, "value", str(category)), "SHIP LOG UPDATED")


def _seeded_room_layout(seed: int) -> dict[tuple[int, int], str]:
    rng = random.Random(seed)
    cells = {(0, 0)}
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    while len(cells) < 6:
        anchor = rng.choice(sorted(cells))
        dx, dy = rng.choice(directions)
        candidate = (anchor[0] + dx, anchor[1] + dy)
        if max(abs(candidate[0]), abs(candidate[1])) <= 2:
            cells.add(candidate)

    ordered = sorted(cells, key=lambda cell: (cell[0] - cell[1], cell[0] + cell[1]))
    prow = max(ordered, key=lambda cell: (cell[0] - cell[1], -(cell[0] + cell[1])))
    remaining = [cell for cell in ordered if cell != prow]
    roles = ["REACTOR", "LAB", "CARGO", "CREW", "ENGINEERING"]
    rng.shuffle(roles)
    layout = {prow: "BRIDGE"}
    layout.update(zip(remaining, roles))
    return layout


def _seeded_walk_route(rooms: dict[tuple[int, int], str]) -> list[tuple[int, int]]:
    start = next(cell for cell, room in rooms.items() if room == "BRIDGE")
    route = [start]
    visited = {start}

    def visit(cell: tuple[int, int]) -> None:
        neighbors = sorted(
            neighbor
            for neighbor in (
                (cell[0] + 1, cell[1]), (cell[0] - 1, cell[1]),
                (cell[0], cell[1] + 1), (cell[0], cell[1] - 1),
            )
            if neighbor in rooms
        )
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            route.append(neighbor)
            visit(neighbor)
            route.append(cell)

    visit(start)
    return route


def _crew_assignment_room(asteroids: tuple[AsteroidRecord, ...]) -> str:
    """Translate the current PR lifecycle into a diegetic work destination."""
    target = _active_mining_asteroid(asteroids)
    if target is None:
        return "BRIDGE"
    return {
        "detected": "BRIDGE",
        "sampling": "LAB",
        "certified": "CARGO",
        "unstable": "ENGINEERING",
    }.get(target.processing_state, "BRIDGE")


def _shortest_room_route(
    rooms: dict[tuple[int, int], str], start: tuple[int, int], target: tuple[int, int]
) -> list[tuple[int, int]]:
    """Find a connected room-only path; black space can never enter the route."""
    if start == target:
        return [start]
    frontier = [start]
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    for cell in frontier:
        for neighbor in (
            (cell[0] + 1, cell[1]), (cell[0] - 1, cell[1]),
            (cell[0], cell[1] + 1), (cell[0], cell[1] - 1),
        ):
            if neighbor not in rooms or neighbor in parents:
                continue
            parents[neighbor] = cell
            frontier.append(neighbor)
            if neighbor == target:
                path = [target]
                while path[-1] != start:
                    path.append(parents[path[-1]])
                return list(reversed(path))
    return [start]


def _task_route_phase(
    route: list[tuple[int, int]], now: datetime, step_seconds: float = 3.0, work_seconds: float = 7.0
) -> tuple[tuple[int, int], tuple[int, int], float, bool]:
    """Cycle from station to assigned room, work there, then return calmly."""
    if len(route) <= 1:
        cell = route[0]
        return cell, cell, 0.0, True
    step = max(0.1, step_seconds)
    travel = (len(route) - 1) * step
    idle_seconds = 5.0
    cycle = travel * 2 + max(0.1, work_seconds) + idle_seconds
    phase = now.timestamp() % cycle

    if phase < travel:
        edge = min(len(route) - 2, int(phase // step))
        return route[edge], route[edge + 1], (phase % step) / step, False
    phase -= travel
    if phase < work_seconds:
        return route[-1], route[-1], 0.0, True
    phase -= work_seconds
    if phase < travel:
        reverse_route = list(reversed(route))
        edge = min(len(reverse_route) - 2, int(phase // step))
        return reverse_route[edge], reverse_route[edge + 1], (phase % step) / step, False
    return route[0], route[0], 0.0, False


def _movement_direction(start: tuple[int, int], end: tuple[int, int]) -> str:
    return {
        (1, 0): "south-east",
        (-1, 0): "north-west",
        (0, 1): "south-west",
        (0, -1): "north-east",
        (0, 0): "south",
    }.get((end[0] - start[0], end[1] - start[1]), "south")


def _crew_is_working(now: datetime, offset_seconds: int = 0) -> bool:
    """Alternate calm idle and diegetic work loops without external timers."""
    return (int(now.timestamp()) + offset_seconds) % 12 < 8


def _manual_crew_task(config: dict, crew_id: str) -> str | None:
    tasks = config.get("manual_tasks", {})
    if not isinstance(tasks, dict):
        return None
    value = tasks.get(crew_id)
    return str(value).strip().lower() if value else None


def _active_mining_asteroid(asteroids: tuple[AsteroidRecord, ...]) -> AsteroidRecord | None:
    priority = {"sampling": 0, "certified": 1, "unstable": 2, "detected": 3}
    candidates = [asteroid for asteroid in asteroids if asteroid.processing_state in priority]
    return min(candidates, key=lambda asteroid: (priority[asteroid.processing_state], asteroid.updated_at), default=None)


def _drone_progress(state: str, updated_at: str, now: datetime) -> float | None:
    try:
        changed_at = datetime.fromisoformat(updated_at)
        age = max(0.0, (now - changed_at).total_seconds())
    except (TypeError, ValueError):
        age = 0.0
    if state == "sampling":
        return min(1.0, age / 5.0)
    if state == "certified":
        return max(0.0, 1.0 - age / 5.0) if age <= 8.0 else None
    if state == "unstable":
        return 1.0
    if state == "detected":
        return 0.0
    return None


def _mining_bay_progress(resources: dict[str, int], prs_per_tier: int = 60) -> tuple[int, int, int]:
    """Return durable bay tier and progress within its long-term PR milestone."""
    target = max(1, prs_per_tier)
    refined = max(0, resources.get("refined_alloy", 0))
    return 1 + refined // target, refined % target, target


def _mining_bay_tier(resources: dict[str, int], prs_per_tier: int = 60) -> int:
    return _mining_bay_progress(resources, prs_per_tier)[0]


def _crew_position(tile_position: tuple[int, int], scale: float = 1.0) -> tuple[int, int]:
    return tile_position[0] + round(48 * scale), tile_position[1] + round(50 * scale)


def _doorway_crew_position(
    start_room: tuple[int, int], end_room: tuple[int, int], scale: float = 1.0
) -> tuple[int, int]:
    """Place the crew sprite's feet in the center of the shared door opening."""
    start_center = (start_room[0] + round(64 * scale), start_room[1] + round(82 * scale))
    end_center = (end_room[0] + round(64 * scale), end_room[1] + round(82 * scale))
    door_center = ((start_center[0] + end_center[0]) // 2, (start_center[1] + end_center[1]) // 2)
    return door_center[0] - round(6 * scale), door_center[1] - round(19 * scale)


def _local_doorway_position(direction: tuple[int, int], scale: float = 1.0) -> tuple[int, int]:
    """Return the shared corridor center in room-local isometric coordinates."""
    dx, dy = direction
    return (
        round((64 + (dx - dy) * ROOM_STEP_X / 2) * scale),
        round((82 + (dx + dy) * ROOM_STEP_Y / 2) * scale),
    )


def _should_cut_shared_wall(
    cell: tuple[int, int], neighbor: tuple[int, int], rooms: dict[tuple[int, int], str]
) -> bool:
    """Cut only the foreground wall; the connected room behind supplies the visible floor."""
    return neighbor in rooms and (sum(cell), cell[0]) > (sum(neighbor), neighbor[0])


def _door_open_amount(progress: float) -> float:
    """Open before the crew reaches the wall, then close after it has crossed."""
    clamped = max(0.0, min(1.0, progress))
    if clamped < 0.2:
        return clamped / 0.2
    if clamped <= 0.8:
        return 1.0
    return (1.0 - clamped) / 0.2


def _route_via_doorway(
    start: tuple[int, int], doorway: tuple[int, int], end: tuple[int, int], progress: float
) -> tuple[int, int]:
    """Route between rooms through the explicit doorway instead of the baked wall."""
    clamped = max(0.0, min(1.0, progress))
    if clamped <= 0.5:
        segment_start, segment_end, segment_progress = start, doorway, clamped * 2
    else:
        segment_start, segment_end, segment_progress = doorway, end, (clamped - 0.5) * 2
    return (
        round(segment_start[0] + (segment_end[0] - segment_start[0]) * segment_progress),
        round(segment_start[1] + (segment_end[1] - segment_start[1]) * segment_progress),
    )
