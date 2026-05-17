from __future__ import annotations

from pixel_ops.events.ambient_signals import (
    AmbientProvider,
    AmbientSignal,
    AmbientSignalKind,
    ambient_signal_to_work_event,
    classify_text_kind,
)

SocialPlatform = AmbientProvider
SocialSignalKind = AmbientSignalKind
SocialSignal = AmbientSignal


def classify_text_signal(text: str, *, default_kind: SocialSignalKind) -> SocialSignalKind:
    return classify_text_kind(text, default_kind=default_kind)


def signal_to_work_event(signal: SocialSignal):
    return ambient_signal_to_work_event(signal)


__all__ = [
    "SocialPlatform",
    "SocialSignalKind",
    "SocialSignal",
    "classify_text_signal",
    "signal_to_work_event",
]
