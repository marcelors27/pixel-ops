from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import ImageDraw

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.plugins.pokemon.pokemon import get_pokemon
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.render.fonts import font, font_scale_for_canvas
from pixel_ops.plugins.pokemon.render.palette import palette_for_hour
from pixel_ops.render.renderer import PixelRenderer
from pixel_ops.plugins.pokemon.render.sprites import AshSpriteSet, PokemonSpriteStore, pokeball, scale_sprite
from pixel_ops.plugins.pokemon.scenes.entities import AshCharacter, PokemonEncounter


class MainScene:
    def __init__(
        self,
        width: int,
        height: int,
        primary_timezone: str,
        scanlines: bool = True,
        pokemon_api: PokeApiClient | None = None,
        lazy_download: bool = True,
        scene_fps: int = 12,
        ash_assets_dir: Path | None = None,
    ):
        self.renderer = PixelRenderer(width, height)
        self.primary_timezone = primary_timezone
        self.scanlines = scanlines
        self.pokemon_api = pokemon_api
        self.lazy_download = lazy_download
        self.sprite_store = PokemonSpriteStore()
        self.scene_fps = scene_fps
        asset_root = Path(__file__).resolve().parents[1] / "assets/sprites/ash"
        self.ash_sprites = AshSpriteSet(ash_assets_dir or asset_root, scene_fps=scene_fps)
        self.frame = 0
        self.ash = AshCharacter()
        self.encounter = PokemonEncounter(self.load_pokemon(25))
        self.rng = random.Random(151)

    def load_pokemon(self, number: int) -> Pokemon:
        if self.pokemon_api:
            return self.pokemon_api.get(number, allow_download=self.lazy_download)
        return get_pokemon(number - 1)

    def update_encounter(self) -> None:
        self.ash.update(self.encounter.phase)
        if self.encounter.update(self.ash):
            self.ash = AshCharacter()
            self.encounter = PokemonEncounter(self.load_pokemon(self.rng.randrange(1, 152)))

    def render(self, people: list[PersonTime], event: CalendarEvent | None, now: datetime | None = None):
        with font_scale_for_canvas(self.renderer.width, self.renderer.height):
            self.frame += 1
            self.update_encounter()
            base_now = now or datetime.now(ZoneInfo(self.primary_timezone))
            pal = palette_for_hour(base_now.hour)
            img = self.renderer.canvas(pal["bg"])
            draw = ImageDraw.Draw(img)

            self._draw_background(draw, pal)
            self._draw_time_panel(draw, pal, people)
            self._draw_calendar(draw, pal, event, base_now)
            self._draw_world(img, draw, pal)

            if self.scanlines:
                img = self.renderer.apply_scanlines(img)
            return img

    def _draw_background(self, draw, pal) -> None:
        for y in range(0, 292, 16):
            shade = tuple(max(0, c - (y // 16) * 2) for c in pal["bg"])
            draw.rectangle((0, y, 319, y + 15), fill=shade)
        draw.rectangle((0, 292, 319, 479), fill=pal["ground"])
        for x in range(-20, 340, 24):
            draw.polygon([(x, 292), (x + 12, 280), (x + 24, 292)], fill=(64, 136, 72))

    def _draw_time_panel(self, draw, pal, people: list[PersonTime]) -> None:
        PixelRenderer.draw_panel(draw, (12, 16, 308, 218), pal["panel"], pal["panel_shadow"], pal["ink"])
        row_font = font(18)
        draw.rectangle((26, 38, 294, 41), fill=pal["blue"])
        y = 52
        for person in people[:5]:
            status_color = {
                "working": pal["green"],
                "ending": pal["yellow"],
                "off": pal["red"],
            }.get(person.status, pal["panel_shadow"])
            draw.text((28, y), person.key, font=row_font, fill=pal["ink"])
            draw.text((96, y), person.local_time.strftime("%H:%M"), font=row_font, fill=pal["ink"])
            draw.ellipse((248, y + 4, 262, y + 18), fill=status_color, outline=pal["ink"])
            y += 28

    def _draw_calendar(self, draw, pal, event: CalendarEvent | None, now: datetime) -> None:
        PixelRenderer.draw_panel(draw, (12, 230, 308, 286), pal["panel"], pal["panel_shadow"], pal["ink"])
        text_font = font(16)
        if event:
            label = f"NEXT: {event.title[:17]} {event.countdown_label(now)}"
        else:
            label = "NEXT: No meetings"
        draw.text((26, 249), label, font=text_font, fill=pal["ink"])
        if self.frame % 24 < 12:
            draw.polygon([(286, 254), (294, 260), (286, 266)], fill=pal["red"])

    def _draw_world(self, img, draw, pal) -> None:
        ash = self.ash_sprites.frame(self.ash.state, self.frame)
        img.paste(ash, self.ash.position, ash)
        e = self.encounter
        if e.phase == "approach":
            sprite_path = e.pokemon.animated_sprite_path or e.pokemon.sprite_path
            poke = self.sprite_store.sprite_for(sprite_path, e.pokemon.number, self.frame, scale=2)
            img.paste(poke, (e.x, e.y), poke)
        elif e.phase == "catch":
            ball = scale_sprite(pokeball(self.frame // 6), 3)
            bx = int(self.ash.x + 42 + min(52, e.phase_frame * 3))
            img.paste(ball, (bx, 365), ball)
        elif e.phase == "caught":
            msg_font = font(14)
            PixelRenderer.draw_panel(draw, (22, 420, 298, 466), pal["panel"], pal["panel_shadow"], pal["ink"])
            draw.text((36, 436), f"Caught #{e.pokemon.number:03d} {e.pokemon.name}", font=msg_font, fill=pal["ink"])
