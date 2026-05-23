# Pixel OPs Config Studio

Local React configuration UI for the Pixel OPs runtime.

The Python runtime owns rendering, events, integrations, hardware, and plugin behavior. Config Studio edits the JSON config files that the runtime already loads and hot-reloads.

## Run

```bash
cd config-studio
npm install
npm run dev
```

Use the Vite dev server for the real configuration workflow. The production build is static and does not provide the local write API.

## Build

```bash
npm run build
```

## What It Edits

Core files are always available:

- `pixel_ops/config/display.json`
- `pixel_ops/config/integrations.json`
- `pixel_ops/config/people.json`

Visual plugin files are discovered from `pixel_ops/plugins/*/plugin.py` and loaded only when that plugin is selected. For Pokemon this currently includes:

- `pixel_ops/plugins/pokemon/game.json`
- `pixel_ops/plugins/pokemon/pokemon.json`
- `pixel_ops/plugins/pokemon/companions.json`

Integration sidecars are exposed only when explicitly mapped by the local API. Discord currently uses:

- `pixel_ops/config/discord_people.json`

Secrets are not edited here. Keep tokens and API keys in `.env` and only configure their environment variable names in JSON.

## Local API

The Vite plugin exposes local endpoints:

- `GET /api/config-manifest`: detected core, integration, and visual plugin config metadata.
- `GET /api/config?plugins=pokemon`: selected runtime config payload.
- `PUT /api/config`: writes known JSON config keys back to the repository.
- `GET /api/npc-sprites`: generated Pokemon NPC sprite preview manifest and GIFs.

The API intentionally writes only known config descriptors. It does not accept arbitrary paths.
