from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass(frozen=True)
class CrossHeroWorkoutLine:
    text: str
    emphasized: bool = False
    gap_before: bool = False


@dataclass(frozen=True)
class CrossHeroWorkout:
    title: str = "WOD"
    description: str = ""
    sections: tuple[str, ...] = ()
    program: str = ""
    structured_lines: tuple[CrossHeroWorkoutLine, ...] = ()


@dataclass(frozen=True)
class CrossHeroClass:
    starts_at: datetime
    name: str
    reservations: int = 0
    capacity: int | None = None
    coach: str = ""


@dataclass(frozen=True)
class CrossHeroDaySnapshot:
    day: date
    workout: CrossHeroWorkout | None = None
    classes: tuple[CrossHeroClass, ...] = ()


class CrossHeroDaySource:
    """Fetches the current workout and class occupancy from configurable CrossHero endpoints.

    CrossHero only documents its authentication headers publicly. The workout and
    schedule URLs are therefore config values so a box can use the endpoints from
    its official Postman collection without coupling the runtime to private routes.
    """

    def __init__(
        self,
        *,
        box_env: str = "PIXEL_OPS_CROSSHERO_BOX",
        token_env: str = "PIXEL_OPS_CROSSHERO_ACCESS_TOKEN",
        session_cookie_env: str = "PIXEL_OPS_CROSSHERO_SESSION_COOKIE",
        dashboard_url: str = "https://crosshero.com/dashboard/classes",
        workout_url: str = "",
        classes_url: str = "",
        poll_seconds: int = 300,
        timeout_seconds: int = 10,
        env_path: Path | None = None,
    ):
        self.box_env = box_env
        self.token_env = token_env
        self.session_cookie_env = session_cookie_env
        self.dashboard_url = dashboard_url.strip()
        self.workout_url = workout_url.strip()
        self.classes_url = classes_url.strip()
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.env_path = env_path
        self._last_poll_at: datetime | None = None
        self._snapshot: CrossHeroDaySnapshot | None = None

    def current(self, now: datetime) -> CrossHeroDaySnapshot | None:
        box = os.getenv(self.box_env, "").strip()
        token = os.getenv(self.token_env, "").strip()
        session_cookie = self._secret(self.session_cookie_env, prefer_file=True)
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = now
        if session_cookie and self.dashboard_url:
            try:
                self._snapshot = self._current_from_dashboard(now, session_cookie)
            except (requests.RequestException, ValueError, TypeError):
                pass
            return self._snapshot
        if not box or not token or not (self.workout_url or self.classes_url):
            return None
        params = {"date": now.date().isoformat()}
        headers = {"CROSSHERO_BOX": box, "CROSSHERO_ACCESS_TOKEN": token}
        workout = None
        classes: tuple[CrossHeroClass, ...] = ()
        if self.workout_url:
            workout = _workout_from_payload(self._get_json(self.workout_url, headers, params))
        if self.classes_url:
            classes = _classes_from_payload(self._get_json(self.classes_url, headers, params), now)
        self._snapshot = CrossHeroDaySnapshot(day=now.date(), workout=workout, classes=classes)
        return self._snapshot

    def _secret(self, name: str, *, prefer_file: bool = False) -> str:
        file_value = _dot_env_value(self.env_path, name)
        if prefer_file and file_value:
            return file_value
        return os.getenv(name, "").strip() or file_value

    def _current_from_dashboard(self, now: datetime, session_cookie: str) -> CrossHeroDaySnapshot:
        headers = {"Cookie": session_cookie, "Accept": "text/html,application/xhtml+xml"}
        index_html = self._get_text(self.dashboard_url, headers)
        choices = _dashboard_class_choices(index_html)
        if not choices:
            raise ValueError("CrossHero dashboard session is invalid or no classes are available")
        classes: list[CrossHeroClass] = []
        workout = None
        for class_id, label in choices:
            detail_html = self._get_text(self.dashboard_url, headers, {"id": class_id})
            detail_class, detail_workout = _dashboard_detail(detail_html, label, now)
            if detail_class is not None:
                classes.append(detail_class)
            if workout is None and detail_workout is not None:
                workout = detail_workout
        return CrossHeroDaySnapshot(now.date(), workout, tuple(sorted(classes, key=lambda item: item.starts_at)))

    def _get_json(self, url: str, headers: dict[str, str], params: dict[str, str]) -> Any:
        response = requests.get(url, headers=headers, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def _get_text(self, url: str, headers: dict[str, str], params: dict[str, str] | None = None) -> str:
        response = requests.get(url, headers=headers, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text


def _dashboard_class_choices(page: str) -> list[tuple[str, str]]:
    select = re.search(r'<select[^>]+id=["\']class_reservation_single_class_id["\'][^>]*>(.*?)</select>', page, re.IGNORECASE | re.DOTALL)
    if not select:
        return []
    choices = []
    for attrs, body in re.findall(r"<option\b([^>]*)>(.*?)</option>", select.group(1), re.IGNORECASE | re.DOTALL):
        value_match = re.search(r'value=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        label = _html_text(body)
        if value_match and label and re.search(r"\b\d{1,2}:\d{2}\b", label):
            choices.append((value_match.group(1), label))
    return choices


def _dashboard_detail(page: str, fallback_label: str, now: datetime) -> tuple[CrossHeroClass | None, CrossHeroWorkout | None]:
    occupancy = _class_text(page, "ch-classes-occupancy__stat-value")
    meta = _class_text(page, "ch-classes-occupancy__meta")
    coach = _class_text(page, "ch-classes-occupancy__coach-name")
    count_match = re.search(r"(\d+)\s*/\s*(\d+)", occupancy)
    time_match = re.search(r"(\d{1,2}:\d{2})", meta or fallback_label)
    if not time_match:
        return None, _dashboard_workout(page)
    starts_at = datetime.combine(now.date(), datetime.strptime(time_match.group(1), "%H:%M").time(), tzinfo=now.tzinfo)
    name = re.sub(r"^\s*\d{1,2}:\d{2}\s*", "", fallback_label).strip() or "Aula"
    class_item = CrossHeroClass(
        starts_at=starts_at,
        name=name,
        reservations=int(count_match.group(1)) if count_match else 0,
        capacity=int(count_match.group(2)) if count_match else None,
        coach=coach.removeprefix("Coach ").strip(),
    )
    return class_item, _dashboard_workout(page)


def _dashboard_workout(page: str) -> CrossHeroWorkout | None:
    section = re.search(r'<section[^>]+class=["\'][^"\']*today-wod[^"\']*["\'][^>]*>(.*?)</section>', page, re.IGNORECASE | re.DOTALL)
    if not section:
        return None
    components = re.search(r'<div[^>]+class=["\'][^"\']*today-wod-components[^"\']*["\'][^>]*>(.*)', section.group(1), re.IGNORECASE | re.DOTALL)
    html = components.group(1) if components else section.group(1)
    lines = _workout_html_lines(html)
    text = "\n".join(line.text for line in lines)
    return CrossHeroWorkout(title="WOD do dia", description=text, structured_lines=lines) if text else None


def _class_text(page: str, class_name: str) -> str:
    match = re.search(rf'<[^>]+class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>(.*?)</[^>]+>', page, re.IGNORECASE | re.DOTALL)
    return _html_text(match.group(1)) if match else ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def _html_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return " · ".join(parser.parts)


class _WorkoutTextExtractor(HTMLParser):
    _BLOCK_TAGS = {"div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[tuple[str, bool] | None] = []
        self.parts: list[str] = []
        self.strong_depth = 0
        self.emphasized = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._BLOCK_TAGS and self.parts:
            self._flush()
        if tag in {"strong", "b"}:
            self.strong_depth += 1
        elif tag == "br":
            self._flush(force=True)
        elif tag == "img":
            alt = next((value for name, value in attrs if name.lower() in {"alt", "aria-label", "title"} and value), "")
            value = _workout_display_text(alt)
            if value:
                self.parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"strong", "b"}:
            self.strong_depth = max(0, self.strong_depth - 1)
        if tag in self._BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        value = _workout_display_text(data)
        if not value:
            return
        self.parts.append(value)
        self.emphasized = self.emphasized or self.strong_depth > 0

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self, *, force: bool = False) -> None:
        text = " ".join(self.parts).strip()
        if text:
            self.lines.append((text, self.emphasized))
        elif force and self.lines and self.lines[-1] is not None:
            self.lines.append(None)
        self.parts = []
        self.emphasized = False


def _workout_html_lines(value: str) -> tuple[CrossHeroWorkoutLine, ...]:
    parser = _WorkoutTextExtractor()
    parser.feed(value)
    parser.close()
    result: list[CrossHeroWorkoutLine] = []
    gap_before = False
    for item in parser.lines:
        if item is None:
            gap_before = True
            continue
        text, emphasized = item
        result.append(CrossHeroWorkoutLine(text, emphasized, gap_before and bool(result)))
        gap_before = False
    return tuple(result)


def _workout_display_text(value: str) -> str:
    """Normalize spacing while preserving complete Unicode emoji sequences."""
    return " ".join(str(value or "").split())


def workout_display_tokens(value: str) -> tuple[tuple[str, bool], ...]:
    """Split workout text into regular text and complete Unicode emoji sequences."""
    parts: list[str] = []
    source = str(value or "")
    index = 0
    tokens: list[tuple[str, bool]] = []
    while index < len(source):
        if _starts_emoji_sequence(source, index):
            if parts:
                tokens.append(("".join(parts), False))
                parts = []
            end = _emoji_sequence_end(source, index)
            tokens.append((source[index:end], True))
            index = end
            continue
        parts.append(source[index])
        index += 1
    if parts:
        tokens.append(("".join(parts), False))
    return tuple(tokens)


def _starts_emoji_sequence(value: str, index: int) -> bool:
    codepoint = ord(value[index])
    if _is_emoji_codepoint(codepoint):
        return True
    return value[index] in "#*0123456789" and any(ord(item) == 0x20E3 for item in value[index + 1 : index + 3])


def _emoji_sequence_end(value: str, start: int) -> int:
    index = start + 1
    first = ord(value[start])
    if 0x1F1E6 <= first <= 0x1F1FF and index < len(value) and 0x1F1E6 <= ord(value[index]) <= 0x1F1FF:
        index += 1
    while index < len(value):
        codepoint = ord(value[index])
        if codepoint in {0xFE0E, 0xFE0F, 0x20E3} or 0x1F3FB <= codepoint <= 0x1F3FF or 0xE0020 <= codepoint <= 0xE007F:
            index += 1
            continue
        if codepoint == 0x200D and index + 1 < len(value) and _is_emoji_codepoint(ord(value[index + 1])):
            index += 2
            continue
        break
    return index


def _is_emoji_codepoint(codepoint: int) -> bool:
    starters = _unicode_emoji_starters()
    if starters:
        return codepoint in starters
    return (
        codepoint in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x2328, 0x23CF, 0x24C2, 0x25B6, 0x25C0, 0x2B50, 0x2B55, 0x3030, 0x303D, 0x3297, 0x3299}
        or 0x2194 <= codepoint <= 0x2199
        or 0x21A9 <= codepoint <= 0x21AA
        or 0x231A <= codepoint <= 0x231B
        or 0x23E9 <= codepoint <= 0x23F3
        or 0x23F8 <= codepoint <= 0x23FA
        or 0x25AA <= codepoint <= 0x25AB
        or 0x25FB <= codepoint <= 0x25FE
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2934 <= codepoint <= 0x2935
        or 0x2B05 <= codepoint <= 0x2B07
        or 0x2B1B <= codepoint <= 0x2B1C
        or 0x1F000 <= codepoint <= 0x1FAFF
    )


def _emoji_key(value: str) -> str:
    return "-".join(f"{ord(character):X}" for character in value)


@lru_cache(maxsize=1)
def _unicode_emoji_names() -> dict[str, str]:
    path = Path(__file__).with_name("unicode_emoji_names.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return {str(key): str(value).upper() for key, value in payload.items() if key and value}


@lru_cache(maxsize=1)
def _unicode_emoji_starters() -> frozenset[int]:
    return frozenset(
        int(key.split("-", 1)[0], 16)
        for key in _unicode_emoji_names()
        if key.split("-", 1)[0] not in {"23", "2A", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39"}
    )


def _dot_env_value(path: Path | None, name: str) -> str:
    if path is None:
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    pattern = re.compile(rf"^(?:export\s+)?{re.escape(name)}=(.*)$")
    for line in raw.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        return value.replace('\\"', '"').replace("\\\\", "\\").strip()
    return ""


def _workout_from_payload(payload: Any) -> CrossHeroWorkout | None:
    item = _first_record(payload, ("workout", "wod", "workouts", "data", "results"))
    if not isinstance(item, dict):
        return None
    title = _workout_display_text(_text(item, "title", "name")) or "WOD"
    description = _workout_display_text(_text(item, "description", "content", "details", "workout"))
    program = _workout_display_text(_nested_text(item.get("program")) or _text(item, "program_name", "activity"))
    raw_sections = item.get("sections") or item.get("blocks") or item.get("parts") or []
    sections = []
    if isinstance(raw_sections, list):
        for section in raw_sections:
            value = _workout_display_text(_nested_text(section))
            if value:
                sections.append(value)
    if not description and not sections and title == "WOD":
        return None
    return CrossHeroWorkout(title=title, description=description, sections=tuple(sections), program=program)


def _classes_from_payload(payload: Any, now: datetime) -> tuple[CrossHeroClass, ...]:
    records = _record_list(payload, ("classes", "schedules", "sessions", "activities", "data", "results"))
    classes = []
    for item in records:
        if not isinstance(item, dict):
            continue
        starts_at = _parse_datetime(item, now)
        if starts_at is None or starts_at.date() != now.date():
            continue
        reservations = _integer(item, "reservations_count", "bookings_count", "registered_count", "attendees_count", "reservations", "bookings") or 0
        capacity = _integer(item, "capacity", "limit", "max_reservations", "slots")
        name = _text(item, "name", "title", "program_name", "activity") or _nested_text(item.get("program")) or "Aula"
        coach = _text(item, "coach_name", "instructor_name") or _nested_text(item.get("coach"))
        classes.append(CrossHeroClass(starts_at, name, reservations, capacity, coach))
    return tuple(sorted(classes, key=lambda item: item.starts_at))


def _first_record(payload: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(payload, list):
        return payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value[0] if value else None
        if isinstance(value, dict):
            nested = _first_record(value, keys)
            return nested if nested is not None else value
    return payload


def _record_list(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _record_list(value, keys)
            if nested:
                return nested
    return []


def _parse_datetime(item: dict[str, Any], now: datetime) -> datetime | None:
    value = next((item.get(key) for key in ("starts_at", "start_at", "start", "datetime", "date_time") if item.get(key)), None)
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(now.tzinfo) if parsed.tzinfo and now.tzinfo else parsed
        except ValueError:
            pass
    day = str(item.get("date") or now.date().isoformat())
    clock = str(item.get("time") or item.get("start_time") or "")
    try:
        return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=now.tzinfo)
    except ValueError:
        return None


def _text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(value, "name", "title", "description", "content", "text")
    return ""


def _integer(item: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, list):
            return len(value)
        try:
            if value is not None and value != "":
                return int(value)
        except (TypeError, ValueError):
            continue
    return None
