from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ProjectItem:
    provider: str
    id: str
    title: str
    state: str = "inbox"
    area: str = ""
    next_action: str = ""
    review_at: datetime | None = None
    touched_at: datetime | None = None
    importance: int = 1
    health: str = ""
    priority: str = ""
    progress: int = 0
    phase: str = ""
    url: str = ""


@dataclass(frozen=True)
class ProjectSnapshot:
    projects: tuple[ProjectItem, ...]
    observed_at: datetime
    provider: str = ""
    status: str = "ok"


@dataclass(frozen=True)
class ProjectRadar:
    focus: ProjectItem | None
    resurfacing: ProjectItem | None
    inbox_count: int
    review_count: int


def project_radar(snapshot: ProjectSnapshot | None, now: datetime) -> ProjectRadar:
    if not snapshot:
        return ProjectRadar(None, None, 0, 0)
    open_projects = [project for project in snapshot.projects if _normalized_state(project.state) not in {"done", "complete", "completed", "concluido", "concluida"}]
    inbox_count = sum(_normalized_state(project.state) in {"", "inbox", "entrada"} for project in open_projects)
    review_count = sum(bool(project.review_at and _aware(project.review_at) <= _aware(now)) for project in open_projects)
    active = [project for project in open_projects if _normalized_state(project.state) in {"active", "ativo", "ativa", "focus", "foco", "doing", "em andamento"}]
    focus = max(active, key=lambda project: (_importance(project), _timestamp(project.touched_at)), default=None)
    candidates = [project for project in open_projects if project is not focus]
    resurfacing = max(candidates, key=lambda project: _attention_score(project, now), default=None)
    if focus is None and resurfacing is not None:
        focus, resurfacing = resurfacing, max(
            (project for project in candidates if project is not focus),
            key=lambda project: _attention_score(project, now),
            default=None,
        )
    return ProjectRadar(focus, resurfacing, inbox_count, review_count)


def project_age_days(project: ProjectItem, now: datetime) -> int:
    if not project.touched_at:
        return 0
    return max(0, int((_aware(now) - _aware(project.touched_at)).total_seconds() // 86400))


def project_radar_scores(project: ProjectItem, now: datetime) -> tuple[int, int, int, int, int]:
    """Return objective HUD scores for clarity, planning, execution, health and impact."""
    clarity = 100 if project.next_action.strip() else 20
    planning = 35
    if project.phase.strip():
        planning += 30
    if project.review_at:
        planning += 35 if _aware(project.review_at) >= _aware(now) else 15
    execution = max(0, min(100, int(project.progress or 0)))
    health_key = _normalized_state(project.health)
    health = {
        "no rumo": 90,
        "on track": 90,
        "atencao": 55,
        "attention": 55,
        "bloqueado": 20,
        "blocked": 20,
    }.get(health_key, 50)
    impact = max(20, min(100, _importance(project) * 34))
    return clarity, planning, execution, health, impact


def _attention_score(project: ProjectItem, now: datetime) -> tuple[int, int, int, float]:
    state = _normalized_state(project.state)
    overdue_days = 0
    if project.review_at and _aware(project.review_at) <= _aware(now):
        overdue_days = max(1, int((_aware(now) - _aware(project.review_at)).total_seconds() // 86400) + 1)
    cadence = 30 if state in {"incubating", "incubando", "someday", "algum dia"} else 7 if state in {"waiting", "aguardando", "blocked", "bloqueado"} else 3
    age_pressure = max(0, project_age_days(project, now) - cadence)
    missing_action = 1 if not project.next_action and state not in {"inbox", "entrada"} else 0
    return (overdue_days, missing_action, age_pressure + _importance(project), -_timestamp(project.touched_at))


def _normalized_state(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _importance(project: ProjectItem) -> int:
    return max(0, min(3, int(project.importance or 0)))


def _timestamp(value: datetime | None) -> float:
    return _aware(value).timestamp() if value else 0.0


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
