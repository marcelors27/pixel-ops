from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from pixel_ops.data_sources.ai_usage import AIUsageSnapshot
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.timezones import PersonTime
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
    _draw_flag(draw, x, y + 1, person.country, pal.ink)
    draw.text((x + 20, y - 2), f"{person.display_key or person.key} {person.local_time:%H:%M}", font=row_font, fill=pal.ink)
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
    pal,
) -> None:
    label = _fit_text(draw, f"{person.display_key or person.key} {person.local_time:%H:%M}", width, chip_font)
    draw.text((x, y - 1), label, font=chip_font, fill=pal.ink)
    draw.text((x, y + 13), _fit_text(draw, person.timezone_label, width, zone_font), font=zone_font, fill=pal.blue)


def draw_hud(
    draw: ImageDraw.ImageDraw,
    people: list[PersonTime],
    event: CalendarEvent | None,
    now: datetime,
    pal,
    pull_requests: list[PullRequestSummary] | None = None,
    ai_usage: AIUsageSnapshot | None = None,
) -> None:
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
        _draw_timezone_chip(draw, person, x, y, 62, chip_font, zone_font, pal)

    label = _activity_label(draw, event, pull_requests or [], now, 282, small_font)
    draw.rectangle((18, 190, 300, 191), fill=pal.blue)
    draw.text((18, 195), label, font=small_font, fill=pal.blue)
    if ai_usage and ai_usage.gauges:
        _draw_ai_usage_compact(draw, ai_usage, now, 162, 144, pal)


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
        state = "DRAFT" if pr.draft else "PR"
        items.append(f"{state}: #{pr.number} {pr.title}")
    if not items:
        items.append("NEXT: No meetings | PRS: none open")
    index = int(now.timestamp() // 5) % len(items)
    return _fit_text(draw, items[index], width, text_font)


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
        value = _ai_usage_gauge_value(gauge, pct)
        draw.text((bar_x + bar_width + 3, row_y - 2), _fit_text(draw, value, 28, small), font=small, fill=pal.ink)


def _ai_usage_gauge_short_label(gauge) -> str:
    if gauge.provider == "openai_api":
        return "API"
    return "5H" if "5H" in gauge.label else "W"


def _ai_usage_gauge_value(gauge, pct: float | None) -> str:
    if gauge.status == "error":
        return "ERR"
    if gauge.provider == "openai_api":
        return _ai_usage_label(gauge.total_tokens, gauge.cost_usd)
    if pct is not None and gauge.reset_at:
        return f"{max(0.0, min(100.0, pct)):.0f}%"
    return _ai_usage_label(gauge.total_tokens, gauge.cost_usd)


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
