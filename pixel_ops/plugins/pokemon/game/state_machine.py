from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class GamePhase(str, Enum):
    WALKING = "walking"
    ENCOUNTER_START = "encounter_start"
    POKEMON_APPEARS = "pokemon_appears"
    ASH_THROWS = "ash_throws"
    BALL_SHAKE = "ball_shake"
    CAUGHT = "caught"
    RESUME_WALKING = "resume_walking"


DEFAULT_DURATIONS_SECONDS = {
    GamePhase.WALKING: 5.0,
    GamePhase.ENCOUNTER_START: 1.4,
    GamePhase.POKEMON_APPEARS: 2.0,
    GamePhase.ASH_THROWS: 1.4,
    GamePhase.BALL_SHAKE: 2.0,
    GamePhase.CAUGHT: 2.6,
    GamePhase.RESUME_WALKING: 1.2,
}


@dataclass
class GameStateMachine:
    animation_fps: int
    durations: dict[GamePhase, float]
    phase: GamePhase = GamePhase.WALKING
    phase_started_at: datetime | None = None
    elapsed_seconds: float = 0.0
    min_phase_seconds: dict[GamePhase, float] | None = None

    @classmethod
    def from_seconds(cls, fps: int, seconds_config: dict | None = None) -> "GameStateMachine":
        durations = dict(DEFAULT_DURATIONS_SECONDS)
        aliases = {
            GamePhase.ENCOUNTER_START: "start_seconds",
            GamePhase.POKEMON_APPEARS: "appears_seconds",
            GamePhase.ASH_THROWS: "throw_seconds",
            GamePhase.BALL_SHAKE: "shake_seconds",
        }
        for phase in GamePhase:
            key = f"{phase.value}_seconds"
            if seconds_config and key in seconds_config:
                durations[phase] = max(0.05, float(seconds_config[key]))
            alias = aliases.get(phase)
            if seconds_config and alias in seconds_config:
                durations[phase] = max(0.05, float(seconds_config[alias]))
        return cls(animation_fps=fps, durations=durations)

    def tick(self, now: datetime) -> tuple[GamePhase, bool]:
        if self.phase_started_at is None:
            self.phase_started_at = now
            self.elapsed_seconds = 0.0
            return self.phase, False

        self.elapsed_seconds = max(0.0, (now - self.phase_started_at).total_seconds())
        if self.elapsed_seconds < self.duration_for_phase(self.phase):
            return self.phase, False

        self.phase = self._next_phase(self.phase)
        self.phase_started_at = now
        self.elapsed_seconds = 0.0
        return self.phase, True

    def set_phase(self, phase: GamePhase, now: datetime) -> None:
        self.phase = phase
        self.phase_started_at = now
        self.elapsed_seconds = 0.0

    def require_phase_seconds(self, phase: GamePhase, seconds: float) -> None:
        if self.min_phase_seconds is None:
            self.min_phase_seconds = {}
        self.min_phase_seconds[phase] = max(0.0, seconds)

    def duration_for_phase(self, phase: GamePhase) -> float:
        minimum = 0.0 if self.min_phase_seconds is None else self.min_phase_seconds.get(phase, 0.0)
        return max(self.durations[phase], minimum)

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
        return min(1.0, self.elapsed_seconds / max(0.001, self.duration_for_phase(self.phase)))

    @property
    def frame_in_phase(self) -> int:
        return max(0, int(self.elapsed_seconds * self.animation_fps))
