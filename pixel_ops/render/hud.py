from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from pixel_ops.data_sources.ai_usage import AIUsageSnapshot
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.pc_stats import PCStatsSnapshot
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.render.fonts import font, icon_font
from pixel_ops.render.renderer import PixelRenderer


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, text_font) -> str:
    if draw.textbbox((0, 0), text, font=text_font)[2] <= max_width:
        return text
    clipped = text
    while clipped and draw.textbbox((0, 0), f"{clipped}...", font=text_font)[2] > max_width:
        clipped = clipped[:-1]
    return f"{clipped}..." if clipped else ""


def _draw_flag(draw: ImageDraw.ImageDraw, x: int, y: int, code: str, outline) -> None:
    code = code.upper()
    box = (x, y, x + 15, y + 10)
    draw.rectangle(box, fill=(238, 238, 238), outline=outline)
    if code == "MX":
        draw.rectangle((x + 1, y + 1, x + 5, y + 9), fill=(0, 104, 71))
        draw.rectangle((x + 6, y + 1, x + 10, y + 9), fill=(255, 255, 255))
        draw.rectangle((x + 11, y + 1, x + 14, y + 9), fill=(206, 17, 38))
        draw.point((x + 8, y + 5), fill=(133, 96, 38))
    elif code == "US":
        for row in range(1, 10, 2):
            draw.rectangle((x + 1, y + row, x + 14, y + row), fill=(178, 34, 52))
        draw.rectangle((x + 1, y + 1, x + 7, y + 5), fill=(60, 59, 110))
        draw.point((x + 3, y + 2), fill=(255, 255, 255))
        draw.point((x + 5, y + 4), fill=(255, 255, 255))
    elif code == "BR":
        draw.rectangle((x + 1, y + 1, x + 14, y + 9), fill=(0, 156, 59))
        draw.polygon(((x + 8, y + 2), (x + 13, y + 5), (x + 8, y + 8), (x + 3, y + 5)), fill=(255, 223, 0))
        draw.ellipse((x + 6, y + 3, x + 10, y + 7), fill=(0, 39, 118))
    elif code == "IN":
        draw.rectangle((x + 1, y + 1, x + 14, y + 3), fill=(255, 153, 51))
        draw.rectangle((x + 1, y + 4, x + 14, y + 6), fill=(255, 255, 255))
        draw.rectangle((x + 1, y + 7, x + 14, y + 9), fill=(19, 136, 8))
        draw.point((x + 8, y + 5), fill=(0, 0, 128))
    elif code == "PT":
        draw.rectangle((x + 1, y + 1, x + 6, y + 9), fill=(0, 102, 0))
        draw.rectangle((x + 7, y + 1, x + 14, y + 9), fill=(255, 0, 0))
        draw.point((x + 7, y + 5), fill=(255, 204, 0))


def _draw_timezone_card(
    draw: ImageDraw.ImageDraw,
    person: PersonTime,
    x: int,
    y: int,
    width: int,
    row_font,
    zone_font,
    name_font,
    pal,
) -> None:
    status_color = {
        "working": pal.green,
        "ending": pal.yellow,
        "off": pal.red,
    }.get(person.status, pal.panel_shadow)
    text_x = x
    if person.show_flag and person.country:
        _draw_flag(draw, x, y + 1, person.country, pal.ink)
        text_x += 20
    draw.text((text_x, y - 2), f"{person.display_key or person.key} {person.local_time:%H:%M}", font=row_font, fill=pal.ink)
    draw.rectangle((x + width - 9, y + 3, x + width - 2, y + 10), fill=status_color, outline=pal.ink)
    draw.text((x, y + 14), _fit_text(draw, person.timezone_label, width, zone_font), font=zone_font, fill=pal.ink)
    if person.name:
        draw.text((x, y + 25), _fit_text(draw, person.name, width, name_font), font=name_font, fill=pal.blue)


def _draw_timezone_chip(
    draw: ImageDraw.ImageDraw,
    person: PersonTime,
    x: int,
    y: int,
    width: int,
    chip_font,
    zone_font,
    name_font,
    pal,
    show_status: bool = False,
) -> None:
    status_color = {
        "working": pal.green,
        "ending": pal.yellow,
        "off": pal.red,
    }.get(person.status, pal.panel_shadow)
    text_x = x
    text_width = width
    if person.show_flag and person.country:
        _draw_flag(draw, x, y + 1, person.country, pal.ink)
        text_x += 20
        text_width -= 20
    if show_status:
        draw.rectangle((x + width - 7, y + 4, x + width - 2, y + 9), fill=status_color, outline=pal.ink)
        text_width -= 9
    text_width = max(1, text_width)
    label = _fit_text(draw, f"{person.display_key or person.key} {person.local_time:%H:%M}", text_width, chip_font)
    draw.text((text_x, y - 1), label, font=chip_font, fill=pal.ink)
    draw.text((text_x, y + 13), _fit_text(draw, person.timezone_label, text_width, zone_font), font=zone_font, fill=pal.blue)
    if person.name:
        draw.text((text_x, y + 24), _fit_text(draw, person.name, text_width, name_font), font=name_font, fill=pal.ink)


def draw_hud(
    draw: ImageDraw.ImageDraw,
    people: list[PersonTime],
    event: CalendarEvent | None,
    now: datetime,
    pal,
    pull_requests: list[PullRequestSummary] | None = None,
    ai_usage: AIUsageSnapshot | None = None,
    weather: WeatherState | None = None,
    work_events: list[WorkEvent] | None = None,
    pc_stats: PCStatsSnapshot | None = None,
    layout: dict | None = None,
) -> None:
    if layout:
        _draw_configured_hud(draw, people, event, now, pal, pull_requests or [], ai_usage, weather, work_events or [], pc_stats, layout)
        return

    PixelRenderer.draw_panel(draw, (8, 8, 312, 212), pal.panel, pal.panel_shadow, pal.ink)
    row_font = font(13)
    zone_font = font(9)
    name_font = font(8)
    small_font = font(11)
    chip_font = font(9)

    primary = [person for person in people if person.name]
    empty_us = [person for person in people if not person.name]
    positions = (
        (18, 20, 132),
        (162, 20, 132),
        (18, 66, 132),
        (162, 66, 132),
        (18, 112, 132),
    )
    for person, (x, y, width) in zip(primary, positions):
        _draw_timezone_card(draw, person, x, y, width, row_font, zone_font, name_font, pal)

    if empty_us:
        _draw_flag(draw, 18, 151, "US", pal.ink)
    compact_positions = ((38, 150), (104, 150), (170, 150), (236, 150))
    for person, (x, y) in zip(empty_us, compact_positions):
        _draw_timezone_chip(draw, person, x, y, 62, chip_font, zone_font, name_font, pal)

    label = _activity_label(draw, event, pull_requests or [], now, 282, small_font)
    draw.rectangle((18, 181, 300, 182), fill=pal.blue)
    draw.text((18, 186), label, font=small_font, fill=pal.blue)
    if ai_usage and ai_usage.gauges:
        _draw_ai_usage_compact(draw, ai_usage, now, 162, 132, pal)


def _draw_configured_hud(
    draw: ImageDraw.ImageDraw,
    people: list[PersonTime],
    event: CalendarEvent | None,
    now: datetime,
    pal,
    pull_requests: list[PullRequestSummary],
    ai_usage: AIUsageSnapshot | None,
    weather: WeatherState | None,
    work_events: list[WorkEvent],
    pc_stats: PCStatsSnapshot | None,
    layout: dict,
) -> None:
    small_font = font(11)
    chip_font = font(9)
    zone_font = font(8)
    name_font = font(7)
    for timezones_box in _layout_boxes(layout, "timezones"):
        PixelRenderer.draw_panel(draw, timezones_box, pal.panel, pal.panel_shadow, pal.ink)
        _draw_timezone_flex_grid(draw, people, timezones_box, chip_font, zone_font, name_font, pal)

    for activity_box in _layout_boxes(layout, "activity"):
        _draw_activity_panel(draw, event, pull_requests, now, activity_box, pal)

    for route_box in _layout_boxes(layout, "route_signal"):
        _draw_route_signal_panel(draw, event, pull_requests, ai_usage, work_events, now, route_box, pal)

    for gauges_box in _layout_boxes(layout, "gauges"):
        _draw_ai_usage_panel(draw, ai_usage, now, gauges_box, pal)

    for weather_box in _layout_boxes(layout, "weather"):
        _draw_weather_compact(draw, weather, weather_box, pal)

    for pc_box in _layout_boxes(layout, "pc_stats"):
        _draw_pc_stats_panel(draw, pc_stats, pc_box, pal)


def _layout_boxes(layout: dict, key: str) -> list[tuple[int, int, int, int]]:
    boxes = []
    for item_key, raw in layout.items():
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or item_key)
        if kind == key:
            boxes.append(_layout_raw_box(raw, (0, 0, 1, 1)))
    return boxes


def _layout_box(layout: dict, key: str, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    raw = layout.get(key)
    if not isinstance(raw, dict):
        for item_key, item in layout.items():
            if isinstance(item, dict) and str(item.get("kind") or item_key) == key:
                raw = item
                break
    if not isinstance(raw, dict):
        return fallback
    return _layout_raw_box(raw, fallback)


def _layout_raw_box(raw: dict, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    try:
        x = int(raw.get("x", fallback[0]))
        y = int(raw.get("y", fallback[1]))
        width = int(raw.get("width", fallback[2] - fallback[0]))
        height = int(raw.get("height", fallback[3] - fallback[1]))
    except (TypeError, ValueError):
        return fallback
    return x, y, x + max(1, width), y + max(1, height)


def _draw_timezone_flex_grid(
    draw: ImageDraw.ImageDraw,
    people: list[PersonTime],
    box: tuple[int, int, int, int],
    chip_font,
    zone_font,
    name_font,
    pal,
) -> None:
    if not people:
        return
    padding_x = 8
    gap_x = 6
    gap_y = 2
    content_x = box[0] + padding_x
    content_y = box[1] + 8
    content_w = max(1, box[2] - box[0] - padding_x * 2)
    content_h = max(1, box[3] - content_y - 8)
    min_cell_w = 92 if any(person.show_flag for person in people) else 62
    max_columns = max(1, content_w // min_cell_w)
    columns = min(len(people), max_columns)
    rows = (len(people) + columns - 1) // columns
    while rows * 30 + (rows - 1) * gap_y > content_h and columns < len(people):
        columns += 1
        rows = (len(people) + columns - 1) // columns
    cell_w = max(1, (content_w - gap_x * (columns - 1)) // columns)
    cell_h = max(28, min(42, (content_h - gap_y * (rows - 1)) // rows))
    for index, person in enumerate(people):
        row = index // columns
        column = index % columns
        x = content_x + column * (cell_w + gap_x)
        y = content_y + row * (cell_h + gap_y)
        _draw_timezone_chip(
            draw,
            person,
            x,
            y,
            cell_w,
            chip_font,
            zone_font,
            name_font,
            pal,
            show_status=True,
        )


def _draw_weather_compact(draw: ImageDraw.ImageDraw, weather: WeatherState | None, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    label_font = font(10)
    range_font = font(7)
    icon_x = box[0] + 7
    icon_y = box[1] + max(4, (box[3] - box[1] - 22) // 2)
    text_x = box[0] + 34
    text_width = max(1, box[2] - text_x - 8)
    if weather is None:
        _draw_weather_icon(draw, "unknown", icon_x, icon_y, pal)
        draw.text((text_x, box[1] + 9), "-", font=label_font, fill=pal.ink)
        return
    condition = _weather_condition(weather)
    _draw_weather_icon(draw, condition, icon_x, icon_y, pal)
    label = f"{round(weather.temperature_c):d}° {_weather_condition_label(condition)}"
    draw.text((text_x, box[1] + 7), _fit_text(draw, label, text_width, label_font), font=label_font, fill=pal.ink)
    _draw_temperature_range(draw, weather, text_x, box[1] + 24, text_width, range_font, pal)


def _draw_temperature_range(
    draw: ImageDraw.ImageDraw,
    weather: WeatherState,
    x: int,
    y: int,
    width: int,
    text_font,
    pal,
) -> None:
    arrow_font = icon_font(6)
    up = "\uf062"
    down = "\uf063"
    high = "--" if weather.temperature_max_c is None else f"{round(weather.temperature_max_c):d}"
    low = "--" if weather.temperature_min_c is None else f"{round(weather.temperature_min_c):d}"
    first = f"{high}°"
    second = f"{low}°"
    draw.text((x, y + 1), up, font=arrow_font, fill=pal.red)
    draw.text((x + 8, y), first, font=text_font, fill=pal.ink)
    second_x = x + 37
    if draw.textbbox((0, 0), f"{first} {second}", font=text_font)[2] > width - 12:
        second_x = x + 32
    draw.text((second_x, y + 1), down, font=arrow_font, fill=pal.blue)
    draw.text((second_x + 8, y), second, font=text_font, fill=pal.ink)


def _weather_condition(weather: WeatherState) -> str:
    code = weather.weather_code
    effects = set(weather.effects)
    if code in (95, 96, 99):
        return "storm"
    if code in (71, 73, 75, 77, 85, 86) or "snow" in effects:
        return "snow"
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82) or "rain" in effects:
        return "rain"
    if code in (45, 48):
        return "fog"
    if code == 3:
        return "cloudy"
    if code in (1, 2) or weather.cloud_cover >= 35:
        return "partly"
    if "wind" in effects:
        return "wind"
    if "cold" in effects:
        return "cold"
    if "hot" in effects:
        return "hot"
    return "clear"


def _weather_condition_label(condition: str) -> str:
    return {
        "clear": "CLEAR",
        "partly": "PART",
        "cloudy": "CLOUD",
        "fog": "FOG",
        "drizzle": "DRIZ",
        "rain": "RAIN",
        "snow": "SNOW",
        "storm": "STORM",
        "wind": "WIND",
        "cold": "COLD",
        "hot": "HOT",
    }.get(condition, condition.upper()[:5])


def _draw_weather_icon(draw: ImageDraw.ImageDraw, condition: str, x: int, y: int, pal) -> None:
    glyph, color = _weather_icon_glyph(condition, getattr(pal, "phase", ""))
    glyph_font = icon_font(20)
    bounds = draw.textbbox((0, 0), glyph, font=glyph_font)
    draw.text((x + (24 - (bounds[2] - bounds[0])) // 2, y + (23 - (bounds[3] - bounds[1])) // 2 - bounds[1]), glyph, font=glyph_font, fill=color)


def _weather_icon_glyph(condition: str, day_phase: str) -> tuple[str, tuple[int, int, int]]:
    icons = {
        "clear": ("\uf185", (176, 120, 48)),  # sun
        "partly": ("\uf6c4", (176, 120, 48)),  # cloud-sun
        "rain": ("\uf73d", (64, 128, 200)),  # cloud-rain
        "drizzle": ("\uf73d", (64, 128, 200)),  # cloud-rain
        "storm": ("\uf0e7", (176, 120, 48)),  # bolt
        "snow": ("\uf2dc", (64, 128, 184)),  # snowflake
        "fog": ("\uf75f", (104, 120, 136)),  # smog
        "cloudy": ("\uf0c2", (104, 120, 136)),  # cloud
        "wind": ("\uf72e", (64, 88, 112)),  # wind
        "cold": ("\uf2dc", (64, 128, 184)),  # snowflake
        "hot": ("\uf185", (176, 120, 48)),  # sun
        "unknown": ("\uf059", (72, 88, 112)),  # circle-question
    }
    if condition == "clear" and day_phase == "night":
        return "\uf186", (112, 112, 128)  # moon
    if condition == "partly" and day_phase == "night":
        return "\uf6c3", (112, 112, 128)  # cloud-moon
    if condition in icons:
        return icons[condition]
    if day_phase == "night":
        return "\uf186", (112, 112, 128)  # moon
    return "\uf185", (176, 120, 48)  # sun


def _draw_activity_panel(
    draw: ImageDraw.ImageDraw,
    event: CalendarEvent | None,
    pull_requests: list[PullRequestSummary],
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    text_font = font(10)
    content_width = max(1, box[2] - box[0] - 16)
    label = _activity_label(draw, event, pull_requests, now, content_width, text_font)
    draw.text((box[0] + 8, box[1] + 13), label, font=text_font, fill=pal.ink)


def _draw_route_signal_panel(
    draw: ImageDraw.ImageDraw,
    event: CalendarEvent | None,
    pull_requests: list[PullRequestSummary],
    ai_usage: AIUsageSnapshot | None,
    work_events: list[WorkEvent],
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    signal = _route_signal(event, pull_requests, ai_usage, work_events, now)
    glyph, color = _route_signal_icon(signal)
    glyph_font = icon_font(14)
    label_font = font(10)
    icon_x = box[0] + 8
    icon_y = box[1] + max(4, (box[3] - box[1] - 16) // 2)
    bounds = draw.textbbox((0, 0), glyph, font=glyph_font)
    draw.text((icon_x + (18 - (bounds[2] - bounds[0])) // 2, icon_y - bounds[1]), glyph, font=glyph_font, fill=color)
    label = f"ROUTE {signal}"
    draw.text((box[0] + 34, box[1] + 13), _fit_text(draw, label, box[2] - box[0] - 42, label_font), font=label_font, fill=pal.ink)


def _route_signal(
    event: CalendarEvent | None,
    pull_requests: list[PullRequestSummary],
    ai_usage: AIUsageSnapshot | None,
    work_events: list[WorkEvent],
    now: datetime,
) -> str:
    if event:
        seconds_until = (event.starts_at - now).total_seconds()
        if seconds_until <= 10 * 60:
            return "MEET"
    if any(event.category in (EventCategory.BUILD_BROKEN, EventCategory.DEPLOY_STARTED, EventCategory.DEPLOY_COMPLETED) for event in work_events):
        return "OPS"
    if any((not pr.draft) and pr.review_state.lower() in ("review", "changes_requested") for pr in pull_requests):
        return "REVIEW"
    if ai_usage and ai_usage.pressure >= 0.75:
        return "AI"
    if pull_requests:
        return "CODE"
    return "CALM"


def _route_signal_icon(signal: str) -> tuple[str, tuple[int, int, int]]:
    icons = {
        "MEET": ("\uf073", (112, 112, 184)),  # calendar
        "OPS": ("\uf135", (184, 104, 64)),  # rocket
        "REVIEW": ("\uf06e", (80, 136, 192)),  # eye
        "AI": ("\uf544", (136, 96, 184)),  # robot
        "CODE": ("\uf121", (72, 144, 104)),  # code
        "CALM": ("\uf14e", (96, 120, 160)),  # compass
    }
    return icons.get(signal, icons["CALM"])


def _draw_ai_usage_panel(draw: ImageDraw.ImageDraw, ai_usage: AIUsageSnapshot | None, now: datetime, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    value_font = font(10)
    if not ai_usage or not ai_usage.gauges:
        draw.text((box[0] + 8, box[1] + 13), "-", font=value_font, fill=pal.ink)
        return
    _draw_ai_usage_compact(draw, ai_usage, now, box[0] + 8, box[1] + 13, pal)


def _draw_pc_stats_panel(draw: ImageDraw.ImageDraw, pc_stats: PCStatsSnapshot | None, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    label_font = font(7)
    value_font = font(9)
    if not pc_stats or not pc_stats.metrics:
        draw.text((box[0] + 8, box[1] + 13), "PC -", font=value_font, fill=pal.ink)
        return
    x0, y0, x1, y1 = box
    content_w = max(1, x1 - x0 - 12)
    row_h = 12
    max_rows = max(1, (y1 - y0 - 8) // row_h)
    metrics = pc_stats.metrics[:max_rows]
    for index, metric in enumerate(metrics):
        y = y0 + 6 + index * row_h
        color = _pc_metric_color(metric.status, pal)
        draw.rectangle((x0 + 6, y + 2, x0 + 10, y + 6), fill=color, outline=pal.ink)
        label = _fit_text(draw, metric.label, 26, label_font)
        draw.text((x0 + 14, y - 1), label, font=label_font, fill=pal.blue)
        value_x = x0 + 43
        draw.text((value_x, y - 2), _fit_text(draw, metric.value, content_w - 37, value_font), font=value_font, fill=pal.ink)


def _pc_metric_color(status: str, pal):
    if status == "critical":
        return pal.red
    if status == "warn":
        return pal.yellow
    if status == "unknown":
        return pal.panel_shadow
    return pal.green


def _activity_label(
    draw: ImageDraw.ImageDraw,
    event: CalendarEvent | None,
    pull_requests: list[PullRequestSummary],
    now: datetime,
    width: int,
    text_font,
) -> str:
    items: list[str] = []
    if event:
        items.append(f"NEXT: {event.title[:22]} {event.countdown_label(now)}")
    for pr in pull_requests[:4]:
        state = _pull_request_state_label(pr)
        items.append(f"{state}: #{pr.number} {pr.title}")
    if not items:
        items.append("NEXT: No meetings | PRS: none open")
    index = int(now.timestamp() // 5) % len(items)
    return _fit_text(draw, items[index], width, text_font)


def _pull_request_state_label(pr: PullRequestSummary) -> str:
    if pr.draft:
        return "DRAFT"
    state = pr.review_state.lower()
    if state == "merged":
        return "MERGED"
    if state == "closed":
        return "CLOSED"
    return "PR"


def _draw_ai_usage_compact(draw: ImageDraw.ImageDraw, ai_usage: AIUsageSnapshot, now: datetime, x: int, y: int, pal) -> None:
    codex = [item for item in ai_usage.gauges if item.provider == "codex" and item.status != "quiet"]
    codex_5h = next((item for item in codex if "5H" in item.label), None)
    codex_weekly = next((item for item in codex if "5H" not in item.label), None)
    openai_api = next((item for item in ai_usage.gauges if item.provider == "openai_api" and item.status != "quiet"), None)
    second = openai_api if openai_api and int(now.timestamp() // 6) % 2 == 0 else codex_weekly
    gauges = [item for item in (codex_5h, second or openai_api) if item is not None]
    if not gauges:
        return
    small = font(7)
    bar_width = 46
    for index, gauge in enumerate(gauges):
        row_y = y + index * 10
        label = _ai_usage_gauge_short_label(gauge)
        draw.text((x, row_y - 2), label, font=small, fill=pal.ink)
        bar_x = x + 14
        draw.rectangle((bar_x, row_y, bar_x + bar_width, row_y + 5), outline=pal.ink, fill=pal.panel)
        pct = gauge.used_percent
        if pct is None and gauge.provider != "openai_api" and gauge.total_tokens:
            pct = min(100.0, gauge.total_tokens / 250_000 * 100.0)
        if pct is not None:
            fill_width = int(bar_width * max(0.0, min(100.0, pct)) / 100.0)
            color = pal.red if pct >= 90 else pal.yellow if pct >= 75 else pal.green
            if fill_width > 0:
                draw.rectangle((bar_x + 1, row_y + 1, bar_x + fill_width, row_y + 4), fill=color)
        value = _ai_usage_gauge_value(gauge, pct, now)
        draw.text((bar_x + bar_width + 3, row_y - 2), _fit_text(draw, value, 45, small), font=small, fill=pal.ink)


def _ai_usage_gauge_short_label(gauge) -> str:
    if gauge.provider == "openai_api":
        return "API"
    return "5H" if "5H" in gauge.label else "W"


def _ai_usage_gauge_value(gauge, pct: float | None, now: datetime) -> str:
    if gauge.status == "error":
        return "ERR"
    if gauge.provider == "openai_api":
        return _ai_usage_label(gauge.total_tokens, gauge.cost_usd)
    if pct is not None and gauge.reset_at:
        return f"{_ai_usage_reset_countdown(now, gauge.reset_at)} +{max(0.0, min(100.0, pct)):.0f}%"
    return _ai_usage_label(gauge.total_tokens, gauge.cost_usd)


def _ai_usage_reset_countdown(now: datetime, reset_at: datetime) -> str:
    base_now = now if now.tzinfo else now.astimezone()
    target = reset_at.astimezone(base_now.tzinfo) if reset_at.tzinfo else reset_at.replace(tzinfo=base_now.tzinfo)
    remaining = (target - base_now).total_seconds()
    if remaining <= 0:
        return "now"
    minutes = int(remaining // 60)
    if minutes < 60:
        return f"{max(1, minutes)}m"
    hours = int(minutes // 60)
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _ai_usage_label(tokens: int | None, cost: float | None) -> str:
    if cost and cost >= 0.01:
        return f"${cost:.0f}" if cost >= 10 else f"${cost:.1f}"
    if not tokens:
        return "-"
    if tokens >= 1_000_000:
        if tokens >= 10_000_000:
            return f"{tokens / 1_000_000:.0f}M"
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens // 1000}k"
    return str(tokens)
