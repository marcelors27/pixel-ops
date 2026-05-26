from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pixel_ops.data_sources.ai_usage import AIUsageSource


class AIUsageSourceTests(unittest.TestCase):
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
        self.assertLess(gauge.used_percent or 0, 1.0)


if __name__ == "__main__":
    unittest.main()
