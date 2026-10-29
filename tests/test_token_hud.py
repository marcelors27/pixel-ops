import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from PIL import Image, ImageDraw
from pixel_ops.data_sources.ai_usage import AIUsageSource, AIUsageSnapshot
from pixel_ops.render.hud import draw_token_usage_panel


class TokenHUDTests(unittest.TestCase):
    def test_history_counts_deltas_once_and_keeps_baseline_before_window(self):
        now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
        def record(day, tokens):
            return {'timestamp': day.isoformat(), 'type': 'event_msg', 'payload': {
                'type': 'token_count', 'info': {'model': 'test-model',
                'total_token_usage': {'input_tokens': tokens},
                'last_token_usage': {'input_tokens': 100}}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'sessions'
            root.mkdir()
            entries = [record(now - timedelta(days=31), 1000),
                       record(now - timedelta(days=29, hours=11), 1100),
                       record(now, 1500), record(now, 1500)]
            (root / 'usage.jsonl').write_text('\n'.join(map(json.dumps, entries)))
            snapshot = AIUsageSource(enabled=True, providers=['codex'], codex_home=Path(tmp)).current(now)
        self.assertEqual(sum(snapshot.daily_tokens.values()), 500)
        self.assertEqual(snapshot.daily_tokens['2026-09-12'], 400)
        self.assertEqual(snapshot.history_requests, 2)
        self.assertEqual(snapshot.favorite_model, 'test-model')

    def test_hud_is_clipped_for_native_and_small_regions(self):
        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        pal = SimpleNamespace(panel=(8, 20, 38), panel_shadow=(2, 7, 16), ink=(226, 236, 238))
        snapshot = AIUsageSnapshot(updated_at=now, daily_tokens={'2026-09-12': 123456}, favorite_model='long-model-name' * 20)
        for size in [(312, 168), (156, 84), (80, 40)]:
            for data in [None, AIUsageSnapshot(), snapshot]:
                image = Image.new('RGB', (320, 172), (255, 0, 255))
                draw_token_usage_panel(ImageDraw.Draw(image), data, now, (4, 2, 4 + size[0], 2 + size[1]), pal)
                self.assertEqual(image.getpixel((3, 2)), (255, 0, 255))
                self.assertEqual(image.getpixel((4 + size[0], 2)), (255, 0, 255))
