from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GamePhase(str, Enum):
    WALKING = "walking"
    ENCOUNTER_START = "encounter_start"
    POKEMON_APPEARS = "pokemon_appears"
    ASH_THROWS = "ash_throws"
    BALL_SHAKE = "ball_shake"
    CAUGHT = "caught"
    RESUME_WALKING = "resume_walking"


DEFAULT_DURATIONS = {
    GamePhase.WALKING: 50,
    GamePhase.ENCOUNTER_START: 14,
    GamePhase.POKEMON_APPEARS: 20,
    GamePhase.ASH_THROWS: 14,
    GamePhase.BALL_SHAKE: 20,
    GamePhase.CAUGHT: 26,
    GamePhase.RESUME_WALKING: 12,
}


@dataclass
class GameStateMachine:
    fps: int
    durations: dict[GamePhase, int]
    phase: GamePhase = GamePhase.WALKING
    frame_in_phase: int = 0

    @classmethod
    def from_seconds(cls, fps: int, seconds_config: dict | None = None) -> "GameStateMachine":
        durations = dict(DEFAULT_DURATIONS)
        aliases = {
            GamePhase.ENCOUNTER_START: "start_seconds",
            GamePhase.POKEMON_APPEARS: "appears_seconds",
            GamePhase.ASH_THROWS: "throw_seconds",
            GamePhase.BALL_SHAKE: "shake_seconds",
        }
        for phase in GamePhase:
            key = f"{phase.value}_seconds"
            if seconds_config and key in seconds_config:
                durations[phase] = max(1, int(float(seconds_config[key]) * fps))
            alias = aliases.get(phase)
            if seconds_config and alias in seconds_config:
                durations[phase] = max(1, int(float(seconds_config[alias]) * fps))
        return cls(fps=fps, durations=durations)

    def tick(self) -> tuple[GamePhase, bool]:
        self.frame_in_phase += 1
        if self.frame_in_phase < self.durations[self.phase]:
            return self.phase, False

        self.phase = self._next_phase(self.phase)
        self.frame_in_phase = 0
        return self.phase, True

    @staticmethod
    def _next_phase(phase: GamePhase) -> GamePhase:
        order = [
            GamePhase.WALKING,
            GamePhase.ENCOUNTER_START,
            GamePhase.POKEMON_APPEARS,
            GamePhase.ASH_THROWS,
            GamePhase.BALL_SHAKE,
            GamePhase.CAUGHT,
            GamePhase.RESUME_WALKING,
        ]
        index = order.index(phase)
        return order[(index + 1) % len(order)]

    @property
    def progress(self) -> float:
        return min(1.0, self.frame_in_phase / max(1, self.durations[self.phase]))
