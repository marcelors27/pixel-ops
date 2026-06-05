from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from pixel_ops.data_sources.companions import CompanionMember, CompanionSnapshot
from pixel_ops.events.ambient_signals import AmbientSignal, AmbientSignalKind
from pixel_ops.integrations.zoom.client import ZoomLiveMeeting, ZoomParticipant


@dataclass
class _ZoomParticipantRecord:
    user_id: str
    name: str
    meeting_id: str
    meeting_name: str = ""


@dataclass
class ZoomParticipantTracker:
    focus_user_id: str = ""
    max_companions: int = 8
    _meetings: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _participants: dict[str, _ZoomParticipantRecord] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.focus_user_id = _zoom_user_id(self.focus_user_id)

    def observe_signal(self, signal: AmbientSignal) -> None:
        meeting_id = _meeting_id(signal)
        if not meeting_id:
            return
        meeting_name = signal.title or signal.metadata.get("meeting_topic", "")
        with self._lock:
            if meeting_name:
                self._meetings[meeting_id] = meeting_name
            if signal.kind in (AmbientSignalKind.MEETING_STARTED, AmbientSignalKind.MEETING_SOON):
                self._meetings.setdefault(meeting_id, meeting_name or meeting_id)
                return
            if signal.kind == AmbientSignalKind.MEETING_ENDED:
                self._meetings.pop(meeting_id, None)
                self._participants = {
                    user_id: record
                    for user_id, record in self._participants.items()
                    if record.meeting_id != meeting_id
                }
                return
            if signal.kind == AmbientSignalKind.PARTICIPANT_JOINED:
                user_id = _participant_user_id(signal)
                if not user_id:
                    return
                name = signal.actor or signal.metadata.get("participant_name") or user_id.removeprefix("zoom:")
                self._participants[user_id] = _ZoomParticipantRecord(
                    user_id=user_id,
                    name=name,
                    meeting_id=meeting_id,
                    meeting_name=self._meetings.get(meeting_id, meeting_name),
                )
                return
            if signal.kind == AmbientSignalKind.PARTICIPANT_LEFT:
                user_id = _participant_user_id(signal)
                if user_id:
                    self._participants.pop(user_id, None)

    def replace_live_meetings(self, meetings: list[ZoomLiveMeeting] | tuple[ZoomLiveMeeting, ...]) -> None:
        with self._lock:
            self._meetings = {
                meeting.meeting_id: meeting.topic or meeting.meeting_id
                for meeting in meetings
                if meeting.meeting_id
            }
            participants: dict[str, _ZoomParticipantRecord] = {}
            for meeting in meetings:
                if not meeting.meeting_id:
                    continue
                for participant in meeting.participants:
                    user_id = _participant_user_id_from_participant(participant)
                    if not user_id:
                        continue
                    participants[user_id] = _ZoomParticipantRecord(
                        user_id=user_id,
                        name=participant.name or user_id.removeprefix("zoom:"),
                        meeting_id=meeting.meeting_id,
                        meeting_name=meeting.topic,
                    )
            self._participants = participants

    def snapshot(self) -> CompanionSnapshot | None:
        with self._lock:
            if not self._participants:
                return None
            meeting_id = self._selected_meeting_id()
            if not meeting_id:
                return None
            records = [
                record
                for record in self._participants.values()
                if record.meeting_id == meeting_id
            ]
            records.sort(key=lambda item: item.name.lower())
            focus_record = next((record for record in records if record.user_id == self.focus_user_id), None)
            members = [
                CompanionMember(user_id=record.user_id, name=record.name)
                for record in records
                if record.user_id != self.focus_user_id
            ]
            meeting_name = self._meetings.get(meeting_id, "")
            if not meeting_name and records:
                meeting_name = records[0].meeting_name
            return CompanionSnapshot(
                members=tuple(members[: self.max_companions]),
                focus_user_id=focus_record.user_id if focus_record else "",
                focus_name=focus_record.name if focus_record else "",
                group_id=meeting_id,
                group_name=meeting_name,
            )

    def _selected_meeting_id(self) -> str:
        if self.focus_user_id:
            focused = self._participants.get(self.focus_user_id)
            if focused:
                return focused.meeting_id
        counts: dict[str, int] = {}
        for record in self._participants.values():
            counts[record.meeting_id] = counts.get(record.meeting_id, 0) + 1
        return max(counts, key=counts.get) if counts else ""


class ZoomCompanionSource:
    def __init__(self, tracker: ZoomParticipantTracker):
        self.tracker = tracker

    def current(self, now=None) -> CompanionSnapshot | None:
        return self.tracker.snapshot()


def _meeting_id(signal: AmbientSignal) -> str:
    return signal.metadata.get("meeting_id") or signal.external_id or ""


def _participant_user_id(signal: AmbientSignal) -> str:
    return _zoom_user_id(
        signal.metadata.get("participant_email")
        or signal.metadata.get("participant_id")
        or signal.actor
        or ""
    )


def _participant_user_id_from_participant(participant: ZoomParticipant) -> str:
    return _zoom_user_id(participant.email or participant.participant_id or participant.name)


def _zoom_user_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    return normalized if normalized.startswith("zoom:") else f"zoom:{normalized}"
