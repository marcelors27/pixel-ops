# Architecture Decision Records

This directory records product and technical decisions for Pixel OPs / GACO.

Format:

- `Status`: `Accepted`, `Proposed`, `Superseded`, or `Deprecated`.
- `Context`: the pressure or problem that led to the decision.
- `Decision`: the chosen direction.
- `Consequences`: tradeoffs and follow-up constraints.

Current ADRs:

- [0001 - Ambient Social Observability, Not Feeds](0001-ambient-social-observability-not-feeds.md)
- [0002 - Provider Integrations Are Runtime Plugins](0002-provider-integrations-are-runtime-plugins.md)
- [0003 - Provider-Neutral Ambient Signals](0003-provider-neutral-ambient-signals.md)
- [0004 - Slack Uses Socket Mode Only](0004-slack-uses-socket-mode-only.md)
- [0005 - JSON Runtime Configuration And Hot Reload](0005-json-runtime-configuration-and-hot-reload.md)
- [0006 - Secrets Stay In Env, Runtime Toggles Move To JSON](0006-secrets-env-runtime-json.md)
- [0007 - AI Decisions Are Optional, Cached, And Throttled](0007-ai-decisions-optional-cached-throttled.md)
- [0008 - Pokemon Is A Visual Plugin, Not The Integration Model](0008-pokemon-visual-plugin-boundary.md)
- [0009 - Meetings Are Ambient Ceremonies](0009-meetings-are-ambient-ceremonies.md)
- [0010 - Weather, Calendar, GitHub, Slack, Discord Share The Same Runtime Boundary](0010-shared-integration-runtime-boundary.md)
- [0011 - Graphify Artifacts Document The Codebase Map](0011-graphify-codebase-map.md)
- [0012 - AI Usage Becomes Ambient Gauges And Events](0012-ai-usage-ambient-gauges.md)
- [0013 - Config Studio Discovers Plugin-Owned Config](0013-config-studio-discovers-plugin-configs.md)
- [0014 - Discord Voice Companions Are Provider State With Visual Mapping](0014-discord-voice-companions-are-provider-state-with-visual-mapping.md)
- [0015 - Timezone Config Is Derived From IANA Selection](0015-timezone-config-is-derived-from-iana-selection.md)
- [0016 - PC Stats Are Local Integration Metrics](0016-pc-stats-are-local-integration-metrics.md)
- [0017 - Linux And Windows Are Supported Runtime Targets](0017-linux-and-windows-are-supported-runtime-targets.md)
- [0018 - ClickUp Tasks Are Planning Snapshots](0018-clickup-tasks-are-planning-snapshots.md)
- [0019 - Media Now Playing Is Local Presence](0019-media-now-playing-is-local-presence.md)
- [0020 - Tasks HUDs Share Provider-Neutral Board State](0020-tasks-huds-share-provider-neutral-board-state.md)
