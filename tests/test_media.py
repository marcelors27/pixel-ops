from __future__ import annotations

import subprocess
import tempfile
import unittest
from io import BytesIO
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from PIL import Image
import requests

from pixel_ops.data_sources.media import BrowserMediaSnapshotReceiver, LocalMediaSource, _youtube_browser_script, _youtube_thumbnail_url


class LocalMediaSourceTests(unittest.TestCase):
    def test_spotify_now_playing_snapshot(self):
        source = LocalMediaSource(providers=["spotify"], poll_seconds=10)
        source._run_osascript = lambda _script: "Song Name\nArtist Name\nAlbum Name"
        now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)

        snapshot = source.current(now)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.provider, "spotify")
        self.assertEqual(snapshot.title, "Song Name")
        self.assertEqual(snapshot.artist, "Artist Name")
        self.assertEqual(snapshot.album, "Album Name")
        self.assertEqual(snapshot.label, "Song Name - Artist Name")
        self.assertTrue(snapshot.is_music)

    def test_spotify_snapshot_caches_artwork_thumbnail(self):
        image_bytes = _png_bytes()
        response = Mock()
        response.content = image_bytes
        response.raise_for_status.return_value = None
        with tempfile.TemporaryDirectory() as tmp, patch("pixel_ops.data_sources.media.requests.get", return_value=response):
            source = LocalMediaSource(providers=["spotify"], poll_seconds=10, cache_dir=tmp)
            source._run_osascript = lambda _script: "Song Name\nArtist Name\nAlbum Name\nhttps://example.test/cover.png"

            snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertTrue(snapshot.thumbnail_path.endswith(".png"))

    def test_empty_or_unavailable_player_returns_none(self):
        source = LocalMediaSource(providers=["spotify"], poll_seconds=10)
        source._run_osascript = lambda _script: ""

        self.assertIsNone(source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc)))

    def test_provider_errors_do_not_escape_render_loop(self):
        source = LocalMediaSource(providers=["spotify"], poll_seconds=10)
        source._run_osascript = lambda _script: (_ for _ in ()).throw(subprocess.TimeoutExpired("osascript", 1))

        self.assertIsNone(source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc)))

    def test_youtube_browser_title_is_cleaned(self):
        source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10)
        source._run_osascript = lambda _script: "Lo-fi beats - YouTube\nYouTube"

        snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.provider, "youtube")
        self.assertEqual(snapshot.title, "Lo-fi beats")
        self.assertEqual(snapshot.artist, "YouTube")
        self.assertTrue(snapshot.is_music)

    def test_regular_youtube_video_is_not_music_by_default(self):
        source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10)
        source._run_osascript = lambda _script: "Architecture talk - YouTube\nYouTube"

        snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertFalse(snapshot.is_music)

    def test_youtube_music_source_is_music(self):
        source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10)
        source._run_osascript = lambda _script: "Song Name - YouTube Music\nYouTube Music"

        snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.title, "Song Name")
        self.assertTrue(snapshot.is_music)

    def test_youtube_vinyl_jazz_set_is_music(self):
        source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10)
        source._run_osascript = lambda _script: "Summer Love Dream Jazz Vinyl Set // Fading Memories & Cool Vibes [60min / 4K] - YouTube\nYouTube"

        snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.title, "Summer Love Dream Jazz Vinyl Set // Fading Memories & Cool Vibes [60min / 4K]")
        self.assertTrue(snapshot.is_music)

    def test_youtube_thumbnail_url_uses_video_id(self):
        self.assertEqual(
            _youtube_thumbnail_url("https://www.youtube.com/watch?v=abc123&list=xyz"),
            "https://img.youtube.com/vi/abc123/mqdefault.jpg",
        )
        self.assertEqual(
            _youtube_thumbnail_url("https://youtu.be/short42"),
            "https://img.youtube.com/vi/short42/mqdefault.jpg",
        )
        self.assertEqual(
            _youtube_thumbnail_url("https://www.youtube.com/shorts/shorts42"),
            "https://img.youtube.com/vi/shorts42/mqdefault.jpg",
        )
        self.assertEqual(
            _youtube_thumbnail_url("https://www.youtube.com/embed/embed42"),
            "https://img.youtube.com/vi/embed42/mqdefault.jpg",
        )

    def test_youtube_snapshot_caches_thumbnail_from_tab_url(self):
        response = Mock()
        response.content = _png_bytes()
        response.raise_for_status.return_value = None
        with tempfile.TemporaryDirectory() as tmp, patch("pixel_ops.data_sources.media.requests.get", return_value=response) as get:
            source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10, cache_dir=tmp)
            source._run_osascript = lambda _script: "Architecture talk - YouTube\nYouTube\nhttps://www.youtube.com/watch?v=video42"

            snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertTrue(snapshot.thumbnail_path.endswith(".jpg"))
        self.assertEqual(get.call_args.args[0], "https://img.youtube.com/vi/video42/mqdefault.jpg")

    def test_thumbnail_download_failure_keeps_now_playing(self):
        with tempfile.TemporaryDirectory() as tmp, patch("pixel_ops.data_sources.media.requests.get", side_effect=requests.RequestException("network")):
            source = LocalMediaSource(providers=["youtube_browser"], poll_seconds=10, cache_dir=tmp)
            source._run_osascript = lambda _script: "Architecture talk - YouTube\nYouTube\nhttps://www.youtube.com/watch?v=video42"

            snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.title, "Architecture talk")
        self.assertEqual(snapshot.thumbnail_path, "")

    def test_youtube_browser_script_scans_all_tabs(self):
        chrome_script = _youtube_browser_script("Google Chrome")
        safari_script = _youtube_browser_script("Safari")

        self.assertIn("set fallbackResult to \"\"", chrome_script)
        self.assertIn("youtube.com/shorts/", chrome_script)
        self.assertIn("youtu.be/", chrome_script)
        self.assertIn("repeat with browserWindow in windows", chrome_script)
        self.assertIn("repeat with tabIndex from 1 to count of tabs of browserWindow", chrome_script)
        self.assertIn("set browserTab to item tabIndex of tabs of browserWindow", chrome_script)
        self.assertIn("tabTitle contains \"jazz\"", chrome_script)
        self.assertIn("tabUrl contains \"list=RD\"", chrome_script)
        self.assertNotIn("active tab of front window", chrome_script)
        self.assertNotIn("«event CrSuExJa»", chrome_script)
        self.assertIn("return fallbackResult", chrome_script)
        self.assertIn("set fallbackResult to \"\"", safari_script)
        self.assertIn("youtube.com/embed/", safari_script)
        self.assertIn("repeat with browserWindow in windows", safari_script)
        self.assertIn("tabTitle contains \"vinyl\"", safari_script)
        self.assertNotIn("do JavaScript", safari_script)
        self.assertNotIn("current tab of front window", safari_script)
        self.assertIn("return fallbackResult", safari_script)

    def test_youtube_browser_apps_are_configurable(self):
        source = LocalMediaSource(providers=["youtube_browser"], youtube_browser_apps=["Arc"])
        scripts: list[str] = []

        def fake_osascript(script: str) -> str:
            scripts.append(script)
            return "Song Name\nArtist Name\nhttps://youtu.be/video42"

        source._run_osascript = fake_osascript

        snapshot = source.current(datetime(2026, 6, 1, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(len(scripts), 1)
        self.assertIn('application "Arc"', scripts[0])
        assert snapshot is not None
        self.assertEqual(snapshot.title, "Song Name")
        self.assertEqual(snapshot.artist, "Artist Name")

    def test_browser_extension_snapshot_is_preferred(self):
        source = LocalMediaSource(providers=["browser_extension", "youtube_browser"], poll_seconds=10, browser_extension_port=0)
        source._run_osascript = lambda _script: "Fallback Video - YouTube\nYouTube"
        source.browser_extension.update(
            {
                "provider": "youtube_music",
                "title": "Browser Song",
                "artist": "Browser Artist",
                "url": "https://music.youtube.com/watch?v=browser42",
                "is_playing": True,
            },
            now=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        )

        snapshot = source.current(datetime(2026, 6, 1, 12, 0, 3, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.provider, "youtube_music")
        self.assertEqual(snapshot.title, "Browser Song")
        self.assertEqual(snapshot.artist, "Browser Artist")
        self.assertTrue(snapshot.is_music)

    def test_browser_extension_snapshot_expires(self):
        source = LocalMediaSource(
            providers=["browser_extension"],
            poll_seconds=10,
            browser_extension_port=0,
            browser_extension_stale_seconds=5,
        )
        source.browser_extension.update(
            {"provider": "youtube", "title": "Old Song", "is_playing": True},
            now=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        )

        self.assertIsNone(source.current(datetime(2026, 6, 1, 12, 0, 6, tzinfo=timezone.utc)))

    def test_browser_extension_http_receiver_accepts_snapshot(self):
        receiver = BrowserMediaSnapshotReceiver(port=0, token="secret")
        receiver.start()
        try:
            response = requests.post(
                f"http://127.0.0.1:{receiver.port}/media/now-playing",
                headers={"X-Pixel-Ops-Token": "secret"},
                json={"provider": "youtube", "title": "HTTP Song", "artist": "HTTP Artist", "is_playing": True},
                timeout=2,
            )
            self.assertEqual(response.status_code, 200)
            payload = receiver.current_payload(datetime.now().astimezone())
        finally:
            receiver.close()

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["title"], "HTTP Song")
        self.assertEqual(payload["artist"], "HTTP Artist")


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
