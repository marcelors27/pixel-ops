from __future__ import annotations

import hashlib
import subprocess
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
        timeout_seconds: int = 2,
        cache_dir: str | Path = "pixel_ops/cache/media_thumbnails",
    ):
        self.enabled = enabled
        self.providers = tuple(provider.strip().lower() for provider in (providers or ["spotify"]) if provider.strip())
        self.poll_seconds = max(1, int(poll_seconds))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.cache_dir = Path(cache_dir)
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
        if provider in ("youtube", "youtube_browser", "browser_youtube"):
            return self._youtube_browser(now)
        return None

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
        for app_name in ("Google Chrome", "Brave Browser", "Safari"):
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


def _youtube_browser_script(app_name: str) -> str:
    if app_name == "Safari":
        return """
        if application "Safari" is running then
          tell application "Safari"
            repeat with browserWindow in windows
              repeat with browserTab in tabs of browserWindow
                set tabUrl to URL of browserTab
                if tabUrl contains "youtube.com/watch" or tabUrl contains "music.youtube.com/watch" then
                  set tabTitle to name of browserTab
                  set sourceName to "YouTube"
                  if tabUrl contains "music.youtube.com/watch" then set sourceName to "YouTube Music"
                  try
                    set pausedState to do JavaScript "Boolean(document.querySelector('video') && document.querySelector('video').paused)" in browserTab
                    if pausedState is false then return tabTitle & linefeed & sourceName & linefeed & tabUrl
                  on error
                    return tabTitle & linefeed & sourceName & linefeed & tabUrl
                  end try
                end if
              end repeat
            end repeat
          end tell
        end if
        return ""
        """
    return f"""
    if application "{app_name}" is running then
      tell application "{app_name}"
        repeat with browserWindow in windows
          repeat with browserTab in tabs of browserWindow
            set tabUrl to URL of browserTab
            if tabUrl contains "youtube.com/watch" or tabUrl contains "music.youtube.com/watch" then
              set tabTitle to title of browserTab
              set sourceName to "YouTube"
              if tabUrl contains "music.youtube.com/watch" then set sourceName to "YouTube Music"
              try
                set pausedState to execute browserTab javascript "Boolean(document.querySelector('video') && document.querySelector('video').paused)"
                if pausedState is false then return tabTitle & linefeed & sourceName & linefeed & tabUrl
              on error
                return tabTitle & linefeed & sourceName & linefeed & tabUrl
              end try
            end if
          end repeat
        end repeat
      end tell
    end if
    return ""
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
    if not video_ids:
        return ""
    return f"https://img.youtube.com/vi/{video_ids[0]}/mqdefault.jpg"


def _infer_music(provider: str, title: str, artist: str = "") -> bool:
    if provider == "spotify":
        return True
    if artist.lower() == "youtube music":
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
