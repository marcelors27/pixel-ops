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

The packaged Electron app starts the same local Config Studio server and points it at the bundled Pixel OPs runtime. On Windows, the installer creates Start Menu and desktop shortcuts named `Pixel OPs Config Studio`.

## Build

```bash
npm run build
```

For an installable desktop app:

```bash
npm run app:build
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

## E-ink firmware updates

The **Firmware do e-ink** panel detects compatible ESP32 serial ports and exposes two operations:

- **Compilar** validates and builds the `e213` PlatformIO environment without touching the device.
- **Instalar atualização** builds, uploads through the selected USB port, and streams progress to the UI.

The local backend uses an installed `pio`/`platformio` executable or falls back to `uvx platformio`. Upload ports must come from the server-side USB scan; arbitrary commands and paths are not accepted.

Firmware endpoints:

- `GET /api/firmware/status`: tool availability, detected ports, operation state, result, and recent logs.
- `POST /api/firmware/build`: starts an asynchronous firmware build.
- `POST /api/firmware/upload` with `{ "port": "/dev/cu.usbmodem..." }`: starts an asynchronous USB upload.
