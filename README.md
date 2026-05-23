# Pixel OPs

[![License](https://img.shields.io/github/license/marcelors27/pixel-ops)](LICENSE)
![Last commit](https://img.shields.io/github/last-commit/marcelors27/pixel-ops)
![Repo size](https://img.shields.io/github/repo-size/marcelors27/pixel-ops)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)

<img src="pixel_ops/assets/logo/pixel_ops_gaco_logo.jpg" alt="Pixel OPs logo" width="512">

Pixel OPs is a plugin-based runtime for small pixel-art operations dashboards. The core owns outputs, event sources, shared data, and display hardware; visual interfaces live in plugins. The default plugin today is `pokemon`.

Pixel OPs treats a tiny secondary screen as an eidetic display: a persistent, glanceable surface that turns operational context into a memorable visual scene. Instead of another dense dashboard tab, it keeps the next meeting, teammate time zones, open pull requests, and ambient work signals in a compact image your brain can recognize quickly.

The project also uses game-like interfaces to make routine operations easier to notice and remember. Meetings become encounters, pull requests become world events, and status changes become part of a playful loop. The goal is not to hide important work behind decoration; it is to make recurring signals more legible, emotionally lighter, and easier to keep in peripheral awareness.

## Run

```bash
python pixel_ops/main.py --plugin pokemon --output preview
python pixel_ops/main.py --plugin pokemon --output window --forever
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

Window mode renders the live dashboard in a desktop window instead of writing a file or using the USB display:

```bash
python pixel_ops/main.py --plugin pokemon --window --forever
python pixel_ops/main.py --plugin pokemon --window --window-scale 1 --forever
python pixel_ops/main.py --plugin pokemon --window --window-scale 3 --forever
```

`--window-scale 1` shows the native 320x480 frame. Higher integer scales enlarge the window with nearest-neighbor pixel scaling.

Local outputs:

```text
pixel_ops/output/preview.png
pixel_ops/output/preview.gif
```

## Configuration

- People and time zones: `pixel_ops/config/people.json`
- Display/FPS/output paths: `pixel_ops/config/display.json`
- Pokemon plugin scene: `pixel_ops/plugins/pokemon/game.json`
- PokeAPI/cache/sprites: `pixel_ops/plugins/pokemon/pokemon.json`

JSON config files are the primary runtime config. Matching YAML files are still
accepted as fallback, but when both exist the JSON file wins. Long-running modes
hot-reload visual app config changes from JSON without restarting the display;
changing output dimensions/FPS or integration enable envs still requires a
restart.

## Plugins

Pixel OPs has three plugin-style boundaries. Keep them separate:

- visual interface plugins render the world;
- integration plugins collect outside activity and normalize it;
- AI decision plugins provide optional structured model decisions.

### Visual Interface Plugins

Visual plugins live in `pixel_ops/plugins/<name>/`. They own a complete display experience and translate shared runtime state into pixels. The current default is `pokemon`.

Visual plugins may depend on core data types such as `PersonTime`, `CalendarEvent`, `PullRequestSummary`, `WeatherState`, `AIUsageSnapshot`, `WorkEvent`, and `EventSource`. They must not make provider transport calls directly. Provider-specific activity should arrive through integration contributions and core events.

The plugin object contract is currently duck-typed by `pixel_ops/main.py`:

- `name`: stable CLI/config key.
- `display_name`: human-readable name for UI tooling.
- `add_arguments(parser)`: optional CLI flags for plugin commands.
- `load_config(plugin_dir, load_config)`: load plugin-owned JSON config.
- `maybe_handle_command(args, root_dir, config)`: handle one-shot commands such as cache warmup.
- `fps(config, display_fps)`: choose the render FPS.
- `event_config(config)`: expose event selection settings to the runtime.
- `build_app(...)`: return a `PixelOpsApp`.

To create a visual plugin:

1. Create `pixel_ops/plugins/<name>/plugin.py`.
2. Add JSON config files under the plugin directory.
3. Implement a plugin class with the methods above.
4. Register it in `pixel_ops/plugins/registry.py`.
5. Keep provider-specific code out of the plugin. Consume `WorkEvent`s, data sources, and optional integration snapshots.
6. Add plugin documentation and an ADR if the plugin changes runtime boundaries or event semantics.

Config Studio discovers visual plugins from `pixel_ops/plugins/*/plugin.py` and loads plugin JSON files only when the plugin is selected.

The Pokemon plugin has its own full documentation with images, configuration examples, cache commands, maps, sprites, calendar setup, GitHub setup, and Discord companion mapping:

- [Pokemon plugin documentation](pixel_ops/plugins/pokemon/README.md)

### Integration Plugins

Integration plugins live in `pixel_ops/integrations/<name>/plugin.py`. They own provider setup, polling, sockets, local file reads, and provider-specific normalization.

Integration plugins implement the protocol in `pixel_ops/integration_plugins/base.py`:

- `name`: stable key under `pixel_ops/config/integrations.json`.
- `enabled(ctx)`: decide whether the plugin should load.
- `build(ctx)`: return an `IntegrationContribution`.

`IntegrationContext` gives a plugin:

- `root_dir`;
- CLI args;
- merged integration config;
- env helpers for secret names and legacy fallback.

`IntegrationContribution` can provide:

- `event_sources`;
- `calendar_paths`;
- `starters`;
- `warmers`;
- `closers`;
- `pull_request_source`;
- `weather_source`;
- `ai_usage_source`.

The registry in `pixel_ops/integration_plugins/registry.py` selects enabled plugins, imports their module, calls `plugin()`, merges contributions into one `IntegrationRuntime`, starts background receivers, and closes them on rebuild.

To create an integration plugin:

1. Create `pixel_ops/integrations/<name>/plugin.py`.
2. Add a class with `name`, `enabled(ctx)`, and `build(ctx)`.
3. Return only normalized contributions from `build(ctx)`.
4. Add the module to `PLUGIN_MODULES` and the env fallback key to `PLUGIN_ENABLES`.
5. Add non-secret config under `pixel_ops/config/integrations.json`.
6. Put secrets in `.env` and reference them by env var name from JSON, for example `token_env`.
7. Normalize social/meeting activity through `AmbientSignal` and `WorkEvent`; do not render raw messages, provider payloads, or chat feeds.

Config Studio detects integration plugins from `pixel_ops/integrations/*/plugin.py`. Sidecar config files still need an explicit manifest mapping so unrelated JSON is not exposed accidentally.

### AI Decision Plugins

AI decision plugins live under `pixel_ops/plugins/ai/`. They are not visual plugins. They provide optional structured decisions to visual plugins while preserving deterministic fallback behavior.

The current protocol is in `pixel_ops/plugins/ai/plugin.py`:

- `enabled`: boolean.
- `decide_json(request)`: return a JSON object matching the request schema, or `None`.

`AiDecisionRequest` contains:

- `system_prompt`;
- `user_payload`;
- `schema_name`;
- `json_schema`;
- `max_output_tokens`.

Rules for AI plugins:

- keep calls optional;
- cache successful decisions when practical;
- return `None` on missing keys, API errors, invalid JSON, or disabled config;
- never make ambient idle behavior depend on network availability;
- keep provider-specific API code in the AI plugin, not in visual scenes.

To add an AI provider, implement the protocol, extend `build_ai_plugin()`, add JSON config under `display.ai`, and document any new secret env vars in `.env.example` and ADRs.

### Config Ownership

Use JSON for runtime settings:

- core display config: `pixel_ops/config/display.json`;
- people/timezones: `pixel_ops/config/people.json`;
- integration enables and settings: `pixel_ops/config/integrations.json`;
- visual plugin config: `pixel_ops/plugins/<name>/*.json`;
- integration sidecars only when an integration owns persistent local state.

Use `.env` only for secrets. Do not move provider toggles, repo lists, city names, guild IDs, sprite choices, or UI-editable runtime values into `.env`.

## Pokemon Cache

Download/cache PokeAPI metadata plus front and animated sprites for the original 151 Pokemon:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
```

For a smaller development cache:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache --pokemon-limit 25
```

Run without network access:

```bash
python pixel_ops/main.py --plugin pokemon --output preview --offline
```

## Events

Runtime access to external systems is handled by integration plugins. Each
plugin is configured in `pixel_ops/config/integrations.json`. The `.env` file is
reserved for secrets such as Slack/GitHub/OpenAI/weather tokens. Editing
`integrations.json` during a long-running display session rebuilds the
integration runtime so enables, polling intervals, repos, calendar URLs, and
weather location can be changed from a UI.

Calendar via local `.ics`:

```bash
python pixel_ops/main.py --ics path/to/calendar.ics
```

Or via env:

```env
{
  "integrations": {
    "ics": {
      "enabled": true,
      "paths": ["/path/to/calendar.ics"],
      "poll_seconds": 300
    }
  }
}
```

Google Calendar via private ICS URL:

```env
{
  "integrations": {
    "google_calendar": {
      "enabled": true,
      "ics_urls": ["https://calendar.google.com/calendar/ical/..."],
      "poll_seconds": 300
    }
  }
}
```

GitHub pull requests in the HUD:

```env
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
```

```json
{
  "integrations": {
    "github": {
      "enabled": true,
      "token_env": "PIXEL_OPS_GITHUB_TOKEN",
      "repos": ["owner/repo"],
      "poll_seconds": 60,
      "max_pull_requests": 4,
      "fetch_deployments": true,
      "deployment_workflows": []
    }
  }
}
```

When `fetch_deployments` is enabled, recent GitHub Actions workflow runs are normalized into ambient deploy/build events. Leave `deployment_workflows` empty to observe all workflows, or list workflow names to treat only those as deploy signals.

Weather provider:

```json
{
  "integrations": {
    "weather": {
      "enabled": true,
      "provider": "open_meteo",
      "city": "Porto Alegre",
      "country_code": "BR",
      "poll_seconds": 900,
      "timeout_seconds": 8,
      "api_key_env": "OPENWEATHERMAP_API_KEY"
    }
  }
}
```

Supported weather providers are `open_meteo` (default, no key), `wttr_in` (no key), and `openweathermap` (requires the configured API key environment variable).

AI usage ambient gauges:

```env
OPENAI_ADMIN_KEY=sk-admin-...
```

```json
{
  "integrations": {
    "ai_usage": {
      "enabled": true,
      "providers": ["codex", "claude", "openai_api"],
      "poll_seconds": 300,
      "codex_home": "~/.codex",
      "claude_projects_path": "~/.claude/projects",
      "openai_admin_key_env": "OPENAI_ADMIN_KEY",
      "thresholds": [75, 90]
    }
  }
}
```

This follows the useful CodexBar pattern: provider-specific collectors normalize
usage into small snapshots and gauges. Pixel OPs keeps that data ambient: the
HUD shows tiny provider meters, and threshold crossings become `ai_usage` work
events that can influence encounters/world mood. It does not render billing
tables or detailed token logs.

Supported sources:

- Codex local JSONL sessions under `CODEX_HOME` or `~/.codex`.
- Claude local JSONL project logs under `~/.claude/projects`.
- OpenAI Admin API usage/cost endpoints via `OPENAI_ADMIN_KEY`.

Slack Socket Mode receiver:

```env
PIXEL_OPS_SLACK_APP_TOKEN=xapp-...
PIXEL_OPS_SLACK_BOT_TOKEN=xoxb-...
```

```json
{
  "integrations": {
    "slack": {
      "enabled": true,
      "app_token_env": "PIXEL_OPS_SLACK_APP_TOKEN",
      "bot_token_env": "PIXEL_OPS_SLACK_BOT_TOKEN",
      "bot_user_id": "U123456",
      "socket_reconnect_seconds": 10
    }
  }
}
```

Enable Socket Mode in the Slack app, create an app-level token with
`connections:write`, and install the bot with event scopes for mentions,
messages, reactions, and presence-like activity. Socket Mode is the recommended
local setup because GACO opens an outbound WebSocket and does not need a public
IP, tunnel, TLS endpoint, or reverse proxy.

Secrets:

```env
PIXEL_OPS_SLACK_APP_TOKEN=xapp-...
PIXEL_OPS_SLACK_BOT_TOKEN=xoxb-...
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
OPENAI_API_KEY=sk-...
OPENAI_ADMIN_KEY=sk-admin-...
```

Supported signals include DMs, mentions, reactions, channel activity,
calls/huddles, incident/deploy/PR keywords, and presence-like joins.

Discord support is exposed as a Gateway dispatch adapter in
`pixel_ops/integrations/discord/gateway.py`; a bot runner can pass dispatch
payloads into `DiscordGatewayAdapter.handle_dispatch()`. Supported signals
include presence, voice activity, mentions, message spikes, and server activity.

All social/meeting providers normalize into `AmbientSignal` before becoming
GACO `WorkEvent`s. That provider-neutral layer lives in
`pixel_ops/events/ambient_signals.py` and uses a small common vocabulary:
`meeting_soon`, `meeting_started`, `meeting_ended`, `participant_joined`,
`voice_activity`, `mention`, `activity_spike`, `quiet_period`,
`incident_signal`, `deploy_signal`, and `review_signal`. Slack, Discord,
Teams, and Zoom integrations should stop at that boundary; the renderer only
sees mood and encounter effects.

## Hardware

Display transport is isolated in `pixel_ops/hardware/`. It contains only the minimal USB bulk transport needed by Pixel OPs.

The current reference device is a TURZX/Turing Smart Screen-style 3.5-inch USB display:

- Size: 3.5-inch portrait display
- Resolution: 320x480
- Protocol: Rev. A-compatible USB bulk transport (`1a86:5722`)
- Backend: `usb_bulk_rev_a`

Purchase links:

- Brazil: [TURZX 3.5-inch secondary USB monitor on Mercado Livre](https://www.mercadolivre.com.br/tela-ips-monitoramento-35-polegadas-secundaria-usb-monitor-turzx-telinha-auxiliar-aida-64-mini-tela-pc/p/MLB29751860)
- United States: [TURZX 3.5-inch USB monitor search on Amazon](https://www.amazon.com/s?k=TURZX+3.5+inch+USB+monitor)

Listings change frequently. Match a 3.5-inch TURZX/Turing Smart Screen/USB monitor with 320x480 resolution before buying.

## Credits

- [CodexBar](https://github.com/steipete/CodexBar), by Peter Steinberger, inspired the provider-normalized AI usage gauges and local/API usage tracking approach used by the `ai_usage` integration.

## Credits

Pixel OPs was originally built from a local fork of [`mathoudebine/turing-smart-screen-python`](https://github.com/mathoudebine/turing-smart-screen-python). The upstream project provided the original USB display protocol research and Python driver foundation for Turing Smart Screen style devices. The current repository keeps a minimal adapted USB bulk transport and RGB565 serializer; the full upstream system monitor, theme library, configuration tools, and bundled app are not included.
