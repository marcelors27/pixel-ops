from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def render_splash(root_dir: Path, display_cfg: dict, width: int, height: int) -> Image.Image | None:
    splash_cfg = display_cfg.get("splash", {})
    if not splash_cfg or not bool(splash_cfg.get("enabled", False)):
        return None

    logo_path = _logo_path(root_dir, splash_cfg)
    if logo_path is None:
        return None

    background = tuple(splash_cfg.get("background", (8, 10, 18)))
    frame = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(frame)
    _draw_pixel_grid(draw, width, height, background)

    with Image.open(logo_path) as source:
        logo = source.convert("RGB")

    logo = _cover_resize(logo, width, height)
    frame.paste(logo, (0, 0))
    return frame


def splash_frame_count(display_cfg: dict, fps: int) -> int:
    seconds = splash_seconds(display_cfg)
    return max(0, int(seconds * fps))


def splash_seconds(display_cfg: dict) -> float:
    splash_cfg = display_cfg.get("splash", {})
    if not splash_cfg or not bool(splash_cfg.get("enabled", False)):
        return 0.0
    return max(0.0, float(splash_cfg.get("seconds", 0)))


def _logo_path(root_dir: Path, splash_cfg: dict) -> Path | None:
    configured = splash_cfg.get("logo_path")
    if configured:
        path = root_dir / configured
        return path if path.exists() else None

    logo_dir = root_dir / splash_cfg.get("logo_dir", "pixel_ops/assets/logo")
    if not logo_dir.exists():
        return None

    for suffix in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        matches = sorted(logo_dir.glob(suffix))
        if matches:
            return matches[0]
    return None


def _draw_pixel_grid(draw: ImageDraw.ImageDraw, width: int, height: int, background: tuple[int, int, int]) -> None:
    grid = tuple(min(255, channel + 12) for channel in background)
    for x in range(0, width, 16):
        draw.line((x, 0, x, height), fill=grid)
    for y in range(0, height, 16):
        draw.line((0, y, width, y), fill=grid)


def _cover_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))
