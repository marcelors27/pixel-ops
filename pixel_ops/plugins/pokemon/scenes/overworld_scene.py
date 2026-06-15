from __future__ import annotations

import hashlib
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from pixel_ops.data_sources.ai_usage import AIUsageSnapshot
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.companions import CompanionSnapshot
from pixel_ops.data_sources.media import MediaNowPlaying
from pixel_ops.data_sources.pc_stats import PCStatsSnapshot
from pixel_ops.data_sources.tasks import TaskSnapshot
from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.plugins.pokemon.game.day_night import day_night_palette
from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.plugins.ai.plugin import AiDecisionPlugin
from pixel_ops.plugins.pokemon.game.encounter_system import EncounterSystem
from pixel_ops.plugins.pokemon.game.mood_engine import MoodEngine
from pixel_ops.plugins.pokemon.game.map_routes import MapArea, MapRouteManager
from pixel_ops.plugins.pokemon.game.pokemon_selector import PokemonSelector
from pixel_ops.plugins.pokemon.game.state_machine import GamePhase, GameStateMachine
from pixel_ops.plugins.pokemon.game.world import World
from pixel_ops.render.fonts import font, font_scale_for_canvas, scaled_px
from pixel_ops.render.hud import draw_hud, hud_palette_for_kind
from pixel_ops.render.renderer import PixelRenderer
from pixel_ops.plugins.pokemon.render.sprites import (
    AshSpriteSet,
    NpcSpriteSet,
    PokemonSpriteStore,
    battle_ash_frame,
    pokeball,
    scale_sprite,
)
from pixel_ops.plugins.pokemon.render.battle_ambience import apply_battle_ambience
from pixel_ops.plugins.pokemon.render.social_effects import draw_social_world_effects
from pixel_ops.plugins.pokemon.render.text_box import (
    draw_text_box,
    scroll_line_start,
    text_box_top_padding,
    text_box_visible_lines,
    wrap_text_lines,
)
from pixel_ops.plugins.pokemon.render.tiles import TILE, draw_house, draw_lamp, draw_tree, make_tile

BATTLE_POKEMON_X = 220
BATTLE_POKEMON_BASE_OFFSET_Y = 96
BATTLE_ASH_X = 8
BATTLE_ASH_BOTTOM_PAD = 2


@dataclass
class VoiceCompanionState:
    x: float
    y: float
    target_x: float
    target_y: float
    direction: str
    next_target_frame: int
    speed: float
    rng: random.Random
    variant: int


@dataclass(frozen=True)
class CapturedPokemonRecord:
    number: int
    name: str
    cause: str
    captured_at: datetime


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
        companion_config: dict | None = None,
        display_layout: dict | None = None,
        layout_theme: str | None = None,
        ash_assets_dir: Path | None = None,
        event_sources: list | None = None,
        ai_plugin: AiDecisionPlugin | None = None,
        capture_store: Any | None = None,
    ):
        cfg = game_config or {}
        self.companion_config = companion_config or {}
        self.display_layout = display_layout or {}
        self.layout_theme = layout_theme or "default"
        self.movement_config = cfg.get("movement", {}) if isinstance(cfg.get("movement", {}), dict) else {}
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
        self.route_speed_px = float(cfg.get("route_speed_px", 2.6))
        self.vertical_wander_px = int(cfg.get("vertical_wander_px", 42))
        self.vertical_wander_frames = max(1, int(float(cfg.get("vertical_wander_seconds", 1.4)) * scene_fps))
        self.horizontal_wander_frames = max(self.vertical_wander_frames, int(1.8 * scene_fps))
        self.vertical_wander_speed_px = float(cfg.get("vertical_wander_speed_px", 2.4))
        self.vertical_wander_rng = random.Random(int(cfg.get("vertical_wander_seed", 421)))
        self._ash_motion_axis = "horizontal"
        self._ash_motion_until_frame = 0
        self._ash_render_x: float | None = None
        self._ash_render_y: float | None = None
        self._ash_vertical_target_y: float | None = None
        self.hud_height = int(cfg.get("hud_height", 72))
        self.text_box_height = int(cfg.get("text_box_height", 76))
        self.static_background = bool(cfg.get("static_background", True))
        self.world = World(speed_px=float(cfg.get("world_speed_px", 1.4)), biome_duration_frames=scene_fps * 18)
        self.state = GameStateMachine.from_seconds(scene_fps, encounter_cfg)
        self.mood_engine = MoodEngine()
        self.current_mood = self.mood_engine.state(datetime.now(ZoneInfo(self.primary_timezone)))
        self.event_sources = event_sources or []
        self.companion_snapshot: CompanionSnapshot | None = None
        self._voice_companions: dict[str, VoiceCompanionState] = {}
        self.encounter_system = EncounterSystem(
            PokemonSelector(
                pokemon_api,
                lazy_download=lazy_download,
                config=cfg.get("events", {}),
                ai_plugin=ai_plugin,
            ),
            sources=self.event_sources,
            queue_limit=int(cfg.get("events", {}).get("queue_limit", 6)),
            on_event=self.mood_engine.observe,
        )
        self.encounter = self.encounter_system.idle_context()
        self.capture_store = capture_store
        self.captured_pokemon: deque[CapturedPokemonRecord] = deque(maxlen=10)
        self._load_captured_pokemon()
        self.pokemon_sprites = PokemonSpriteStore()
        self._previous_sprite_box: tuple[int, int, int, int] | None = None
        self._previous_battle_sprite_box: tuple[int, int, int, int] | None = None
        self._previous_text_key: tuple[str, bool, int] | None = None
        self._text_scroll_key = ""
        self._text_scroll_started_frame = 0
        self._previous_was_battle = False
        self._previous_map_area_id: str | None = None
        self._actor_map_area_id: str | None = None
        asset_root = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
        self.asset_root = ash_assets_dir or asset_root
        self.ash_sprites = AshSpriteSet(
            self.asset_root,
            scene_fps=scene_fps,
            require_local=bool(cfg.get("require_ash_sprite", False)),
        )
        self.npc_sprites = NpcSpriteSet(self.asset_root, scene_fps=scene_fps, scale=2)
        map_viewport = (
            max(1, self.map_box[2] - self.map_box[0]),
            max(1, self.map_box[3] - self.map_box[1]),
        )
        self.map_routes = MapRouteManager(
            Path(__file__).resolve().parents[1] / "assets/maps/firered_leafgreen_clean",
            map_viewport,
            switch_seconds=int(cfg.get("map_switch_seconds", 60)),
            allowed_map_keys=self._configured_walkable_map_keys(),
            walkable_source_rects=self._configured_walkable_source_rects(),
        )
        self._battle_backgrounds: dict[str, Image.Image] = {}

    def _configured_walkable_map_keys(self) -> set[str]:
        return set(self._configured_walkable_source_rects())

    def _configured_walkable_source_rects(self) -> dict[str, list[tuple[int, int, int, int]]]:
        if not isinstance(self.movement_config, dict):
            return {}
        raw_walkable = self.movement_config.get("walkable", {})
        raw_rects = raw_walkable.get("source_rects", []) if isinstance(raw_walkable, dict) else []
        if not isinstance(raw_rects, list):
            return {}
        rects_by_map: dict[str, list[tuple[int, int, int, int]]] = {}
        for item in raw_rects:
            if not isinstance(item, dict):
                continue
            map_id = str(item.get("map") or item.get("map_id") or "").strip()
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            w = int(item.get("w", item.get("width", 0)))
            h = int(item.get("h", item.get("height", 0)))
            if map_id and w > 0 and h > 0:
                rects_by_map.setdefault(map_id, []).append((x, y, x + w, y + h))
        return rects_by_map

    @property
    def text_box(self) -> tuple[int, int, int, int]:
        return self._layout_box(
            "text_box",
            (8, self.renderer.height - self.text_box_height - 2, self.renderer.width - 8, self.renderer.height - 2),
        )

    @property
    def hud_box(self) -> tuple[int, int, int, int]:
        return (0, 0, self.renderer.width, self.hud_height)

    @property
    def map_box(self) -> tuple[int, int, int, int]:
        return self._layout_box("game", (0, self.hud_height, self.renderer.width, self.text_box[1] - 4))

    def _layout_box(self, key: str, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        raw = self.display_layout.get(key) if isinstance(self.display_layout, dict) else None
        if not isinstance(raw, dict) and isinstance(self.display_layout, dict):
            for item_key, item in self.display_layout.items():
                if isinstance(item, dict) and str(item.get("kind") or item_key) == key:
                    raw = item
                    break
        if not isinstance(raw, dict):
            return fallback
        try:
            x = int(raw.get("x", fallback[0]))
            y = int(raw.get("y", fallback[1]))
            width = int(raw.get("width", fallback[2] - fallback[0]))
            height = int(raw.get("height", fallback[3] - fallback[1]))
        except (TypeError, ValueError):
            return fallback
        x0 = max(0, min(self.renderer.width - 1, x))
        y0 = max(0, min(self.renderer.height - 1, y))
        x1 = max(x0 + 1, min(self.renderer.width, x0 + max(1, width)))
        y1 = max(y0 + 1, min(self.renderer.height, y0 + max(1, height)))
        return x0, y0, x1, y1

    def advance(self, now: datetime | None = None, weather: WeatherState | None = None) -> GamePhase:
        self.frame += 1
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        self.encounter_system.poll(base_now)
        phase, changed = self.state.tick(base_now)
        if changed and phase == GamePhase.ENCOUNTER_START:
            pal = day_night_palette(base_now.hour)
            encounter = self.encounter_system.next_encounter(pal.phase, now=base_now, weather=weather)
            if encounter is None:
                if not self.encounter_system.queue:
                    self.encounter = self.encounter_system.idle_context()
                self.state.set_phase(GamePhase.WALKING, base_now)
                return GamePhase.WALKING
            self.encounter = encounter
            self.state.require_phase_seconds(
                GamePhase.POKEMON_APPEARS,
                self._message_scroll_seconds(encounter.message_for(GamePhase.POKEMON_APPEARS)),
            )
        elif changed and phase == GamePhase.CAUGHT:
            self._record_capture(base_now)
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
        weather: WeatherState | None = None,
        ai_usage: AIUsageSnapshot | None = None,
        pc_stats: PCStatsSnapshot | None = None,
        task_snapshot: TaskSnapshot | None = None,
        media: MediaNowPlaying | None = None,
        companion_snapshot: CompanionSnapshot | None = None,
        today_events: list[CalendarEvent] | None = None,
        gamification=None,
        work_events: list[WorkEvent] | None = None,
    ):
        with font_scale_for_canvas(self.renderer.width, self.renderer.height):
            base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
            phase = self.advance(base_now, weather=weather)
            recent_events = work_events if work_events is not None else self.encounter_system.recent(base_now)
            self.companion_snapshot = companion_snapshot
            return self.render_full(
                people,
                event,
                base_now,
                phase,
                pull_requests=pull_requests,
                weather=weather,
                ai_usage=ai_usage,
                pc_stats=pc_stats,
                task_snapshot=task_snapshot,
                media=media,
                companion_snapshot=companion_snapshot,
                today_events=today_events,
                gamification=gamification,
                work_events=recent_events,
            )

    def render_full(
        self,
        people: list[PersonTime],
        event: CalendarEvent | None,
        now: datetime | None = None,
        phase: GamePhase | None = None,
        pull_requests: list[PullRequestSummary] | None = None,
        weather: WeatherState | None = None,
        ai_usage: AIUsageSnapshot | None = None,
        pc_stats: PCStatsSnapshot | None = None,
        task_snapshot: TaskSnapshot | None = None,
        media: MediaNowPlaying | None = None,
        companion_snapshot: CompanionSnapshot | None = None,
        today_events: list[CalendarEvent] | None = None,
        gamification=None,
        work_events: list[WorkEvent] | None = None,
    ) -> Image.Image:
        with font_scale_for_canvas(self.renderer.width, self.renderer.height):
            phase = phase or self.state.phase
            base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
            if companion_snapshot is not None:
                self.companion_snapshot = companion_snapshot
            pal = day_night_palette(base_now.hour)
            img = self.render_base(
                people,
                event,
                base_now,
                pull_requests=pull_requests,
                weather=weather,
                ai_usage=ai_usage,
                pc_stats=pc_stats,
                task_snapshot=task_snapshot,
                media=media,
                today_events=today_events,
                gamification=gamification,
                work_events=work_events,
            )
            if self._is_battle_phase(phase):
                self._draw_battle_scene(img, phase, pal)
            else:
                self._draw_sprites(img, phase, pal)
            message = self._display_message(self.encounter.message_for(phase))
            draw_text_box(img, self.text_box, message, pal, self._text_frame(message))
            if self.scanlines:
                img = self.renderer.apply_scanlines(img)
            return img

    def render_base(
        self,
        people: list[PersonTime],
        event: CalendarEvent | None,
        now: datetime | None = None,
        pull_requests: list[PullRequestSummary] | None = None,
        weather: WeatherState | None = None,
        ai_usage: AIUsageSnapshot | None = None,
        pc_stats: PCStatsSnapshot | None = None,
        task_snapshot: TaskSnapshot | None = None,
        media: MediaNowPlaying | None = None,
        today_events: list[CalendarEvent] | None = None,
        gamification=None,
        work_events: list[WorkEvent] | None = None,
    ) -> Image.Image:
        with font_scale_for_canvas(self.renderer.width, self.renderer.height):
            base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
            pal = day_night_palette(base_now.hour)
            img = self.renderer.canvas(pal.panel_shadow)
            draw = ImageDraw.Draw(img)

            self._draw_sky(draw, pal)
            self._draw_world(img, draw, pal, base_now, weather)
            self.current_mood = self.mood_engine.state(base_now, weather=weather, calendar_event=event)
            draw_social_world_effects(img, self.map_box, self.current_mood, self.frame)
            self._draw_movement_debug_overlay(draw, pal)
            draw_hud(
                draw,
                people,
                event,
                base_now,
                pal,
                pull_requests=pull_requests,
                ai_usage=ai_usage,
                weather=weather,
                work_events=work_events,
                pc_stats=pc_stats,
                task_snapshot=task_snapshot,
                media=media,
                today_events=today_events,
                gamification=gamification,
                layout=self.display_layout,
                layout_theme=self.layout_theme,
            )
            self._draw_pokemon_capture_huds(draw, hud_palette_for_kind(pal, self.layout_theme, "pokemon_captures"))
            return img

    def _record_capture(self, now: datetime) -> None:
        pokemon = self.encounter.pokemon
        record = CapturedPokemonRecord(
            number=pokemon.number,
            name=pokemon.name,
            cause=_capture_cause_label(self.encounter.event),
            captured_at=now,
        )
        if self.captured_pokemon and self.captured_pokemon[0].number == record.number and self.captured_pokemon[0].cause == record.cause:
            return
        self.captured_pokemon.appendleft(record)
        if self.capture_store is not None:
            event = self.encounter.event
            self.capture_store.record_pokemon_capture(
                pokemon.number,
                pokemon.name,
                record.cause,
                captured_at=now,
                source_provider=event.source if event else "ambient",
                source_category=event.category.value if event else EventCategory.AMBIENT.value,
                types=getattr(pokemon, "types", ()),
            )

    def _load_captured_pokemon(self) -> None:
        if self.capture_store is None:
            return
        try:
            records = self.capture_store.recent_pokemon_captures(10)
        except Exception:
            return
        for record in reversed(records):
            captured_at = _parse_capture_datetime(record.last_seen_at or record.captured_at, self.primary_timezone)
            self.captured_pokemon.appendleft(
                CapturedPokemonRecord(
                    number=record.pokemon_number,
                    name=record.pokemon_name,
                    cause=record.cause,
                    captured_at=captured_at,
                )
            )

    def _draw_pokemon_capture_huds(self, draw: ImageDraw.ImageDraw, pal) -> None:
        for box in self._layout_boxes("pokemon_captures"):
            self._draw_pokemon_capture_hud(draw, box, pal)

    def _draw_pokemon_capture_hud(self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], pal) -> None:
        PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
        row_font = font(8)
        cause_font = font(7)
        x0, y0, x1, y1 = _draw_panel_title(draw, box, "POKEMON CAUGHT", pal)
        content_x = x0 + 7
        content_w = max(1, x1 - x0 - 14)
        if not self.captured_pokemon:
            draw.text((content_x, y0 + 7), "No captures yet", font=row_font, fill=pal.ink)
            return

        available_h = max(1, y1 - y0 - 22)
        columns = 2 if content_w >= 260 else 1
        rows_per_column = 5 if columns == 2 else 10
        column_gap = 8 if columns == 2 else 0
        column_w = max(1, (content_w - column_gap * (columns - 1)) // columns)
        row_h = max(12, min(21, available_h // rows_per_column))
        max_rows = min(10, max(1, rows_per_column * columns))
        for index, record in enumerate(list(self.captured_pokemon)[:max_rows]):
            column = index // rows_per_column
            row = index % rows_per_column
            item_x = content_x + column * (column_w + column_gap)
            y = y0 + 7 + row * row_h
            if y + row_h > y1 - 2:
                break
            ball_size = 8 if row_h <= 10 else 10
            ball_y = y + max(0, (row_h - ball_size) // 2)
            _draw_tiny_pokeball(draw, item_x, ball_y, ball_size, pal)
            text_x = item_x + ball_size + 5
            text_w = max(1, column_w - ball_size - 5)
            if row_h >= 18:
                name = _fit_text(draw, f"#{record.number:03d} {record.name.upper()}", text_w, row_font)
                cause = _fit_text(draw, f"{_capture_timestamp_label(record.captured_at, self.primary_timezone)} - {record.cause}", text_w, cause_font)
                draw.text((text_x, y - 1), name, font=row_font, fill=pal.ink)
                draw.text((text_x, y + 9), cause, font=cause_font, fill=pal.blue)
            else:
                label = _fit_text(
                    draw,
                    f"#{record.number:03d} {record.name.upper()} {_capture_timestamp_label(record.captured_at, self.primary_timezone)}",
                    text_w,
                    row_font,
                )
                draw.text((text_x, y - 1), label, font=row_font, fill=pal.ink)

    def _layout_boxes(self, kind: str) -> list[tuple[int, int, int, int]]:
        if not isinstance(self.display_layout, dict):
            return []
        boxes: list[tuple[int, int, int, int]] = []
        for item_key, raw in self.display_layout.items():
            if not isinstance(raw, dict):
                continue
            if str(raw.get("kind") or item_key) == kind:
                box = self._layout_box(item_key, (0, 0, 1, 1))
                if box[2] - box[0] >= 8 and box[3] - box[1] >= 8:
                    boxes.append(box)
        return boxes

    def render_dirty_regions(self, base: Image.Image, now: datetime | None = None) -> list[tuple[int, int, Image.Image]]:
        base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
        phase = self.advance(base_now)
        pal = day_night_palette(base_now.hour)
        regions: list[tuple[int, int, Image.Image]] = []

        if self._is_battle_phase(phase):
            if not self._previous_was_battle:
                x0, y0, _, _ = self.battle_box
                region = self._battle_background_for_current_mood(pal).copy()
                self._draw_battle_sprites(region, phase, offset=(x0, y0))
                regions.append((x0, y0, region))
            else:
                current_box = self._battle_sprite_box_for_phase(phase)
                sprite_box = self._union_boxes(self._previous_battle_sprite_box, current_box)
                if sprite_box:
                    x0, y0, _, _ = self.battle_box
                    bg = self._battle_background_for_current_mood(pal)
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

        message = self._display_message(self.encounter.message_for(phase))
        text_frame = self._text_frame(message)
        text_key = (message, text_frame % 20 < 10, self._text_scroll_start(message, text_frame))
        if text_key != self._previous_text_key:
            self._previous_text_key = text_key
            text_box = self.text_box
            region = base.crop(text_box)
            local_box = (0, 0, text_box[2] - text_box[0], text_box[3] - text_box[1])
            draw_text_box(region, local_box, text_key[0], pal, text_frame)
            regions.append((text_box[0], text_box[1], region))

        return regions

    def prime_dirty_tracking(self) -> None:
        phase = self.state.phase
        self._previous_sprite_box = self._sprite_box_for_phase(phase)
        self._previous_battle_sprite_box = self._battle_sprite_box_for_phase(phase) if self._is_battle_phase(phase) else None
        message = self._display_message(self.encounter.message_for(phase))
        text_frame = self._text_frame(message)
        self._previous_text_key = (message, text_frame % 20 < 10, self._text_scroll_start(message, text_frame))
        self._previous_was_battle = self._is_battle_phase(phase)
        self._previous_map_area_id = self.current_map_area.area_id if self.current_map_area else None

    def _text_frame(self, message: str) -> int:
        if message != self._text_scroll_key:
            self._text_scroll_key = message
            self._text_scroll_started_frame = self.frame
        return max(0, self.frame - self._text_scroll_started_frame)

    def _display_message(self, message: str) -> str:
        if message != "ASH is looking for Pokemon.":
            return message
        return f"{message}\n{self._world_state_caption()}"

    def _world_state_caption(self) -> str:
        mood = self.current_mood
        captions = {
            "quiet_route": "The route is quiet and calm.",
            "ambient_route": "The route feels steady.",
            "lively_town": "The town has a soft buzz.",
            "electric_city": "The city hums with energy.",
            "stormy_night": "A tense storm hangs nearby.",
            "forge_city": "The forge district feels charged.",
            "festival_town": "Festival lights warm the streets.",
        }
        if mood.world_state in captions:
            return captions[mood.world_state]
        if mood.world_state.startswith("meeting_"):
            return "Meeting energy fills the plaza."
        if mood.mood == "tense":
            return "The air feels tense."
        if mood.mood == "celebrating":
            return "The town feels celebratory."
        return "The world feels ambient."

    def _text_scroll_start(self, message: str, text_frame: int) -> int:
        x0, y0, x1, y1 = self.text_box
        text_x = x0 + scaled_px(12)
        text_y = y0 + text_box_top_padding()
        max_lines = text_box_visible_lines(self.text_box, message, text_y=text_y)
        scratch = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(scratch)
        lines = wrap_text_lines(draw, message, font(14), x1 - text_x - scaled_px(26))
        return scroll_line_start(lines, max_lines, text_frame)

    def _message_scroll_seconds(self, message: str) -> float:
        if not message:
            return 0.0
        x0, y0, x1, y1 = self.text_box
        text_x = x0 + scaled_px(12)
        text_y = y0 + text_box_top_padding()
        max_lines = text_box_visible_lines(self.text_box, message, text_y=text_y)
        scratch = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(scratch)
        lines = wrap_text_lines(draw, message, font(14), x1 - text_x - scaled_px(26))
        hidden_lines = max(0, len(lines) - max_lines)
        if hidden_lines == 0:
            return 0.0
        hold_frames = 8
        step_frames = 8
        cycle_frames = hold_frames + hidden_lines * step_frames + hold_frames
        return cycle_frames / max(1, self.scene_fps)

    def _draw_sky(self, draw: ImageDraw.ImageDraw, pal) -> None:
        x0, y0, x1, _ = self.map_box
        sky_bottom = y0 + 40
        for y in range(y0, sky_bottom):
            t = (y - y0) / max(1, sky_bottom - y0)
            color = tuple(int(pal.sky_top[i] * (1 - t) + pal.sky_bottom[i] * t) for i in range(3))
            draw.line((x0, y, x1, y), fill=color)
        if pal.phase == "night":
            star_y = y0 + 10
            for x, y in ((38, star_y), (82, star_y + 12), (166, star_y - 4), (244, star_y + 8), (286, star_y + 18)):
                if x0 <= x <= x1 and y0 <= y <= self.map_box[3]:
                    draw.point((x, y), fill=pal.light)
                    draw.point((x + 1, y), fill=pal.light)
        else:
            sun_size = 34
            sun_x1 = min(x1 - 8, x0 + 286)
            sun_y0 = y0 + 8
            if sun_x1 - sun_size >= x0 and sun_y0 + sun_size <= self.map_box[3]:
                draw.ellipse((sun_x1 - sun_size, sun_y0, sun_x1, sun_y0 + sun_size), fill=pal.light, outline=pal.panel_shadow)

    def _draw_world(self, img, draw: ImageDraw.ImageDraw, pal, now: datetime, weather: WeatherState | None = None) -> None:
        area = self.map_routes.area_for_timestamp(now.timestamp())
        if area:
            self.current_map_area = area
            self.current_map_timestamp = now.timestamp()
            self._reposition_actors_for_map_change(area)
            img.paste(self._map_background_image(area, pal), (self.map_box[0], self.map_box[1]))
            if weather:
                self._draw_weather_effects(img, weather, area, pal)
            return

        x0, y0, x1, y1 = self.map_box
        top = y0 + 40
        bottom = y1
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
            for x in range(x0, x1, TILE):
                img.paste(tiles[name], (x, y))

        self._draw_static_props(draw, pal, top, trail_top)
        if weather:
            self._draw_weather_effects(img, weather, None, pal)

    def _reposition_actors_for_map_change(self, area: MapArea) -> None:
        if area.area_id == self._actor_map_area_id:
            return
        self._actor_map_area_id = area.area_id
        self._reposition_ash_in_walkable_area()
        self._reposition_companions_in_walkable_area()

    def _reposition_ash_in_walkable_area(self) -> None:
        if not self._movement_screen_rects("ash"):
            return
        ash = self.ash_sprites.frame(f"idle_{self.ash_direction}", self.frame)
        rng = random.Random(f"{self.current_map_area.area_id}:ash" if self.current_map_area else "ash")
        target = self._random_movement_target("ash", rng, ash.width, ash.height)
        if target is None:
            return
        x, y = target
        self.encounter_x = x
        self.ash_y = y
        self._ash_render_x = float(x)
        self._ash_render_y = float(y)
        self._ash_vertical_target_y = None
        self._ash_motion_axis = "horizontal"
        self._ash_motion_until_frame = self.frame + self._random_horizontal_frames()

    def _reposition_companions_in_walkable_area(self) -> None:
        if not self._voice_companions or not self._movement_screen_rects("companions"):
            return
        for state in self._voice_companions.values():
            sprite = self.npc_sprites.frame(state.variant, "idle_down", self.frame)
            target = self._random_movement_target("companions", state.rng, sprite.width, sprite.height)
            if target is None:
                continue
            state.x = float(target[0])
            state.y = float(target[1])
            state.target_x = state.x
            state.target_y = state.y
            state.direction = "down"
            state.next_target_frame = self.frame + state.rng.randint(self.scene_fps * 2, self.scene_fps * 6)

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

    def _draw_weather_effects(self, img: Image.Image, weather: WeatherState, area: MapArea | None, pal) -> None:
        effects = set(weather.effects)
        outdoor = area is None or not area.sheltered
        x0, y0, x1, y1 = self.map_box
        box = (x0, y0, x1, y1)
        if outdoor and "cloudy" in effects:
            self._blend_map_region(img, box, (112, 128, 144), 0.16)
        if "cold" in effects:
            self._blend_map_region(img, box, (176, 216, 248), 0.10)
        if "hot" in effects:
            self._blend_map_region(img, box, (248, 176, 88), 0.11)

        draw = ImageDraw.Draw(img)
        if outdoor and "wind" in effects:
            self._draw_wind(draw, box)
        if outdoor and "rain" in effects:
            self._draw_rain(draw, box)
        if outdoor and "snow" in effects:
            self._draw_snow(draw, box)
        if self._should_draw_legacy_weather_badge():
            self._draw_weather_badge(draw, weather, pal)

    def _should_draw_legacy_weather_badge(self) -> bool:
        return not isinstance(self.display_layout, dict) or not self.display_layout

    @staticmethod
    def _blend_map_region(img: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int], alpha: float) -> None:
        region = img.crop(box)
        tinted = Image.blend(region, Image.new("RGB", region.size, color), alpha)
        img.paste(tinted, box)

    def _draw_rain(self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        offset = (self.frame * 3) % 18
        for x in range(x0 - 24, x1 + 24, 18):
            for y in range(y0 - 18, y1 + 18, 24):
                sx = x + ((y // 24) % 2) * 8
                sy = y + offset
                draw.line((sx, sy, sx - 5, sy + 10), fill=(128, 184, 232), width=1)

    def _draw_snow(self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        offset = (self.frame // 2) % 20
        for x in range(x0 + 8, x1, 24):
            for y in range(y0 + 4, y1, 28):
                sx = x + ((y // 28) % 3) * 5
                sy = y + offset
                if sy >= y1:
                    sy -= y1 - y0
                draw.point((sx, sy), fill=(232, 248, 255))
                draw.point((sx + 1, sy), fill=(232, 248, 255))

    def _draw_wind(self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        offset = (self.frame * 2) % 42
        for y in range(y0 + 34, y1 - 16, 44):
            start = x0 + 14 + offset
            for x in range(start - 42, x1, 86):
                draw.arc((x, y, x + 38, y + 12), 190, 350, fill=(224, 232, 216), width=1)
                draw.line((x + 20, y + 7, x + 42, y + 7), fill=(224, 232, 216), width=1)

    def _draw_weather_badge(self, draw: ImageDraw.ImageDraw, weather: WeatherState, pal) -> None:
        temp_label, range_label = self._weather_labels(weather)
        temp_font = font(14)
        range_font = font(7)
        temp_box = draw.textbbox((0, 0), temp_label, font=temp_font)
        range_box = draw.textbbox((0, 0), range_label, font=range_font)
        width = max(
            72,
            22 + temp_box[2] - temp_box[0] + 16,
            range_box[2] - range_box[0] + 12,
        )
        x1 = self.renderer.width - 8
        x0 = max(182, x1 - width)
        y0 = max(self.hud_height + 6, 216)
        y1 = y0 + 28
        draw.rectangle((x0 + 2, y0 + 2, x1 + 2, y1 + 2), fill=(16, 24, 32))
        draw.rectangle((x0, y0, x1, y1), fill=(236, 232, 208), outline=(40, 48, 56))
        self._draw_weather_icon(draw, weather.primary_effect, x0 + 6, y0 + 2, pal.phase)
        draw.text((x1 - (temp_box[2] - temp_box[0]) - 5, y0 + 1), temp_label, font=temp_font, fill=(32, 40, 56))
        draw.text((x0 + 5, y0 + 18), range_label, font=range_font, fill=(72, 88, 112))

    def _draw_weather_icon(self, draw: ImageDraw.ImageDraw, effect: str, x: int, y: int, day_phase: str) -> None:
        if effect == "rain":
            self._draw_cloud_icon(draw, x, y, rain=True)
        elif effect == "cloudy":
            self._draw_cloud_icon(draw, x, y)
        elif effect == "wind":
            draw.arc((x, y + 2, x + 14, y + 10), 200, 350, fill=(64, 88, 112), width=1)
            draw.line((x + 6, y + 7, x + 18, y + 7), fill=(64, 88, 112), width=1)
            draw.arc((x + 2, y + 7, x + 16, y + 15), 200, 350, fill=(64, 88, 112), width=1)
            draw.line((x + 7, y + 12, x + 17, y + 12), fill=(64, 88, 112), width=1)
        elif effect == "snow":
            self._draw_cloud_icon(draw, x, y, snow=True)
        elif effect == "cold":
            draw.line((x + 9, y, x + 9, y + 16), fill=(64, 128, 184), width=1)
            draw.line((x + 2, y + 4, x + 16, y + 12), fill=(64, 128, 184), width=1)
            draw.line((x + 16, y + 4, x + 2, y + 12), fill=(64, 128, 184), width=1)
            draw.ellipse((x + 7, y + 6, x + 11, y + 10), fill=(232, 248, 255), outline=(64, 128, 184))
        elif effect == "hot":
            draw.ellipse((x + 4, y + 2, x + 16, y + 14), fill=(248, 192, 64), outline=(176, 96, 48))
            for x1, y1, x2, y2 in ((10, 0, 10, 3), (10, 13, 10, 17), (1, 8, 4, 8), (16, 8, 19, 8)):
                draw.line((x + x1, y + y1, x + x2, y + y2), fill=(176, 96, 48), width=1)
        elif day_phase == "night":
            draw.ellipse((x + 5, y + 2, x + 16, y + 13), fill=(232, 232, 184), outline=(112, 112, 128))
            draw.ellipse((x + 10, y, x + 19, y + 11), fill=(236, 232, 208))
        else:
            draw.ellipse((x + 4, y + 2, x + 16, y + 14), fill=(248, 200, 72), outline=(176, 120, 48))

    @staticmethod
    def _draw_cloud_icon(draw: ImageDraw.ImageDraw, x: int, y: int, rain: bool = False, snow: bool = False) -> None:
        cloud = (104, 120, 136)
        light = (224, 232, 232)
        draw.ellipse((x + 2, y + 5, x + 10, y + 13), fill=light, outline=cloud)
        draw.ellipse((x + 7, y + 2, x + 16, y + 12), fill=light, outline=cloud)
        draw.rectangle((x + 5, y + 8, x + 18, y + 14), fill=light, outline=cloud)
        if rain:
            for dx in (5, 10, 15):
                draw.line((x + dx, y + 15, x + dx - 2, y + 18), fill=(64, 128, 200), width=1)
        if snow:
            for dx in (5, 11, 17):
                draw.point((x + dx, y + 17), fill=(64, 128, 184))
                draw.point((x + dx + 1, y + 17), fill=(64, 128, 184))

    @staticmethod
    def _weather_labels(weather: WeatherState) -> tuple[str, str]:
        temp = f"{round(weather.temperature_c):d}C"
        low = "--" if weather.temperature_min_c is None else f"{round(weather.temperature_min_c):d}"
        high = "--" if weather.temperature_max_c is None else f"{round(weather.temperature_max_c):d}"
        return temp, f"L {low}  H {high}"

    def _map_background_image(self, area: MapArea, pal) -> Image.Image:
        return self.map_routes.background_for_area(
            area,
            pal.phase,
            None if pal.phase == "morning" else lambda image: self._tint_for_day_phase(image, pal, area),
        )

    @property
    def battle_box(self) -> tuple[int, int, int, int]:
        return self.map_box

    def _battle_local_pokemon_x(self) -> int:
        x0, _, x1, _ = self.battle_box
        width = x1 - x0
        if width <= 360:
            return BATTLE_POKEMON_X
        return int(width * 0.68)

    def _battle_pokemon_x(self) -> int:
        x0, _, _, _ = self.battle_box
        return x0 + self._battle_local_pokemon_x()

    def _battle_local_ash_x(self) -> int:
        x0, _, x1, _ = self.battle_box
        width = x1 - x0
        if width <= 360:
            return BATTLE_ASH_X
        return int(width * 0.15)

    def _battle_ash_x(self) -> int:
        x0, _, _, _ = self.battle_box
        return x0 + self._battle_local_ash_x()

    def _battle_pokemon_base_y(self) -> int:
        _, y0, _, y1 = self.battle_box
        return min(y1 - 58, y0 + BATTLE_POKEMON_BASE_OFFSET_Y)

    def _draw_battle_scene(self, img: Image.Image, phase: GamePhase, pal) -> None:
        x0, y0, x1, y1 = self.battle_box
        img.paste(self._battle_background_for_current_mood(pal), (x0, y0))
        self._draw_battle_sprites(img, phase)

    def _battle_background_for_current_mood(self, pal) -> Image.Image:
        return apply_battle_ambience(self._battle_background_image(pal), self.current_mood)

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
            (self._battle_local_pokemon_x(), self._battle_pokemon_base_y() - y0),
            (124, 34),
            pal,
            near=False,
        )
        ash = scale_sprite(battle_ash_frame(1), 2)
        self._draw_battle_platform(
            draw,
            (self._battle_local_ash_x() + ash.width // 2, y1 - y0 - BATTLE_ASH_BOTTOM_PAD - 16),
            (154, 42),
            pal,
            near=True,
        )
        self._battle_backgrounds[pal.phase] = background
        return background

    def _tint_for_day_phase(self, image: Image.Image, pal, area: MapArea | None = None) -> Image.Image:
        if pal.phase == "night" and area and area.environment == "indoor":
            return self._warm_indoor_light(image)
        if pal.phase == "night":
            alpha = 0.46
        elif pal.phase == "dawn":
            alpha = 0.24
        else:
            alpha = 0.14
        overlay = Image.new("RGB", image.size, pal.sky_top)
        return Image.blend(image, overlay, alpha)

    @staticmethod
    def _warm_indoor_light(image: Image.Image) -> Image.Image:
        warmed = Image.blend(image, Image.new("RGB", image.size, (255, 210, 132)), 0.12)
        pixels = warmed.load()
        for y in range(warmed.height):
            for x in range(warmed.width):
                r, g, b = pixels[x, y]
                pixels[x, y] = (
                    min(255, int(r * 1.04) + 4),
                    min(255, int(g * 1.03) + 3),
                    min(255, int(b * 0.96)),
                )
        return warmed

    def _battle_sprite_layers(self, phase: GamePhase) -> list[tuple[Image.Image, int, int]]:
        layers: list[tuple[Image.Image, int, int]] = []
        _, y0, _, y1 = self.battle_box
        pokemon_base_y = self._battle_pokemon_base_y()
        sprite_path = self.encounter.pokemon.animated_sprite_path or self.encounter.pokemon.sprite_path
        ball_layer: tuple[Image.Image, int, int] | None = None
        if phase in (GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE):
            ball = scale_sprite(pokeball(self.frame), 2)
            ball_layer = (ball, *self._battle_ball_position(phase, ball, pokemon_base_y, y1))

        if phase != GamePhase.CAUGHT:
            if phase == GamePhase.ENCOUNTER_START:
                pokemon_step = 0
            elif phase == GamePhase.POKEMON_APPEARS:
                pokemon_step = self.state.frame_in_phase * 3
            else:
                pokemon_step = int(self.state.durations[GamePhase.POKEMON_APPEARS] * self.scene_fps) * 3
            pokemon_scale = 1 if sprite_path and sprite_path.exists() else 2
            poke = self.pokemon_sprites.sprite_for(
                sprite_path,
                self.encounter.pokemon.number,
                pokemon_step,
                scale=pokemon_scale,
                loop=False,
            )
            pokemon_x = self._battle_pokemon_x() - poke.width // 2
            pokemon_y = pokemon_base_y - poke.height
            if phase == GamePhase.ENCOUNTER_START:
                pokemon_y += int(10 * (1 - self.state.progress))
            ball_touched_pokemon = bool(
                phase in (GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE)
                and ball_layer
                and self._boxes_overlap(
                    (pokemon_x, pokemon_y, pokemon_x + poke.width, pokemon_y + poke.height),
                    (
                        ball_layer[1],
                        ball_layer[2],
                        ball_layer[1] + ball_layer[0].width,
                        ball_layer[2] + ball_layer[0].height,
                    ),
                )
            )
            if not ball_touched_pokemon:
                layers.append((poke, pokemon_x, pokemon_y))

        if phase == GamePhase.ASH_THROWS:
            ash_step = 1 + int(self.state.progress * 16)
        else:
            ash_step = 1
        ash = scale_sprite(battle_ash_frame(ash_step), 2)
        layers.append((ash, self._battle_ash_x(), y1 - ash.height - BATTLE_ASH_BOTTOM_PAD))

        if ball_layer:
            layers.append(ball_layer)
        return layers

    def _battle_ball_position(
        self,
        phase: GamePhase,
        ball: Image.Image,
        pokemon_base_y: int,
        battle_y1: int,
    ) -> tuple[int, int]:
        if phase == GamePhase.ASH_THROWS:
            progress = self.state.progress
            start_x = self._battle_ash_x() + 104
            start_y = battle_y1 - 108
            end_x = self._battle_pokemon_x() - ball.width // 2
            end_y = pokemon_base_y - ball.height // 2
            x = int(start_x + (end_x - start_x) * progress)
            y = int(start_y + (end_y - start_y) * progress - 42 * progress * (1 - progress))
            return x, y

        shake = (-5, 5, 0, -3, 3, 0)[(self.frame // 2) % 6]
        return self._battle_pokemon_x() - ball.width // 2 + shake, pokemon_base_y - ball.height // 2

    @staticmethod
    def _boxes_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
        return (
            first[0] < second[2]
            and first[2] > second[0]
            and first[1] < second[3]
            and first[3] > second[1]
        )

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

    def _sprite_layers(self, phase: GamePhase) -> list[tuple[Image.Image, int, int, str]]:
        layers: list[tuple[Image.Image, int, int, str]] = []
        snapshot = self._companion_snapshot()
        ash_streaming = bool(getattr(snapshot, "focus_streaming", False)) if snapshot is not None else False
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
        if ash_streaming:
            self.ash_direction = "down"
            ash_y = route_y
            ash = self.ash_sprites.frame("idle_down", self.frame)
        clamped_ash_x, clamped_ash_y = self._clamp_sprite_to_movement(
            "ash",
            ash_x,
            ash_y,
            ash.width,
            ash.height,
            self.vertical_wander_rng,
        )
        if (clamped_ash_x, clamped_ash_y) != (ash_x, ash_y):
            ash_x, ash_y = clamped_ash_x, clamped_ash_y
            self.encounter_x = ash_x
            self.ash_y = ash_y
            self._ash_render_x = float(ash_x)
            self._ash_render_y = float(ash_y)
            self._ash_vertical_target_y = None
        layers.extend(self._voice_companion_layers(ash_x, ash_y, phase, snapshot=snapshot))
        layers.append((ash, ash_x, ash_y, ""))
        if ash_streaming:
            screen = self._live_screen_sprite()
            sx, sy = self._live_screen_position(ash_x, ash_y, ash.width, ash.height, screen)
            layers.append((screen, sx, sy, ""))

        if phase in (GamePhase.ENCOUNTER_START, GamePhase.POKEMON_APPEARS, GamePhase.ASH_THROWS, GamePhase.BALL_SHAKE):
            sprite_path = self.encounter.pokemon.animated_sprite_path or self.encounter.pokemon.sprite_path
            poke = self.pokemon_sprites.sprite_for(sprite_path, self.encounter.pokemon.number, self.frame, scale=2)
            wobble = 1 if phase in (GamePhase.ENCOUNTER_START, GamePhase.POKEMON_APPEARS) and self.frame % 10 < 5 else 0
            if not (phase == GamePhase.ENCOUNTER_START and self.frame % 8 < 4):
                layers.append((poke, self.pokemon_x, self.pokemon_y + wobble, ""))

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
            layers.append((ball, bx, by, ""))
        return layers

    def _draw_sprites(self, img: Image.Image, phase: GamePhase, pal, offset: tuple[int, int] = (0, 0)) -> None:
        ox, oy = offset
        draw = ImageDraw.Draw(img)
        for sprite, x, y, label in self._sprite_layers(phase):
            img.paste(sprite, (x - ox, y - oy), sprite)
            if label:
                self._draw_companion_label(draw, label, x - ox + sprite.width // 2, y - oy + sprite.height + 1, pal)

    def _sprite_box_for_phase(self, phase: GamePhase) -> tuple[int, int, int, int] | None:
        layers = self._sprite_layers(phase)
        if not layers:
            return None
        boxes = []
        for sprite, x, y, label in layers:
            boxes.append((x, y, x + sprite.width, y + sprite.height))
            if label:
                boxes.append((x - 18, y + sprite.height, x + sprite.width + 18, y + sprite.height + 12))
        return self._pad_box(self._union_many(boxes), 4)

    def _voice_companion_layers(
        self,
        ash_x: int,
        ash_y: int,
        phase: GamePhase,
        snapshot=None,
    ) -> list[tuple[Image.Image, int, int, str]]:
        if snapshot is None:
            self._voice_companions.clear()
            return []
        stream_active = bool(getattr(snapshot, "active_stream_user_ids", ()))
        if not snapshot.members and not stream_active:
            self._voice_companions.clear()
            return []
        active_ids = {member.user_id for member in snapshot.members}
        for user_id in list(self._voice_companions):
            if user_id not in active_ids:
                self._voice_companions.pop(user_id, None)
        layers: list[tuple[Image.Image, int, int, str]] = []
        streamer_ids = set(getattr(snapshot, "active_stream_user_ids", ()))
        for member in snapshot.members:
            seed = int(hashlib.sha1(member.user_id.encode("utf-8")).hexdigest()[:8], 16)
            visual = self._companion_visual(member.user_id)
            state = self._voice_companion_state(member.user_id, seed, ash_x, ash_y, visual.get("sprite_variant"))
            calendar_companion = self._is_calendar_companion(member.user_id)
            muted = bool(getattr(member, "muted", False))
            streaming = stream_active and member.user_id in streamer_ids
            watching_stream = stream_active and not streaming
            if streaming:
                state.target_x = state.x
                state.target_y = state.y
                state.direction = "down"
            elif muted:
                state.target_x = state.x
                state.target_y = state.y
            else:
                self._update_voice_companion_state(state)
            anim = f"walk_{state.direction}"
            if streaming or muted or (abs(state.x - state.target_x) < 0.6 and abs(state.y - state.target_y) < 0.6):
                anim = f"idle_{state.direction}"
            companion = self.npc_sprites.frame(state.variant, anim, self.frame)
            if calendar_companion:
                companion = self._calendar_companion_sprite(companion)
            if watching_stream:
                companion = self._stream_viewer_sprite(companion)
            if muted:
                companion = self._muted_companion_sprite(companion)
            x, y = self._clamp_sprite_to_movement(
                "companions",
                int(round(state.x)),
                int(round(state.y)),
                companion.width,
                companion.height,
                state.rng,
            )
            if (x, y) != (int(round(state.x)), int(round(state.y))):
                state.x = float(x)
                state.y = float(y)
                state.target_x = state.x
                state.target_y = state.y
            label = str(visual.get("label") or member.name)
            if calendar_companion:
                label = f"CAL {label}"
            layers.append((companion, x, y, self._short_companion_name(label)))
            if streaming:
                screen = self._live_screen_sprite()
                sx, sy = self._live_screen_position(x, y, companion.width, companion.height, screen)
                layers.append((screen, sx, sy, ""))
        return sorted(layers, key=lambda item: item[2] + item[0].height)

    def _live_screen_position(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        screen: Image.Image,
    ) -> tuple[int, int]:
        right_x = x + width - 4
        left_x = x - screen.width + 4
        sx = right_x if right_x + screen.width <= self.map_box[2] - 2 else left_x
        sy = y + max(0, (height - screen.height) // 2) - 2
        return self._clamp_sprite_x(sx, screen.width), self._clamp_sprite_y(sy, screen.height)

    def _live_screen_sprite(self) -> Image.Image:
        sprite = Image.new("RGBA", (34, 22), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sprite)
        pulse = (self.frame // max(1, self.scene_fps // 2)) % 2
        border = (28, 32, 48, 255)
        panel = (232, 242, 250, 255) if pulse else (214, 232, 246, 255)
        red = (220, 42, 54, 255)
        text_x = 5 + int((self.frame // max(1, self.scene_fps // 4)) % 5)
        draw.rectangle((2, 1, 31, 17), fill=border)
        draw.rectangle((4, 3, 29, 15), fill=panel)
        draw.rectangle((14, 17, 19, 20), fill=border)
        draw.rectangle((9, 20, 24, 21), fill=border)
        draw.text((text_x, 5), "LIVE", font=font(7), fill=red)
        return sprite

    @staticmethod
    def _stream_viewer_sprite(sprite: Image.Image) -> Image.Image:
        rgba = sprite.convert("RGBA")
        alpha = rgba.getchannel("A")
        glow = Image.new("RGBA", rgba.size, (72, 126, 210, 255))
        tinted = Image.blend(rgba, glow, 0.16)
        tinted.putalpha(alpha)
        return tinted

    @staticmethod
    def _muted_companion_sprite(sprite: Image.Image) -> Image.Image:
        rgba = sprite.convert("RGBA")
        alpha = rgba.getchannel("A")
        shade = Image.new("RGBA", rgba.size, (20, 22, 30, 255))
        muted = Image.blend(rgba, shade, 0.48)
        muted.putalpha(alpha)
        return muted

    @staticmethod
    def _calendar_companion_sprite(sprite: Image.Image) -> Image.Image:
        rgba = sprite.convert("RGBA")
        alpha = rgba.getchannel("A")
        aura = Image.new("RGBA", rgba.size, (245, 190, 74, 255))
        tinted = Image.blend(rgba, aura, 0.22)
        draw = ImageDraw.Draw(tinted)
        draw.rectangle((0, 0, min(9, tinted.width - 1), min(7, tinted.height - 1)), fill=(36, 42, 68, 230), outline=(245, 220, 132, 255))
        draw.rectangle((2, 3, min(7, tinted.width - 2), min(5, tinted.height - 2)), fill=(245, 220, 132, 255))
        tinted.putalpha(alpha)
        return tinted

    @staticmethod
    def _is_calendar_companion(user_id: str) -> bool:
        return str(user_id).startswith("calendar:")

    def _companion_visual(self, user_id: str) -> dict:
        raw = self.companion_config if isinstance(self.companion_config, dict) else {}
        value = raw.get(user_id, {}) if isinstance(raw, dict) else {}
        return value if isinstance(value, dict) else {}

    def _voice_companion_state(
        self,
        user_id: str,
        seed: int,
        ash_x: int,
        ash_y: int,
        sprite_variant: int | None,
    ) -> VoiceCompanionState:
        state = self._voice_companions.get(user_id)
        if state is not None:
            variant = sprite_variant if sprite_variant is not None else seed % self.npc_sprites.count
            state.variant = max(0, min(self.npc_sprites.count - 1, variant))
            return state
        rng = random.Random(seed)
        variant = sprite_variant if sprite_variant is not None else seed % self.npc_sprites.count
        variant = max(0, min(self.npc_sprites.count - 1, variant))
        sample = self.npc_sprites.frame(variant, "idle_down", self.frame)
        sprite_w = sample.width
        sprite_h = sample.height
        x, y = self._random_companion_target(rng, sprite_w, sprite_h)
        if not self._voice_companions and not self._movement_screen_rects("companions"):
            x = self._clamp_sprite_x(ash_x + rng.randint(-52, 52), sprite_w)
            y = self._clamp_sprite_y(ash_y + rng.randint(-48, 28), sprite_h)
        state = VoiceCompanionState(
            x=float(x),
            y=float(y),
            target_x=float(x),
            target_y=float(y),
            direction="down",
            next_target_frame=self.frame + rng.randint(self.scene_fps * 2, self.scene_fps * 6),
            speed=0.7 + rng.random() * 0.9,
            rng=rng,
            variant=variant,
        )
        self._set_next_companion_target(state, sprite_w, sprite_h)
        self._voice_companions[user_id] = state
        return state

    def _update_voice_companion_state(self, state: VoiceCompanionState) -> None:
        sprite = self.npc_sprites.frame(state.variant, "idle_down", self.frame)
        if self._movement_screen_rects("companions") and not self._sprite_movement_rect(
            "companions",
            int(round(state.x)),
            int(round(state.y)),
            sprite.width,
            sprite.height,
        ):
            x, y = self._clamp_sprite_to_movement(
                "companions",
                int(round(state.x)),
                int(round(state.y)),
                sprite.width,
                sprite.height,
            )
            state.x = float(x)
            state.y = float(y)
            state.target_x = state.x
            state.target_y = state.y
            state.direction = "down"
            return
        dx = state.target_x - state.x
        dy = state.target_y - state.y
        distance = max(0.01, (dx * dx + dy * dy) ** 0.5)
        if distance <= state.speed or self.frame >= state.next_target_frame:
            state.x = state.target_x
            state.y = state.target_y
            self._set_next_companion_target(state, sprite.width, sprite.height)
            state.next_target_frame = self.frame + state.rng.randint(self.scene_fps * 2, self.scene_fps * 7)
            return
        step = min(state.speed, distance)
        state.x += dx / distance * step
        state.y += dy / distance * step

    def _random_companion_target(self, rng: random.Random, width: int, height: int) -> tuple[int, int]:
        configured = self._random_movement_target("companions", rng, width, height)
        if configured is not None:
            return configured
        x0, y0, x1, y1 = self.map_box
        min_x = x0 + 8
        max_x = max(min_x, x1 - width - 8)
        min_y = y0 + 10
        max_y = max(min_y, y1 - height - 18)
        return rng.randint(min_x, max_x), rng.randint(min_y, max_y)

    def _set_next_companion_target(self, state: VoiceCompanionState, width: int, height: int) -> None:
        configured = self._random_movement_target("companions", state.rng, width, height)
        if configured is not None:
            current_rect = self._sprite_movement_rect(
                "companions",
                int(round(state.x)),
                int(round(state.y)),
                width,
                height,
            )
            if current_rect is None:
                x, y = self._clamp_sprite_to_movement(
                    "companions",
                    int(round(state.x)),
                    int(round(state.y)),
                    width,
                    height,
                )
                state.x = float(x)
                state.y = float(y)
                state.target_x = state.x
                state.target_y = state.y
                state.direction = "down"
                return
            configured = self._random_target_in_screen_rect(state.rng, width, height, current_rect) or configured
            state.target_x = float(configured[0])
            state.target_y = float(configured[1])
            dx = state.target_x - state.x
            dy = state.target_y - state.y
            if abs(dx) > abs(dy):
                state.target_y = state.y
                state.direction = "right" if dx > 0 else "left"
            else:
                state.target_x = state.x
                state.direction = "down" if dy > 0 else "up"
            return
        x0, y0, x1, y1 = self.map_box
        min_x = x0 + 8
        max_x = max(min_x, x1 - width - 8)
        min_y = y0 + 10
        max_y = max(min_y, y1 - height - 18)
        directions = ("down", "up", "right", "left")
        for _ in range(8):
            direction = directions[state.rng.randrange(len(directions))]
            distance = state.rng.randint(20, 76)
            target_x = state.x
            target_y = state.y
            if direction == "down":
                target_y = min(max_y, state.y + distance)
            elif direction == "up":
                target_y = max(min_y, state.y - distance)
            elif direction == "right":
                target_x = min(max_x, state.x + distance)
            else:
                target_x = max(min_x, state.x - distance)
            if abs(target_x - state.x) >= 4 or abs(target_y - state.y) >= 4:
                state.direction = direction
                state.target_x = float(target_x)
                state.target_y = float(target_y)
                return
        state.target_x, state.target_y = self._random_companion_target(state.rng, width, height)
        dx = state.target_x - state.x
        dy = state.target_y - state.y
        if abs(dx) > abs(dy):
            state.target_y = state.y
            state.direction = "right" if dx > 0 else "left"
        else:
            state.target_x = state.x
            state.direction = "down" if dy > 0 else "up"

    def _companion_snapshot(self) -> CompanionSnapshot | None:
        return self.companion_snapshot

    def _clamp_sprite_x(self, x: int, width: int) -> int:
        x0, _, x1, _ = self.map_box
        return max(x0 + 2, min(x1 - width - 2, x))

    def _clamp_sprite_y(self, y: int, height: int) -> int:
        _, y0, _, y1 = self.map_box
        return max(y0 + 4, min(y1 - height - 14, y))

    def _movement_source_rects(self, actor: str, key: str = "source_rects") -> list[tuple[int, int, int, int]]:
        area = self.current_map_area
        if area is None:
            return []
        raw_sections = []
        if isinstance(self.movement_config, dict):
            if actor in ("ash", "companions"):
                raw_sections.append(self.movement_config.get("walkable", {}))
                raw_sections.append(self.movement_config.get(actor, {}))
            else:
                raw_sections.append(self.movement_config.get(actor, {}))
        rects: list[tuple[int, int, int, int]] = []
        for raw_actor in raw_sections:
            raw_rects = raw_actor.get(key, []) if isinstance(raw_actor, dict) else []
            if not isinstance(raw_rects, list):
                continue
            for item in raw_rects:
                if not isinstance(item, dict):
                    continue
                map_id = str(item.get("map") or item.get("map_id") or "")
                if map_id and map_id not in (area.map_key, area.source_path.name, str(area.source_path)):
                    continue
                x = int(item.get("x", 0))
                y = int(item.get("y", 0))
                w = int(item.get("w", item.get("width", 0)))
                h = int(item.get("h", item.get("height", 0)))
                if w > 0 and h > 0:
                    rects.append((x, y, x + w, y + h))
        return rects

    def _source_rect_to_screen(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        area = self.current_map_area
        if area is None:
            return None
        crop_x0, crop_y0, crop_x1, crop_y1 = area.crop_box
        ix0 = max(rect[0], crop_x0)
        iy0 = max(rect[1], crop_y0)
        ix1 = min(rect[2], crop_x1)
        iy1 = min(rect[3], crop_y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return None
        viewport_w = self.map_box[2] - self.map_box[0]
        viewport_h = self.map_box[3] - self.map_box[1]
        crop_w = crop_x1 - crop_x0
        crop_h = crop_y1 - crop_y0
        paste_x = (viewport_w - crop_w) // 2
        paste_y = (viewport_h - crop_h) // 2
        screen_x0 = max(self.map_box[0], self.map_box[0] + paste_x + ix0 - crop_x0)
        screen_y0 = max(self.map_box[1], self.map_box[1] + paste_y + iy0 - crop_y0)
        screen_x1 = min(self.map_box[2], self.map_box[0] + paste_x + ix1 - crop_x0)
        screen_y1 = min(self.map_box[3], self.map_box[1] + paste_y + iy1 - crop_y0)
        if screen_x1 <= screen_x0 or screen_y1 <= screen_y0:
            return None
        return screen_x0, screen_y0, screen_x1, screen_y1

    def _movement_screen_rects(self, actor: str, key: str = "source_rects") -> list[tuple[int, int, int, int]]:
        rects = []
        for rect in self._movement_source_rects(actor, key):
            screen_rect = self._source_rect_to_screen(rect)
            if screen_rect is not None:
                rects.append(screen_rect)
        return rects

    def _sprite_movement_rect(
        self,
        actor: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int] | None:
        for x0, y0, x1, y1 in self._movement_screen_rects(actor):
            sprite_rect = (x, y, x + width, y + height)
            if (
                x0 <= x
                and y0 <= y
                and x + width <= x1
                and y + height <= y1
                and not self._sprite_intersects_movement_blockers(actor, sprite_rect)
            ):
                return x0, y0, x1, y1
        return None

    def _sprite_intersects_movement_blockers(self, actor: str, sprite_rect: tuple[int, int, int, int]) -> bool:
        blockers = self._movement_screen_rects(actor, "avoid_source_rects") + self._movement_screen_rects("blocked")
        return any(self._rects_intersect(sprite_rect, blocker) for blocker in blockers)

    @staticmethod
    def _random_target_in_screen_rect(
        rng: random.Random,
        width: int,
        height: int,
        rect: tuple[int, int, int, int],
    ) -> tuple[int, int] | None:
        x0, y0, x1, y1 = rect
        max_x = x1 - width
        max_y = y1 - height
        if max_x < x0 or max_y < y0:
            return None
        return rng.randint(x0, max_x), rng.randint(y0, max_y)

    @staticmethod
    def _point_in_rects(x: int, y: int, rects: list[tuple[int, int, int, int]]) -> bool:
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in rects)

    def _random_movement_target(self, actor: str, rng: random.Random, width: int, height: int) -> tuple[int, int] | None:
        walkable = self._movement_screen_rects(actor)
        if not walkable:
            return None
        candidates = []
        for x0, y0, x1, y1 in walkable:
            min_x = x0
            max_x = x1 - width
            min_y = y0
            max_y = y1 - height
            if max_x >= min_x and max_y >= min_y:
                candidates.append((min_x, min_y, max_x, max_y))
        if not candidates:
            return None
        for _ in range(16):
            min_x, min_y, max_x, max_y = candidates[rng.randrange(len(candidates))]
            x = rng.randint(min_x, max_x)
            y = rng.randint(min_y, max_y)
            if self._sprite_movement_rect(actor, x, y, width, height):
                return x, y
        min_x, min_y, max_x, max_y = candidates[0]
        for x in range(min_x, max_x + 1, max(1, width // 2)):
            for y in range(min_y, max_y + 1, max(1, height // 2)):
                if self._sprite_movement_rect(actor, x, y, width, height):
                    return x, y
        return None

    def _clamp_sprite_to_movement(
        self,
        actor: str,
        x: int,
        y: int,
        width: int,
        height: int,
        rng: random.Random | None = None,
    ) -> tuple[int, int]:
        if not self._movement_screen_rects(actor):
            return self._clamp_sprite_x(x, width), self._clamp_sprite_y(y, height)
        if self._sprite_movement_rect(actor, x, y, width, height):
            return x, y
        target = self._nearest_movement_target(actor, x, y, width, height)
        if target is not None:
            return target
        return self._clamp_sprite_x(x, width), self._clamp_sprite_y(y, height)

    def _nearest_movement_target(
        self,
        actor: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> tuple[int, int] | None:
        best: tuple[int, int, int] | None = None
        for x0, y0, x1, y1 in self._movement_screen_rects(actor):
            max_x = x1 - width
            max_y = y1 - height
            if max_x < x0 or max_y < y0:
                continue
            cx = max(x0, min(max_x, x))
            cy = max(y0, min(max_y, y))
            candidates = [(cx, cy)]
            step_x = max(1, width // 2)
            step_y = max(1, height // 2)
            xs = list(range(x0, max_x + 1, step_x))
            ys = list(range(y0, max_y + 1, step_y))
            if not xs or xs[-1] != max_x:
                xs.append(max_x)
            if not ys or ys[-1] != max_y:
                ys.append(max_y)
            candidates.extend((scan_x, scan_y) for scan_x in xs for scan_y in ys)
            for candidate_x, candidate_y in candidates:
                if not self._sprite_movement_rect(actor, candidate_x, candidate_y, width, height):
                    continue
                distance = abs(candidate_x - x) + abs(candidate_y - y)
                if best is None or distance < best[0]:
                    best = (distance, candidate_x, candidate_y)
        if best is not None:
            return best[1], best[2]
        return None

    def _clamp_point_to_movement(self, actor: str, x: int, y: int) -> tuple[int, int]:
        walkable = self._movement_screen_rects(actor)
        if not walkable:
            return x, y
        if self._point_in_rects(x, y, walkable):
            return x, y
        best = None
        for x0, y0, x1, y1 in walkable:
            cx = max(x0, min(x1, x))
            cy = max(y0, min(y1, y))
            distance = abs(cx - x) + abs(cy - y)
            if best is None or distance < best[0]:
                best = (distance, cx, cy)
        return (best[1], best[2]) if best else (x, y)

    @staticmethod
    def _rects_intersect(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> bool:
        return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

    def _draw_movement_debug_overlay(self, draw: ImageDraw.ImageDraw, pal) -> None:
        if not (bool(self.movement_config.get("debug_overlay", False)) if isinstance(self.movement_config, dict) else False):
            return
        colors = (
            ("walkable", "source_rects", pal.green),
            ("walkable", "avoid_source_rects", pal.red),
            ("blocked", "source_rects", pal.red),
        )
        for actor, key, color in colors:
            for rect in self._movement_screen_rects(actor, key):
                draw.rectangle(rect, outline=color, width=2)

    @staticmethod
    def _short_companion_name(name: str) -> str:
        clean = name.strip() or "Friend"
        return clean[:10]

    def _draw_companion_label(self, draw: ImageDraw.ImageDraw, label: str, center_x: int, y: int, pal) -> None:
        label_font = font(8)
        box = draw.textbbox((0, 0), label, font=label_font)
        width = box[2] - box[0] + 6
        x0 = max(self.map_box[0] + 1, min(self.map_box[2] - width - 1, center_x - width // 2))
        y0 = min(self.map_box[3] - 10, y)
        draw.rectangle((x0 + 1, y0 + 1, x0 + width + 1, y0 + 10), fill=(16, 24, 32))
        draw.rectangle((x0, y0, x0 + width, y0 + 9), fill=pal.panel, outline=pal.panel_shadow)
        draw.text((x0 + 3, y0), label, font=label_font, fill=pal.ink)

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
        moving = phase in (GamePhase.WALKING, GamePhase.RESUME_WALKING)
        if moving and self.current_map_area:
            (x, y), direction = self.map_routes.pose_on_route(
                self.current_map_area,
                self.overworld_walk_frame,
                self.route_speed_px,
            )
            target_x, target_y = self._clamp_point_to_movement("ash", self.map_box[0] + x, self.map_box[1] + y)
            return self._moving_ash_pose(target_x, target_y, direction)
        x = self._ash_x_for_phase(phase)
        if moving:
            x, y = self._clamp_point_to_movement("ash", x, self.ash_y)
            return self._moving_ash_pose(x, y, None)
        self._ash_render_x = float(x)
        self._ash_render_y = float(self.ash_y)
        self._ash_motion_axis = "horizontal"
        return x, self.ash_y, None

    def _moving_ash_pose(self, target_x: int, base_y: int, route_direction: str | None) -> tuple[int, int, str | None]:
        if self._ash_render_x is None or self._ash_render_y is None:
            self._ash_render_x = float(target_x)
            self._ash_render_y = float(base_y)
            self._ash_motion_until_frame = self.frame + self._random_horizontal_frames()

        if self._ash_motion_axis == "vertical":
            return self._vertical_ash_pose(base_y)

        if self.frame >= self._ash_motion_until_frame and self.vertical_wander_px > 0:
            self._start_vertical_wander(base_y)
            return self._vertical_ash_pose(base_y)

        previous_x = self._ash_render_x
        step = max(1.0, self.route_speed_px)
        self._ash_render_x = self._move_toward(self._ash_render_x, float(target_x), step)
        x_delta = self._ash_render_x - previous_x
        direction = route_direction
        if abs(x_delta) >= 0.5:
            direction = "right" if x_delta > 0 else "left"
        return int(round(self._ash_render_x)), int(round(self._ash_render_y)), direction

    def _vertical_ash_pose(self, base_y: int) -> tuple[int, int, str | None]:
        assert self._ash_render_x is not None
        assert self._ash_render_y is not None
        if self._ash_vertical_target_y is None:
            self._start_vertical_wander(base_y)
        assert self._ash_vertical_target_y is not None
        previous_y = self._ash_render_y
        self._ash_render_y = self._move_toward(
            self._ash_render_y,
            self._ash_vertical_target_y,
            self.vertical_wander_speed_px,
        )
        reached_target = abs(self._ash_render_y - self._ash_vertical_target_y) < 0.5
        if reached_target and self.frame >= self._ash_motion_until_frame:
            self._ash_motion_axis = "horizontal"
            self._ash_motion_until_frame = self.frame + self._random_horizontal_frames()
            self._ash_vertical_target_y = None
        y_delta = self._ash_render_y - previous_y
        direction = None
        if abs(y_delta) >= 0.5:
            direction = "down" if y_delta > 0 else "up"
        return int(round(self._ash_render_x)), int(round(self._ash_render_y)), direction

    def _start_vertical_wander(self, base_y: int) -> None:
        assert self._ash_render_y is not None
        min_y = self.map_box[1] + 4
        max_y = self.map_box[3] - 48
        target = float(base_y + self.vertical_wander_rng.randint(-self.vertical_wander_px, self.vertical_wander_px))
        target = min(max_y, max(min_y, target))
        if abs(target - self._ash_render_y) < 8:
            direction = -1 if self._ash_render_y > (min_y + max_y) / 2 else 1
            target = min(max_y, max(min_y, self._ash_render_y + direction * min(18, self.vertical_wander_px)))
        self._ash_motion_axis = "vertical"
        self._ash_motion_until_frame = self.frame + self.vertical_wander_frames
        self._ash_vertical_target_y = target

    def _random_horizontal_frames(self) -> int:
        return self.horizontal_wander_frames + self.vertical_wander_rng.randint(0, max(1, self.scene_fps))

    @staticmethod
    def _move_toward(current: float, target: float, step: float) -> float:
        if abs(target - current) <= step:
            return target
        return current + step if target > current else current - step


def _capture_cause_label(event: WorkEvent | None) -> str:
    if event is None or event.category == EventCategory.AMBIENT:
        return "AMBIENT ROUTE"
    labels = {
        EventCategory.PULL_REQUEST: "PR",
        EventCategory.REVIEW_REQUESTED: "REVIEW",
        EventCategory.PR_APPROVED: "APPROVAL",
        EventCategory.PR_CLOSED: "PR CLOSED",
        EventCategory.MERGE: "MERGE",
        EventCategory.MEETING: "MEETING",
        EventCategory.BUILD_BROKEN: "CI ALERT",
        EventCategory.DEPLOY_STARTED: "DEPLOY START",
        EventCategory.DEPLOY_COMPLETED: "DEPLOY DONE",
        EventCategory.INCIDENT: "INCIDENT",
        EventCategory.MESSAGE_IMPORTANT: "MESSAGE",
        EventCategory.SOCIAL_ACTIVITY: "SOCIAL WEATHER",
        EventCategory.SOCIAL_PRESENCE: "PRESENCE",
        EventCategory.SOCIAL_QUIET: "QUIET",
        EventCategory.AI_USAGE: "AI USAGE",
    }
    base = labels.get(event.category, event.category.value.replace("_", " ").upper())
    if event.category in (EventCategory.MESSAGE_IMPORTANT, EventCategory.SOCIAL_ACTIVITY, EventCategory.SOCIAL_PRESENCE, EventCategory.SOCIAL_QUIET):
        return base
    context = event.repo or event.metadata.get("repo") or event.title
    if not context:
        return base
    return f"{base} {_compact_capture_context(context)}"


def _parse_capture_datetime(value: str, timezone_name: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(ZoneInfo(timezone_name))


def _capture_timestamp_label(value: datetime, timezone_name: str) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo(timezone_name))
    return value.strftime("%d/%m %H:%M")


def _compact_capture_context(value: str) -> str:
    compact = " ".join(str(value).replace("\n", " ").split())
    if "/" in compact and len(compact) > 24:
        compact = compact.split("/")[-1]
    return compact[:42]


def _draw_tiny_pokeball(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, pal) -> None:
    size = max(7, size)
    box = (x, y, x + size - 1, y + size - 1)
    mid = y + size // 2
    draw.ellipse(box, fill=(248, 248, 248), outline=pal.ink)
    draw.pieslice(box, 180, 360, fill=(224, 48, 48))
    draw.arc(box, 180, 360, fill=pal.ink)
    draw.line((x + 1, mid, x + size - 2, mid), fill=pal.ink)
    button = max(2, size // 3)
    bx = x + size // 2 - button // 2
    by = mid - button // 2
    draw.ellipse((bx, by, bx + button, by + button), fill=pal.panel, outline=pal.ink)


def _draw_panel_title(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, pal) -> tuple[int, int, int, int]:
    title_font = font(7)
    x0, y0, x1, y1 = box
    label = _fit_text(draw, title, max(1, x1 - x0 - 18), title_font)
    bounds = draw.textbbox((0, 0), label, font=title_font)
    label_w = bounds[2] - bounds[0] + 8
    label_h = bounds[3] - bounds[1] + 5
    label_x = x0 + 5
    label_y = y0
    draw.rectangle((label_x, label_y, min(x1 - 5, label_x + label_w), label_y + label_h), fill=(255, 255, 255), outline=pal.ink)
    draw.text((label_x + 4, label_y + 2 - bounds[1]), label, font=title_font, fill=pal.blue)
    return x0, min(y1 - 1, y0 + 13), x1, y1


_TEXT_WIDTH_CACHE: dict[tuple[int, str], int] = {}


def _text_width(draw: ImageDraw.ImageDraw, text: str, text_font) -> int:
    key = (id(text_font), text)
    cached = _TEXT_WIDTH_CACHE.get(key)
    if cached is not None:
        return cached
    bounds = draw.textbbox((0, 0), text, font=text_font)
    width = bounds[2] - bounds[0]
    if len(_TEXT_WIDTH_CACHE) > 4096:
        _TEXT_WIDTH_CACHE.clear()
    _TEXT_WIDTH_CACHE[key] = width
    return width


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, text_font) -> str:
    if _text_width(draw, text, text_font) <= max_width:
        return text
    lo = 0
    hi = len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _text_width(draw, f"{text[:mid]}...", text_font) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return f"{text[:lo]}..." if lo else ""
