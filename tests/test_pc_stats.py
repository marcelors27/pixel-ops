from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from unittest.mock import patch

from pixel_ops.data_sources.pc_stats import PCStatsSource, _linux_temperature_c, _normalize_disk_path, _parse_tasklist_top_memory


class PCStatsTests(unittest.TestCase):
    def test_pc_stats_source_respects_configured_fields(self):
        source = PCStatsSource(fields=["cpu", "ram", "missing_field"], poll_seconds=1)

        snapshot = source.current()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual([metric.key for metric in snapshot.metrics], ["cpu", "ram", "missing_field"])
        self.assertEqual(snapshot.metrics[-1].status, "unknown")

    def test_linux_temperature_reads_sysfs_milli_celsius(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            zone = root / "class/thermal/thermal_zone0"
            zone.mkdir(parents=True)
            (zone / "temp").write_text("45125\n", encoding="utf-8")

            self.assertEqual(_linux_temperature_c(root), 45.125)

    def test_windows_disk_default_uses_system_drive(self):
        with patch("pixel_ops.data_sources.pc_stats.platform.system", return_value="Windows"), patch.dict("os.environ", {"SystemDrive": "D:"}):
            self.assertEqual(_normalize_disk_path("/"), "D:\\")

    def test_windows_tasklist_parser_finds_top_memory_process(self):
        output = '\n'.join(
            [
                '"Code.exe","1234","Console","1","1,234,000 K"',
                '"python.exe","5678","Console","1","98,000 K"',
            ]
        )

        self.assertEqual(_parse_tasklist_top_memory(output), (1_234_000 * 1024, "Code.exe"))


if __name__ == "__main__":
    unittest.main()
