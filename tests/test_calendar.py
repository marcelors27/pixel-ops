from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pixel_ops.data_sources.calendar import next_ics_event, today_ics_events


class CalendarDataTests(unittest.TestCase):
    def test_today_ics_events_extracts_meeting_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.ics"
            path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "SUMMARY:Planning Sync",
                        "DTSTART;TZID=America/Sao_Paulo:20260602T090000",
                        "DTEND;TZID=America/Sao_Paulo:20260602T100000",
                        "LOCATION:Zoom Room",
                        "ORGANIZER;CN=Marcelo:mailto:marcelo@example.com",
                        "ATTENDEE;CN=Ana:mailto:ana@example.com",
                        "ATTENDEE;CN=Bia:mailto:bia@example.com",
                        "DESCRIPTION:Agenda<br/>Roadmap and launches https://zoom.us/j/123",
                        "END:VEVENT",
                        "BEGIN:VEVENT",
                        "SUMMARY:Tomorrow",
                        "DTSTART;TZID=America/Sao_Paulo:20260603T090000",
                        "DTEND;TZID=America/Sao_Paulo:20260603T100000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 6, 2, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

            events = today_ics_events(path, now)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].title, "Planning Sync")
            self.assertEqual(events[0].ends_at.hour, 10)
            self.assertEqual(events[0].location, "Zoom Room")
            self.assertEqual(events[0].organizer, "Marcelo")
            self.assertEqual(events[0].attendees, ("Ana", "Bia"))
            self.assertIn("Roadmap", events[0].description)
            self.assertEqual(events[0].meeting_url, "https://zoom.us/j/123")

    def test_next_ics_event_still_returns_next_future_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.ics"
            path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "SUMMARY:Later",
                        "DTSTART;TZID=America/Sao_Paulo:20260602T130000",
                        "DTEND;TZID=America/Sao_Paulo:20260602T140000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 6, 2, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

            event = next_ics_event(path, now)

            self.assertEqual(event.title, "Later")

    def test_cancelled_ics_event_is_not_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.ics"
            path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "UID:removed@example.com",
                        "SUMMARY:Removed Meeting",
                        "STATUS:CANCELLED",
                        "DTSTART;TZID=America/Sao_Paulo:20260602T090000",
                        "DTEND;TZID=America/Sao_Paulo:20260602T100000",
                        "END:VEVENT",
                        "BEGIN:VEVENT",
                        "UID:kept@example.com",
                        "SUMMARY:Kept Meeting",
                        "DTSTART;TZID=America/Sao_Paulo:20260602T110000",
                        "DTEND;TZID=America/Sao_Paulo:20260602T120000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 6, 2, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

            events = today_ics_events(path, now)

            self.assertEqual([event.title for event in events], ["Kept Meeting"])

    def test_cancelled_recurring_occurrence_is_not_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.ics"
            path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "UID:daily@example.com",
                        "SUMMARY:Daily Sync",
                        "DTSTART;TZID=America/Sao_Paulo:20260601T090000",
                        "DTEND;TZID=America/Sao_Paulo:20260601T093000",
                        "RRULE:FREQ=DAILY;COUNT=3",
                        "END:VEVENT",
                        "BEGIN:VEVENT",
                        "UID:daily@example.com",
                        "SUMMARY:Daily Sync",
                        "STATUS:CANCELLED",
                        "RECURRENCE-ID;TZID=America/Sao_Paulo:20260602T090000",
                        "DTSTART;TZID=America/Sao_Paulo:20260602T090000",
                        "DTEND;TZID=America/Sao_Paulo:20260602T093000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 6, 2, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

            self.assertEqual(today_ics_events(path, now), [])


if __name__ == "__main__":
    unittest.main()
