from __future__ import annotations

import random
from dataclasses import dataclass

from pixel_ops.plugins.pokemon.pokemon import Pokemon, get_pokemon
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.plugins.pokemon.game.state_machine import GamePhase


@dataclass
class Encounter:
    pokemon: Pokemon

    def message_for(self, phase: GamePhase) -> str:
        name = self.pokemon.name.upper()
        if phase == GamePhase.ENCOUNTER_START:
            return f"Wild {name} appeared!"
        if phase == GamePhase.POKEMON_APPEARS:
            return f"Wild {name} appeared!"
        if phase == GamePhase.ASH_THROWS:
            return "ASH used POKE BALL!"
        if phase == GamePhase.BALL_SHAKE:
            return "..."
        if phase == GamePhase.CAUGHT:
            return f"CAUGHT #{self.pokemon.number:03d} {name}"
        return "ASH is looking for Pokemon."


class EncounterSpawner:
    def __init__(self, pokemon_api: PokeApiClient | None, lazy_download: bool = True, seed: int = 151):
        self.pokemon_api = pokemon_api
        self.lazy_download = lazy_download
        self.rng = random.Random(seed)

    def spawn(self) -> Encounter:
        number = self.rng.randrange(1, 152)
        if self.pokemon_api:
            pokemon = self.pokemon_api.get(number, allow_download=self.lazy_download)
        else:
            pokemon = get_pokemon(number - 1)
        return Encounter(pokemon)
