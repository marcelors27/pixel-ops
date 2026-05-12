from __future__ import annotations

from datetime import datetime, time


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def status_for(now: datetime, work_start: str, work_end: str) -> str:
    start = parse_hhmm(work_start)
    end = parse_hhmm(work_end)
    current = now.time()
    if start <= current < end:
        minutes_to_end = ((end.hour * 60 + end.minute) - (current.hour * 60 + current.minute))
        return "ending" if minutes_to_end <= 60 else "working"
    return "off"
