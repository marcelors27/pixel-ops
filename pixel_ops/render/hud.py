from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from pixel_ops.data_sources.ai_usage import AIUsageSnapshot
from pixel_ops.data_sources.availability import status_for
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.media import MediaNowPlaying
from pixel_ops.data_sources.pc_stats import PCStatsSnapshot
from pixel_ops.data_sources.tasks import TaskItem, TaskSnapshot
from pixel_ops.data_sources.timezones import PersonTime
from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.render.fonts import font, icon_font, scaled_px
from pixel_ops.render.renderer import PixelRenderer


HUD_THEME_TONES: dict[str, dict[str, tuple[int, int, int]]] = {
    "pokemon": {
        "timezones": (93, 169, 233),
        "timezones_clock": (93, 169, 233),
        "activity": (239, 100, 97),
        "meetings_day": (247, 201, 72),
        "calendar_day": (247, 201, 72),
        "route_signal": (95, 191, 122),
        "gauges": (190, 119, 246),
        "weather": (79, 192, 218),
        "pc_stats": (240, 163, 93),
        "tasks": (126, 196, 122),
        "clickup_tasks": (126, 196, 122),
        "tasks_board": (223, 122, 122),
        "media": (247, 169, 64),
        "now_playing": (247, 169, 64),
        "pokemon_captures": (235, 86, 96),
    },
    "terminal": {
        "timezones": (98, 220, 142),
        "timezones_clock": (98, 220, 142),
        "activity": (96, 204, 255),
        "meetings_day": (232, 219, 116),
        "calendar_day": (232, 219, 116),
        "route_signal": (142, 255, 188),
        "gauges": (150, 225, 255),
        "weather": (90, 195, 255),
        "pc_stats": (188, 255, 128),
        "tasks": (122, 240, 164),
        "clickup_tasks": (122, 240, 164),
        "tasks_board": (255, 160, 128),
        "media": (188, 255, 128),
        "now_playing": (188, 255, 128),
        "pokemon_captures": (122, 240, 164),
    },
    "ocean": {
        "timezones": (75, 175, 225),
        "timezones_clock": (75, 175, 225),
        "activity": (91, 204, 189),
        "meetings_day": (165, 216, 255),
        "calendar_day": (165, 216, 255),
        "route_signal": (86, 214, 165),
        "gauges": (120, 190, 255),
        "weather": (66, 197, 218),
        "pc_stats": (88, 183, 210),
        "tasks": (123, 225, 188),
        "clickup_tasks": (123, 225, 188),
        "tasks_board": (102, 190, 235),
        "media": (140, 210, 255),
        "now_playing": (140, 210, 255),
        "pokemon_captures": (98, 184, 222),
    },
    "ember": {
        "timezones": (255, 177, 93),
        "timezones_clock": (255, 177, 93),
        "activity": (255, 111, 91),
        "meetings_day": (255, 207, 102),
        "calendar_day": (255, 207, 102),
        "route_signal": (255, 142, 83),
        "gauges": (234, 118, 165),
        "weather": (255, 154, 89),
        "pc_stats": (255, 190, 98),
        "tasks": (255, 161, 96),
        "clickup_tasks": (255, 161, 96),
        "tasks_board": (255, 112, 112),
        "media": (255, 196, 92),
        "now_playing": (255, 196, 92),
        "pokemon_captures": (255, 96, 96),
    },
}


class _ThemePalette:
    def __init__(self, base, **overrides):
        self._base = base
        self.__dict__.update(overrides)

    def __getattr__(self, name: str):
        return getattr(self._base, name)


def hud_palette_for_kind(pal, layout_theme: str | None, kind: str):
    theme_tones = HUD_THEME_TONES.get(str(layout_theme or "default"))
    if not theme_tones:
        return pal
    accent = theme_tones.get(kind) or next(iter(theme_tones.values()))
    return _ThemePalette(
        pal,
        blue=accent,
        panel_shadow=_mix_color(accent, pal.panel_shadow, 0.38),
    )


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, text_font) -> str:
    if draw.textbbox((0, 0), text, font=text_font)[2] <= max_width:
        return text
    clipped = text
    while clipped and draw.textbbox((0, 0), f"{clipped}...", font=text_font)[2] > max_width:
        clipped = clipped[:-1]
    return f"{clipped}..." if clipped else ""


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, text_font, max_lines: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines:
        used_words = " ".join(lines).split()
        if len(used_words) < len(words) or draw.textbbox((0, 0), lines[-1], font=text_font)[2] > max_width:
            lines[-1] = _fit_text(draw, lines[-1], max_width, text_font)
    return lines


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
    current = person.local_time.strftime("%H:%M")
    key_label = person.display_key or person.key
    time_box = draw.textbbox((0, 0), current, font=row_font)
    time_w = time_box[2] - time_box[0]
    draw.text((text_x, y - 3), current, font=row_font, fill=pal.ink)
    draw.text((text_x + time_w + 5, y + 1), _fit_text(draw, key_label, max(1, width - time_w - 24), zone_font), font=zone_font, fill=pal.blue)
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
    task_snapshot: TaskSnapshot | None = None,
    media: MediaNowPlaying | None = None,
    today_events: list[CalendarEvent] | None = None,
    layout: dict | None = None,
    layout_theme: str | None = None,
) -> None:
    if layout:
        _draw_configured_hud(
            draw,
            people,
            event,
            now,
            pal,
            pull_requests or [],
            ai_usage,
            weather,
            work_events or [],
            pc_stats,
            task_snapshot,
            media,
            today_events or [],
            layout,
            layout_theme,
        )
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
    task_snapshot: TaskSnapshot | None,
    media: MediaNowPlaying | None,
    today_events: list[CalendarEvent],
    layout: dict,
    layout_theme: str | None,
) -> None:
    small_font = font(11)
    chip_font = font(9)
    zone_font = font(8)
    name_font = font(7)
    for timezones_box in _layout_boxes(layout, "timezones"):
        hud_pal = hud_palette_for_kind(pal, layout_theme, "timezones")
        PixelRenderer.draw_panel(draw, timezones_box, hud_pal.panel, hud_pal.panel_shadow, hud_pal.ink)
        inner_box = _draw_panel_title(draw, timezones_box, "TIMEZONES", hud_pal)
        _draw_timezone_flex_grid(draw, people, inner_box, chip_font, zone_font, name_font, hud_pal)

    for timezones_box in _layout_boxes(layout, "timezones_clock"):
        hud_pal = hud_palette_for_kind(pal, layout_theme, "timezones_clock")
        PixelRenderer.draw_panel(draw, timezones_box, hud_pal.panel, hud_pal.panel_shadow, hud_pal.ink)
        inner_box = _draw_panel_title(draw, timezones_box, "TIMEZONES", hud_pal)
        _draw_timezone_clock_grid(draw, people, inner_box, chip_font, zone_font, name_font, hud_pal)

    for activity_box in _layout_boxes(layout, "activity"):
        _draw_activity_panel(draw, event, pull_requests, now, activity_box, hud_palette_for_kind(pal, layout_theme, "activity"))

    for meetings_box in [*_layout_boxes(layout, "meetings_day"), *_layout_boxes(layout, "calendar_day")]:
        _draw_meetings_day_panel(draw, today_events, now, meetings_box, hud_palette_for_kind(pal, layout_theme, "meetings_day"))

    for route_box in _layout_boxes(layout, "route_signal"):
        _draw_route_signal_panel(draw, event, pull_requests, ai_usage, work_events, now, route_box, hud_palette_for_kind(pal, layout_theme, "route_signal"))

    for gauges_box in _layout_boxes(layout, "gauges"):
        _draw_ai_usage_panel(draw, ai_usage, now, gauges_box, hud_palette_for_kind(pal, layout_theme, "gauges"))

    for weather_box in _layout_boxes(layout, "weather"):
        _draw_weather_compact(draw, weather, weather_box, hud_palette_for_kind(pal, layout_theme, "weather"))

    for pc_box in _layout_boxes(layout, "pc_stats"):
        _draw_pc_stats_panel(draw, pc_stats, pc_box, hud_palette_for_kind(pal, layout_theme, "pc_stats"))

    for task_box in [*_layout_boxes(layout, "tasks"), *_layout_boxes(layout, "clickup_tasks")]:
        _draw_tasks_panel(draw, task_snapshot, now, task_box, hud_palette_for_kind(pal, layout_theme, "tasks"))

    for task_board_box in _layout_boxes(layout, "tasks_board"):
        _draw_tasks_board_panel(draw, task_snapshot, now, task_board_box, hud_palette_for_kind(pal, layout_theme, "tasks_board"))

    for media_box in [*_layout_boxes(layout, "media"), *_layout_boxes(layout, "now_playing")]:
        _draw_media_panel(draw, media, now, media_box, hud_palette_for_kind(pal, layout_theme, "media"))


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


def _draw_panel_title(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, pal) -> tuple[int, int, int, int]:
    title_font = font(7)
    x0, y0, x1, y1 = box
    label = _fit_text(draw, title, max(1, x1 - x0 - 18), title_font)
    bounds = draw.textbbox((0, 0), label, font=title_font)
    label_w = bounds[2] - bounds[0] + 8
    label_h = bounds[3] - bounds[1] + 5
    label_x = x0 + 5
    label_y = y0
    draw.rectangle((label_x, label_y, min(x1 - 5, label_x + label_w), label_y + label_h), fill=(255, 255, 255), outline=pal.ink)
    draw.text((label_x + 4, label_y + 2 - bounds[1]), label, font=title_font, fill=pal.blue)
    return x0, min(y1 - 1, y0 + 13), x1, y1


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
    gap_y = 2
    content_x = box[0] + padding_x
    content_y = box[1] + 7
    content_w = max(1, box[2] - box[0] - padding_x * 2)
    content_h = max(1, box[3] - content_y - 8)
    label_w = _timezone_label_width(content_w)
    timeline_w = max(1, content_w - label_w - 4)
    block_count = _timezone_block_count(timeline_w)
    header_h = 17 if content_h >= 54 else 0
    if header_h:
        _draw_timezone_timeline_header(draw, people[0], content_x + label_w + 4, content_y, timeline_w, block_count, zone_font, pal)
        content_y += header_h
        content_h = max(1, content_h - header_h)
    row_h = 24 if content_w >= 220 else 18
    max_rows = max(1, (content_h + gap_y) // (row_h + gap_y))
    visible_people = people[:max_rows]
    block_h = len(visible_people) * row_h + max(0, len(visible_people) - 1) * gap_y
    start_y = content_y + max(0, (content_h - block_h) // 2)
    for index, person in enumerate(visible_people):
        y = start_y + index * (row_h + gap_y)
        _draw_timezone_timeline_row(draw, person, content_x, y, content_w, row_h, chip_font, zone_font, pal)


def _draw_timezone_clock_grid(
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
    padding_y = 7
    gap_x = 8
    gap_y = 4
    content_x = box[0] + padding_x
    content_y = box[1] + padding_y
    content_w = max(1, box[2] - box[0] - padding_x * 2)
    content_h = max(1, box[3] - box[1] - padding_y * 2)
    columns = 2 if content_w >= 180 else 1
    card_w = max(1, (content_w - gap_x * (columns - 1)) // columns)
    row_h = 34 if card_w >= 72 else 24
    max_rows = max(1, (content_h + gap_y) // (row_h + gap_y))
    visible_people = people[: max_rows * columns]
    for index, person in enumerate(visible_people):
        column = index % columns
        row = index // columns
        x = content_x + column * (card_w + gap_x)
        y = content_y + row * (row_h + gap_y)
        if row_h >= 34:
            _draw_timezone_chip(draw, person, x, y, card_w, chip_font, zone_font, name_font, pal, show_status=True)
        else:
            label = _fit_text(draw, f"{person.display_key or person.key} {person.local_time:%H:%M}", card_w, chip_font)
            draw.text((x, y + 4), label, font=chip_font, fill=pal.ink)


def _draw_timezone_timeline_row(
    draw: ImageDraw.ImageDraw,
    person: PersonTime,
    x: int,
    y: int,
    width: int,
    height: int,
    label_font,
    time_font,
    pal,
) -> None:
    label_w = _timezone_label_width(width)
    timeline_w = max(1, width - label_w - 4)
    block_count = _timezone_block_count(timeline_w)
    block_w = max(8, timeline_w // block_count)
    label = person.name or person.timezone_label or person.display_key or person.key
    key_label = person.display_key or person.key
    current = person.local_time.strftime("%H:%M")
    if width >= 220:
        flag_w = 19
        if person.show_flag and person.country:
            _draw_flag(draw, x, y + 2, person.country, pal.ink)
        text_x = x + flag_w
        label_width = max(1, label_w - flag_w - 2)
        clock_w = min(label_width, scaled_px(66))
        clock_h = min(height - 3, scaled_px(19))
        clock_y = y + max(0, (height - clock_h) // 2)
        status_color = {
            "working": pal.green,
            "ending": pal.yellow,
            "off": pal.red,
        }.get(person.status, pal.panel_shadow)
        draw.rectangle((text_x, clock_y, text_x + clock_w, clock_y + clock_h), fill=pal.panel, outline=pal.ink)
        draw.rectangle((text_x + 1, clock_y + 1, text_x + 5, clock_y + clock_h - 1), fill=status_color)
        _draw_segment_clock(draw, current, text_x + 8, clock_y + 2, clock_w - 10, clock_h - 4, pal)
        meta_x = text_x + clock_w + 5
        meta_w = max(1, label_width - clock_w - 5)
        if meta_w >= 24:
            draw.text((meta_x, y), _fit_text(draw, label, meta_w, label_font), font=label_font, fill=pal.ink)
            draw.text((meta_x, y + 11), _fit_text(draw, key_label, meta_w, time_font), font=time_font, fill=pal.blue)
    else:
        if person.name and width >= 180:
            label = person.name.split()[0]
        compact = f"{person.local_time:%H:%M} {label}"
        draw.text((x, y + 2), _fit_text(draw, compact, label_w - 2, label_font), font=label_font, fill=pal.ink)
    block_x = x + label_w + 4
    for index in range(block_count):
        offset = index
        local_time = _future_local_time(person, offset)
        status = status_for(local_time, person.work_start, person.work_end)
        fill = _timezone_timeline_fill(status, pal)
        x0 = block_x + index * block_w
        x1 = min(x + width, block_x + (index + 1) * block_w)
        if x1 <= x0:
            continue
        draw.rectangle((x0, y, x1, y + height), fill=fill)
        outline = pal.ink if index == 0 else _mix_color(pal.ink, pal.panel, 0.55)
        draw.rectangle((x0, y, x1, y + height), outline=outline)
        if index == 0:
            draw.rectangle((x0 + 1, y + 1, x1 - 1, y + height - 1), outline=pal.ink)
        time_label = _compact_hour_label(local_time) if block_w >= 28 else local_time.strftime("%H")
        text_box = draw.textbbox((0, 0), time_label, font=time_font)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        draw.text(
            (x0 + max(1, (x1 - x0 - text_w) // 2), y + max(1, (height - text_h) // 2) - 1),
            time_label,
            font=time_font,
            fill=pal.ink,
        )


def _timezone_label_width(width: int) -> int:
    if width >= 360:
        return min(width // 2, scaled_px(211))
    if width >= 220:
        return min(width // 2, scaled_px(156))
    return min(48, max(26, width // 4))


def _draw_segment_clock(
    draw: ImageDraw.ImageDraw,
    value: str,
    x: int,
    y: int,
    width: int,
    height: int,
    pal,
) -> None:
    digits = [char for char in value if char.isdigit()]
    if len(digits) != 4 or width < 38 or height < 11:
        text_font = font(8)
        draw.text((x, y), _fit_text(draw, value, width, text_font), font=text_font, fill=pal.ink)
        return

    digit_w = max(6, min(10, (width - 7) // 4))
    digit_h = max(9, height)
    stroke = max(1, min(2, digit_w // 4))
    gap = max(1, (width - digit_w * 4 - 3) // 4)
    colon_w = 3
    total_w = digit_w * 4 + gap * 3 + colon_w
    start_x = x + max(0, (width - total_w) // 2)
    digit_y = y + max(0, (height - digit_h) // 2)
    active = pal.ink
    offsets = (
        start_x,
        start_x + digit_w + gap,
        start_x + digit_w * 2 + gap * 2 + colon_w,
        start_x + digit_w * 3 + gap * 3 + colon_w,
    )
    for char, digit_x in zip(digits, offsets):
        _draw_segment_digit(draw, int(char), digit_x, digit_y, digit_w, digit_h, stroke, active)
    colon_x = start_x + digit_w * 2 + gap
    dot = max(1, stroke)
    draw.rectangle((colon_x + 1, digit_y + digit_h // 3 - dot, colon_x + 1 + dot, digit_y + digit_h // 3), fill=active)
    draw.rectangle((colon_x + 1, digit_y + digit_h * 2 // 3, colon_x + 1 + dot, digit_y + digit_h * 2 // 3 + dot), fill=active)


def _draw_segment_digit(
    draw: ImageDraw.ImageDraw,
    digit: int,
    x: int,
    y: int,
    width: int,
    height: int,
    stroke: int,
    active,
) -> None:
    segments = {
        0: "abcedf",
        1: "bc",
        2: "abged",
        3: "abgcd",
        4: "fgbc",
        5: "afgcd",
        6: "afgecd",
        7: "abc",
        8: "abcdefg",
        9: "abfgcd",
    }
    active_segments = set(segments.get(digit, ""))
    mid = y + height // 2
    segment_boxes = {
        "a": (x + stroke, y, x + width - stroke, y + stroke - 1),
        "b": (x + width - stroke, y + stroke, x + width - 1, mid - 1),
        "c": (x + width - stroke, mid + 1, x + width - 1, y + height - stroke - 1),
        "d": (x + stroke, y + height - stroke, x + width - stroke, y + height - 1),
        "e": (x, mid + 1, x + stroke - 1, y + height - stroke - 1),
        "f": (x, y + stroke, x + stroke - 1, mid - 1),
        "g": (x + stroke, mid, x + width - stroke, mid + stroke - 1),
    }
    for name, box in segment_boxes.items():
        if name in active_segments:
            draw.rectangle(box, fill=active)


def _timezone_block_count(timeline_width: int) -> int:
    return min(10, max(4, timeline_width // 30))


def _draw_timezone_timeline_header(
    draw: ImageDraw.ImageDraw,
    anchor: PersonTime,
    x: int,
    y: int,
    width: int,
    block_count: int,
    text_font,
    pal,
) -> None:
    block_w = max(8, width // block_count)
    for index in range(block_count):
        local_time = _future_local_time(anchor, index)
        x0 = x + index * block_w
        x1 = min(x + width, x + (index + 1) * block_w)
        if x1 <= x0:
            continue
        if index == 0:
            draw.rectangle((x0, y, x1, y + 15), fill=pal.blue, outline=pal.ink)
            fill = pal.panel
        else:
            draw.line((x0, y + 3, x0, y + 15), fill=_mix_color(pal.ink, pal.panel, 0.55))
            fill = pal.blue
        date_label = local_time.strftime("%b %-d") if index == 0 or local_time.hour == 0 else ""
        hour_label = _compact_hour_label(local_time)
        if date_label and block_w >= 34:
            label = date_label
        else:
            label = hour_label
        text_w = draw.textbbox((0, 0), label, font=text_font)[2]
        draw.text((x0 + max(1, (x1 - x0 - text_w) // 2), y + 3), label, font=text_font, fill=fill)


def _future_local_time(person: PersonTime, offset_hours: int) -> datetime:
    base = person.local_time.astimezone()
    return (base + timedelta(hours=offset_hours)).astimezone(ZoneInfo(person.timezone))


def _compact_hour_label(value: datetime) -> str:
    hour = int(value.strftime("%I"))
    suffix = value.strftime("%p").lower()[:1]
    return f"{hour}{suffix}"


def _timezone_timeline_fill(status: str, pal):
    if status == "working":
        return _mix_color(pal.blue, pal.panel, 0.28)
    if status == "ending":
        return pal.yellow
    return _mix_color(pal.panel_shadow, pal.panel, 0.35)


def _mix_color(first, second, second_weight: float):
    first_weight = 1.0 - second_weight
    return tuple(int(first[index] * first_weight + second[index] * second_weight) for index in range(3))


def _draw_weather_compact(draw: ImageDraw.ImageDraw, weather: WeatherState | None, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    content_box = _draw_panel_title(draw, box, "WEATHER", pal)
    label_font = font(10)
    range_font = font(7)
    x0, y0, x1, y1 = content_box
    content_w = max(1, x1 - x0 - 12)
    content_h = max(1, y1 - y0 - 8)
    icon_w = 24
    gap = 7
    text_w = min(max(1, content_w - icon_w - gap), 70)
    group_w = icon_w + gap + text_w
    group_x = x0 + max(6, (x1 - x0 - group_w) // 2)
    group_y = y0 + max(4, (content_h - 31) // 2 + 4)
    icon_x = group_x
    icon_y = group_y + max(0, (31 - 23) // 2)
    text_x = group_x + icon_w + gap
    text_width = max(1, min(text_w, x1 - text_x - 6))
    if weather is None:
        _draw_weather_icon(draw, "unknown", icon_x, icon_y, pal)
        dash_w = draw.textbbox((0, 0), "-", font=label_font)[2]
        draw.text((text_x + max(0, (text_width - dash_w) // 2), group_y + 7), "-", font=label_font, fill=pal.ink)
        return
    condition = _weather_condition(weather)
    _draw_weather_icon(draw, condition, icon_x, icon_y, pal)
    label = f"{round(weather.temperature_c):d}° {_weather_condition_label(condition)}"
    draw.text((text_x, group_y + 4), _fit_text(draw, label, text_width, label_font), font=label_font, fill=pal.ink)
    _draw_temperature_range(draw, weather, text_x, group_y + 21, text_width, range_font, pal)


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
    content_box = _draw_panel_title(draw, box, "ACTIVITY", pal)
    text_font = font(10)
    content_width = max(1, content_box[2] - content_box[0] - 16)
    label = _activity_label(draw, event, pull_requests, now, content_width, text_font)
    draw.text((content_box[0] + 8, content_box[1] + 3), label, font=text_font, fill=pal.ink)


def _draw_meetings_day_panel(
    draw: ImageDraw.ImageDraw,
    events: list[CalendarEvent],
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    title_font = font(7)
    time_font = font(8)
    meeting_font = font(8)
    meta_font = font(6)
    x0, y0, x1, y1 = _draw_panel_title(draw, box, "MEETINGS TODAY", pal)
    content_x = x0 + 7
    content_w = max(1, x1 - x0 - 14)
    if not events:
        draw.text((content_x, y0 + 7), "No meetings today", font=meeting_font, fill=pal.ink)
        return

    visible_events = sorted(events, key=lambda item: item.starts_at)
    card_gap = 4
    min_card_h = 28
    max_cards = max(1, min(len(visible_events), (y1 - y0 - 10) // (min_card_h + card_gap)))
    card_h = max(min_card_h, min(58, (y1 - y0 - 8 - card_gap * (max_cards - 1)) // max_cards))
    for index, event in enumerate(visible_events[:max_cards]):
        card_y = y0 + 6 + index * (card_h + card_gap)
        card_box = (content_x, card_y, x1 - 7, min(y1 - 5, card_y + card_h))
        _draw_meeting_card(draw, event, now, card_box, pal, title_font, time_font, meeting_font, meta_font)

    remaining = len(visible_events) - max_cards
    if remaining > 0 and y1 - y0 >= 42:
        label = f"+{remaining} later"
        draw.text((x1 - 7 - draw.textbbox((0, 0), label, font=meta_font)[2], y1 - 12), label, font=meta_font, fill=pal.blue)


def _draw_meeting_card(
    draw: ImageDraw.ImageDraw,
    event: CalendarEvent,
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
    title_font,
    time_font,
    meeting_font,
    meta_font,
) -> None:
    x0, y0, x1, y1 = box
    status, status_color = _meeting_status(event, now, pal)
    card_fill = (246, 248, 252)
    card_shadow = (198, 206, 218)
    card_ink = (16, 24, 38)
    card_meta = (58, 78, 112)
    draw.rectangle((x0 + 1, y0 + 1, x1 + 1, y1 + 1), fill=card_shadow)
    draw.rectangle(box, fill=card_fill, outline=status_color)
    draw.rectangle((x0, y0, x0 + 3, y1), fill=status_color)
    content_w = max(1, x1 - x0 - 10)
    time_label = _meeting_time_label(event)
    status_label = _fit_text(draw, status, max(28, min(54, content_w // 3)), title_font)
    draw.text((x0 + 7, y0 + 2), _fit_text(draw, time_label, max(1, content_w - 58), time_font), font=time_font, fill=status_color)
    draw.text((x1 - 5 - draw.textbbox((0, 0), status_label, font=title_font)[2], y0 + 3), status_label, font=title_font, fill=status_color)

    title_y = y0 + 12
    title_lines = _wrap_text(draw, event.title, content_w, meeting_font, 2 if y1 - y0 >= 48 else 1)
    for line_index, line in enumerate(title_lines):
        draw.text((x0 + 7, title_y + line_index * 10), line, font=meeting_font, fill=card_ink)

    meta_y = title_y + max(1, len(title_lines)) * 10 + 1
    if meta_y + 7 > y1 - 2:
        return
    meta_lines = _meeting_meta_lines(event, now)
    for line in meta_lines:
        if meta_y + 7 > y1 - 2:
            break
        draw.text((x0 + 7, meta_y), _fit_text(draw, line, content_w - 2, meta_font), font=meta_font, fill=card_meta)
        meta_y += 8


def _meeting_status(event: CalendarEvent, now: datetime, pal) -> tuple[str, tuple[int, int, int]]:
    ends_at = event.ends_at or event.starts_at + timedelta(minutes=30)
    if event.starts_at <= now < ends_at:
        return "LIVE", pal.green
    if event.starts_at < now:
        return "DONE", pal.panel_shadow
    minutes = int((event.starts_at - now).total_seconds() // 60)
    if minutes <= 15:
        return f"{minutes}M", pal.yellow
    return "UPCOMING", pal.blue


def _meeting_time_label(event: CalendarEvent) -> str:
    if event.all_day:
        return "ALL DAY"
    start = event.starts_at.strftime("%H:%M")
    if event.ends_at:
        return f"{start}-{event.ends_at.strftime('%H:%M')} ({_meeting_duration_label(event)})"
    return start


def _meeting_duration_label(event: CalendarEvent) -> str:
    if not event.ends_at:
        return ""
    minutes = max(1, int((event.ends_at - event.starts_at).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}"


def _meeting_meta_lines(event: CalendarEvent, now: datetime) -> list[str]:
    lines: list[str] = []
    location = _meeting_location_label(event)
    if location:
        lines.append(location)
    people = _meeting_people_label(event)
    if people:
        lines.append(people)
    if event.description:
        lines.append(event.description)
    if event.starts_at > now:
        lines.append(f"starts in {event.countdown_label(now)}")
    return lines


def _meeting_location_label(event: CalendarEvent) -> str:
    if event.location:
        return event.location
    if event.meeting_url:
        return _meeting_url_label(event.meeting_url)
    return ""


def _meeting_people_label(event: CalendarEvent) -> str:
    bits = []
    if event.organizer:
        bits.append(f"org {event.organizer}")
    if event.attendees:
        names = ", ".join(event.attendees[:3])
        suffix = f" +{len(event.attendees) - 3}" if len(event.attendees) > 3 else ""
        bits.append(f"{len(event.attendees)}p {names}{suffix}")
    return " / ".join(bits)


def _meeting_url_label(url: str) -> str:
    text = url.removeprefix("https://").removeprefix("http://")
    return text.split("/", 1)[0]


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
    content_box = _draw_panel_title(draw, box, "ROUTE", pal)
    signal = _route_signal(event, pull_requests, ai_usage, work_events, now)
    glyph, color = _route_signal_icon(signal)
    glyph_font = icon_font(14)
    label_font = font(10)
    icon_x = content_box[0] + 8
    icon_y = content_box[1] + max(2, (content_box[3] - content_box[1] - 16) // 2)
    bounds = draw.textbbox((0, 0), glyph, font=glyph_font)
    draw.text((icon_x + (18 - (bounds[2] - bounds[0])) // 2, icon_y - bounds[1]), glyph, font=glyph_font, fill=color)
    draw.text((content_box[0] + 34, content_box[1] + 6), _fit_text(draw, signal, content_box[2] - content_box[0] - 42, label_font), font=label_font, fill=pal.ink)


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
    content_box = _draw_panel_title(draw, box, "AI GAUGES", pal)
    value_font = font(10)
    if not ai_usage or not ai_usage.gauges:
        draw.text((content_box[0] + 8, content_box[1] + 3), "-", font=value_font, fill=pal.ink)
        return
    _draw_ai_usage_window(draw, ai_usage, now, content_box, pal)


def _draw_pc_stats_panel(draw: ImageDraw.ImageDraw, pc_stats: PCStatsSnapshot | None, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    content_box = _draw_panel_title(draw, box, "PC STATS", pal)
    label_font = font(7)
    value_font = font(9)
    if not pc_stats or not pc_stats.metrics:
        draw.text((content_box[0] + 8, content_box[1] + 3), "-", font=value_font, fill=pal.ink)
        return
    x0, y0, x1, y1 = content_box
    content_w = max(1, x1 - x0 - 12)
    row_h = 12
    max_rows = max(1, (y1 - y0 - 8) // row_h)
    metrics = pc_stats.metrics[:max_rows]
    for index, metric in enumerate(metrics):
        y = y0 + 4 + index * row_h
        color = _pc_metric_color(metric.status, pal)
        draw.rectangle((x0 + 6, y + 2, x0 + 10, y + 6), fill=color, outline=pal.ink)
        label = _fit_text(draw, metric.label, 26, label_font)
        draw.text((x0 + 14, y - 1), label, font=label_font, fill=pal.blue)
        value_x = x0 + 43
        draw.text((value_x, y - 2), _fit_text(draw, metric.value, content_w - 37, value_font), font=value_font, fill=pal.ink)


def _draw_tasks_panel(
    draw: ImageDraw.ImageDraw,
    snapshot: TaskSnapshot | None,
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    task_font = font(8)
    due_font = font(7)
    label = (snapshot.provider if snapshot and snapshot.provider else "tasks").upper()
    x0, y0, x1, y1 = _draw_panel_title(draw, box, label, pal)
    content_x = x0 + 8
    content_w = max(1, x1 - x0 - 16)
    if not snapshot or not snapshot.tasks:
        draw.text((content_x, y0 + 7), "No dated tasks", font=task_font, fill=pal.ink)
        return
    row_h = 23 if content_w >= 150 else 18
    max_rows = max(1, (y1 - y0 - 22) // row_h)
    for index, task in enumerate(snapshot.tasks[:max_rows]):
        y = y0 + 6 + index * row_h
        color = _task_color(task, now, pal)
        is_subtask = bool(getattr(task, "parent_id", ""))
        marker_x = content_x + (5 if is_subtask else 0)
        draw.rectangle((marker_x, y + 2, marker_x + 5, y + 7), fill=color, outline=pal.ink)
        label_x = marker_x + 9
        label_w = max(1, content_w - (label_x - content_x))
        due_label = _task_due_label(task, now)
        meta_label = _task_meta_label(task, due_label)
        if row_h >= 23:
            title = f"> {task.title}" if is_subtask else task.title
            draw.text((label_x, y - 2), _fit_text(draw, title, label_w, task_font), font=task_font, fill=pal.ink)
            draw.text((label_x, y + 10), _fit_text(draw, meta_label, label_w, due_font), font=due_font, fill=pal.blue)
        else:
            prefix = "> " if is_subtask else ""
            label = f"{prefix}{task.title} {meta_label}"
            draw.text((label_x, y - 1), _fit_text(draw, label, label_w, task_font), font=task_font, fill=pal.ink)


def _draw_tasks_board_panel(
    draw: ImageDraw.ImageDraw,
    snapshot: TaskSnapshot | None,
    now: datetime,
    box: tuple[int, int, int, int],
    pal,
) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    column_font = font(7)
    card_font = font(7)
    meta_font = font(6)
    provider = (snapshot.provider if snapshot and snapshot.provider else "tasks").upper()
    x0, y0, x1, y1 = _draw_panel_title(draw, box, f"{provider} BOARD", pal)
    content_x = x0 + 7
    content_w = max(1, x1 - x0 - 14)
    if not snapshot or not snapshot.tasks:
        draw.text((content_x, y0 + 7), "No task cards", font=card_font, fill=pal.ink)
        return

    columns = _task_board_columns(snapshot.tasks)
    visible_columns = columns[: max(1, min(4, content_w // 54))]
    column_gap = 4
    column_w = max(1, (content_w - column_gap * (len(visible_columns) - 1)) // len(visible_columns))
    board_y = y0 + 6
    card_h = 24 if column_w >= 70 else 19
    max_cards = max(1, (y1 - board_y - 6) // card_h)
    for column_index, (column_name, tasks) in enumerate(visible_columns):
        cx = content_x + column_index * (column_w + column_gap)
        draw.rectangle((cx, board_y, cx + column_w - 1, y1 - 7), fill=pal.panel_shadow, outline=pal.ink)
        header = f"{column_name[:10]} {len(tasks)}"
        draw.text((cx + 3, board_y + 2), _fit_text(draw, header.upper(), column_w - 6, column_font), font=column_font, fill=pal.yellow)
        for card_index, task in enumerate(tasks[:max_cards]):
            cy = board_y + 13 + card_index * card_h
            if cy + card_h - 2 > y1 - 8:
                break
            color = _task_color(task, now, pal)
            draw.rectangle((cx + 3, cy, cx + column_w - 4, cy + card_h - 3), fill=pal.panel, outline=color)
            title = f"> {task.title}" if task.parent_id else task.title
            draw.text((cx + 6, cy + 2), _fit_text(draw, title, column_w - 12, card_font), font=card_font, fill=pal.ink)
            if card_h >= 24:
                meta = _task_board_meta(task, now)
                draw.text((cx + 6, cy + 12), _fit_text(draw, meta, column_w - 12, meta_font), font=meta_font, fill=pal.blue)


def _task_board_columns(tasks: tuple[TaskItem, ...]) -> list[tuple[str, list[TaskItem]]]:
    grouped: dict[str, list[TaskItem]] = {}
    for task in tasks:
        column = (task.column or task.status or "Open").strip() or "Open"
        grouped.setdefault(column, []).append(task)
    ordered_names = sorted(grouped, key=lambda name: (_task_column_rank(name), name.lower()))
    no_due = datetime.max.replace(tzinfo=timezone.utc)
    return [(name, sorted(grouped[name], key=lambda task: (task.order, task.due_at or no_due, task.title.lower()))) for name in ordered_names]


def _task_column_rank(name: str) -> int:
    normalized = name.lower().replace("_", " ").replace("-", " ")
    ranks = (
        ("backlog", "todo", "to do", "open", "inbox"),
        ("progress", "doing", "active"),
        ("review", "blocked", "waiting"),
        ("done", "closed", "complete"),
    )
    for index, aliases in enumerate(ranks):
        if any(alias in normalized for alias in aliases):
            return index
    return 2


def _task_board_meta(task: TaskItem, now: datetime) -> str:
    bits = []
    if task.group:
        bits.append(task.group)
    if task.assignee:
        bits.append(task.assignee)
    bits.append(_task_due_label(task, now))
    return " / ".join(bits)


def _draw_media_panel(draw: ImageDraw.ImageDraw, media: MediaNowPlaying | None, now: datetime, box: tuple[int, int, int, int], pal) -> None:
    PixelRenderer.draw_panel(draw, box, pal.panel, pal.panel_shadow, pal.ink)
    title_font = font(8)
    track_font = font(10)
    artist_font = font(8)
    x0, y0, x1, y1 = _draw_panel_title(draw, box, "NOW PLAYING", pal)
    content_x = x0 + 8
    vinyl_radius = min(15, max(9, (y1 - y0 - 20) // 2))
    show_media_icon = bool(media and x1 - x0 >= 120 and y1 - y0 >= 46)
    thumbnail = _load_media_thumbnail(media)
    icon_space = vinyl_radius * 2 + 10 if show_media_icon else 0
    content_w = max(1, x1 - x0 - 16 - icon_space)
    if media is None:
        draw.text((content_x, y0 + 7), "Quiet", font=track_font, fill=pal.ink)
        return
    provider = media.provider.upper()
    draw.text((x1 - 8 - draw.textbbox((0, 0), provider, font=title_font)[2], y0 + 2), provider, font=title_font, fill=pal.green)
    if show_media_icon:
        icon_cx = x1 - 8 - vinyl_radius
        icon_cy = y0 + 22
        if media.is_music:
            _draw_vinyl(draw, icon_cx, icon_cy, vinyl_radius, now, pal)
        else:
            _draw_video_icon(draw, icon_cx, icon_cy, vinyl_radius, pal)
    track_y = y0 + 7
    title_lines = _wrap_text(draw, media.title, content_w, track_font, 2)
    for index, line in enumerate(title_lines):
        draw.text((content_x, track_y + index * 12), line, font=track_font, fill=pal.ink)
    artist_y = track_y + max(1, len(title_lines)) * 12 + 1
    artist_drawn = bool(media.artist and artist_y + 8 <= y1 - 32)
    if artist_drawn:
        draw.text((content_x, artist_y), _fit_text(draw, media.artist, content_w, artist_font), font=artist_font, fill=pal.blue)
    if thumbnail:
        thumb_y = max(track_y + max(1, len(title_lines)) * 12 + (12 if artist_drawn else 3), y0 + 50)
        if thumb_y + 18 <= y1 - 8:
            _draw_media_thumbnail(draw, thumbnail, (content_x, thumb_y, x1 - 8, y1 - 8), pal)


def _load_media_thumbnail(media: MediaNowPlaying | None) -> Image.Image | None:
    if not media or not media.thumbnail_path:
        return None
    try:
        return Image.open(media.thumbnail_path).convert("RGB")
    except OSError:
        return None


def _draw_media_thumbnail(draw: ImageDraw.ImageDraw, image: Image.Image, box: tuple[int, int, int, int], pal) -> None:
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    scale = min(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    thumb_x = x0
    thumb_y = y0 + (height - resized.height) // 2
    draw._image.paste(resized, (thumb_x, thumb_y))


def _draw_vinyl(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, now: datetime, pal) -> None:
    outer = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.ellipse(outer, fill=(18, 18, 22), outline=pal.ink)
    for inset in (4, 8):
        if radius - inset > 2:
            draw.ellipse((cx - radius + inset, cy - radius + inset, cx + radius - inset, cy + radius - inset), outline=pal.panel_shadow)
    angle = ((now.second + now.microsecond / 1_000_000) * 220) % 360
    radians = math.radians(angle)
    x = int(cx + math.cos(radians) * (radius - 3))
    y = int(cy + math.sin(radians) * (radius - 3))
    draw.line((cx, cy, x, y), fill=pal.blue, width=1)
    draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=pal.red, outline=pal.ink)
    draw.ellipse((cx - 1, cy - 1, cx + 1, cy + 1), fill=pal.yellow)


def _draw_video_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, pal) -> None:
    width = radius * 2
    height = max(12, int(radius * 1.35))
    x0 = cx - width // 2
    y0 = cy - height // 2
    x1 = cx + width // 2
    y1 = cy + height // 2
    draw.rectangle((x0, y0, x1, y1), fill=pal.panel_shadow, outline=pal.ink)
    draw.rectangle((x0 + 3, y0 + 3, x1 - 3, y1 - 3), outline=pal.blue)
    play = (
        (cx - 3, cy - 5),
        (cx - 3, cy + 5),
        (cx + 6, cy),
    )
    draw.polygon(play, fill=pal.green, outline=pal.ink)


def _task_color(task: TaskItem, now: datetime, pal):
    if not task.due_at:
        return pal.panel_shadow
    seconds = (task.due_at.astimezone(now.tzinfo) - now).total_seconds()
    if seconds < 0:
        return pal.red
    if seconds <= 24 * 3600:
        return pal.yellow
    return pal.green


def _task_due_label(task: TaskItem, now: datetime) -> str:
    if not task.due_at:
        return "NO DUE"
    due_at = task.due_at.astimezone(now.tzinfo)
    remaining = due_at - now
    prefix = due_at.strftime("%b %-d")
    seconds = int(remaining.total_seconds())
    if seconds < 0:
        return f"{prefix} OVERDUE {_duration_short(abs(seconds))}"
    return f"{prefix} {_duration_short(seconds)} left"


def _task_meta_label(task: TaskItem, due_label: str) -> str:
    if task.group:
        return f"{task.group} / {due_label}"
    return due_label


def _duration_short(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days >= 2:
        return f"{days}d"
    if days == 1:
        return f"1d {hours}h"
    if hours >= 1:
        return f"{hours}h {minutes}m"
    return f"{max(1, minutes)}m"


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


def _draw_ai_usage_window(draw: ImageDraw.ImageDraw, ai_usage: AIUsageSnapshot, now: datetime, box: tuple[int, int, int, int], pal) -> None:
    gauges = _visible_ai_usage_gauges(ai_usage, now)
    if not gauges:
        draw.text((box[0] + 8, box[1] + 13), "-", font(10), fill=pal.ink)
        return
    label_font = font(7)
    x0, y0, x1, y1 = box
    content_x = x0 + 8
    content_w = max(1, x1 - x0 - 16)
    available_h = max(1, y1 - y0 - 8)
    row_h = max(12, min(18, available_h // max(1, len(gauges))))
    row_visual_h = 14
    block_h = (len(gauges) - 1) * row_h + row_visual_h
    start_y = y0 + max(5, (y1 - y0 - block_h) // 2)
    for index, gauge in enumerate(gauges):
        row_y = start_y + index * row_h
        if row_y + 9 >= y1:
            break
        pct = _ai_usage_percent(gauge)
        label = f"{_ai_usage_gauge_short_label(gauge)} {_ai_usage_gauge_value(gauge, pct, now)}"
        draw.text((content_x, row_y - 1), _fit_text(draw, label, content_w, label_font), font=label_font, fill=pal.ink)
        bar_y = row_y + 8
        draw.rectangle((content_x, bar_y, content_x + content_w, bar_y + 5), outline=pal.ink, fill=pal.panel)
        if pct is None:
            continue
        fill_width = int(content_w * max(0.0, min(100.0, pct)) / 100.0)
        if fill_width <= 0:
            continue
        color = pal.red if pct >= 90 else pal.yellow if pct >= 75 else pal.green
        draw.rectangle((content_x + 1, bar_y + 1, content_x + fill_width, bar_y + 4), fill=color)


def _visible_ai_usage_gauges(ai_usage: AIUsageSnapshot, now: datetime) -> list:
    codex = [item for item in ai_usage.gauges if item.provider == "codex" and item.status != "quiet"]
    codex_5h = next((item for item in codex if "5H" in item.label), None)
    codex_weekly = next((item for item in codex if "5H" not in item.label), None)
    openai_api = next((item for item in ai_usage.gauges if item.provider == "openai_api" and item.status != "quiet"), None)
    second = openai_api if openai_api and int(now.timestamp() // 6) % 2 == 0 else codex_weekly
    return [item for item in (codex_5h, second or openai_api) if item is not None]


def _ai_usage_gauge_short_label(gauge) -> str:
    if gauge.provider == "openai_api":
        return "API"
    return "5H" if "5H" in gauge.label else "W"


def _ai_usage_percent(gauge) -> float | None:
    pct = gauge.used_percent
    if pct is None and gauge.provider not in ("openai_api", "codex") and gauge.total_tokens:
        pct = min(100.0, gauge.total_tokens / 250_000 * 100.0)
    return pct


def _ai_usage_gauge_value(gauge, pct: float | None, now: datetime) -> str:
    if gauge.status == "error":
        return "ERR"
    usage = _ai_usage_used_label(gauge, pct)
    if gauge.provider == "openai_api":
        return usage
    if pct is not None and gauge.reset_at:
        return f"{usage} used | {_ai_usage_reset_countdown(now, gauge.reset_at)} reset"
    return usage


def _ai_usage_used_label(gauge, pct: float | None) -> str:
    tokens = _ai_usage_label(gauge.total_tokens, gauge.cost_usd)
    if pct is None:
        return tokens
    pct_label = f"{max(0.0, min(100.0, pct)):.0f}%"
    if tokens != "-":
        return f"{tokens} {pct_label}"
    return pct_label


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
    remaining_minutes = minutes % 60
    if hours < 48:
        return f"{hours}h {remaining_minutes}m"
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
