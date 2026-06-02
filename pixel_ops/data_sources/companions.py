from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CompanionMember:
    user_id: str
    name: str
    muted: bool = False
    streaming: bool = False


@dataclass(frozen=True)
class CompanionSnapshot:
    members: tuple[CompanionMember, ...] = ()
    active_stream_user_ids: tuple[str, ...] = ()
    focus_user_id: str = ""
    focus_name: str = ""
    focus_muted: bool = False
    focus_streaming: bool = False
    group_id: str = ""
    group_name: str = ""


class CompanionSource(Protocol):
    def current(self, now: datetime | None = None) -> CompanionSnapshot | None:
        ...
