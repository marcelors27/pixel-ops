from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pixel_ops.events.ambient_signals import AmbientSignal


class AmbientIntegration(Protocol):
    enabled: bool

    def start(self) -> None:
        """Start long-running integration work if needed."""


class AmbientSignalClassifier(Protocol):
    def classify(self, payload: dict) -> AmbientSignal | None:
        """Turn provider-specific payloads into normalized ambient signals."""


class PollingAmbientIntegration(Protocol):
    enabled: bool

    def poll(self, now: datetime) -> list[AmbientSignal]:
        """Return normalized ambient signals for polling-based providers."""
