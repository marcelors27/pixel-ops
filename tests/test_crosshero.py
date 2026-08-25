from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from pixel_ops.data_sources.crosshero import CrossHeroDaySource, _workout_display_text


class CrossHeroDaySourceTests(unittest.TestCase):
    def test_scrapes_dashboard_class_ids_occupancy_and_wod(self):
        index = Mock(text='''
          <select id="class_reservation_single_class_id">
            <option value=""></option>
            <option value="class-7">07:00 CrossFit</option>
            <option value="class-18">18:00 CrossFit</option>
          </select>
        ''')
        detail_7 = Mock(text='''
          <div class="ch-classes-occupancy__meta">Coach · 07:00 – 08:00</div>
          <div class="ch-classes-occupancy__coach-name">Coach Ana</div>
          <span class="ch-classes-occupancy__stat-value">8/11</span>
          <section class="today-wod"><div class="today-wod-components">
            <strong>STRENGTH 2<br><br>MOBILITY</strong>
            <div>Ankle - Hip - Thoracic - Shoulder - Wrist</div>
            <div><br></div>
            <div><strong>ACTIVATION</strong></div>
            <div>10 Back Squat (barra vazia)</div>
            <div>21-15-9 Thrusters 🔥 <img alt="💪" src="emoji.png"></div>
          </div></section>
        ''')
        detail_18 = Mock(text='''
          <div class="ch-classes-occupancy__meta">Coach · 18:00 – 19:00</div>
          <div class="ch-classes-occupancy__coach-name">Coach Bia</div>
          <span class="ch-classes-occupancy__stat-value">11/11</span>
        ''')
        for response in (index, detail_7, detail_18):
            response.raise_for_status.return_value = None
        now = datetime(2026, 8, 18, 9, tzinfo=ZoneInfo("America/Sao_Paulo"))

        with patch.dict("os.environ", {"SESSION": "_crosshero_session=secret"}), patch(
            "pixel_ops.data_sources.crosshero.requests.get", side_effect=[index, detail_7, detail_18]
        ) as get:
            snapshot = CrossHeroDaySource(session_cookie_env="SESSION", poll_seconds=1).current(now)

        self.assertEqual(snapshot.workout.title, "WOD do dia")
        self.assertIn("21-15-9 Thrusters 🔥 💪", snapshot.workout.description)
        self.assertEqual(
            [line.text for line in snapshot.workout.structured_lines],
            ["STRENGTH 2", "MOBILITY", "Ankle - Hip - Thoracic - Shoulder - Wrist", "ACTIVATION", "10 Back Squat (barra vazia)", "21-15-9 Thrusters 🔥 💪"],
        )
        self.assertTrue(snapshot.workout.structured_lines[0].emphasized)
        self.assertTrue(snapshot.workout.structured_lines[1].gap_before)
        self.assertTrue(snapshot.workout.structured_lines[3].emphasized)
        self.assertTrue(snapshot.workout.structured_lines[3].gap_before)
        self.assertEqual([(item.starts_at.hour, item.reservations, item.capacity) for item in snapshot.classes], [(7, 8, 11), (18, 11, 11)])
        self.assertEqual(snapshot.classes[0].coach, "Ana")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["Cookie"], "_crosshero_session=secret")
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"id": "class-7"})

    def test_converts_emoticons_to_pixel_font_safe_markers(self):
        self.assertEqual(_workout_display_text("AMRAP 🔥💪 ⏱️ ✅ 🥵"), "AMRAP 🔥💪 ⏱️ ✅ 🥵")
        self.assertEqual(_workout_display_text("Run 🏃‍♂️ 400m"), "Run 🏃‍♂️ 400m")

    def test_converts_complete_unicode_emoji_sequence_shapes(self):
        value = "faces 🫨 family 👨‍👩‍👧‍👦 tone 🧑🏿‍🚒 flags 🇧🇷 🏴󠁧󠁢󠁳󠁣󠁴󠁿 keycap 7️⃣ symbol ©️"
        self.assertEqual(
            _workout_display_text(value),
            value,
        )

    def test_keeps_numbers_and_hashes_that_are_not_keycap_emoji(self):
        self.assertEqual(_workout_display_text("5 rounds #1"), "5 rounds #1")

    def test_fetches_workout_and_daily_class_occupancy(self):
        wod_response = Mock()
        wod_response.json.return_value = {"workout": {"title": "Fran", "description": "21-15-9", "program": {"name": "CrossFit"}}}
        wod_response.raise_for_status.return_value = None
        classes_response = Mock()
        classes_response.json.return_value = {
            "classes": [
                {"starts_at": "2026-08-18T18:00:00-03:00", "name": "CrossFit", "reservations_count": 12, "capacity": 16},
                {"date": "2026-08-18", "start_time": "07:00", "program": {"name": "CrossFit"}, "bookings": [{}, {}]},
                {"starts_at": "2026-08-19T07:00:00-03:00", "name": "Tomorrow", "reservations_count": 3},
            ]
        }
        classes_response.raise_for_status.return_value = None
        now = datetime(2026, 8, 18, 9, tzinfo=ZoneInfo("America/Sao_Paulo"))

        with patch.dict("os.environ", {"BOX": "my-box", "TOKEN": "secret"}), patch(
            "pixel_ops.data_sources.crosshero.requests.get", side_effect=[wod_response, classes_response]
        ) as get:
            snapshot = CrossHeroDaySource(box_env="BOX", token_env="TOKEN", workout_url="https://example/wod", classes_url="https://example/classes").current(now)

        self.assertEqual(snapshot.workout.title, "Fran")
        self.assertEqual(snapshot.workout.program, "CrossFit")
        self.assertEqual([item.starts_at.strftime("%H:%M") for item in snapshot.classes], ["07:00", "18:00"])
        self.assertEqual([item.reservations for item in snapshot.classes], [2, 12])
        self.assertEqual(get.call_args_list[0].kwargs["headers"], {"CROSSHERO_BOX": "my-box", "CROSSHERO_ACCESS_TOKEN": "secret"})
        self.assertEqual(get.call_args_list[0].kwargs["params"], {"date": "2026-08-18"})

    def test_returns_none_without_credentials_or_endpoints(self):
        with patch.dict("os.environ", {}, clear=True), patch("pixel_ops.data_sources.crosshero.requests.get") as get:
            snapshot = CrossHeroDaySource(workout_url="https://example/wod").current(datetime(2026, 8, 18))
        self.assertIsNone(snapshot)
        get.assert_not_called()

    def test_refreshes_dashboard_cookie_from_dot_env_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text('PIXEL_OPS_CROSSHERO_SESSION_COOKIE="session=first"\n', encoding="utf-8")
            source = CrossHeroDaySource(env_path=env_path)
            self.assertEqual(source._secret("PIXEL_OPS_CROSSHERO_SESSION_COOKIE", prefer_file=True), "session=first")
            env_path.write_text('PIXEL_OPS_CROSSHERO_SESSION_COOKIE="session=second"\n', encoding="utf-8")
            self.assertEqual(source._secret("PIXEL_OPS_CROSSHERO_SESSION_COOKIE", prefer_file=True), "session=second")


if __name__ == "__main__":
    unittest.main()
