from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from pixel_ops.data_sources.ai_usage import AIUsageSnapshot
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.render.fonts import font
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
    layout: dict | None = None,
) -> None:
    if layout:
        _draw_configured_hud(draw, people, event, now, pal, pull_requests or [], ai_usage, weather, layout)
        return

    PixelRenderer.draw_panel(draw, (8, 8, 312, 212), pal.panel, pal.panel_shadow, pal.ink)
    row_font = font(13)
    zone_font = font(9)
    name_font = font(8)
    small_font = font(11)
    chip_font = font(9)
    draw.text((18, 18), "TIME LINK", font=small_font, fill=pal.blue)

    primary = [person for person in people if person.name]
    empty_us = [person for person in people if not person.name]
    positions = (
        (18, 36, 132),
        (162, 36, 132),
        (18, 82, 132),
        (162, 82, 132),
        (18, 128, 132),
    )
    for person, (x, y, width) in zip(primary, positions):
        _draw_timezone_card(draw, person, x, y, width, row_font, zone_font, name_font, pal)

    if empty_us:
        _draw_flag(draw, 18, 165, "US", pal.ink)
    compact_positions = ((38, 164), (104, 164), (170, 164), (236, 164))
    for person, (x, y) in zip(empty_us, compact_positions):
        _draw_timezone_chip(draw, person, x, y, 62, chip_font, zone_font, name_font, pal)

    label = _activity_label(draw, event, pull_requests or [], now, 282, small_font)
    draw.rectangle((18, 190, 300, 191), fill=pal.blue)
    draw.text((18, 195), label, font=small_font, fill=pal.blue)
    if ai_usage and ai_usage.gauges:
        _draw_ai_usage_compact(draw, ai_usage, now, 162, 144, pal)


def _draw_configured_hud(
    draw: ImageDraw.ImageDraw,
    people: list[PersonTime],
    event: CalendarEvent | None,
    now: datetime,
    pal,
    pull_requests: list[PullRequestSummary],
    ai_usage: AIUsageSnapshot | None,
    weather: WeatherState | None,
    layout: dict,
) -> None:
    small_font = font(11)
    chip_font = font(9)
    zone_font = font(8)
    name_font = font(7)
    timezones_box = _layout_box(layout, "timezones", (8, 8, 154, 162))
    PixelRenderer.draw_panel(draw, timezones_box, pal.panel, pal.panel_shadow, pal.ink)
    draw.text((timezones_box[0] + 8, timezones_box[1] + 8), "TIME LINK", font=small_font, fill=pal.blue)
    _draw_timezone_flex_grid(draw, people, timezones_box, chip_font, zone_font, name_font, pal)

    activity_box = _layout_box(layout, "activity", (18, 190, 300, 206))
    _draw_activity_panel(draw, event, pull_requests, now, activity_box, pal)

    gauges_box = _layout_box(layout, "gauges", (162, 144, 304, 178))
    _draw_ai_usage_panel(draw, ai_usage, now, gauges_box, pal)

    weather_box = _layout_box(layout, "weather", (162, 8, 304, 50))
    _draw_weather_compact(draw, weather, weather_box, pal)


def _layout_box(layout: dict, key: str, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    raw = layout.get(key)
    if not isinstance(raw, dict):
        return fallback
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
    gap_y = 4
    content_x = box[0] + padding_x
    content_y = box[1] + 28
    content_w = max(1, box[2] - box[0] - padding_x * 2)
    content_h = max(1, box[3] - content_y - 8)
    min_cell_w = 92 if any(person.show_flag for person in people) else 62
    max_columns = max(1, content_w // min_cell_w)
    columns = min(len(people), max_columns)
    rows = (len(people) + columns - 1) // columns
    while rows * 34 + (rows - 1) * gap_y > content_h and columns < len(people):
        columns += 1
        rows = (len(people) + columns - 1) // columns
    cell_w = max(1, (content_w - gap_x * (columns - 1)) // columns)
    cell_h = max(30, min(42, (content_h - gap_y * (rows - 1)) // rows))
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
    small = font(9)
    label_font = font(11)
    draw.text((box[0] + 8, box[1] + 7), "WEATHER", font=small, fill=pal.blue)
    if weather is None:
        draw.text((box[0] + 8, box[1] + 22), "-", font=label_font, fill=pal.ink)
        return
    effect = weather.primary_effect.upper()[:5]
    label = f"{round(weather.temperature_c):d}C {effect}"
    draw.text((box[0] + 8, box[1] + 22), _fit_text(draw, label, box[2] - box[0] - 16, label_font), font=label_font, fill=pal.ink)


def _draw_activity_panel(
    draw: ImageDraw.ImageDraw,
    event: CalendarEvent | None,
    pull_requests: list[PullRequestSummary],
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    title_font = font(9)
    text_font = font(10)
    content_width = max(1, box[2] - box[0] - 16)
    draw.text((box[0] + 8, box[1] + 6), "SIGNALS", font=title_font, fill=pal.blue)
    label = _activity_label(draw, event, pull_requests, now, content_width, text_font)
    draw.text((box[0] + 8, box[1] + 20), label, font=text_font, fill=pal.ink)


def _draw_ai_usage_panel(draw: ImageDraw.ImageDraw, ai_usage: AIUsageSnapshot | None, now: datetime, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    title_font = font(9)
    value_font = font(10)
    draw.text((box[0] + 8, box[1] + 6), "AI GAUGE", font=title_font, fill=pal.blue)
    if not ai_usage or not ai_usage.gauges:
        draw.text((box[0] + 8, box[1] + 20), "-", font=value_font, fill=pal.ink)
        return
    _draw_ai_usage_compact(draw, ai_usage, now, box[0] + 8, box[1] + 22, pal)


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
    draw.text((x, y - 2), "AI", font=small, fill=pal.blue)
    for index, gauge in enumerate(gauges):
        row_y = y + index * 10
        label = _ai_usage_gauge_short_label(gauge)
        draw.text((x + 27, row_y - 2), label, font=small, fill=pal.ink)
        bar_x = x + 40
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
