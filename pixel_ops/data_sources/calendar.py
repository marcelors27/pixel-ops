from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    location: str = ""
    description: str = ""
    organizer: str = ""
    attendees: tuple[str, ...] = ()
    meeting_url: str = ""
    all_day: bool = False

    def countdown_label(self, now: datetime) -> str:
        remaining = self.starts_at - now
        if remaining.total_seconds() <= 0:
            return "now"
        minutes = int(remaining.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes}m"
        return f"{minutes // 60}h{minutes % 60:02d}"


def next_mock_event(now: datetime) -> CalendarEvent:
    minute_bucket = 15 - (now.minute % 15)
    if minute_bucket < 3:
        minute_bucket += 15
    starts_at = now + timedelta(minutes=minute_bucket)
    return CalendarEvent("Product Review", starts_at, ends_at=starts_at + timedelta(minutes=30), location="Demo room")


def next_ics_event(path: str | Path, now: datetime) -> CalendarEvent | None:
    events = ics_events_between(path, now, now + timedelta(days=370))
    return min(events, key=lambda event: event.starts_at) if events else None


def today_ics_events(path: str | Path, now: datetime) -> list[CalendarEvent]:
    start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    end = start + timedelta(days=1)
    return ics_events_between(path, start, end)


def ics_events_between(path: str | Path, start: datetime, end: datetime) -> list[CalendarEvent]:
    ics_path = Path(path)
    if not ics_path.exists():
        return []
    events: list[CalendarEvent] = []
    title = None
    starts_at = None
    ends_at = None
    rrule = None
    exdates: set[datetime] = set()
    location = ""
    description = ""
    organizer = ""
    attendees: list[str] = []
    meeting_url = ""
    all_day = False
    for raw_line in _unfold_ics_lines(ics_path.read_text(encoding="utf-8", errors="ignore")):
        line = raw_line.strip()
        name = _ics_property_name(line)
        if name == "SUMMARY":
            title = _clean_ics_text(line.split(":", 1)[1])[:80]
        elif line.startswith("DTSTART"):
            starts_at = _parse_ics_datetime(line, start)
            all_day = "VALUE=DATE" in line.split(":", 1)[0]
        elif line.startswith("DTEND"):
            ends_at = _parse_ics_datetime(line, start)
        elif name == "LOCATION":
            location = _clean_ics_text(line.split(":", 1)[1])[:120]
        elif name == "DESCRIPTION":
            description = _clean_ics_text(line.split(":", 1)[1])[:240]
            meeting_url = meeting_url or _first_url(description)
        elif name == "ORGANIZER":
            organizer = _ics_person_label(line)
        elif name == "ATTENDEE":
            attendee = _ics_person_label(line)
            if attendee and attendee not in attendees:
                attendees.append(attendee)
        elif line.startswith("RRULE:"):
            rrule = line.split(":", 1)[1]
        elif line.startswith("EXDATE"):
            exdates.update(_parse_ics_datetime_values(line, start))
        elif line == "END:VEVENT" and title and starts_at:
            meeting_url = meeting_url or _first_url(location)
            duration = (ends_at - starts_at) if ends_at else None
            for occurrence_start in _event_occurrences_between(starts_at, rrule, exdates, start, end):
                occurrence_end = occurrence_start + duration if duration else None
                events.append(
                    CalendarEvent(
                        title,
                        occurrence_start,
                        ends_at=occurrence_end,
                        location=location,
                        description=description,
                        organizer=organizer,
                        attendees=tuple(attendees[:12]),
                        meeting_url=meeting_url,
                        all_day=all_day,
                    )
                )
            title = None
            starts_at = None
            ends_at = None
            rrule = None
            exdates = set()
            location = ""
            description = ""
            organizer = ""
            attendees = []
            meeting_url = ""
            all_day = False
    return sorted(events, key=lambda event: (event.starts_at, event.title.lower()))


def download_ics(url: str, cache_path: str | Path, timeout_seconds: int = 8) -> Path | None:
    if not url:
        return None
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException:
        return path if path.exists() else None
    path.write_text(response.text, encoding="utf-8")
    return path


def _unfold_ics_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)
    return lines


def _parse_ics_datetime(line: str, now: datetime) -> datetime | None:
    head, value = line.split(":", 1)
    try:
        if "VALUE=DATE" in head:
            parsed_date = datetime.strptime(value[:8], "%Y%m%d").date()
            return datetime.combine(parsed_date, time.min, tzinfo=now.tzinfo)
        if value.endswith("Z"):
            return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone(now.tzinfo)
        tz = _tzid_from_head(head)
        parsed = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        if tz:
            return parsed.replace(tzinfo=ZoneInfo(tz)).astimezone(now.tzinfo)
        return parsed.replace(tzinfo=now.tzinfo)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _parse_ics_datetime_values(line: str, now: datetime) -> list[datetime]:
    head, values = line.split(":", 1)
    parsed: list[datetime] = []
    for value in values.split(","):
        dt = _parse_ics_datetime(f"{head}:{value}", now)
        if dt:
            parsed.append(dt)
    return parsed


def _event_occurrences_between(
    starts_at: datetime,
    rrule: str | None,
    exdates: set[datetime],
    start: datetime,
    end: datetime,
) -> list[datetime]:
    if not rrule:
        return [starts_at] if start <= starts_at < end else []
    occurrences: list[datetime] = []
    horizon_days = max(1, min(370, (end.date() - start.date()).days + 8))
    checked_now = start - timedelta(days=1)
    for _ in range(horizon_days + 1):
        next_start = _next_recurrence(starts_at, rrule, exdates, checked_now, horizon_days=horizon_days)
        if not next_start or next_start >= end:
            break
        if next_start >= start:
            occurrences.append(next_start)
        checked_now = next_start
    return occurrences


def _next_recurrence(
    starts_at: datetime,
    rrule: str | None,
    exdates: set[datetime],
    now: datetime,
    horizon_days: int = 370,
) -> datetime | None:
    if not rrule:
        return None
    rule = _parse_rrule(rrule)
    freq = rule.get("FREQ", "")
    interval = max(1, int(rule.get("INTERVAL", "1")))
    until = _parse_rrule_until(rule.get("UNTIL"), now)
    count = int(rule.get("COUNT", "0") or "0")
    bydays = _parse_bydays(rule.get("BYDAY")) or (starts_at.weekday(),)

    checked = 0
    for day_offset in range(0, horizon_days + 1):
        candidate_date = (now + timedelta(days=day_offset)).date()
        candidate = datetime.combine(candidate_date, starts_at.timetz())
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=starts_at.tzinfo)
        candidate = candidate.astimezone(now.tzinfo)
        if candidate <= now or candidate < starts_at:
            continue
        if until and candidate > until:
            return None
        if candidate.replace(microsecond=0) in {item.replace(microsecond=0) for item in exdates}:
            continue
        if not _matches_recurrence(candidate, starts_at, freq, interval, bydays):
            continue
        if count and _occurrence_index(candidate, starts_at, freq, bydays) >= count:
            return None
        checked += 1
        return candidate
    return None


def _ics_property_name(line: str) -> str:
    head = line.split(":", 1)[0]
    return head.split(";", 1)[0].upper()


def _ics_person_label(line: str) -> str:
    head, value = line.split(":", 1)
    params = _ics_params(head)
    label = params.get("CN") or value.removeprefix("mailto:").split("@", 1)[0]
    return _clean_ics_text(label)[:48]


def _ics_params(head: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in head.split(";")[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        params[key.upper()] = value.strip('"')
    return params


def _clean_ics_text(value: str) -> str:
    text = _unescape_ics_text(value)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.replace("\\n", " ").split())


def _first_url(value: str) -> str:
    match = re.search(r"https?://[^\s<>\"]+", value)
    return match.group(0).rstrip(".,)") if match else ""


def _parse_rrule(rrule: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in rrule.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            values[key] = value
    return values


def _parse_rrule_until(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    return _parse_ics_datetime(f"DTSTART:{value}", now)


def _parse_bydays(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    mapping = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
    days = []
    for item in value.split(","):
        key = item[-2:]
        if key in mapping:
            days.append(mapping[key])
    return tuple(days)


def _matches_recurrence(
    candidate: datetime,
    starts_at: datetime,
    freq: str,
    interval: int,
    bydays: tuple[int, ...],
) -> bool:
    if freq == "DAILY":
        return (candidate.date() - starts_at.date()).days % interval == 0
    if freq == "WEEKLY":
        start_week = starts_at.date() - timedelta(days=starts_at.weekday())
        candidate_week = candidate.date() - timedelta(days=candidate.weekday())
        weeks = (candidate_week - start_week).days // 7
        return weeks % interval == 0 and candidate.weekday() in bydays
    if freq == "MONTHLY":
        months = (candidate.year - starts_at.year) * 12 + candidate.month - starts_at.month
        return months % interval == 0 and candidate.day == starts_at.day
    return False


def _occurrence_index(candidate: datetime, starts_at: datetime, freq: str, bydays: tuple[int, ...]) -> int:
    if freq == "DAILY":
        return (candidate.date() - starts_at.date()).days + 1
    if freq == "WEEKLY":
        return ((candidate.date() - starts_at.date()).days // 7) * max(1, len(bydays)) + 1
    if freq == "MONTHLY":
        return (candidate.year - starts_at.year) * 12 + candidate.month - starts_at.month + 1
    return 1


def _tzid_from_head(head: str) -> str | None:
    for part in head.split(";"):
        if part.startswith("TZID="):
            return part.split("=", 1)[1]
    return None


def _unescape_ics_text(value: str) -> str:
    return (
        value.replace("\\n", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )
