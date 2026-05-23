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
from pixel_ops.integrations.slack.classifier import classify_slack_event
from pixel_ops.integrations.slack.source import SlackBusEventSource


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
        self.assertEqual(len(snapshot.members), 1)
        self.assertEqual(snapshot.members[0].name, "Ana")
        self.assertTrue(snapshot.members[0].muted)

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

    def test_slack_classifier_maps_mentions_to_high_priority_work_events(self):
        signal = classify_slack_event(
            {"event_id": "E1", "event": {"type": "message", "channel_type": "channel", "text": "hey <@BOT>", "user": "U1", "channel": "C1"}},
            bot_user_id="BOT",
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind.value, "mention")


if __name__ == "__main__":
    unittest.main()
