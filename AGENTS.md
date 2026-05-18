# Agent Guide

This repository is a Python runtime for Pixel OPs / GACO: a plugin-based ambient operations display for small pixel screens.

The core rule is that external activity must become ambient world state, not a feed, notification wall, or cloned chat UI.

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
- `pixel_ops/integration_plugins/base.py`: integration plugin contract.
- `pixel_ops/integration_plugins/registry.py`: enable-driven runtime loader.
- `pixel_ops/main.py`: CLI, config loading, hot reload, runtime rebuild.
- `pixel_ops/plugins/pokemon/plugin.py`: Pokemon interface plugin boundary.
- `pixel_ops/plugins/pokemon/scenes/overworld_scene.py`: current main scene.
- `pixel_ops/plugins/pokemon/game/social_weather.py`: social weather/world mood logic.
- `pixel_ops/plugins/pokemon/game/ai_selector.py`: Pokemon-specific AI selection and throttling.

## Configuration

JSON is the primary runtime config format:

- `pixel_ops/config/display.json`: display, output paths, timezone, AI provider settings.
- `pixel_ops/config/people.json`: people and time zones.
- `pixel_ops/config/integrations.json`: integration enables and non-secret provider settings.
- `pixel_ops/plugins/pokemon/game.json`: Pokemon scene, encounters, event mappings, AI selector throttle.
- `pixel_ops/plugins/pokemon/pokemon.json`: PokeAPI/cache/sprite settings.

YAML is only a fallback when the matching JSON file does not exist.

`.env` is for secrets only:

- `PIXEL_OPS_SLACK_APP_TOKEN`
- `PIXEL_OPS_SLACK_BOT_TOKEN`
- `PIXEL_OPS_GITHUB_TOKEN`
- `OPENAI_API_KEY`

Do not move non-secret toggles back into `.env`. Use JSON so future UI tooling can edit config graphically.

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
    "weather": { "enabled": false }
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

Slack uses Socket Mode only. Do not re-add webhook fallback unless an ADR changes that decision.

Discord currently exposes a Gateway dispatch adapter and event source boundary. A bot runner can feed dispatch payloads into the adapter.

Teams and Zoom have placeholder classifiers/client boundaries. They should also normalize into `AmbientSignal`, not into provider-specific renderer state.

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

## Documentation

Architecture decisions live in `docs/adr/`.

When making an architectural change, add or update an ADR if the change affects:

- provider/plugin boundaries;
- config ownership;
- event semantics;
- AI call policy;
- hot reload behavior;
- renderer/product principles.

