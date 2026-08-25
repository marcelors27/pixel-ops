from __future__ import annotations

import base64
import hashlib
import http.server
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageOps

from pixel_ops.outputs.base import DisplayOutput
from pixel_ops.render.hud import draw_eink_telemetry_huds


EINK_WIDTH = 250
EINK_HEIGHT = 122
EINK_ROW_BYTES = (EINK_WIDTH + 7) // 8
EINK_FRAME_BYTES = EINK_ROW_BYTES * EINK_HEIGHT


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/healthz":
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def log_message(self, _format: str, *_args) -> None:
        return


class _PcHealthServer:
    def __init__(self) -> None:
        self._server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), _HealthHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="eink-pc-health", daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


@dataclass(frozen=True)
class EInkFrame:
    payload: bytes
    digest: str


@dataclass(frozen=True)
class EInkDirtyRegion:
    x: int
    y: int
    width: int
    height: int


class _PullFrameState:
    def __init__(self, token: str, sleep_seconds: int) -> None:
        self.token = token
        self.sleep_seconds = sleep_seconds
        self.frame: EInkFrame | None = None
        self.history: dict[str, bytes] = {}
        self.lock = threading.Lock()

    def publish(self, frame: EInkFrame) -> None:
        with self.lock:
            if self.frame is not None:
                self.history[self.frame.digest] = self.frame.payload
                while len(self.history) > 8:
                    self.history.pop(next(iter(self.history)))
            self.frame = frame


class _PullFrameHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != "/eink/frame":
            self.send_error(404)
            return
        state: _PullFrameState = self.server.pull_state  # type: ignore[attr-defined]
        if state.token and self.headers.get("Authorization") != f"Bearer {state.token}":
            self.send_error(401)
            return
        with state.lock:
            frame = state.frame
            requested_digest = self.headers.get("If-None-Match", "").strip('"')
            previous = state.history.get(requested_digest)
        if frame is None:
            self.send_error(503, "frame_not_ready")
            return
        if requested_digest == frame.digest:
            self.send_response(304)
            self.send_header("X-Pixel-Ops-Sleep-Seconds", str(state.sleep_seconds))
            self.end_headers()
            return
        refresh = "partial" if previous is not None else "full"
        dirty = find_eink_dirty_region(previous, frame.payload) if previous is not None else None
        dirty = dirty or EInkDirtyRegion(0, 0, EINK_WIDTH, EINK_HEIGHT)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(frame.payload)))
        self.send_header("ETag", f'"{frame.digest}"')
        self.send_header("X-Pixel-Ops-SHA256", frame.digest)
        self.send_header("X-Pixel-Ops-Refresh", refresh)
        self.send_header("X-Pixel-Ops-Dirty-X", str(dirty.x))
        self.send_header("X-Pixel-Ops-Dirty-Y", str(dirty.y))
        self.send_header("X-Pixel-Ops-Dirty-Width", str(dirty.width))
        self.send_header("X-Pixel-Ops-Dirty-Height", str(dirty.height))
        self.send_header("X-Pixel-Ops-Sleep-Seconds", str(state.sleep_seconds))
        self.end_headers()
        self.wfile.write(frame.payload)

    def log_message(self, _format: str, *_args) -> None:
        return


class _PullFrameServer:
    def __init__(self, port: int, token: str, sleep_seconds: int) -> None:
        self.state = _PullFrameState(token, sleep_seconds)
        self._server = http.server.ThreadingHTTPServer(("0.0.0.0", port), _PullFrameHandler)
        self._server.pull_state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, name="eink-frame-pull", daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def find_eink_dirty_region(previous: bytes, current: bytes, *, width: int = EINK_WIDTH, height: int = EINK_HEIGHT) -> EInkDirtyRegion | None:
    """Return the smallest pixel rectangle whose monochrome bits changed."""
    row_bytes = (width + 7) // 8
    if len(previous) != row_bytes * height or len(current) != row_bytes * height:
        return EInkDirtyRegion(0, 0, width, height)
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        row = y * row_bytes
        for byte_x in range(row_bytes):
            changed = previous[row + byte_x] ^ current[row + byte_x]
            if not changed:
                continue
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width and changed & (0x80 >> bit):
                    min_x, min_y = min(min_x, x), min(min_y, y)
                    max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < 0:
        return None
    return EInkDirtyRegion(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def compose_eink_white_background(frame: Image.Image, layout: dict) -> Image.Image:
    """Keep configured layout regions and replace the unused E213 canvas with white."""
    if not layout:
        return frame
    composed = Image.new("RGB", frame.size, "white")
    for raw in layout.values():
        if not isinstance(raw, dict):
            continue
        try:
            x = max(0, int(raw.get("x", 0)))
            y = max(0, int(raw.get("y", 0)))
            width = max(1, int(raw.get("width", 1)))
            height = max(1, int(raw.get("height", 1)))
        except (TypeError, ValueError):
            continue
        box = (x, y, min(frame.width, x + width), min(frame.height, y + height))
        if box[2] > box[0] and box[3] > box[1]:
            composed.paste(frame.crop(box), box[:2])
    return composed


def encode_eink_frame(
    frame: Image.Image,
    *,
    width: int = EINK_WIDTH,
    height: int = EINK_HEIGHT,
    dither: bool = True,
    threshold: int = 160,
    invert: bool = False,
    accent_pattern: bool = True,
) -> EInkFrame:
    """Encode a PIL frame as row-aligned, MSB-first monochrome pixels.

    A set bit represents a black pixel. Each row is padded to a whole byte so
    the firmware can address pixels without depending on PIL's internal layout.
    """

    color = frame.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    resized = color.convert("L")
    if invert:
        resized = ImageOps.invert(resized)
    if dither:
        monochrome = resized.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        limit = max(0, min(255, int(threshold)))
        monochrome = resized.point(lambda value: 255 if value >= limit else 0, mode="1")

    pixels = monochrome.load()
    color_pixels = color.load()
    accent_mask = [
        [max(color_pixels[x, y]) - min(color_pixels[x, y]) >= 45 for x in range(width)]
        for y in range(height)
    ]
    accent_integral = [[0] * (width + 1) for _ in range(height + 1)]
    for y in range(height):
        row_total = 0
        for x in range(width):
            row_total += int(accent_mask[y][x])
            accent_integral[y + 1][x + 1] = accent_integral[y][x + 1] + row_total

    def dense_accent(x: int, y: int) -> bool:
        x0, y0 = max(0, x - 2), max(0, y - 2)
        x1, y1 = min(width, x + 3), min(height, y + 3)
        count = accent_integral[y1][x1] - accent_integral[y0][x1] - accent_integral[y1][x0] + accent_integral[y0][x0]
        return count * 5 >= (x1 - x0) * (y1 - y0) * 3

    row_bytes = (width + 7) // 8
    payload = bytearray(row_bytes * height)
    for y in range(height):
        row_offset = y * row_bytes
        for x in range(width):
            red, green, blue = color_pixels[x, y]
            is_accent = accent_pattern and accent_mask[y][x]
            is_yellow = is_accent and red >= 160 and green >= 120 and blue + 30 < min(red, green)
            if is_yellow:
                is_black = True
            elif is_accent and dense_accent(x, y):
                is_black = (x + y) % 4 < 2
            elif is_accent:
                is_black = True
            else:
                is_black = pixels[x, y] == 0
            if is_black:
                payload[row_offset + (x // 8)] |= 0x80 >> (x % 8)
    encoded = bytes(payload)
    return EInkFrame(payload=encoded, digest=hashlib.sha256(encoded).hexdigest())


class EInkHttpOutput(DisplayOutput):
    """Wi-Fi output for the Pixel OPs firmware running on a Heltec E213."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        width: int = EINK_WIDTH,
        height: int = EINK_HEIGHT,
        timeout_seconds: float = 45,
        min_frame_interval_seconds: float = 15,
        full_refresh_every: int = 100,
        dither: bool = False,
        threshold: int = 175,
        invert: bool = False,
        accent_pattern: bool = True,
        debug_frame_path: str = "",
        heartbeat_interval_seconds: float = 3,
        heartbeat_lease_seconds: int = 12,
        standalone_weather_enabled: bool = False,
        standalone_latitude: float = 0,
        standalone_longitude: float = 0,
        standalone_utc_offset_minutes: int = -180,
        layout: dict | None = None,
        white_background: bool = True,
        battery_powered: bool = False,
        deep_sleep_seconds: int = 300,
        pull_port: int = 8765,
    ):
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)
        self.width = int(width)
        self.height = int(height)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.min_frame_interval_seconds = max(0, float(min_frame_interval_seconds))
        self.full_refresh_every = max(1, int(full_refresh_every))
        self.dither = bool(dither)
        self.threshold = max(0, min(255, int(threshold)))
        self.invert = bool(invert)
        self.accent_pattern = bool(accent_pattern)
        self.debug_frame_path = str(debug_frame_path)
        self.heartbeat_interval_seconds = max(1, float(heartbeat_interval_seconds))
        self.heartbeat_lease_seconds = max(5, int(heartbeat_lease_seconds))
        self.standalone_weather_enabled = bool(standalone_weather_enabled)
        self.standalone_latitude = max(-90.0, min(90.0, float(standalone_latitude)))
        self.standalone_longitude = max(-180.0, min(180.0, float(standalone_longitude)))
        self.standalone_utc_offset_minutes = max(-720, min(840, int(standalone_utc_offset_minutes)))
        self.layout = dict(layout or {})
        self.white_background = bool(white_background)
        self.battery_powered = bool(battery_powered)
        self.deep_sleep_seconds = max(30, int(deep_sleep_seconds))
        self.pull_port = max(0, min(65535, int(pull_port)))
        self._device_status: dict = {}
        self._session: requests.Session | None = None
        self._last_digest = ""
        self._last_payload: bytes | None = None
        self._last_send_at: float | None = None
        self._refresh_count = 0
        self._health_server: _PcHealthServer | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_sequence = 0
        self._force_resend = threading.Event()
        self._pull_server: _PullFrameServer | None = None
        self._pull_capable = False
        self._bootstrap_pending = False

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict) -> EInkHttpOutput:
        return cls(
            base_url=str(cfg.get("url") or cfg.get("base_url") or "http://pixelops-e213.local"),
            token=str(cfg.get("token") or ""),
            width=width,
            height=height,
            timeout_seconds=float(cfg.get("timeout_seconds", 45)),
            min_frame_interval_seconds=float(cfg.get("min_frame_interval_seconds", 15)),
            full_refresh_every=int(cfg.get("full_refresh_every", 100)),
            dither=bool(cfg.get("dither", False)),
            threshold=int(cfg.get("threshold", 175)),
            invert=bool(cfg.get("invert", False)),
            accent_pattern=bool(cfg.get("accent_pattern", True)),
            debug_frame_path=str(cfg.get("debug_frame_path") or ""),
            heartbeat_interval_seconds=float(cfg.get("heartbeat_interval_seconds", 3)),
            heartbeat_lease_seconds=int(cfg.get("heartbeat_lease_seconds", 12)),
            standalone_weather_enabled=bool(cfg.get("standalone_weather_enabled", False)),
            standalone_latitude=float(cfg.get("standalone_latitude", 0)),
            standalone_longitude=float(cfg.get("standalone_longitude", 0)),
            standalone_utc_offset_minutes=int(cfg.get("standalone_utc_offset_minutes", -180)),
            layout=cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {},
            white_background=bool(cfg.get("white_background", True)),
            battery_powered=bool(cfg.get("battery_powered", False)),
            deep_sleep_seconds=int(cfg.get("deep_sleep_seconds", 300)),
            pull_port=int(cfg.get("pull_port", 8765)),
        )

    def start(self) -> None:
        if not self.base_url:
            raise ValueError("E-ink output requires a non-empty URL.")
        if (self.width, self.height) != (EINK_WIDTH, EINK_HEIGHT):
            raise ValueError(f"Heltec E213 output requires {EINK_WIDTH}x{EINK_HEIGHT}, got {self.width}x{self.height}.")
        self._session = requests.Session()
        if self.battery_powered:
            self._pull_server = _PullFrameServer(self.pull_port, self.token, self.deep_sleep_seconds)
            self._pull_server.start()
        try:
            response = self._session.get(
                f"{self.base_url}/status",
                headers=self._headers(),
                timeout=min(self.timeout_seconds, 2) if self.battery_powered else self.timeout_seconds,
            )
            response.raise_for_status()
            status = response.json()
            self._device_status = dict(status)
            remote_size = (int(status.get("width", 0)), int(status.get("height", 0)))
            if remote_size != (self.width, self.height):
                raise RuntimeError(f"E-ink device reports {remote_size[0]}x{remote_size[1]}, expected {self.width}x{self.height}.")
            if self.battery_powered and int(status.get("deep_sleep_protocol", 0)) >= 1:
                self._pull_capable = True
                self._bootstrap_pending = True
            if not self.battery_powered and int(status.get("watchdog_protocol", 0)) >= 1:
                self._start_watchdog()
        except RuntimeError:
            self.stop()
            raise
        except requests.RequestException as error:
            if self.battery_powered:
                # A configured battery device is normally asleep. It will pull
                # from the stable host port on its next wake cycle.
                self._pull_capable = True
                return
            self.stop()
            raise RuntimeError(f"E-ink status check failed: {error}") from error
        except (ValueError, KeyError, TypeError) as error:
            self.stop()
            raise RuntimeError(f"E-ink status check failed: {error}") from error

    def send(self, frame: Image.Image) -> None:
        if self._session is None:
            raise RuntimeError("EInkHttpOutput.start() must be called before send().")

        if self._force_resend.is_set():
            self._last_digest = ""
            self._last_send_at = None
            self._force_resend.clear()

        if self.white_background:
            frame = compose_eink_white_background(frame, self.layout)
        frame = draw_eink_telemetry_huds(frame, self.layout, self._device_status)

        if self.debug_frame_path:
            debug_path = Path(self.debug_frame_path)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            frame.save(debug_path)

        encoded = encode_eink_frame(
            frame,
            width=self.width,
            height=self.height,
            dither=self.dither,
            threshold=self.threshold,
            invert=self.invert,
            accent_pattern=self.accent_pattern,
        )
        if encoded.digest == self._last_digest:
            return

        now = time.monotonic()
        if self._last_send_at is not None and now - self._last_send_at < self.min_frame_interval_seconds:
            return

        refresh = "full" if self._refresh_count % self.full_refresh_every == 0 else "partial"
        dirty = EInkDirtyRegion(0, 0, self.width, self.height)
        if refresh == "partial" and self._last_payload is not None:
            dirty = find_eink_dirty_region(self._last_payload, encoded.payload, width=self.width, height=self.height) or dirty
        if self._pull_server is not None:
            self._pull_server.state.publish(encoded)
        if self.battery_powered and self._pull_capable and not self._bootstrap_pending:
            self._remember_frame(encoded, now)
            return
        headers = {
            **self._headers(),
            "Content-Type": "application/octet-stream",
            "X-Pixel-Ops-Width": str(self.width),
            "X-Pixel-Ops-Height": str(self.height),
            "X-Pixel-Ops-SHA256": encoded.digest,
            "X-Pixel-Ops-Refresh": refresh,
            "X-Pixel-Ops-Encoding": "base64",
            "X-Pixel-Ops-Dirty-X": str(dirty.x),
            "X-Pixel-Ops-Dirty-Y": str(dirty.y),
            "X-Pixel-Ops-Dirty-Width": str(dirty.width),
            "X-Pixel-Ops-Dirty-Height": str(dirty.height),
            "X-Pixel-Ops-Battery-Powered": "1" if self.battery_powered else "0",
            "X-Pixel-Ops-Battery-Lease-Seconds": str(max(60, int(self.min_frame_interval_seconds * 3))),
            "X-Pixel-Ops-Pull-Port": str(self._pull_server.port if self._pull_server else self.pull_port),
            "X-Pixel-Ops-Deep-Sleep-Seconds": str(self.deep_sleep_seconds),
        }
        try:
            response = self._session.post(
                f"{self.base_url}/frame",
                data=base64.b64encode(encoded.payload),
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(f"E-ink frame delivery failed: {error}") from error
        self._bootstrap_pending = False
        self._remember_frame(encoded, now)

    def stop(self) -> None:
        self._stop_watchdog()
        if self._pull_server is not None:
            self._pull_server.stop()
        self._pull_server = None
        if self._session is not None:
            self._session.close()
        self._session = None
        self._last_digest = ""
        self._last_payload = None
        self._last_send_at = None
        self._refresh_count = 0
        self._pull_capable = False
        self._bootstrap_pending = False

    def _remember_frame(self, encoded: EInkFrame, sent_at: float) -> None:
        self._last_digest = encoded.digest
        self._last_payload = encoded.payload
        self._last_send_at = sent_at
        self._refresh_count += 1

    def _start_watchdog(self) -> None:
        if self._heartbeat_thread is not None:
            return
        self._health_server = _PcHealthServer()
        self._health_server.start()
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="eink-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def _stop_watchdog(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=self.heartbeat_interval_seconds + 1)
        self._heartbeat_thread = None
        if self._health_server is not None:
            self._health_server.stop()
        self._health_server = None

    def _heartbeat_loop(self) -> None:
        session = requests.Session()
        try:
            while not self._heartbeat_stop.is_set():
                self._send_heartbeat(session)
                self._heartbeat_stop.wait(self.heartbeat_interval_seconds)
        finally:
            session.close()

    def _send_heartbeat(self, session: requests.Session) -> bool:
        self._heartbeat_sequence += 1
        headers = {
            **self._headers(),
            "X-Pixel-Ops-Sequence": str(self._heartbeat_sequence),
            "X-Pixel-Ops-Lease-Seconds": str(self.heartbeat_lease_seconds),
            "X-Pixel-Ops-Health-Port": str(self._health_server.port if self._health_server else 0),
            "X-Pixel-Ops-Weather-Enabled": "1" if self.standalone_weather_enabled else "0",
            "X-Pixel-Ops-Latitude": f"{self.standalone_latitude:.5f}",
            "X-Pixel-Ops-Longitude": f"{self.standalone_longitude:.5f}",
            "X-Pixel-Ops-Utc-Offset-Minutes": str(self.standalone_utc_offset_minutes),
            "X-Pixel-Ops-Hud-Battery": self._hud_box_header("eink_battery"),
            "X-Pixel-Ops-Hud-Wireless": self._hud_box_header("eink_wireless"),
            "X-Pixel-Ops-Hud-Status": self._hud_box_header("eink_status"),
        }
        try:
            response = session.post(
                f"{self.base_url}/heartbeat",
                headers=headers,
                timeout=min(self.timeout_seconds, self.heartbeat_interval_seconds),
            )
            response.raise_for_status()
            try:
                heartbeat_status = response.json()
                self._device_status = {**self._device_status, **heartbeat_status}
                if bool(heartbeat_status.get("needs_frame", False)):
                    self._force_resend.set()
            except (ValueError, AttributeError, TypeError):
                pass
            return True
        except requests.RequestException:
            return False

    def _hud_box_header(self, kind: str) -> str:
        for key, raw in self.layout.items():
            if not isinstance(raw, dict) or str(raw.get("kind") or key) != kind:
                continue
            try:
                x = max(0, min(self.width - 1, int(raw.get("x", 0))))
                y = max(0, min(self.height - 1, int(raw.get("y", 0))))
                width = max(1, min(self.width - x, int(raw.get("width", 1))))
                height = max(1, min(self.height - y, int(raw.get("height", 1))))
                return f"{x},{y},{width},{height}"
            except (TypeError, ValueError):
                break
        return "off"

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}
