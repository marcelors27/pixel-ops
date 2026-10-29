from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pixel_ops.data_sources.ai_usage import AIUsageSource, _codex_rate_limit_status


class AIUsageSourceTests(unittest.TestCase):
    def test_weekly_primary_is_not_a_five_hour_quota(self):
        now = datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc)
        status = _codex_rate_limit_status(now, {
            "primary": {"used_percent": 4, "window_minutes": 10080,
                        "resets_at": int((now + timedelta(days=6)).timestamp())},
            "secondary": None,
        })
        self.assertIsNone(status.primary_percent)
        self.assertEqual(status.secondary_percent, 4)
        self.assertEqual(status.secondary_reset_at, now + timedelta(days=6))

    def test_standard_windows_preserve_both_quotas(self):
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        status = _codex_rate_limit_status(now, {
            "primary": {"used_percent": 12, "window_minutes": 300},
            "secondary": {"used_percent": 34, "window_minutes": 10080},
        })
        self.assertEqual(status.primary_percent, 12)
        self.assertEqual(status.secondary_percent, 34)

    def test_expired_codex_rate_limit_status_does_not_keep_stale_percent(self):
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            session_dir = codex_home / "sessions" / "2026" / "05" / "25"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "rollout.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "timestamp": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 100,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 50,
                                }
                            },
                            "rate_limits": {
                                "primary": {
                                    "used_percent": 99.0,
                                    "window_minutes": 300,
                                    "resets_at": int((now - timedelta(seconds=1)).timestamp()),
                                }
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            source = AIUsageSource(enabled=True, providers=["codex"], codex_home=codex_home)

            snapshot = source.current(now)

        gauge = next(item for item in snapshot.gauges if item.label == "Codex 5H")
        self.assertIsNone(gauge.reset_at)
        self.assertNotEqual(gauge.used_percent, 99.0)
        self.assertIsNone(gauge.used_percent)

    def test_codex_tokens_do_not_imply_quota_without_rate_limit_status(self):
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            session_dir = codex_home / "sessions" / "2026" / "05" / "25"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "rollout.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "timestamp": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 800_000,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 50_000,
                                }
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            source = AIUsageSource(enabled=True, providers=["codex"], codex_home=codex_home)

            snapshot = source.current(now)

        gauge = next(item for item in snapshot.gauges if item.label == "Codex 5H")
        self.assertEqual(gauge.total_tokens, 850_000)
        self.assertIsNone(gauge.used_percent)


if __name__ == "__main__":
    unittest.main()
