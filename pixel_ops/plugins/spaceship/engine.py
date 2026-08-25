from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from PIL import Image

from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.plugins.spaceship.persistence import AsteroidRecord, ShipProfile, SpaceshipStateStore


MATERIALS = ("iron", "silicon_crystal", "orbital_cobalt", "energy_ice", "amber_ore", "data_fragment")


@dataclass(frozen=True)
class SpaceshipSnapshot:
    now: datetime
    profile: ShipProfile
    resources: dict[str, int]
    asteroids: tuple[AsteroidRecord, ...]
    observations: dict[str, object]
    recent_event: WorkEvent | None


class SpaceshipEngine:
    name = "spaceship"

    def __init__(self, scene, store: SpaceshipStateStore, config: dict | None = None):
        cfg = config or {}
        self.scene = scene
        self.store = store
        self.save_interval = max(1.0, float(cfg.get("save_interval_seconds", 15)))
        self.max_tick = max(0.1, float(cfg.get("max_tick_seconds", 30)))
        self.distance_rate = max(0.0, float(cfg.get("distance_per_active_second", 0.02)))
        self.energy_rate = max(0.0, float(cfg.get("energy_per_active_second", 1 / 60)))
        self.now: datetime | None = None
        self.last_tick: datetime | None = None
        self.pending_active_seconds = 0.0
        self.observations: dict[str, object] = {}
        self.recent_event: WorkEvent | None = None
        self._profile = self.store.profile()
        self._resources = self.store.resources()
        self._asteroids = tuple(self.store.asteroids())

    def consume(self, event: PixelOpsEvent | WorkEvent) -> None:
        if isinstance(event, WorkEvent):
            self._consume_work_event(event)
            return
        if event.type == "runtime.tick":
            self._consume_tick(event.occurred_at)
            return
        value = event.payload.get("value")
        self.observations[event.type] = value
        if event.type == "github.pull_requests_updated" and isinstance(value, list):
            self._observe_pull_requests(value, event.occurred_at)

    def render(self) -> Image.Image:
        if self.now is None:
            raise RuntimeError("SpaceshipEngine requires runtime.tick before render")
        return self.scene.render(self.snapshot())

    def snapshot(self) -> SpaceshipSnapshot:
        if self.now is None:
            raise RuntimeError("SpaceshipEngine requires runtime.tick before snapshot")
        return SpaceshipSnapshot(
            now=self.now,
            profile=self._profile,
            resources=dict(self._resources),
            asteroids=self._asteroids,
            observations=dict(self.observations),
            recent_event=self.recent_event,
        )

    def close(self) -> None:
        self._flush()
        self.last_tick = None

    def _consume_tick(self, now: datetime) -> None:
        if self.last_tick is not None:
            elapsed = (now - self.last_tick).total_seconds()
            if elapsed > 0:
                self.pending_active_seconds += min(elapsed, self.max_tick)
        self.last_tick = now
        self.now = now
        if self.pending_active_seconds >= self.save_interval:
            self._flush()

    def _flush(self) -> None:
        if self.pending_active_seconds <= 0 or self.now is None:
            return
        self.store.advance_time(self.pending_active_seconds, self.distance_rate, self.energy_rate, self.now)
        self.pending_active_seconds = 0.0
        self._refresh_profile()

    def _observe_pull_requests(self, values: list, now: datetime) -> None:
        for value in values:
            if not isinstance(value, PullRequestSummary):
                continue
            pr_key = f"{value.repo}#{value.number}"
            self.store.discover_asteroid(
                pr_key, value.repo, value.number, material_for_pr(pr_key), _asteroid_state(value.review_state), now
            )
        self._refresh_cargo()

    def _consume_work_event(self, event: WorkEvent) -> None:
        self.recent_event = event
        if event.source != "github":
            return
        event_key = event.external_id or _fallback_event_key(event)
        pr_key = _pr_key(event)
        if pr_key is None:
            return
        state, resource = _event_effect(event.category)
        now = event.occurred_at or self.now or datetime.now().astimezone()
        repo, _, number = pr_key.rpartition("#")
        if repo and number.isdigit():
            self.store.discover_asteroid(pr_key, repo, int(number), material_for_pr(pr_key), "detected", now)
        self.store.apply_event(event_key, pr_key, state, resource, now)
        self._refresh_cargo()

    def _refresh_profile(self) -> None:
        self._profile = self.store.profile()

    def _refresh_cargo(self) -> None:
        self._resources = self.store.resources()
        self._asteroids = tuple(self.store.asteroids())


def material_for_pr(pr_key: str) -> str:
    digest = hashlib.sha256(pr_key.encode("utf-8")).digest()
    return MATERIALS[digest[0] % len(MATERIALS)]


def _pr_key(event: WorkEvent) -> str | None:
    external = str(event.external_id or "")
    if "#" in external:
        return external.split(":", 1)[0]
    if event.repo and "#" in event.title:
        number = event.title.split("#", 1)[1].split()[0]
        return f"{event.repo}#{number}"
    return None


def _event_effect(category: EventCategory) -> tuple[str, str | None]:
    effects = {
        EventCategory.PULL_REQUEST: ("detected", None),
        EventCategory.REVIEW_REQUESTED: ("sampling", "mineral_sample"),
        EventCategory.PR_APPROVED: ("certified", "data_fragment"),
        EventCategory.MERGE: ("refined", "refined_alloy"),
        EventCategory.PR_CLOSED: ("abandoned", None),
        EventCategory.BUILD_BROKEN: ("unstable", None),
    }
    return effects.get(category, (category.value, None))


def _asteroid_state(review_state: str) -> str:
    return {"merged": "refined", "closed": "abandoned", "open": "detected", "review": "sampling"}.get(
        str(review_state or "").lower(), str(review_state or "detected")
    )


def _fallback_event_key(event: WorkEvent) -> str:
    raw = f"{event.source}|{event.category.value}|{event.repo}|{event.title}|{event.occurred_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
