from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


@dataclass(frozen=True)
class MediaNowPlaying:
    provider: str
    title: str
    artist: str = ""
    album: str = ""
    is_playing: bool = True
    is_music: bool = False
    thumbnail_path: str = ""
    observed_at: datetime | None = None

    @property
    def label(self) -> str:
        if self.artist:
            return f"{self.title} - {self.artist}"
        return self.title


class LocalMediaSource:
    def __init__(
        self,
        enabled: bool = True,
        providers: list[str] | None = None,
        poll_seconds: int = 10,
        timeout_seconds: int = 10,
        cache_dir: str | Path = "pixel_ops/cache/media_thumbnails",
        youtube_browser_apps: list[str] | None = None,
        browser_extension_host: str = "127.0.0.1",
        browser_extension_port: int = 47832,
        browser_extension_token: str = "",
        browser_extension_stale_seconds: int = 15,
    ):
        self.enabled = enabled
        self.providers = tuple(provider.strip().lower() for provider in (providers or ["spotify"]) if provider.strip())
        self.poll_seconds = max(1, int(poll_seconds))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.cache_dir = Path(cache_dir)
        self.browser_extension = BrowserMediaSnapshotReceiver(
            host=browser_extension_host,
            port=browser_extension_port,
            token=browser_extension_token,
            stale_seconds=browser_extension_stale_seconds,
        )
        self.youtube_browser_apps = tuple(
            app.strip()
            for app in (
                youtube_browser_apps
                or ["Google Chrome", "Brave Browser", "Microsoft Edge", "Arc", "Safari"]
            )
            if app.strip()
        )
        self._last_poll_at: datetime | None = None
        self._snapshot: MediaNowPlaying | None = None

    def current(self, now: datetime | None = None) -> MediaNowPlaying | None:
        if not self.enabled:
            return None
        base_now = now or datetime.now().astimezone()
        if self._last_poll_at and (base_now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = base_now
        for provider in self.providers:
            try:
                snapshot = self._current_for_provider(provider, base_now)
            except (OSError, subprocess.SubprocessError, requests.RequestException, ValueError):
                snapshot = None
            if snapshot is not None:
                self._snapshot = snapshot
                return snapshot
        self._snapshot = None
        return None

    def _current_for_provider(self, provider: str, now: datetime) -> MediaNowPlaying | None:
        if provider == "spotify":
            return self._spotify(now)
        if provider in ("browser_extension", "browser_media", "browser"):
            return self._browser_extension(now)
        if provider in ("youtube", "youtube_browser", "browser_youtube"):
            return self._youtube_browser(now)
        return None

    def start(self) -> None:
        if any(provider in ("browser_extension", "browser_media", "browser") for provider in self.providers):
            self.browser_extension.start()

    def close(self) -> None:
        self.browser_extension.close()

    def _spotify(self, now: datetime) -> MediaNowPlaying | None:
        output = self._run_osascript(
            """
            if application "Spotify" is running then
              tell application "Spotify"
                if player state is playing then
                  set trackName to name of current track
                  set artistName to artist of current track
                  set albumName to album of current track
                  set coverUrl to artwork url of current track
                  return trackName & linefeed & artistName & linefeed & albumName & linefeed & coverUrl
                end if
              end tell
            end if
            return ""
            """
        )
        lines = _clean_lines(output)
        if not lines:
            return None
        return MediaNowPlaying(
            provider="spotify",
            title=lines[0],
            artist=lines[1] if len(lines) > 1 else "",
            album=lines[2] if len(lines) > 2 else "",
            is_music=True,
            thumbnail_path=self._thumbnail_path(lines[3]) if len(lines) > 3 else "",
            observed_at=now,
        )

    def _youtube_browser(self, now: datetime) -> MediaNowPlaying | None:
        for app_name in self.youtube_browser_apps:
            output = self._run_osascript(_youtube_browser_script(app_name))
            lines = _clean_lines(output)
            if len(lines) >= 2:
                thumbnail_url = _youtube_thumbnail_url(lines[2]) if len(lines) > 2 else ""
                return MediaNowPlaying(
                    provider="youtube",
                    title=_clean_youtube_title(lines[0]),
                    artist=lines[1],
                    is_music=_infer_music("youtube", lines[0], lines[1]),
                    thumbnail_path=self._thumbnail_path(thumbnail_url),
                    observed_at=now,
                )
        return None

    def _browser_extension(self, now: datetime) -> MediaNowPlaying | None:
        payload = self.browser_extension.current_payload(now)
        if payload is None:
            return None
        title = str(payload.get("title") or "").strip()
        if not title:
            return None
        provider = str(payload.get("provider") or "browser").strip().lower() or "browser"
        artist = str(payload.get("artist") or payload.get("source") or "").strip()
        album = str(payload.get("album") or "").strip()
        url = str(payload.get("url") or "").strip()
        artwork_url = str(payload.get("artwork_url") or "").strip()
        thumbnail_url = artwork_url or (_youtube_thumbnail_url(url) if "youtu" in url.lower() else "")
        return MediaNowPlaying(
            provider=provider,
            title=_clean_youtube_title(title) if provider in ("youtube", "youtube_music") else title,
            artist=artist,
            album=album,
            is_playing=bool(payload.get("is_playing", True)),
            is_music=_infer_music(provider, title, artist),
            thumbnail_path=self._thumbnail_path(thumbnail_url),
            observed_at=now,
        )

    def _thumbnail_path(self, url: str) -> str:
        url = url.strip()
        if not url:
            return ""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg"
        parsed_path = urlparse(url).path.lower()
        if parsed_path.endswith(".png"):
            suffix = ".png"
        elif parsed_path.endswith(".webp"):
            suffix = ".webp"
        path = self.cache_dir / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}{suffix}"
        if path.exists() and path.stat().st_size > 0:
            return str(path)
        try:
            response = requests.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            return ""
        path.write_bytes(response.content)
        return str(path)

    def _run_osascript(self, script: str) -> str:
        return subprocess.check_output(
            ["osascript", "-e", script],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=self.timeout_seconds,
        ).strip()


class BrowserMediaSnapshotReceiver:
    def __init__(self, host: str = "127.0.0.1", port: int = 47832, token: str = "", stale_seconds: int = 15):
        self.host = host
        self.port = int(port)
        self.token = token
        self.stale_seconds = max(1, int(stale_seconds))
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._received_at: datetime | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if self.path != "/media/now-playing":
                    self.send_error(404)
                    return
                if receiver.token and self.headers.get("X-Pixel-Ops-Token", "") != receiver.token:
                    self.send_error(401)
                    return
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                if content_length <= 0 or content_length > 8192:
                    self.send_error(400)
                    return
                try:
                    payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.send_error(400)
                    return
                if not isinstance(payload, dict):
                    self.send_error(400)
                    return
                receiver.update(payload)
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args) -> None:
                return

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError:
            self._server = None
            return
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="browser-media-snapshot", daemon=True)
        self._thread.start()

    def close(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None
        self._thread = None

    def update(self, payload: dict, now: datetime | None = None) -> None:
        sanitized = _sanitize_browser_media_payload(payload)
        with self._lock:
            self._payload = sanitized
            self._received_at = now or datetime.now().astimezone()

    def current_payload(self, now: datetime | None = None) -> dict | None:
        base_now = now or datetime.now().astimezone()
        with self._lock:
            if self._payload is None or self._received_at is None:
                return None
            if (base_now - self._received_at).total_seconds() > self.stale_seconds:
                return None
            if self._payload.get("is_playing") is False:
                return None
            return dict(self._payload)


def _sanitize_browser_media_payload(payload: dict) -> dict:
    return {
        "provider": str(payload.get("provider") or "browser")[:40],
        "title": str(payload.get("title") or "")[:240],
        "artist": str(payload.get("artist") or "")[:160],
        "album": str(payload.get("album") or "")[:160],
        "source": str(payload.get("source") or "")[:80],
        "url": str(payload.get("url") or "")[:1000],
        "artwork_url": str(payload.get("artwork_url") or "")[:1000],
        "is_playing": bool(payload.get("is_playing", True)),
    }


def _youtube_browser_script(app_name: str) -> str:
    url_condition = (
        'tabUrl contains "youtube.com/watch" '
        'or tabUrl contains "music.youtube.com/watch" '
        'or tabUrl contains "youtu.be/" '
        'or tabUrl contains "youtube.com/shorts/" '
        'or tabUrl contains "youtube.com/embed/"'
    )
    if app_name == "Safari":
        return f"""
        set fallbackResult to ""
        if application "Safari" is running then
          tell application "Safari"
            repeat with browserWindow in windows
              repeat with browserTab in tabs of browserWindow
                set tabUrl to URL of browserTab
                if {url_condition} then
                  set tabTitle to name of browserTab
                  set sourceName to "YouTube"
                  if tabUrl contains "music.youtube.com/watch" then set sourceName to "YouTube Music"
                  set tabResult to tabTitle & linefeed & sourceName & linefeed & tabUrl
                  if fallbackResult is "" then set fallbackResult to tabResult
                  ignoring case
                    if sourceName is "YouTube Music" or tabUrl contains "list=RD" or tabTitle contains "music" or tabTitle contains "audio" or tabTitle contains "lyric" or tabTitle contains "jazz" or tabTitle contains "vinyl" or tabTitle contains "lo-fi" or tabTitle contains "lofi" or tabTitle contains "playlist" or tabTitle contains "mix" or tabTitle contains "set" then return tabResult
                  end ignoring
                end if
              end repeat
            end repeat
          end tell
        end if
        return fallbackResult
        """
    return f"""
    set fallbackResult to ""
    if application "{app_name}" is running then
      tell application "{app_name}"
        repeat with browserWindow in windows
          repeat with tabIndex from 1 to count of tabs of browserWindow
            set browserTab to item tabIndex of tabs of browserWindow
            set tabUrl to URL of browserTab
            if {url_condition} then
              set tabTitle to title of browserTab
              set sourceName to "YouTube"
              if tabUrl contains "music.youtube.com/watch" then set sourceName to "YouTube Music"
              set tabResult to tabTitle & linefeed & sourceName & linefeed & tabUrl
              if fallbackResult is "" then set fallbackResult to tabResult
              ignoring case
                if sourceName is "YouTube Music" or tabUrl contains "list=RD" or tabTitle contains "music" or tabTitle contains "audio" or tabTitle contains "lyric" or tabTitle contains "jazz" or tabTitle contains "vinyl" or tabTitle contains "lo-fi" or tabTitle contains "lofi" or tabTitle contains "playlist" or tabTitle contains "mix" or tabTitle contains "set" then return tabResult
              end ignoring
            end if
          end repeat
        end repeat
      end tell
    end if
    return fallbackResult
    """


def _clean_lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _clean_youtube_title(title: str) -> str:
    for suffix in (" - YouTube Music", " - YouTube"):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title.strip()


def _youtube_thumbnail_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    video_ids = query.get("v") or []
    video_id = video_ids[0] if video_ids else ""
    if not video_id and parsed.netloc.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/", 1)[0]
    if not video_id:
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed"}:
            video_id = path_parts[1]
    if not video_id:
        return ""
    return f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"


def _infer_music(provider: str, title: str, artist: str = "") -> bool:
    if provider == "spotify":
        return True
    if provider == "youtube_music" or artist.lower() == "youtube music":
        return True
    normalized = f"{title} {artist}".lower()
    music_terms = (
        "official audio",
        "official music video",
        "music video",
        "lyric video",
        "lyrics",
        "visualizer",
        "full album",
        "lo-fi",
        "lofi",
        "playlist",
        "mix",
        "remix",
        "cover",
        "live session",
        "vinyl set",
        "dj set",
        "live set",
    )
    music_genres = (
        "jazz",
        "lofi",
        "lo-fi",
        "ambient",
        "house",
        "techno",
        "disco",
        "soul",
        "funk",
        "blues",
        "reggae",
        "hip hop",
        "classical",
        "synthwave",
        "soundtrack",
    )
    duration_markers = ("min", "hour", "hours", "set")
    if any(term in normalized for term in music_terms):
        return True
    if any(genre in normalized for genre in music_genres) and any(marker in normalized for marker in duration_markers):
        return True
    return False
