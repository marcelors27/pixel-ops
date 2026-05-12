from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.plugins.pokemon.game.day_night import day_night_palette
from pixel_ops.events.base import WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.plugins.pokemon.game.encounter_system import EncounterSystem
from pixel_ops.plugins.pokemon.game.map_routes import MapArea, MapRouteManager
from pixel_ops.plugins.pokemon.game.pokemon_selector import PokemonSelector
from pixel_ops.plugins.pokemon.game.state_machine import GamePhase, GameStateMachine
from pixel_ops.plugins.pokemon.game.world import World
from pixel_ops.render.hud import draw_hud
from pixel_ops.render.renderer import PixelRenderer
from pixel_ops.plugins.pokemon.render.sprites import (
    AshSpriteSet,
    PokemonSpriteStore,
    battle_ash_frame,
    pokeball,
    scale_sprite,
)
from pixel_ops.plugins.pokemon.render.text_box import draw_text_box
from pixel_ops.plugins.pokemon.render.tiles import TILE, draw_house, draw_lamp, draw_tree, make_tile

BATTLE_POKEMON_X = 220
BATTLE_POKEMON_BASE_OFFSET_Y = 96
BATTLE_ASH_X = 8
BATTLE_ASH_BOTTOM_PAD = 2


class OverworldScene:
    def __init__(
        self,
        width: int,
        height: int,
        primary_timezone: str,
        scanlines: bool = True,
        pokemon_api: PokeApiClient | None = None,
        lazy_download: bool = True,
        scene_fps: int = 10,
        game_config: dict | None = None,
        ash_assets_dir: Path | None = None,
        event_sources: list | None = None,
    ):
        cfg = game_config or {}
        encounter_cfg = cfg.get("encounter", {})
        self.renderer = PixelRenderer(width, height)
        self.primary_timezone = primary_timezone
        self.scanlines = scanlines
        self.scene_fps = scene_fps
        self.frame = 0
        self.overworld_walk_frame = 0
        self.current_map_area: MapArea | None = None
        self.current_map_timestamp = 0.0
        self.ash_direction = "down"
        self.ash_x = int(cfg.get("ash_x", 118))
        self.ash_y = int(cfg.get("ash_y", 312))
        self.pokemon_x = int(cfg.get("pokemon_x", 220))
        self.pokemon_y = int(cfg.get("pokemon_y", 300))
        self.walk_start_x = int(cfg.get("walk_start_x", 28))
        self.encounter_x = int(cfg.get("encounter_x", 132))
        self.walk_exit_x = int(cfg.get("walk_exit_x", 258))
        self.hud_height = int(cfg.get("hud_height", 72))
        self.text_box_height = int(cfg.get("text_box_height", 76))
        self.static_background = bool(cfg.get("static_background", True))
        self.world = World(speed_px=float(cfg.get("world_speed_px", 1.4)), biome_duration_frames=scene_fps * 18)
        self.state = GameStateMachine.from_seconds(scene_fps, encounter_cfg)
        self.encounter_system = EncounterSystem(
            PokemonSelector(
                pokemon_api,
                lazy_download=lazy_download,
                config=cfg.get("events", {}),
            ),
            sources=event_sources or [],
            queue_limit=int(cfg.get("events", {}).get("queue_limit", 6)),
        )
        self.encounter = self.encounter_system.ambient_context("morning")
        self.pokemon_sprites = PokemonSpriteStore()
        self._previous_sprite_box: tuple[int, int, int, int] | None = None
        self._previous_battle_sprite_box: tuple[int, int, int, int] | None = None
        self._previous_text_key: tuple[str, bool] | None = None
        self._previous_was_battle = False
        self._previous_map_area_id: str | None = None
        asset_root = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
        self.asset_root = ash_assets_dir or asset_root
        self.ash_sprites = AshSpriteSet(
            self.asset_root,
            scene_fps=scene_fps,
            require_local=bool(cfg.get("require_ash_sprite", False)),
        )
        map_viewport = (self.renderer.width, self.text_box[1] - self.hud_height - 4)
        self.map_routes = MapRouteManager(
            Path(__file__).resolve().parents[1] / "assets/maps/firered_leafgreen",
            map_viewport,
            switch_seconds=int(cfg.get("map_switch_seconds", 300)),
        )
        self._battle_backgrounds: dict[str, Image.Image] = {}

    @property
    def text_box(self) -> tuple[int, int, int, int]:
        return (8, self.renderer.height - self.text_box_height - 2, 312, self.renderer.height - 2)

    @property
    def hud_box(self) -> tuple[int, int, int, int]:
        return (0, 0, self.renderer.width, self.hud_height)

    @property
    def map_box(self) -> tuple[int, int, int, int]:
        return (0, self.hud_height, self.renderer.width, self.text_box[1] - 4)

    def advance(self, now: datetime | None = None) -> GamePhase:
        self.frame += 1
        if now:
            self.encounter_system.poll(now)
        phase, changed = self.state.tick()
        if changed and phase == GamePhase.ENCOUNTER_START:
            base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
            pal = day_night_palette(base_now.hour)
            encounter = self.encounter_system.next_encounter(pal.phase)
            if encounter is None:
                self.encounter = self.encounter_system.ambient_context(pal.phase)
                self.state.phase = GamePhase.WALKING
                self.state.frame_in_phase = 0
                return GamePhase.WALKING
            self.encounter = encounter
        moving = phase in (GamePhase.WALKING, GamePhase.RESUME_WALKING)
        if moving:
            self.overworld_walk_frame += 1
        if not self.static_background:
            self.world.tick(moving=moving)
        return phase

    def render(
        self,
        people: list[PersonTime],
        event: CalendarEvent | None,
        now: datetime | None = None,
        pull_requests: list[PullRequestSummary] | None = None,
    ):
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        phase = self.advance(base_now)
        return self.render_full(people, event, base_now, phase, pull_requests=pull_requests)

    def render_full(
        self,
        people: list[PersonTime],
        event: CalendarEvent | None,
        now: datetime | None = None,
        phase: GamePhase | None = None,
        pull_requests: list[PullRequestSummary] | None = None,
    ) -> Image.Image:
        phase = phase or self.state.phase
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        pal = day_night_palette(base_now.hour)
        img = self.render_base(people, event, base_now, pull_requests=pull_requests)
        if self._is_battle_phase(phase):
            self._draw_battle_scene(img, phase, pal)
        else:
            self._draw_sprites(img, phase, pal)
        draw_text_box(img, self.text_box, self.encounter.message_for(phase), pal, self.frame)
        if self.scanlines:
            img = self.renderer.apply_scanlines(img)
        return img

    def render_base(
        self,
        people: list[PersonTime],
        event: CalendarEvent | None,
        now: datetime | None = None,
        pull_requests: list[PullRequestSummary] | None = None,
    ) -> Image.Image:
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        pal = day_night_palette(base_now.hour)
        img = self.renderer.canvas(pal.sky_top)
        draw = ImageDraw.Draw(img)

        self._draw_sky(draw, pal)
        self._draw_world(img, draw, pal, base_now)
        draw_hud(draw, people, event, base_now, pal, pull_requests=pull_requests)
        return img

    def render_dirty_regions(self, base: Image.Image, now: datetime | None = None) -> list[tuple[int, int, Image.Image]]:
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        phase = self.advance(base_now)
        pal = day_night_palette(base_now.hour)
        regions: list[tuple[int, int, Image.Image]] = []

        if self._is_battle_phase(phase):
            if not self._previous_was_battle:
                x0, y0, _, _ = self.battle_box
                region = self._battle_background_image(pal).copy()
                self._draw_battle_sprites(region, phase, offset=(x0, y0))
                regions.append((x0, y0, region))
            else:
                current_box = self._battle_sprite_box_for_phase(phase)
                sprite_box = self._union_boxes(self._previous_battle_sprite_box, current_box)
                if sprite_box:
                    x0, y0, _, _ = self.battle_box
                    bg = self._battle_background_image(pal)
                    local_box = (sprite_box[0] - x0, sprite_box[1] - y0, sprite_box[2] - x0, sprite_box[3] - y0)
                    region = bg.crop(local_box)
                    self._draw_battle_sprites(region, phase, offset=(sprite_box[0], sprite_box[1]))
                    regions.append((sprite_box[0], sprite_box[1], region))
            self._previous_battle_sprite_box = self._battle_sprite_box_for_phase(phase)
            self._previous_sprite_box = None
            self._previous_was_battle = True
        else:
            if self._previous_was_battle:
                x0, y0, x1, y1 = self.map_box
                regions.append((x0, y0, base.crop(self.map_box)))
                self._previous_sprite_box = None
                self._previous_battle_sprite_box = None
                self._previous_was_battle = False
            current_area_id = self.current_map_area.area_id if self.current_map_area else None
            if current_area_id != self._previous_map_area_id:
                x0, y0, _, _ = self.map_box
                regions.append((x0, y0, base.crop(self.map_box)))
                self._previous_sprite_box = None
                self._previous_map_area_id = current_area_id
            current_box = self._sprite_box_for_phase(phase)
            sprite_box = self._union_boxes(self._previous_sprite_box, current_box)
            self._previous_sprite_box = current_box
            if sprite_box:
                region = base.crop(sprite_box)
                self._draw_sprites(region, phase, pal, offset=(sprite_box[0], sprite_box[1]))
                regions.append((sprite_box[0], sprite_box[1], region))

        text_key = (self.encounter.message_for(phase), self.frame % 20 < 10)
        if text_key != self._previous_text_key:
            self._previous_text_key = text_key
            text_box = self.text_box
            region = base.crop(text_box)
            local_box = (0, 0, text_box[2] - text_box[0], text_box[3] - text_box[1])
            draw_text_box(region, local_box, text_key[0], pal, self.frame)
            regions.append((text_box[0], text_box[1], region))

        return regions

    def prime_dirty_tracking(self) -> None:
        phase = self.state.phase
        self._previous_sprite_box = self._sprite_box_for_phase(phase)
        self._previous_battle_sprite_box = self._battle_sprite_box_for_phase(phase) if self._is_battle_phase(phase) else None
        self._previous_text_key = (self.encounter.message_for(phase), self.frame % 20 < 10)
        self._previous_was_battle = self._is_battle_phase(phase)
        self._previous_map_area_id = self.current_map_area.area_id if self.current_map_area else None

    def _draw_sky(self, draw: ImageDraw.ImageDraw, pal) -> None:
        sky_bottom = self.hud_height + 40
        for y in range(self.hud_height, sky_bottom):
            t = (y - self.hud_height) / max(1, sky_bottom - self.hud_height)
            color = tuple(int(pal.sky_top[i] * (1 - t) + pal.sky_bottom[i] * t) for i in range(3))
            draw.line((0, y, self.renderer.width, y), fill=color)
        if pal.phase == "night":
            for x, y in ((38, 150), (82, 162), (166, 146), (244, 158), (286, 168)):
                draw.point((x, y), fill=pal.light)
                draw.point((x + 1, y), fill=pal.light)
        else:
            draw.ellipse((252, 144, 286, 178), fill=pal.light, outline=pal.panel_shadow)

    def _draw_world(self, img, draw: ImageDraw.ImageDraw, pal, now: datetime) -> None:
        area = self.map_routes.area_for_timestamp(now.timestamp())
        if area:
            self.current_map_area = area
            self.current_map_timestamp = now.timestamp()
            img.paste(self._map_background_image(area, pal), (0, self.hud_height))
            return

        top = self.hud_height + 40
        bottom = self.renderer.height - self.text_box_height - 14
        tiles = {name: make_tile(name, pal) for name in ("grass", "tall_grass", "path")}
        trail_top = self.ash_y + 34
        trail_bottom = min(bottom, trail_top + 56)
        for y in range(top, bottom, TILE):
            if trail_top <= y < trail_bottom:
                name = "path"
            elif y < top + 48:
                name = "tall_grass" if (y // TILE) % 2 else "grass"
            else:
                name = "grass"
            for x in range(0, self.renderer.width, TILE):
                img.paste(tiles[name], (x, y))

        self._draw_static_props(draw, pal, top, trail_top)

    def _tile_row_for_biome(self) -> list[str]:
        biome = self.world.biome
        if biome == "town":
            return ["pavement", "pavement", "path", "grass"]
        if biome == "route":
            return ["grass", "path", "grass", "tall_grass", "grass"]
        if biome == "grass":
            return ["tall_grass", "grass", "tall_grass", "path"]
        if biome == "center":
            return ["pavement", "path", "grass", "pavement"]
        return ["grass", "path", "grass", "pavement"]

    def _draw_biome_props(self, draw: ImageDraw.ImageDraw, pal, top: int) -> None:
        offset = -(int(self.world.scroll_x) % 180)
        for base_x in range(offset - 180, self.renderer.width + 220, 180):
            if self.world.biome == "center":
                draw_house(draw, base_x + 24, top - 16, pal, center=True)
                draw_lamp(draw, base_x + 112, top + 22, pal)
            elif self.world.biome in ("town", "village"):
                draw_house(draw, base_x + 16, top - 10, pal)
                draw_tree(draw, base_x + 112, top + 26, pal)
                draw_lamp(draw, base_x + 150, top + 42, pal)
            elif self.world.biome == "route":
                draw_tree(draw, base_x + 18, top + 8, pal)
                draw_tree(draw, base_x + 128, top + 42, pal)
            else:
                draw_tree(draw, base_x + 58, top + 10, pal)

    def _draw_static_props(self, draw: ImageDraw.ImageDraw, pal, top: int, trail_top: int) -> None:
        draw_house(draw, 14, top + 14, pal, center=True)
        draw_house(draw, 218, top + 18, pal)
        draw_tree(draw, 94, top + 18, pal)
        draw_tree(draw, 170, top + 28, pal)
        draw_lamp(draw, 140, trail_top - 28, pal)
        draw.rectangle((0, trail_top - 4, self.renderer.width, trail_top - 1), fill=pal.path_dark)
        draw.rectangle((0, trail_top + 56, self.renderer.width, trail_top + 59), fill=pal.path_dark)

    def _map_background_image(self, area: MapArea, pal) -> Image.Image:
        return self.map_routes.background_for_area(
            area,
            pal.phase,
            None if pal.phase == "morning" else lambda image: self._tint_for_day_phase(image, pal),
        )

    @property
    def battle_box(self) -> tuple[int, int, int, int]:
        return self.map_box

    def _battle_pokemon_base_y(self) -> int:
        _, y0, _, y1 = self.battle_box
        return min(y1 - 58, y0 + BATTLE_POKEMON_BASE_OFFSET_Y)

    def _draw_battle_scene(self, img: Image.Image, phase: GamePhase, pal) -> None:
        x0, y0, x1, y1 = self.battle_box
        img.paste(self._battle_background_image(pal), (x0, y0))
        self._draw_battle_sprites(img, phase)

    def _battle_background_image(self, pal) -> Image.Image:
        cached = self._battle_backgrounds.get(pal.phase)
        if cached is not None:
            return cached

        x0, y0, x1, y1 = self.battle_box
        background = Image.new("RGB", (x1 - x0, y1 - y0), pal.sky_bottom)
        draw = ImageDraw.Draw(background)
        for y in range(background.height):
            t = y / max(1, background.height)
            color = tuple(int(pal.sky_bottom[i] * (1 - t) + pal.panel[i] * t) for i in range(3))
            draw.line((0, y, background.width, y), fill=color)
        for y in range(28, background.height - 18, 12):
            draw.line((12, y, background.width - 12, y), fill=pal.path_dark)

        self._draw_battle_platform(
            draw,
            (BATTLE_POKEMON_X, self._battle_pokemon_base_y() - y0),
            (124, 34),
            pal,
            near=False,
        )
        ash = scale_sprite(battle_ash_frame(1), 2)
        self._draw_battle_platform(
            draw,
            (BATTLE_ASH_X + ash.width // 2, y1 - y0 - BATTLE_ASH_BOTTOM_PAD - 16),
            (154, 42),
            pal,
            near=True,
        )
        self._battle_backgrounds[pal.phase] = background
        return background

    def _tint_for_day_phase(self, image: Image.Image, pal) -> Image.Image:
        if pal.phase == "night":
            alpha = 0.46
        elif pal.phase == "dawn":
            alpha = 0.24
        else:
            alpha = 0.14
        overlay = Image.new("RGB", image.size, pal.sky_top)
        return Image.blend(image, overlay, alpha)

    def _battle_sprite_layers(self, phase: GamePhase) -> list[tuple[Image.Image, int, int]]:
        layers: list[tuple[Image.Image, int, int]] = []
        _, y0, _, y1 = self.battle_box
        pokemon_base_y = self._battle_pokemon_base_y()
        sprite_path = self.encounter.pokemon.animated_sprite_path or self.encounter.pokemon.sprite_path
        if phase != GamePhase.CAUGHT:
            if phase == GamePhase.ENCOUNTER_START:
                pokemon_step = 0
            elif phase == GamePhase.POKEMON_APPEARS:
                pokemon_step = self.state.frame_in_phase * 3
            else:
                pokemon_step = self.state.durations[GamePhase.POKEMON_APPEARS] * 3
            poke = self.pokemon_sprites.sprite_for(sprite_path, self.encounter.pokemon.number, pokemon_step, scale=1, loop=False)
            if phase == GamePhase.ENCOUNTER_START:
                appear_progress = self.state.progress
                y_shift = int(10 * (1 - appear_progress))
                layers.append((poke, BATTLE_POKEMON_X - poke.width // 2, pokemon_base_y - poke.height + y_shift))
            else:
                layers.append((poke, BATTLE_POKEMON_X - poke.width // 2, pokemon_base_y - poke.height))

        if phase == GamePhase.ASH_THROWS:
            ash_step = 1 + min(3, int(self.state.progress * 4))
        else:
            ash_step = 1
        ash = scale_sprite(battle_ash_frame(ash_step), 2)
        layers.append((ash, BATTLE_ASH_X, y1 - ash.height - BATTLE_ASH_BOTTOM_PAD))

        if phase in (GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE):
            ball = scale_sprite(pokeball(self.frame), 2)
            if phase == GamePhase.ASH_THROWS:
                progress = self.state.progress
                start_x = 112
                start_y = y1 - 108
                end_x = BATTLE_POKEMON_X - 6
                end_y = pokemon_base_y - 2
                bx = int(start_x + (end_x - start_x) * progress)
                by = int(start_y + (end_y - start_y) * progress - 42 * progress * (1 - progress))
            else:
                shake = (-5, 5, 0, -3, 3, 0)[(self.frame // 2) % 6]
                bx = BATTLE_POKEMON_X - 6 + shake
                by = pokemon_base_y + 2
            layers.append((ball, bx, by))
        return layers

    def _draw_battle_sprites(self, img: Image.Image, phase: GamePhase, offset: tuple[int, int] = (0, 0)) -> None:
        ox, oy = offset
        for sprite, x, y in self._battle_sprite_layers(phase):
            img.paste(sprite, (x - ox, y - oy), sprite)

    def _battle_sprite_box_for_phase(self, phase: GamePhase) -> tuple[int, int, int, int] | None:
        layers = self._battle_sprite_layers(phase)
        if not layers:
            return None
        boxes = [(x, y, x + sprite.width, y + sprite.height) for sprite, x, y in layers]
        box = self._pad_box(self._union_many(boxes), 4)
        bx0, by0, bx1, by1 = self.battle_box
        return (max(bx0, box[0]), max(by0, box[1]), min(bx1, box[2]), min(by1, box[3]))

    def _draw_battle_platform(
        self,
        draw: ImageDraw.ImageDraw,
        center: tuple[int, int],
        size: tuple[int, int],
        pal,
        near: bool,
    ) -> None:
        cx, cy = center
        w, h = size
        fill = pal.grass if near else pal.grass_dark
        outline = pal.tree_dark
        draw.ellipse((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), fill=fill, outline=outline, width=2)
        draw.arc((cx - w // 2 + 10, cy - h // 2 + 7, cx + w // 2 - 10, cy + h // 2 - 6), 0, 180, fill=pal.light, width=2)

    @staticmethod
    def _is_battle_phase(phase: GamePhase) -> bool:
        return phase in (
            GamePhase.ENCOUNTER_START,
            GamePhase.POKEMON_APPEARS,
            GamePhase.ASH_THROWS,
            GamePhase.BALL_SHAKE,
            GamePhase.CAUGHT,
        )

    def enqueue_event(self, event: WorkEvent) -> None:
        self.encounter_system.enqueue(event)

    def _sprite_layers(self, phase: GamePhase) -> list[tuple[Image.Image, int, int]]:
        layers: list[tuple[Image.Image, int, int]] = []
        ash_x, route_y, direction = self._ash_pose_for_phase(phase)
        if direction:
            self.ash_direction = direction
        ash_state = f"walk_{self.ash_direction}" if phase in (GamePhase.WALKING, GamePhase.RESUME_WALKING) else f"idle_{self.ash_direction}"
        if phase == GamePhase.ASH_THROWS:
            ash_state = "catch"
        ash = self.ash_sprites.frame(ash_state, self.frame)
        walking = phase in (GamePhase.WALKING, GamePhase.RESUME_WALKING)
        step_index = int(self.frame * 6 / max(1, self.scene_fps))
        ash_y = route_y + (1 if walking and step_index % 2 else 0)
        layers.append((ash, ash_x, ash_y))

        if phase in (GamePhase.ENCOUNTER_START, GamePhase.POKEMON_APPEARS, GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE):
            sprite_path = self.encounter.pokemon.animated_sprite_path or self.encounter.pokemon.sprite_path
            poke = self.pokemon_sprites.sprite_for(sprite_path, self.encounter.pokemon.number, self.frame, scale=2)
            wobble = 1 if phase in (GamePhase.ENCOUNTER_START, GamePhase.POKEMON_APPEARS) and self.frame % 10 < 5 else 0
            if not (phase == GamePhase.ENCOUNTER_START and self.frame % 8 < 4):
                layers.append((poke, self.pokemon_x, self.pokemon_y + wobble))

        if phase in (GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE):
            ball = scale_sprite(pokeball(self.frame // 4), 2)
            if phase == GamePhase.ASH_THROWS:
                progress = self.state.progress
                bx = int(ash_x + 42 + (self.pokemon_x - ash_x - 42) * progress)
                by = int(self.ash_y + 20 - 36 * progress + 22 * progress * progress)
            else:
                shake = (-3, 3, 0, -2)[(self.frame // 4) % 4]
                bx = self.pokemon_x + 12 + shake
                by = self.pokemon_y + 22
            layers.append((ball, bx, by))
        return layers

    def _draw_sprites(self, img: Image.Image, phase: GamePhase, pal, offset: tuple[int, int] = (0, 0)) -> None:
        ox, oy = offset
        for sprite, x, y in self._sprite_layers(phase):
            img.paste(sprite, (x - ox, y - oy), sprite)

    def _sprite_box_for_phase(self, phase: GamePhase) -> tuple[int, int, int, int] | None:
        layers = self._sprite_layers(phase)
        if not layers:
            return None
        boxes = [(x, y, x + sprite.width, y + sprite.height) for sprite, x, y in layers]
        return self._pad_box(self._union_many(boxes), 4)

    def _pad_box(self, box: tuple[int, int, int, int], pad: int) -> tuple[int, int, int, int]:
        return (
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(self.renderer.width, box[2] + pad),
            min(self.renderer.height, box[3] + pad),
        )

    @staticmethod
    def _union_many(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
        return (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )

    @staticmethod
    def _union_boxes(
        a: tuple[int, int, int, int] | None,
        b: tuple[int, int, int, int] | None,
    ) -> tuple[int, int, int, int] | None:
        if a is None:
            return b
        if b is None:
            return a
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))

    def _ash_x_for_phase(self, phase: GamePhase) -> int:
        if phase == GamePhase.WALKING:
            return int(self.walk_start_x + (self.encounter_x - self.walk_start_x) * self.state.progress)
        if phase == GamePhase.RESUME_WALKING:
            return int(self.encounter_x + (self.walk_exit_x - self.encounter_x) * self.state.progress)
        return self.encounter_x

    def _ash_pose_for_phase(self, phase: GamePhase) -> tuple[int, int, str | None]:
        if phase in (GamePhase.WALKING, GamePhase.RESUME_WALKING) and self.current_map_area:
            (x, y), direction = self.map_routes.pose_on_route(self.current_map_area, self.overworld_walk_frame)
            return x, self.hud_height + y, direction
        return self._ash_x_for_phase(phase), self.ash_y, None
