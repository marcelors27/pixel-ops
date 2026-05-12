from __future__ import annotations

from dataclasses import dataclass

from pixel_ops.plugins.pokemon.pokemon import Pokemon


@dataclass
class AshCharacter:
    x: float = 22
    y: int = 356
    speed: float = 1.6
    state: str = "walk_right"

    def update(self, encounter_phase: str, target_x: int = 142) -> None:
        if encounter_phase == "approach":
            self.state = "walk_right"
            self.x = min(float(target_x), self.x + self.speed)
        elif encounter_phase == "catch":
            self.state = "catch"
        elif encounter_phase == "caught":
            self.state = "idle"
            self.x += 0.25
            if self.x > 36:
                self.x = 22

    @property
    def position(self) -> tuple[int, int]:
        return int(round(self.x)), self.y


@dataclass
class PokemonEncounter:
    pokemon: Pokemon
    x: int = 226
    y: int = 354
    phase: str = "approach"
    phase_frame: int = 0
    message_timer: int = 0

    def update(self, ash: AshCharacter) -> bool:
        self.phase_frame += 1
        if self.phase == "approach" and ash.x >= 142:
            self.phase = "catch"
            self.phase_frame = 0
        elif self.phase == "catch" and self.phase_frame > 24:
            self.phase = "caught"
            self.message_timer = 54
            self.phase_frame = 0
        elif self.phase == "caught":
            self.message_timer -= 1
            return self.message_timer <= 0
        return False
