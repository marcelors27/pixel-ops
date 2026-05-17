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

- People and time zones: `pixel_ops/config/people.yaml`
- Display/FPS/output paths: `pixel_ops/config/display.yaml`
- Pokemon plugin scene: `pixel_ops/plugins/pokemon/game.yaml`
- PokeAPI/cache/sprites: `pixel_ops/plugins/pokemon/pokemon.yaml`

## Plugins

The Pokemon plugin has its own full documentation with images, configuration examples, cache commands, maps, sprites, calendar setup, and GitHub setup:

- [Pokemon plugin documentation](pixel_ops/plugins/pokemon/README.md)

Plugins live in `pixel_ops/plugins/<name>/` and expose a plugin class with:

- `name`
- `add_arguments(parser)`
- `load_config(plugin_dir, load_yaml)`
- `maybe_handle_command(args, root_dir, config)`
- `fps(config, display_fps)`
- `event_config(config)`
- `build_app(...)`

Register new interfaces in `pixel_ops/plugins/registry.py`.

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
plugin is loaded only when its own enable variable is true:

```text
PIXEL_OPS_SLACK_ENABLED
PIXEL_OPS_DISCORD_ENABLED
PIXEL_OPS_GITHUB_ENABLED
PIXEL_OPS_GOOGLE_CALENDAR_ENABLED
PIXEL_OPS_ICS_ENABLED
```

Calendar via local `.ics`:

```bash
python pixel_ops/main.py --ics path/to/calendar.ics
```

Or via env:

```env
PIXEL_OPS_ICS_ENABLED=true
PIXEL_OPS_ICS_PATH=/path/to/calendar.ics
PIXEL_OPS_ICS_POLL_SECONDS=300
```

Google Calendar via private ICS URL:

```env
PIXEL_OPS_GOOGLE_CALENDAR_ENABLED=true
PIXEL_OPS_GOOGLE_CALENDAR_ICS_URL=https://calendar.google.com/calendar/ical/...
PIXEL_OPS_GOOGLE_CALENDAR_POLL_SECONDS=300
```

GitHub pull requests in the HUD:

```env
PIXEL_OPS_GITHUB_ENABLED=true
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
PIXEL_OPS_GITHUB_REPOS=owner/repo
PIXEL_OPS_GITHUB_POLL_SECONDS=60
PIXEL_OPS_GITHUB_MAX_PRS=4
```

Slack and Discord are interpreted as ambient social weather, not message feeds.
Message bodies are only used for short-lived semantic classification; rendered
events become encounters, mood shifts, particles, NPC density, and meeting
ceremonies.

Slack Socket Mode receiver:

```env
PIXEL_OPS_SLACK_ENABLED=true
PIXEL_OPS_SLACK_APP_TOKEN=xapp-...
PIXEL_OPS_SLACK_BOT_TOKEN=xoxb-...
PIXEL_OPS_SLACK_BOT_USER_ID=U123456
PIXEL_OPS_SLACK_SOCKET_RECONNECT_SECONDS=10
```

Enable Socket Mode in the Slack app, create an app-level token with
`connections:write`, and install the bot with event scopes for mentions,
messages, reactions, and presence-like activity. Socket Mode is the recommended
local setup because GACO opens an outbound WebSocket and does not need a public
IP, tunnel, TLS endpoint, or reverse proxy.

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

Pixel OPs was originally built from a local fork of [`mathoudebine/turing-smart-screen-python`](https://github.com/mathoudebine/turing-smart-screen-python). The upstream project provided the original USB display protocol research and Python driver foundation for Turing Smart Screen style devices. The current repository keeps a minimal adapted USB bulk transport and RGB565 serializer; the full upstream system monitor, theme library, configuration tools, and bundled app are not included.
