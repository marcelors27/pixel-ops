from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any
from urllib.parse import quote

import requests

from pixel_ops.events.ambient_signals import AmbientProvider, AmbientSignal, AmbientSignalKind, ambient_signal_to_work_event
from pixel_ops.events.event_bus import EventBus


@dataclass(frozen=True)
class ZoomParticipant:
    participant_id: str
    name: str
    email: str = ""


@dataclass(frozen=True)
class ZoomLiveMeeting:
    meeting_id: str
    topic: str = ""
    participants: tuple[ZoomParticipant, ...] = ()


class ZoomApiClient:
    def __init__(
        self,
        account_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        *,
        api_base_url: str = "https://api.zoom.us/v2",
        auth_base_url: str = "https://zoom.us",
        timeout_seconds: int = 8,
        page_size: int = 30,
    ):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_base_url = api_base_url.rstrip("/")
        self.auth_base_url = auth_base_url.rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.page_size = max(1, min(300, int(page_size)))
        self._access_token = ""
        self._token_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.client_id and self.client_secret)

    def live_meetings(self) -> list[ZoomLiveMeeting]:
        meetings = self._live_meeting_headers()
        live: list[ZoomLiveMeeting] = []
        for meeting in meetings:
            meeting_id = _meeting_id(meeting)
            if not meeting_id:
                continue
            live.append(
                ZoomLiveMeeting(
                    meeting_id=meeting_id,
                    topic=str(meeting.get("topic") or meeting.get("meeting_name") or ""),
                    participants=tuple(self.live_participants(meeting_id)),
                )
            )
        return live

    def live_participants(self, meeting_id: str) -> list[ZoomParticipant]:
        participants: list[ZoomParticipant] = []
        next_page_token = ""
        while True:
            params = {"type": "live", "page_size": self.page_size}
            if next_page_token:
                params["next_page_token"] = next_page_token
            payload = self._get_json(f"/metrics/meetings/{_encode_meeting_id(meeting_id)}/participants", params=params)
            for raw in payload.get("participants") or []:
                if isinstance(raw, dict):
                    participant = _participant(raw)
                    if participant:
                        participants.append(participant)
            next_page_token = str(payload.get("next_page_token") or "")
            if not next_page_token:
                break
        return participants

    def _live_meeting_headers(self) -> list[dict[str, Any]]:
        meetings: list[dict[str, Any]] = []
        next_page_token = ""
        while True:
            params = {"type": "live", "page_size": self.page_size}
            if next_page_token:
                params["next_page_token"] = next_page_token
            payload = self._get_json("/metrics/meetings", params=params)
            meetings.extend(item for item in payload.get("meetings") or [] if isinstance(item, dict))
            next_page_token = str(payload.get("next_page_token") or "")
            if not next_page_token:
                break
        return meetings

    def _get_json(self, path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise ValueError("Zoom API credentials are required for polling")
        response = requests.get(
            f"{self.api_base_url}{path}",
            headers={"Authorization": f"Bearer {self._token()}"},
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token
        response = requests.post(
            f"{self.auth_base_url}/oauth/token",
            params={"grant_type": "account_credentials", "account_id": self.account_id},
            auth=(self.client_id, self.client_secret),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = str(payload.get("access_token") or "")
        expires_in = int(payload.get("expires_in") or 3600)
        self._token_expires_at = now + expires_in
        if not self._access_token:
            raise ValueError("Zoom OAuth response did not include access_token")
        return self._access_token


class ZoomPollingRunner:
    def __init__(
        self,
        client: ZoomApiClient,
        tracker,
        bus: EventBus,
        *,
        enabled: bool = True,
        poll_seconds: int = 30,
    ):
        self.client = client
        self.tracker = tracker
        self.bus = bus
        self.enabled = enabled
        self.poll_seconds = max(10, int(poll_seconds))
        self._stop = Event()
        self._thread: Thread | None = None
        self._participant_ids: set[str] = set()
        self._warned_unavailable = False

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        if not self.client.configured:
            self._warn_once("Zoom polling skipped: missing Zoom OAuth credentials")
            return
        self._stop.clear()
        self._thread = Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self, now: datetime | None = None) -> None:
        base_now = now or datetime.now(timezone.utc)
        meetings = self.client.live_meetings()
        self.tracker.replace_live_meetings(meetings)
        current_ids = {_participant_key(meeting, participant) for meeting in meetings for participant in meeting.participants}
        previous_ids = self._participant_ids
        for key in sorted(current_ids - previous_ids):
            meeting, participant = _find_participant(meetings, key)
            if meeting and participant:
                self.bus.publish(ambient_signal_to_work_event(_participant_signal(AmbientSignalKind.PARTICIPANT_JOINED, meeting, participant, base_now)))
        for key in sorted(previous_ids - current_ids):
            meeting_id, participant_id = key.split(":", 1)
            self.bus.publish(
                ambient_signal_to_work_event(
                    AmbientSignal(
                        provider=AmbientProvider.ZOOM,
                        kind=AmbientSignalKind.PARTICIPANT_LEFT,
                        actor=participant_id.removeprefix("zoom:"),
                        title=meeting_id,
                        intensity=0.35,
                        occurred_at=base_now,
                        external_id=f"{meeting_id}:{participant_id}:left",
                        metadata={"meeting_id": meeting_id, "participant_id": participant_id},
                    )
                )
            )
        self._participant_ids = current_ids

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                self._warn_once(f"Zoom polling unavailable: {error}")
            self._stop.wait(self.poll_seconds)
        self._thread = None

    def _warn_once(self, message: str) -> None:
        if self._warned_unavailable:
            return
        print(message)
        self._warned_unavailable = True


def _meeting_id(meeting: dict[str, Any]) -> str:
    return str(meeting.get("uuid") or meeting.get("id") or meeting.get("meeting_id") or "")


def _participant(raw: dict[str, Any]) -> ZoomParticipant | None:
    email = str(raw.get("email") or raw.get("user_email") or "")
    name = str(raw.get("user_name") or raw.get("name") or email or raw.get("id") or raw.get("participant_user_id") or "")
    participant_id = str(raw.get("id") or raw.get("participant_user_id") or email or name)
    if not participant_id and not name:
        return None
    return ZoomParticipant(participant_id=participant_id, name=name, email=email)


def _encode_meeting_id(meeting_id: str) -> str:
    encoded = quote(str(meeting_id), safe="")
    if str(meeting_id).startswith("/") or "//" in str(meeting_id):
        return quote(encoded, safe="")
    return encoded


def _participant_key(meeting: ZoomLiveMeeting, participant: ZoomParticipant) -> str:
    user_id = _zoom_user_id(participant.email or participant.participant_id or participant.name)
    return f"{meeting.meeting_id}:{user_id}"


def _find_participant(meetings: list[ZoomLiveMeeting], key: str) -> tuple[ZoomLiveMeeting | None, ZoomParticipant | None]:
    for meeting in meetings:
        for participant in meeting.participants:
            if _participant_key(meeting, participant) == key:
                return meeting, participant
    return None, None


def _participant_signal(kind: AmbientSignalKind, meeting: ZoomLiveMeeting, participant: ZoomParticipant, now: datetime) -> AmbientSignal:
    user_id = _zoom_user_id(participant.email or participant.participant_id or participant.name)
    return AmbientSignal(
        provider=AmbientProvider.ZOOM,
        kind=kind,
        actor=participant.name or user_id.removeprefix("zoom:"),
        title=meeting.topic,
        intensity=0.6,
        occurred_at=now,
        external_id=f"{meeting.meeting_id}:{user_id}:{kind.value}",
        metadata={
            "meeting_id": meeting.meeting_id,
            "meeting_topic": meeting.topic,
            "participant_id": participant.participant_id,
            "participant_name": participant.name,
            "participant_email": participant.email,
        },
    )


def _zoom_user_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    return normalized if normalized.startswith("zoom:") else f"zoom:{normalized}"
