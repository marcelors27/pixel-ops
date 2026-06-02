from __future__ import annotations

import subprocess
import tempfile
import unittest
from io import BytesIO
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from PIL import Image
import requests

from pixel_ops.data_sources.media import LocalMediaSource, _youtube_browser_script, _youtube_thumbnail_url


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

        self.assertIn("repeat with browserWindow in windows", chrome_script)
        self.assertIn("repeat with browserTab in tabs of browserWindow", chrome_script)
        self.assertIn("execute browserTab javascript", chrome_script)
        self.assertNotIn("active tab of front window", chrome_script)
        self.assertIn("repeat with browserWindow in windows", safari_script)
        self.assertIn("do JavaScript", safari_script)
        self.assertNotIn("current tab of front window", safari_script)


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
