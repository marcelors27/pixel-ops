from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pixel_ops.events.base import EventCategory
from pixel_ops.events.event_bus import EventBus
from pixel_ops.integrations.discord.client import DiscordGatewayClient
from pixel_ops.integrations.discord.companions import DiscordCompanionStore
from pixel_ops.integrations.discord.gateway import DiscordBusEventSource
from pixel_ops.integrations.discord.voice_state import DiscordVoiceStateTracker
from pixel_ops.integrations.kite.source import PixelOpsKiteClient
from pixel_ops.integrations.slack.activity import SlackAmbientAggregator
from pixel_ops.integrations.slack.classifier import classify_slack_event
from pixel_ops.integrations.slack.source import SlackBusEventSource
from pixel_ops.integrations.zoom.client import ZoomLiveMeeting, ZoomParticipant, ZoomPollingRunner
from pixel_ops.integrations.zoom.gateway import ZoomBusEventSource
from pixel_ops.integrations.zoom.participants import ZoomCompanionSource, ZoomParticipantTracker


class FakeZoomClient:
    configured = True

    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    def live_meetings(self):
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


class DiscordAndSocialTests(unittest.TestCase):
    def test_discord_companion_store_records_recent_people_in_current_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discord_people.json"
            store = DiscordCompanionStore(path)

            profile = store.record_member("u1", "Ana")
            raw = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(profile.display_name, "Ana")
            self.assertIn("discord_people", raw)
            self.assertEqual(raw["discord_people"]["people"]["u1"]["display_name"], "Ana")
            self.assertNotIn("discord_companions", raw)

    def test_discord_companion_store_imports_legacy_json_into_sqlite(self):
        from pixel_ops.state import PixelOpsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "discord_people.json"
            path.write_text(
                json.dumps(
                    {
                        "discord_people": {
                            "max_recent": 50,
                            "people": {
                                "u1": {
                                    "display_name": "Ana",
                                    "nicknames": ["Ana"],
                                    "last_seen_at": "2026-01-01T12:00:00+00:00",
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            state = PixelOpsStateStore(root / "pixel_ops.sqlite")
            store = DiscordCompanionStore(path, state_store=state)

            self.assertEqual(store.profile("u1").display_name, "Ana")
            store.record_member("u2", "Bia")

            self.assertEqual(state.discord_person("u2").display_name, "Bia")

    def test_voice_tracker_selects_focus_channel_and_preserves_muted_state(self):
        tracker = DiscordVoiceStateTracker(guild_id="g", focus_user_id="me", max_companions=5)
        tracker.observe_guild(
            {
                "id": "g",
                "channels": [{"id": "c1", "name": "General"}, {"id": "c2", "name": "Other"}],
                "members": [{"user": {"id": "u1", "username": "Ana"}}],
            }
        )
        tracker.observe_voice_state({"guild_id": "g", "user_id": "me", "channel_id": "c1"})
        tracker.observe_voice_state(
            {
                "guild_id": "g",
                "user_id": "u1",
                "channel_id": "c1",
                "self_mute": True,
                "member": {"user": {"id": "u1", "username": "Ana"}},
            }
        )
        tracker.observe_voice_state({"guild_id": "g", "user_id": "u2", "channel_id": "c2", "member": {"user": {"id": "u2", "username": "Bia"}}})

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot.channel_id, "c1")
        self.assertEqual(snapshot.channel_name, "General")
        self.assertEqual(snapshot.focus_user_id, "me")
        self.assertEqual(len(snapshot.members), 1)
        self.assertEqual(snapshot.members[0].name, "Ana")
        self.assertTrue(snapshot.members[0].muted)

    def test_voice_tracker_marks_active_streams_in_selected_channel(self):
        tracker = DiscordVoiceStateTracker(guild_id="g", focus_user_id="me", max_companions=5)
        tracker.observe_guild({"id": "g", "channels": [{"id": "c1", "name": "General"}]})
        tracker.observe_voice_state({"guild_id": "g", "user_id": "me", "channel_id": "c1", "self_stream": True})
        tracker.observe_voice_state({"guild_id": "g", "user_id": "u1", "channel_id": "c1", "member": {"user": {"id": "u1", "username": "Ana"}}})

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot.active_stream_user_ids, ("me",))
        self.assertEqual(snapshot.focus_user_id, "me")
        self.assertTrue(snapshot.focus_streaming)
        self.assertFalse(snapshot.members[0].streaming)

    def test_discord_gateway_client_publishes_voice_join_but_presence_only_updates_tracker(self):
        bus = EventBus(maxlen=8)
        tracker = DiscordVoiceStateTracker(guild_id="g", focus_user_id="me")
        tracker.observe_guild({"id": "g", "channels": [{"id": "c1", "name": "General"}]})
        tracker.observe_voice_state({"guild_id": "g", "user_id": "me", "channel_id": "c1"})
        client = DiscordGatewayClient(bus, tracker, token="", guild_id="g", enabled=False)

        client._handle_dispatch({"t": "PRESENCE_UPDATE", "d": {"user": {"id": "u1", "username": "Ana"}}})
        self.assertEqual(len(bus), 0)

        client._handle_dispatch({"t": "VOICE_STATE_UPDATE", "s": 42, "d": {"guild_id": "g", "user_id": "u1", "channel_id": "c1"}})
        events = bus.drain()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, EventCategory.MEETING)
        self.assertEqual(events[0].metadata["channel_name"], "General")
        self.assertEqual(events[0].metadata["voice_member_ids"], "u1")

    def test_discord_and_slack_bus_sources_drain_only_when_enabled(self):
        now = datetime.now(timezone.utc)
        bus = EventBus(maxlen=4)
        bus.publish("event")

        self.assertEqual(SlackBusEventSource(bus, enabled=False).poll(now), [])
        self.assertEqual(SlackBusEventSource(bus, enabled=True).poll(now), ["event"])

        bus.publish("discord")
        self.assertEqual(DiscordBusEventSource(bus, enabled=True).poll(now), ["discord"])

    def test_zoom_polling_runner_updates_live_meeting_companions(self):
        bus = EventBus(maxlen=8)
        tracker = ZoomParticipantTracker(focus_user_id="me@example.com", max_companions=5)
        me = ZoomParticipant(participant_id="me@example.com", name="Me", email="me@example.com")
        ana = ZoomParticipant(participant_id="ana@example.com", name="Ana", email="ana@example.com")
        client = FakeZoomClient(
            [
                [ZoomLiveMeeting(meeting_id="m1", topic="Planning", participants=(me, ana))],
                [ZoomLiveMeeting(meeting_id="m1", topic="Planning", participants=(me,))],
            ]
        )
        runner = ZoomPollingRunner(client, tracker, bus, poll_seconds=10)

        runner.poll_once(datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc))

        snapshot = ZoomCompanionSource(tracker).current()
        events = ZoomBusEventSource(bus, enabled=True).poll(datetime.now(timezone.utc))

        self.assertEqual(snapshot.focus_user_id, "zoom:me@example.com")
        self.assertEqual(snapshot.members[0].user_id, "zoom:ana@example.com")
        self.assertEqual(snapshot.group_name, "Planning")
        self.assertEqual(events[0].category, EventCategory.MEETING)

        runner.poll_once(datetime(2026, 6, 4, 12, 1, tzinfo=timezone.utc))

        snapshot = ZoomCompanionSource(tracker).current()
        events = ZoomBusEventSource(bus, enabled=True).poll(datetime.now(timezone.utc))
        self.assertEqual(snapshot.members, ())
        self.assertEqual(events[0].metadata["ambient_kind"], "participant_left")

    def test_pixelops_kite_envelope_updates_zoom_companions(self):
        bus = EventBus(maxlen=8)
        tracker = ZoomParticipantTracker(focus_user_id="me@example.com", max_companions=5)
        client = PixelOpsKiteClient(bus, ws_url="wss://kite.example/connect", token="secret", enabled=False, zoom_tracker=tracker)

        client.handle_envelope(_kite_zoom_envelope("meeting.participant_joined", "m1", "Planning", "Me", "me@example.com"))
        client.handle_envelope(_kite_zoom_envelope("meeting.participant_joined", "m1", "Planning", "Ana", "ana@example.com"))

        snapshot = ZoomCompanionSource(tracker).current()
        events = bus.drain()

        self.assertEqual(snapshot.focus_user_id, "zoom:me@example.com")
        self.assertEqual(snapshot.members[0].name, "Ana")
        self.assertEqual(events[-1].metadata["ambient_provider"], "zoom")

    def test_slack_classifier_maps_mentions_to_high_priority_work_events(self):
        signal = classify_slack_event(
            {"event_id": "E1", "event": {"type": "message", "channel_type": "channel", "text": "hey <@BOT>", "user": "U1", "channel": "C1"}},
            bot_user_id="BOT",
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind.value, "mention")

    def test_slack_channel_messages_do_not_become_operational_keyword_events(self):
        signal = classify_slack_event(
            {"event_id": "E2", "event": {"type": "message", "channel_type": "channel", "text": "deploy incident p0", "user": "U1", "channel": "C1"}},
            bot_user_id="BOT",
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind.value, "activity_spike")

    def test_slack_activity_aggregator_emits_only_channel_spikes(self):
        aggregator = SlackAmbientAggregator(
            activity_window_seconds=60,
            activity_threshold=3,
            activity_cooldown_seconds=300,
            channel_rules=SlackAmbientAggregator.rules_from_config(
                {"C1": {"label": "engineering", "tone": "busy", "activity_threshold": 3, "dominant_types": ["electric", "fighting"]}}
            ),
        )
        events = []
        for ts in ("1000.0", "1010.0", "1020.0"):
            signal = classify_slack_event(
                {"event_id": f"E{ts}", "event": {"type": "message", "channel_type": "channel", "text": "ambient", "user": "U1", "channel": "C1", "ts": ts}},
                bot_user_id="BOT",
            )
            events.extend(aggregator.observe(signal))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, EventCategory.SOCIAL_ACTIVITY)
        self.assertEqual(events[0].metadata["activity_count"], "3")
        self.assertEqual(events[0].metadata["channel_label"], "engineering")
        self.assertEqual(events[0].metadata["dominant_types"], "electric,fighting")

    def test_slack_dm_and_huddle_emit_immediately(self):
        aggregator = SlackAmbientAggregator(activity_threshold=10)
        dm = classify_slack_event({"event_id": "D1", "event": {"type": "message", "channel_type": "im", "text": "hey", "user": "U1", "channel": "D1"}})
        huddle = classify_slack_event({"event_id": "H1", "event": {"type": "call_started", "user": "U1", "channel": "C1"}})

        dm_events = aggregator.observe(dm)
        huddle_events = aggregator.observe(huddle)

        self.assertEqual(dm_events[0].category, EventCategory.MESSAGE_IMPORTANT)
        self.assertEqual(dm_events[0].metadata["attention_pressure"], "medium")
        self.assertEqual(huddle_events[0].category, EventCategory.MEETING)
        self.assertEqual(huddle_events[0].metadata["meeting_type"], "huddle")

    def test_slack_aggregator_emits_periodic_summary_without_message_text(self):
        aggregator = SlackAmbientAggregator(activity_window_seconds=60, activity_threshold=10, summary_window_seconds=60)
        first = classify_slack_event(
            {"event_id": "S1", "event": {"type": "message", "channel_type": "channel", "text": "sensitive message body", "user": "U1", "channel": "C1", "ts": "1000.0"}},
            bot_user_id="BOT",
        )
        mention = classify_slack_event(
            {"event_id": "S2", "event": {"type": "message", "channel_type": "channel", "text": "hey <@BOT> private details", "user": "U2", "channel": "C2", "ts": "1070.0"}},
            bot_user_id="BOT",
        )

        self.assertEqual(aggregator.observe(first), [])
        events = aggregator.observe(mention)
        summary = events[-1]

        self.assertEqual(summary.title, "Slack ambient pressure summary")
        self.assertEqual(summary.metadata["activity_count"], "1")
        self.assertEqual(summary.metadata["mentions"], "1")
        self.assertNotIn("sensitive", str(summary.metadata))
        self.assertNotIn("private details", str(summary.metadata))

def _kite_zoom_envelope(event: str, meeting_id: str, topic: str, name: str, email: str) -> dict:
    return {
        "type": "webhook",
        "provider": "zoom",
        "event": event,
        "payload": {
            "event": event,
            "event_ts": 1_780_000_000_001,
            "payload": {
                "object": {
                    "uuid": meeting_id,
                    "topic": topic,
                    "participant": {
                        "id": email,
                        "user_name": name,
                        "email": email,
                    },
                }
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
