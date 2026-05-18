# 0002 - Provider Integrations Are Runtime Plugins

Status: Accepted

## Context

Slack, Discord, GitHub, Google Calendar, ICS, weather, and future Teams/Zoom integrations have different transport needs. Some poll. Some run background receivers. Some contribute event sources. Some contribute data sources such as pull requests or weather.

Hard-coding all providers into the main loop would make local runs brittle and would force unused integrations to load.

## Decision

External providers are integration plugins under `pixel_ops/integrations/<name>/`.

The runtime loader in `pixel_ops/integration_plugins/registry.py` imports a provider only when its config enables it. A provider returns an `IntegrationContribution` with any combination of:

- `event_sources`;
- `calendar_paths`;
- `starters`;
- `warmers`;
- `closers`;
- `pull_request_source`;
- `weather_source`.

## Consequences

Adding a provider requires:

1. A module under `pixel_ops/integrations/<name>/`.
2. A plugin class implementing `enabled(ctx)` and `build(ctx)`.
3. A registry entry in `PLUGIN_MODULES`.
4. An enable default in `PLUGIN_ENABLES`.
5. JSON config under `pixel_ops/config/integrations.json`.

Plugins must be optional. Missing provider credentials should degrade cleanly instead of breaking the display.

