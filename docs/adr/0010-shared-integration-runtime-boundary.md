# 0010 - Weather, Calendar, GitHub, Slack, Discord Share The Same Runtime Boundary

Status: Superseded by [ADR 0026](0026-all-game-inputs-are-platform-events.md)

## Context

Different integrations contribute different kinds of data:

- GitHub contributes pull request state and work events.
- Google Calendar and ICS contribute meetings.
- Weather contributes current environmental state.
- Slack and Discord contribute social activity.

The main loop needs a consistent way to combine these without hard-coded provider branches everywhere.

## Decision

All integrations are merged into one `IntegrationRuntime`.

`IntegrationRuntime` owns:

- event sources;
- calendar paths;
- startup callbacks;
- warmup callbacks;
- close callbacks;
- pull request source;
- weather source;
- loaded plugin names.

`pixel_ops/main.py` builds the visual app from the current runtime contribution.

The weather integration may choose between provider clients such as Open-Meteo, wttr.in, or OpenWeatherMap, but that choice stays inside the weather integration. Each client normalizes provider payloads into `WeatherState`, so visual plugins and the display loop do not branch on provider-specific schemas.

GitHub Actions workflow runs are treated the same way: the GitHub integration maps running, successful, and failed workflow runs into provider-neutral work events such as `deploy_started`, `deploy_completed`, and `build_broken`. Visual plugins consume those categories for ambient route and encounter state without knowing GitHub's workflow schema.

Discord runs as a local Gateway client when enabled. It uses the bot token from `.env`, keeps server/guild IDs and visual limits in JSON config, tracks voice channel state inside the Discord integration, and publishes channel access as provider-neutral voice activity events. Visual plugins may inspect the integration event source for an aggregate voice snapshot, but they must not depend on raw Gateway payloads or render Discord message bodies.

## Consequences

The display loop stays small and provider-agnostic.

Runtime rebuild on config changes can close old background receivers before starting new ones.

Future Teams and Zoom support should use the same contribution model.
