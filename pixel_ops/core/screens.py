from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class ScreenPresentation:
    screen_id: str
    label: str
    plugin: str
    layout: dict[str, Any]
    layout_theme: str
    duration_seconds: float


class ScreenRotationController:
    """Owns presentation rotation without owning game or integration state."""

    def __init__(self, display_config: dict[str, Any]):
        self._lock = RLock()
        self._screens: dict[str, ScreenPresentation] = {}
        self._order: list[str] = []
        self._enabled = False
        self._default_duration = 30.0
        self._active_id = ""
        self._pinned = False
        self._activated_at: datetime | None = None
        self._changes_at: datetime | None = None
        self._revision = 0
        self.update_config(display_config)

    def update_config(self, display_config: dict[str, Any], now: datetime | None = None) -> None:
        wall_now = _utc(now)
        screens, order, enabled, default_duration = _parse_config(display_config)
        with self._lock:
            previous_id = self._active_id
            previous_pinned = self._pinned
            self._screens = screens
            self._order = order
            self._enabled = enabled
            self._default_duration = default_duration
            self._active_id = previous_id if previous_id in screens else order[0]
            self._pinned = previous_pinned and previous_id in screens
            self._revision += 1
            self._activate(self._active_id, wall_now, pinned=self._pinned)

    @property
    def presentation(self) -> ScreenPresentation:
        with self._lock:
            return self._screens[self._active_id]

    def advance(self, now: datetime) -> bool:
        wall_now = _utc(now)
        with self._lock:
            if self._pinned or not self._enabled or len(self._order) < 2 or self._changes_at is None:
                return False
            if wall_now < self._changes_at:
                return False
            self._activate(self._relative_id(1), wall_now, pinned=False)
            return True

    def select(self, screen_id: str, *, pinned: bool = True, now: datetime | None = None) -> bool:
        wall_now = _utc(now)
        with self._lock:
            if screen_id not in self._screens:
                raise KeyError(f"Unknown screen: {screen_id}")
            changed = screen_id != self._active_id or pinned != self._pinned
            self._activate(screen_id, wall_now, pinned=pinned)
            return changed

    def next(self, *, pin: bool | None = None, now: datetime | None = None) -> bool:
        return self._move(1, pin=pin, now=now)

    def previous(self, *, pin: bool | None = None, now: datetime | None = None) -> bool:
        return self._move(-1, pin=pin, now=now)

    def resume(self, now: datetime | None = None) -> bool:
        wall_now = _utc(now)
        with self._lock:
            changed = self._pinned
            self._activate(self._active_id, wall_now, pinned=False)
            return changed

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        wall_now = _utc(now)
        with self._lock:
            active = self._screens[self._active_id]
            remaining_ms = None
            if self._changes_at is not None:
                remaining_ms = max(0, round((self._changes_at - wall_now).total_seconds() * 1000))
            next_id = self._relative_id(1) if len(self._order) > 1 else None
            return {
                "available": True,
                "enabled": self._enabled,
                "mode": "pinned" if self._pinned else "automatic",
                "active_screen_id": active.screen_id,
                "active_screen_label": active.label,
                "next_screen_id": next_id,
                "next_screen_label": self._screens[next_id].label if next_id else None,
                "activated_at": _iso(self._activated_at),
                "changes_at": _iso(self._changes_at),
                "remaining_ms": remaining_ms,
                "revision": self._revision,
                "screens": [
                    {
                        "id": screen_id,
                        "label": self._screens[screen_id].label,
                        "plugin": self._screens[screen_id].plugin,
                        "duration_seconds": self._screens[screen_id].duration_seconds,
                    }
                    for screen_id in self._order
                ],
            }

    def _move(self, offset: int, *, pin: bool | None, now: datetime | None) -> bool:
        wall_now = _utc(now)
        with self._lock:
            target = self._relative_id(offset)
            target_pin = self._pinned if pin is None else pin
            changed = target != self._active_id or target_pin != self._pinned
            self._activate(target, wall_now, pinned=target_pin)
            return changed

    def _relative_id(self, offset: int) -> str:
        index = self._order.index(self._active_id)
        return self._order[(index + offset) % len(self._order)]

    def _activate(self, screen_id: str, now: datetime, *, pinned: bool) -> None:
        self._active_id = screen_id
        self._pinned = pinned
        self._activated_at = now
        duration = self._screens[screen_id].duration_seconds
        rotates = self._enabled and len(self._order) > 1 and not pinned
        self._changes_at = now + timedelta(seconds=duration) if rotates else None
        self._revision += 1


def _parse_config(display: dict[str, Any]) -> tuple[dict[str, ScreenPresentation], list[str], bool, float]:
    rotation = display.get("screen_rotation", {})
    rotation = rotation if isinstance(rotation, dict) else {}
    default_duration = max(1.0, float(rotation.get("default_duration_seconds", 30)))
    raw_screens = display.get("screens", {})
    raw_screens = raw_screens if isinstance(raw_screens, dict) else {}
    screens: dict[str, ScreenPresentation] = {}
    for raw_id, raw in raw_screens.items():
        if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
            continue
        screen_id = str(raw_id).strip()
        layout = raw.get("layout")
        if not screen_id or not isinstance(layout, dict):
            continue
        screens[screen_id] = ScreenPresentation(
            screen_id=screen_id,
            label=str(raw.get("label") or screen_id),
            plugin=str(raw.get("plugin") or display.get("device", {}).get("plugin") or "pokemon"),
            layout=dict(layout),
            layout_theme=str(raw.get("layout_theme") or display.get("layout_theme") or "default"),
            duration_seconds=max(1.0, float(raw.get("duration_seconds", default_duration))),
        )
    requested_order = rotation.get("order", [])
    requested_order = requested_order if isinstance(requested_order, list) else []
    order = [str(item) for item in requested_order if str(item) in screens]
    order.extend(screen_id for screen_id in screens if screen_id not in order)
    if not order:
        fallback_id = "default"
        screens[fallback_id] = ScreenPresentation(
            screen_id=fallback_id,
            label="Default",
            plugin=str(display.get("device", {}).get("plugin") or "pokemon"),
            layout=dict(display.get("layout", {})) if isinstance(display.get("layout"), dict) else {},
            layout_theme=str(display.get("layout_theme") or "default"),
            duration_seconds=default_duration,
        )
        order = [fallback_id]
    initial = str(rotation.get("initial_screen") or "")
    if initial in order:
        order.remove(initial)
        order.insert(0, initial)
    return screens, order, bool(rotation.get("enabled", False)), default_duration


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
