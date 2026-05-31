# Pixel OPs

[![License](https://img.shields.io/github/license/marcelors27/pixel-ops)](LICENSE)
![Last commit](https://img.shields.io/github/last-commit/marcelors27/pixel-ops)
![Repo size](https://img.shields.io/github/repo-size/marcelors27/pixel-ops)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)

<img src="pixel_ops/assets/logo/pixel_ops_gaco_logo.jpg" alt="Pixel OPs logo" width="512">

Pixel OPs is a plugin-based runtime for small pixel-art operations dashboards. The core owns outputs, event sources, shared data, and display hardware; visual interfaces live in plugins. The default visual plugin is `pokemon`.

The display is intentionally ambient. Meetings become encounters, pull requests become world events, Discord voice state becomes map companions, and operational pressure becomes mood instead of a notification wall.

## Quick Start

```bash
python pixel_ops/main.py --plugin pokemon --output preview
python pixel_ops/main.py --plugin pokemon --output window --forever
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
python pixel_ops/main.py --plugin pokemon --output thermalright --forever --fps 2 --offline
```

Window mode:

```bash
python pixel_ops/main.py --plugin pokemon --window --forever
python pixel_ops/main.py --plugin pokemon --window --window-scale 1 --forever
python pixel_ops/main.py --plugin pokemon --window --window-scale 3 --forever
```

Local outputs:

```text
pixel_ops/output/preview.png
pixel_ops/output/preview.gif
```

Platform setup and USB display notes:

- [Linux](docs/linux.md)
- [Windows](docs/windows.md)

## Platform Support

Supported development/runtime targets:

- Linux: `preview`, `gif`, `window`, and TURZX USB with libusb plus udev permissions.
- Windows: `preview`, `gif`, `window`, and TURZX USB with a WinUSB/libusb driver such as Zadig.
- macOS: useful for development and preview/window output, but USB display support is not the primary target.

Run the platform check before testing hardware:

```bash
python scripts/linux_check.py
python scripts/windows_check.py
```

Both checks validate Python dependencies, local system tools, PC stats availability, and expected TURZX USB setup. CI runs Linux and Windows workflows for Python tests, Config Studio build, and offline preview rendering.

## Config Studio

Config Studio is the local React UI for editing runtime JSON config.

```bash
cd config-studio
npm install
npm run dev
```

The dev server exposes local endpoints that read and write repository JSON files. The production build is static; use `npm run dev` for editing config.

Config Studio detects available visual plugins from `pixel_ops/plugins/*/plugin.py`, loads plugin-owned JSON only when the plugin is selected, and detects integrations from `pixel_ops/integrations/*/plugin.py`.

## Configuration

JSON is the primary runtime config format. Matching YAML files are fallback only.

Core config:

- `pixel_ops/config/display.json`: display size, FPS, output target, AI decision config, splash, and HUD layout.
- `pixel_ops/config/people.json`: people and time zones.
- `pixel_ops/config/integrations.json`: integration enables and non-secret provider settings.

Pokemon plugin config:

- `pixel_ops/plugins/pokemon/game.json`: scene timing, HUD/game layout, events, and Pokemon selection behavior.
- `pixel_ops/plugins/pokemon/pokemon.json`: PokeAPI, cache, sprite, and offline settings.
- `pixel_ops/plugins/pokemon/companions.json`: Pokemon-specific visual mapping for Discord companions.

Integration sidecars:

- `pixel_ops/config/discord_people.json`: recent Discord users and nicknames observed from voice state.

Secrets stay in `.env`. Runtime toggles, guild IDs, repo lists, city names, sprite choices, and other UI-editable values stay in JSON.

Secret env vars currently used:

```env
PIXEL_OPS_SLACK_APP_TOKEN=xapp-...
PIXEL_OPS_SLACK_BOT_TOKEN=xoxb-...
PIXEL_OPS_DISCORD_BOT_TOKEN=...
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
PIXEL_OPS_CLICKUP_TOKEN=pk_...
OPENAI_API_KEY=sk-...
OPENAI_ADMIN_KEY=sk-admin-...
OPENWEATHERMAP_API_KEY=...
```

## Plugin Types

Pixel OPs has three plugin-style boundaries:

- visual interface plugins render the world;
- integration plugins collect outside activity and normalize it;
- AI decision plugins provide optional structured model decisions.

### Visual Interface Plugins

Visual plugins live in `pixel_ops/plugins/<name>/`. They own a complete display experience and translate shared runtime state into pixels.

Visual plugins may consume core data types such as `PersonTime`, `CalendarEvent`, `PullRequestSummary`, `WeatherState`, `AIUsageSnapshot`, `WorkEvent`, and `EventSource`. They must not make provider transport calls directly.

The visual plugin object contract is duck-typed by `pixel_ops/main.py`:

- `name`: stable CLI/config key.
- `display_name`: human-readable name for UI tooling.
- `add_arguments(parser)`: optional CLI flags.
- `load_config(plugin_dir, load_config)`: load plugin-owned JSON config.
- `maybe_handle_command(args, root_dir, config)`: handle one-shot commands.
- `fps(config, display_fps)`: choose render FPS.
- `event_config(config)`: expose event settings to the runtime.
- `build_app(...)`: return a `PixelOpsApp`.

To create a visual plugin:

1. Create `pixel_ops/plugins/<name>/plugin.py`.
2. Add plugin JSON files under that directory.
3. Implement the plugin class.
4. Register it in `pixel_ops/plugins/registry.py`.
5. Consume core events/data sources instead of importing provider transports.
6. Add documentation and an ADR when changing runtime boundaries or event semantics.

Pokemon-specific docs:

- [Pokemon plugin documentation](pixel_ops/plugins/pokemon/README.md)

### Integration Plugins

Integration plugins live in `pixel_ops/integrations/<name>/plugin.py`. They own provider setup, polling, sockets, local file reads, and normalization.

Integration plugins implement the protocol in `pixel_ops/integration_plugins/base.py`:

- `name`: stable key under `pixel_ops/config/integrations.json`.
- `enabled(ctx)`: decide whether the plugin should load.
- `build(ctx)`: return an `IntegrationContribution`.

`IntegrationContribution` can provide:

- `event_sources`;
- `calendar_paths`;
- `starters`;
- `warmers`;
- `closers`;
- `pull_request_source`;
- `weather_source`;
- `ai_usage_source`.

To create an integration plugin:

1. Create `pixel_ops/integrations/<name>/plugin.py`.
2. Add a class with `name`, `enabled(ctx)`, and `build(ctx)`.
3. Return normalized contributions only.
4. Add the module to `PLUGIN_MODULES` and env fallback to `PLUGIN_ENABLES`.
5. Add non-secret config under `pixel_ops/config/integrations.json`.
6. Keep secrets in `.env` and reference them from JSON by env var name.
7. Normalize social/meeting activity through `AmbientSignal` and `WorkEvent`.

Provider integrations must not render raw messages, provider payloads, or chat feeds.

### AI Decision Plugins

AI decision plugins live under `pixel_ops/plugins/ai/`. They are not visual plugins.

The protocol in `pixel_ops/plugins/ai/plugin.py` is:

- `enabled`: boolean.
- `decide_json(request)`: return a JSON object matching the request schema, or `None`.

Rules:

- calls are optional;
- successful decisions should be cached when practical;
- return `None` on disabled config, missing keys, API errors, or invalid JSON;
- keep provider-specific API code in the AI plugin, not visual scenes.

To add an AI provider, implement the protocol, extend `build_ai_plugin()`, add JSON config under `display.ai`, and document any new secret env vars.

## Integrations

All providers normalize into ambient state. Social/meeting providers first produce `AmbientSignal`, then `WorkEvent`. The common vocabulary lives in `pixel_ops/events/ambient_signals.py`.

### Calendars

Local ICS file:

```bash
python pixel_ops/main.py --ics path/to/calendar.ics
```

ICS config:

```json
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

```json
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

### GitHub

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

GitHub pull requests feed the compact HUD. When `fetch_deployments` is enabled, recent GitHub Actions workflow runs are normalized into ambient deploy/build events. Leave `deployment_workflows` empty to observe all workflows.

### ClickUp

```json
{
  "integrations": {
    "clickup": {
      "enabled": true,
      "token_env": "PIXEL_OPS_CLICKUP_TOKEN",
      "team_id": "",
      "assignee_id": "",
      "poll_seconds": 120,
      "max_tasks": 5,
      "due_within_days": 14
    }
  }
}
```

ClickUp tasks feed the optional `tasks` HUD window with assigned task names, due dates, and remaining time. Leave `team_id` and `assignee_id` empty to resolve the first authorized Workspace and current API user.

### Weather

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

Supported providers:

- `open_meteo`: default, no key.
- `wttr_in`: no key.
- `openweathermap`: requires the configured API key env var.

### AI Usage

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

Supported sources:

- Codex local JSONL sessions under `CODEX_HOME` or `~/.codex`.
- Claude local JSONL project logs under `~/.claude/projects`.
- OpenAI Admin API usage/cost endpoints via `OPENAI_ADMIN_KEY`.

Pixel OPs renders this as ambient gauges and threshold events, not billing tables or token logs.

### Slack

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

Slack uses Socket Mode. Enable Socket Mode in the Slack app, create an app-level token with `connections:write`, and install the bot with event scopes for mentions, messages, reactions, and presence-like activity.

### Discord

```json
{
  "integrations": {
    "discord": {
      "enabled": true,
      "bot_token_env": "PIXEL_OPS_DISCORD_BOT_TOKEN",
      "guild_id": "1133891225209024633",
      "focus_user_id": "242829666488942593",
      "max_companions": 30,
      "gateway_reconnect_seconds": 10
    }
  }
}
```

Discord runs a local Gateway client. It tracks voice state for one guild, emits provider-neutral voice activity events on voice channel joins/switches, and exposes a current voice snapshot for visual plugins. Recent Discord identities are stored in `discord_people.json`; Pokemon sprite choices are stored separately in `pixel_ops/plugins/pokemon/companions.json`.

## Pokemon Cache

Download/cache PokeAPI metadata plus front and animated sprites:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
python pixel_ops/main.py --plugin pokemon --warm-cache --pokemon-limit 25
```

Run without network access:

```bash
python pixel_ops/main.py --plugin pokemon --output preview --offline
```

## Hardware

Display transport is isolated in `pixel_ops/hardware/`. The current reference device is a TURZX/Turing Smart Screen-style 3.5-inch USB display:

- Size: 3.5-inch portrait display.
- Resolution: 320x480.
- Protocol: Rev. A-compatible USB bulk transport (`1a86:5722`).
- Backend: `usb_bulk_rev_a`.

Purchase links:

- Brazil: [TURZX 3.5-inch secondary USB monitor on Mercado Livre](https://www.mercadolivre.com.br/tela-ips-monitoramento-35-polegadas-secundaria-usb-monitor-turzx-telinha-auxiliar-aida-64-mini-tela-pc/p/MLB29751860)
- United States: [TURZX 3.5-inch USB monitor search on Amazon](https://www.amazon.com/s?k=TURZX+3.5+inch+USB+monitor)

Listings change frequently. Match a 3.5-inch TURZX/Turing Smart Screen/USB monitor with 320x480 resolution before buying.

## Architecture Records

Architecture decisions live in [docs/adr](docs/adr/README.md). Add or update an ADR when changing provider/plugin boundaries, config ownership, event semantics, AI policy, hot reload behavior, or renderer product principles.

## Credits

- [CodexBar](https://github.com/steipete/CodexBar), by Peter Steinberger, inspired the provider-normalized AI usage gauges and local/API usage tracking approach used by the `ai_usage` integration.
- Pixel OPs was originally built from a local fork of [`mathoudebine/turing-smart-screen-python`](https://github.com/mathoudebine/turing-smart-screen-python). The upstream project provided the original USB display protocol research and Python driver foundation for Turing Smart Screen style devices. The current repository keeps a minimal adapted USB bulk transport and RGB565 serializer.
