from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from pixel_ops.data_sources.companions import CompanionMember, CompanionSnapshot
from pixel_ops.integrations.discord.companions import DiscordCompanionStore


@dataclass(frozen=True)
class DiscordVoiceMember:
    user_id: str
    name: str
    channel_id: str
    channel_name: str = ""
    muted: bool = False
    streaming: bool = False


@dataclass(frozen=True)
class DiscordVoiceSnapshot:
    channel_id: str = ""
    channel_name: str = ""
    members: tuple[DiscordVoiceMember, ...] = ()
    active_stream_user_ids: tuple[str, ...] = ()
    focus_user_id: str = ""
    focus_name: str = ""
    focus_muted: bool = False
    focus_streaming: bool = False


@dataclass
class _VoiceRecord:
    user_id: str
    name: str
    channel_id: str
    muted: bool = False
    streaming: bool = False


@dataclass
class DiscordVoiceStateTracker:
    guild_id: str
    focus_user_id: str = ""
    max_companions: int = 5
    companion_store: DiscordCompanionStore | None = None
    _members: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _channels: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _voice: dict[str, _VoiceRecord] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def observe_guild(self, data: dict[str, Any]) -> None:
        if self.guild_id and str(data.get("id") or "") != self.guild_id:
            return
        with self._lock:
            for channel in data.get("channels") or []:
                if isinstance(channel, dict):
                    self._remember_channel(channel)
            for member in data.get("members") or []:
                if isinstance(member, dict):
                    self._remember_member(member)
            for voice_state in data.get("voice_states") or []:
                if isinstance(voice_state, dict):
                    self._observe_voice_state_unlocked(voice_state)

    def observe_voice_state(self, data: dict[str, Any]) -> tuple[DiscordVoiceMember | None, str, str] | None:
        guild_id = str(data.get("guild_id") or self.guild_id)
        if self.guild_id and guild_id != self.guild_id:
            return None
        with self._lock:
            before_channel_id = self._voice.get(str(data.get("user_id") or "")) or None
            previous = before_channel_id.channel_id if before_channel_id else ""
            member = self._observe_voice_state_unlocked(data)
            current = member.channel_id if member else ""
            if current and current != previous:
                return member, previous, current
        return None

    def observe_presence(self, data: dict[str, Any]) -> None:
        user = data.get("user")
        if not isinstance(user, dict):
            return
        user_id = str(user.get("id") or "")
        name = _display_name(user)
        if not user_id or not name:
            return
        with self._lock:
            self._members[user_id] = name

    def snapshot(self) -> DiscordVoiceSnapshot:
        with self._lock:
            records = list(self._voice.values())
            if not records:
                return DiscordVoiceSnapshot()
            channel_id = self._selected_channel_id(records)
            if not channel_id:
                return DiscordVoiceSnapshot()
            members = [
                DiscordVoiceMember(
                    user_id=record.user_id,
                    name=record.name,
                    channel_id=record.channel_id,
                    channel_name=self._channels.get(record.channel_id, ""),
                    muted=record.muted,
                    streaming=record.streaming,
                )
                for record in records
                if record.channel_id == channel_id and record.user_id != self.focus_user_id
            ]
            members.sort(key=lambda item: item.name.lower())
            focus_record = self._voice.get(self.focus_user_id) if self.focus_user_id else None
            focus_in_channel = focus_record if focus_record and focus_record.channel_id == channel_id else None
            active_stream_user_ids = tuple(
                sorted(record.user_id for record in records if record.channel_id == channel_id and record.streaming)
            )
            return DiscordVoiceSnapshot(
                channel_id=channel_id,
                channel_name=self._channels.get(channel_id, ""),
                members=tuple(members[: self.max_companions]),
                active_stream_user_ids=active_stream_user_ids,
                focus_user_id=focus_in_channel.user_id if focus_in_channel else "",
                focus_name=focus_in_channel.name if focus_in_channel else "",
                focus_muted=focus_in_channel.muted if focus_in_channel else False,
                focus_streaming=focus_in_channel.streaming if focus_in_channel else False,
            )

    def _observe_voice_state_unlocked(self, data: dict[str, Any]) -> DiscordVoiceMember | None:
        member = data.get("member")
        if isinstance(member, dict):
            self._remember_member(member)
        user_id = str(data.get("user_id") or "")
        channel_id = str(data.get("channel_id") or "")
        if not user_id:
            return None
        if not channel_id:
            self._voice.pop(user_id, None)
            return None
        name = self._member_name(user_id, member)
        if self.companion_store is not None:
            profile = self.companion_store.record_member(user_id, name)
            name = profile.display_name
        muted = bool(data.get("self_mute") or data.get("mute") or data.get("self_deaf") or data.get("deaf"))
        streaming = bool(data.get("self_stream"))
        self._voice[user_id] = _VoiceRecord(
            user_id=user_id,
            name=name,
            channel_id=channel_id,
            muted=muted,
            streaming=streaming,
        )
        return DiscordVoiceMember(
            user_id=user_id,
            name=name,
            channel_id=channel_id,
            channel_name=self._channels.get(channel_id, ""),
            muted=muted,
            streaming=streaming,
        )

    def _remember_channel(self, channel: dict[str, Any]) -> None:
        channel_id = str(channel.get("id") or "")
        if channel_id:
            self._channels[channel_id] = str(channel.get("name") or channel_id)

    def _remember_member(self, member: dict[str, Any]) -> None:
        user = member.get("user")
        if not isinstance(user, dict):
            return
        user_id = str(user.get("id") or "")
        name = _display_name(user) or str(member.get("nick") or "")
        if user_id and name:
            self._members[user_id] = name

    def _member_name(self, user_id: str, member: object) -> str:
        if isinstance(member, dict):
            nick = str(member.get("nick") or "")
            if nick:
                return nick
            user = member.get("user")
            if isinstance(user, dict):
                name = _display_name(user)
                if name:
                    return name
        return self._members.get(user_id, user_id)

    def _selected_channel_id(self, records: list[_VoiceRecord]) -> str:
        if self.focus_user_id:
            focused = self._voice.get(self.focus_user_id)
            return focused.channel_id if focused else ""
        counts: dict[str, int] = {}
        for record in records:
            counts[record.channel_id] = counts.get(record.channel_id, 0) + 1
        return max(counts, key=counts.get) if counts else ""


class DiscordCompanionSource:
    def __init__(self, tracker: DiscordVoiceStateTracker):
        self.tracker = tracker

    def current(self, now=None) -> CompanionSnapshot:
        snapshot = self.tracker.snapshot()
        return CompanionSnapshot(
            members=tuple(
                CompanionMember(
                    user_id=member.user_id,
                    name=member.name,
                    muted=member.muted,
                    streaming=member.streaming,
                )
                for member in snapshot.members
            ),
            active_stream_user_ids=snapshot.active_stream_user_ids,
            focus_user_id=snapshot.focus_user_id,
            focus_name=snapshot.focus_name,
            focus_muted=snapshot.focus_muted,
            focus_streaming=snapshot.focus_streaming,
            group_id=snapshot.channel_id,
            group_name=snapshot.channel_name,
        )


def _display_name(user: dict[str, Any]) -> str:
    return str(user.get("global_name") or user.get("username") or user.get("id") or "")
