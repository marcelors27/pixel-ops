from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol


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


def merge_companion_snapshots(*snapshots: CompanionSnapshot | None) -> CompanionSnapshot | None:
    sources = [_StaticCompanionSource(snapshot) for snapshot in snapshots if snapshot is not None]
    if not sources:
        return None
    return MergedCompanionSource(sources).current()


def calendar_companion_snapshot(
    events: list[Any] | tuple[Any, ...],
    now: datetime,
    max_members: int = 6,
    fallback_duration_minutes: int = 30,
) -> CompanionSnapshot | None:
    active_event = _active_calendar_event(events, now, fallback_duration_minutes=fallback_duration_minutes)
    if active_event is None:
        return None
    attendees = [
        _calendar_person_name(attendee)
        for attendee in tuple(getattr(active_event, "attendees", ()) or ())
        if _calendar_person_name(attendee)
    ]
    if not attendees:
        organizer = _calendar_person_name(str(getattr(active_event, "organizer", "") or ""))
        attendees = [organizer] if organizer else []
    if not attendees:
        return None

    event_key = _calendar_event_key(active_event)
    members = tuple(
        CompanionMember(
            user_id=f"calendar:{event_key}:{_stable_person_key(name)}",
            name=name,
        )
        for name in attendees[: max(0, max_members)]
    )
    if not members:
        return None
    title = str(getattr(active_event, "title", "") or "Meeting")
    return CompanionSnapshot(
        members=members,
        group_id=f"calendar:{event_key}",
        group_name=title,
    )


class _StaticCompanionSource:
    def __init__(self, snapshot: CompanionSnapshot):
        self.snapshot = snapshot

    def current(self, now: datetime | None = None) -> CompanionSnapshot:
        return self.snapshot


def _active_calendar_event(events: list[Any] | tuple[Any, ...], now: datetime, fallback_duration_minutes: int) -> Any | None:
    candidates = []
    for event in events or ():
        if bool(getattr(event, "all_day", False)):
            continue
        starts_at = getattr(event, "starts_at", None)
        if not isinstance(starts_at, datetime):
            continue
        ends_at = getattr(event, "ends_at", None)
        if not isinstance(ends_at, datetime):
            ends_at = starts_at + timedelta(minutes=max(1, fallback_duration_minutes))
        if _contains_time(starts_at, ends_at, now):
            candidates.append(event)
    return min(candidates, key=lambda event: getattr(event, "starts_at")) if candidates else None


def _contains_time(starts_at: datetime, ends_at: datetime, now: datetime) -> bool:
    if starts_at.tzinfo is not None and now.tzinfo is not None:
        current = now.astimezone(starts_at.tzinfo)
        end = ends_at.astimezone(starts_at.tzinfo) if ends_at.tzinfo is not None else ends_at.replace(tzinfo=starts_at.tzinfo)
        return starts_at <= current < end
    return starts_at <= now < ends_at


def _calendar_event_key(event: Any) -> str:
    starts_at = getattr(event, "starts_at", None)
    stamp = starts_at.isoformat() if isinstance(starts_at, datetime) else ""
    return _stable_person_key(f"{getattr(event, 'title', '')}:{stamp}")


def _calendar_person_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("mailto:"):
        text = text[7:]
    if "@" in text and " " not in text:
        text = text.split("@", 1)[0]
    text = " ".join(text.replace("_", " ").replace(".", " ").split())
    return text[:48]


def _stable_person_key(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:64] or "meeting"
