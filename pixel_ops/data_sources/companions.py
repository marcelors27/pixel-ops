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


class MergedCompanionSource:
    def __init__(self, sources: list[CompanionSource] | tuple[CompanionSource, ...] | None = None):
        self.sources: list[CompanionSource] = list(sources or [])

    def add(self, source: CompanionSource) -> None:
        self.sources.append(source)

    def current(self, now: datetime | None = None) -> CompanionSnapshot | None:
        snapshots = [snapshot for source in self.sources if (snapshot := source.current(now))]
        active_snapshots = [
            snapshot
            for snapshot in snapshots
            if snapshot.members or snapshot.active_stream_user_ids or snapshot.focus_user_id
        ]
        if not active_snapshots:
            return None

        members: list[CompanionMember] = []
        seen_members: set[str] = set()
        stream_ids: list[str] = []
        seen_streams: set[str] = set()
        focus = next((snapshot for snapshot in active_snapshots if snapshot.focus_user_id), None)
        group_ids: list[str] = []
        group_names: list[str] = []
        for snapshot in active_snapshots:
            if snapshot.group_id:
                group_ids.append(snapshot.group_id)
            if snapshot.group_name:
                group_names.append(snapshot.group_name)
            for member in snapshot.members:
                if member.user_id in seen_members:
                    continue
                seen_members.add(member.user_id)
                members.append(member)
            for user_id in snapshot.active_stream_user_ids:
                if user_id in seen_streams:
                    continue
                seen_streams.add(user_id)
                stream_ids.append(user_id)

        return CompanionSnapshot(
            members=tuple(members),
            active_stream_user_ids=tuple(stream_ids),
            focus_user_id=focus.focus_user_id if focus else "",
            focus_name=focus.focus_name if focus else "",
            focus_muted=focus.focus_muted if focus else False,
            focus_streaming=focus.focus_streaming if focus else False,
            group_id=",".join(dict.fromkeys(group_ids)),
            group_name=", ".join(dict.fromkeys(group_names)),
        )
