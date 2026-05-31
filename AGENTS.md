# Agent Guide

This repository is a Python runtime for Pixel OPs / GACO: a plugin-based ambient operations display for small pixel screens.

The core rule is that external activity must become ambient world state, not a feed, notification wall, or cloned chat UI.

## Default Execution Standard

All agents should use the generated graph as default support before planning or changing code.

Start every non-trivial task by checking the graph artifacts in `graphify-out/`:

- `graphify-out/GRAPH_REPORT.md` for the high-level architecture map, god nodes, bridge nodes, and suggested questions.
- `graphify-out/graph.json` for raw relationships when tracing dependencies.
- `graphify-out/graph.html` when a visual map helps inspect coupling.

Use the graph to identify likely affected modules, cross-community boundaries, and central abstractions before editing. This is especially important for changes involving integrations, config loading, event semantics, AI behavior, hot reload, rendering, or plugin boundaries.

If `graphify-out/` is missing or stale after meaningful architecture changes, regenerate or update it before continuing:

```bash
python -m graphify update .
```

The graph is an aid, not a replacement for reading source files. After identifying relevant nodes and paths, inspect the actual code before making edits.

## Product Direction

- Keep the display ambient, peripheral, calm, contextual, and emotional.
- Do not render raw Slack, Discord, Teams, Zoom, or GitHub message bodies.
- Translate social and operational activity into mood, encounter pressure, weather-like effects, ceremonies, and short diegetic text.
- Preserve the compact HUD. Time, weather, next meeting, and useful status should stay visible.
- Avoid popups, notification spam, large cards, and corporate dashboard layouts.

## Architecture

The runtime is split into three layers:

- `pixel_ops/core/`: display app contracts and hardware-neutral rendering loop.
- `pixel_ops/integration_plugins/` and `pixel_ops/integrations/`: optional external providers.
- `pixel_ops/plugins/<name>/`: visual interface plugins. The default is `pokemon`.

Integration providers should stop at Pixel OPs core events. They must not import Pokemon-specific modules or encode Pokemon rules.

The normal event path is:

```text
Provider transport
  -> provider classifier
  -> AmbientSignal
  -> WorkEvent
  -> visual plugin interpretation
  -> renderer/output
```

Key files:

- `pixel_ops/events/ambient_signals.py`: provider-neutral social/meeting vocabulary.
- `pixel_ops/events/event_bus.py`: bounded in-process event queue.
- `pixel_ops/events/github_events.py`: GitHub polling, PR HUD summaries, and GitHub work events.
- `pixel_ops/integration_plugins/base.py`: integration plugin contract.
- `pixel_ops/integration_plugins/registry.py`: enable-driven runtime loader.
- `pixel_ops/main.py`: CLI, config loading, hot reload, runtime rebuild.
- `pixel_ops/plugins/pokemon/plugin.py`: Pokemon interface plugin boundary.
- `pixel_ops/plugins/pokemon/scenes/overworld_scene.py`: current main scene.
- `pixel_ops/plugins/pokemon/game/social_weather.py`: social weather/world mood logic.
- `pixel_ops/plugins/pokemon/game/ai_selector.py`: Pokemon-specific AI selection and throttling.
- `config-studio/`: local React UI for editing JSON config and runtime layout.

## Configuration

JSON is the primary runtime config format:

- `pixel_ops/config/display.json`: display, output paths, timezone, AI provider settings.
- `pixel_ops/config/people.json`: people and time zones.
- `pixel_ops/config/integrations.json`: integration enables and non-secret provider settings.
- `pixel_ops/config/discord_people.json`: recent Discord people captured by the Discord integration.
- `pixel_ops/plugins/pokemon/game.json`: Pokemon scene, encounters, event mappings, AI selector throttle.
- `pixel_ops/plugins/pokemon/pokemon.json`: PokeAPI/cache/sprite settings.
- `pixel_ops/plugins/pokemon/companions.json`: Pokemon visual mapping for provider-owned companion state.

YAML is only a fallback when the matching JSON file does not exist.

`.env` is for secrets only:

- `PIXEL_OPS_SLACK_APP_TOKEN`
- `PIXEL_OPS_SLACK_BOT_TOKEN`
- `PIXEL_OPS_DISCORD_BOT_TOKEN`
- `PIXEL_OPS_GITHUB_TOKEN`
- `PIXEL_OPS_CLICKUP_TOKEN`
- `OPENWEATHERMAP_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_ADMIN_KEY`

Do not move non-secret toggles back into `.env`. Use JSON so future UI tooling can edit config graphically.

Config Studio edits JSON config through its Vite dev server. Treat layout windows as presentation only: removing an `activity`, `route_signal`, `pc_stats`, `weather`, `tasks`, or similar display region must not disable the underlying integration or stop runtime snapshot/event production.

## Integration Plugins

Each integration is loaded only when enabled by config:

```json
{
  "integrations": {
    "slack": { "enabled": false },
    "discord": { "enabled": false },
    "github": { "enabled": true },
    "google_calendar": { "enabled": true },
    "ics": { "enabled": true },
    "weather": { "enabled": false },
    "ai_usage": { "enabled": true },
    "pc_stats": { "enabled": true },
    "clickup": { "enabled": false }
  }
}
```

Current plugin module map:

- `slack` -> `pixel_ops.integrations.slack.plugin`
- `discord` -> `pixel_ops.integrations.discord.plugin`
- `github` -> `pixel_ops.integrations.github.plugin`
- `google_calendar` -> `pixel_ops.integrations.google_calendar.plugin`
- `ics` -> `pixel_ops.integrations.ics.plugin`
- `weather` -> `pixel_ops.integrations.weather.plugin`
- `ai_usage` -> `pixel_ops.integrations.ai_usage.plugin`
- `pc_stats` -> `pixel_ops.integrations.pc_stats.plugin`
- `clickup` -> `pixel_ops.integrations.clickup.plugin`

Slack uses Socket Mode only. Do not re-add webhook fallback unless an ADR changes that decision.

Discord currently exposes a Gateway client, dispatch adapter, voice state tracker, event source boundary, and companion people store. Voice/presence state may become companion movement or ambience, but provider state should still normalize through the integration boundary before the visual plugin interprets it.

Teams and Zoom have placeholder classifiers/client boundaries. They should also normalize into `AmbientSignal`, not into provider-specific renderer state.

AI usage follows the same provider boundary. Codex, Claude, and OpenAI API usage are normalized into gauges and `ai_usage` work events. Do not render raw logs, prompts, responses, or billing tables.

PC stats are local runtime metrics. They expose compact gauges such as CPU, RAM, disk, battery, temperature, top process, GPU identity, uptime, and load. Keep collection in `pixel_ops/data_sources/pc_stats.py` and the `pc_stats` integration; visual plugins should consume snapshots, not call platform APIs directly.

ClickUp tasks are work planning state. Keep API polling in `pixel_ops/data_sources/clickup.py` and the `clickup` integration; visual plugins should consume snapshots and render compact task pressure, due dates, and remaining time rather than raw comments or activity feeds.

GitHub exposes both `pull_request_source` for compact HUD summaries and an event source for encounters/mood. These paths must stay independent from layout visibility: hiding PR/activity/route windows cannot stop PR opened, merged, closed, build, or deploy events from entering the event queue.

## AI Calls

AI selection is optional and throttled.

Rules:

- Ambient idle encounters never call OpenAI.
- Slack and Discord are skipped by default for Pokemon AI selection.
- The default throttle allows one pending request, a 90 second cooldown, and four requests per 15 minutes.
- Successful decisions are cached under `pixel_ops/cache/ai_decisions`.
- If AI is unavailable, the local knowledge base and deterministic fallback must keep the display working.

Provider-agnostic AI code lives in `pixel_ops/plugins/ai/plugin.py`.
Pokemon-specific prompt, parsing, and throttle logic lives in `pixel_ops/plugins/pokemon/game/ai_selector.py`.

## Hot Reload

Long-running display modes watch JSON config files. When config changes:

- Visual app config is rebuilt.
- Integration config changes rebuild the integration runtime.
- Output dimensions, selected output mode, and CLI-level process choices still require process restart.

The current watcher is timestamp-based in `pixel_ops/config_loader.py`.

## Running

Common commands:

```bash
python pixel_ops/main.py --plugin pokemon --output preview
python pixel_ops/main.py --plugin pokemon --output window --forever
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

Warm the Pokemon cache:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
```

Generate or update the architecture graph:

```bash
python -m graphify update .
```

The generated graph artifacts live in `graphify-out/`.

Run Config Studio:

```bash
cd config-studio
npm run dev
```

The Config Studio runtime panel can check config, render a preview, and start/stop window mode through local `/api/runtime/*` endpoints.

## Documentation

Architecture decisions live in `docs/adr/`.

When making an architectural change, add or update an ADR if the change affects:

- provider/plugin boundaries;
- config ownership;
- event semantics;
- AI call policy;
- hot reload behavior;
- renderer/product principles.
