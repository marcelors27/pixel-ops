from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .availability import status_for


@dataclass(frozen=True)
class PersonTime:
    key: str
    name: str
    timezone: str
    local_time: datetime
    status: str
    country: str = ""
    timezone_label: str = ""
    display_key: str = ""
    show_flag: bool = False


def build_people_times(people: list[dict], now: datetime | None = None) -> list[PersonTime]:
    base_now = now or datetime.now().astimezone()
    rows = []
    for person in people:
        local = base_now.astimezone(ZoneInfo(person["timezone"]))
        is_daylight = bool(local.dst() and local.dst().total_seconds())
        display_key = person.get("daylight_key" if is_daylight else "standard_key", person["key"])
        rows.append(
            PersonTime(
                key=person["key"],
                name=person["name"],
                timezone=person["timezone"],
                local_time=local,
                status=status_for(local, person.get("work_start", "09:00"), person.get("work_end", "18:00")),
                country=person.get("country", ""),
                timezone_label=person.get("timezone_label", person["timezone"].split("/")[-1].replace("_", " ")),
                display_key=display_key,
                show_flag=bool(person.get("show_flag", False)),
            )
        )
    return rows
