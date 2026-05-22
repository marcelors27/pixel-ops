# Pixel OPs Config Studio

Local configuration UI for the Pixel OPs runtime.

This folder is intentionally separate from `pixel_ops/`: the Python runtime keeps owning rendering,
events, integrations, and plugin behavior, while this app edits the JSON config files that the
runtime already knows how to load and hot-reload.

## Files Edited

- `pixel_ops/config/display.json`
- `pixel_ops/config/integrations.json`
- `pixel_ops/config/people.json`
- `pixel_ops/plugins/pokemon/game.json`
- `pixel_ops/plugins/pokemon/pokemon.json`

Secrets are not edited here. Keep tokens and API keys in `.env` and only configure the corresponding
environment variable names in this studio.

`display.json` also owns the local runtime target now: output type, equipment preset, window scale,
run duration, forever mode, FPS, resolution, and the screen layout boxes used by the HUD/game render.

## Run

```bash
cd config-studio
npm install
npm run dev
```

The Vite dev server exposes a local-only `/api/config` endpoint that reads and writes the JSON files
above from the repository root.

## Build

```bash
npm run build
```

The production build is a static UI. Editing JSON files requires the Vite dev server plugin, so use
`npm run dev` for the actual local configuration workflow.
