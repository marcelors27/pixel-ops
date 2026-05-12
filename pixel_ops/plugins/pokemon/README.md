# Pokemon Plugin

The Pokemon plugin renders a classic handheld RPG-style operations dashboard for a TURZX/Turing/UsbMonitor 3.5" display.

Display communication uses the minimal internal transport in `pixel_ops/hardware/`.

## Local Preview

```bash
python pixel_ops/main.py --plugin pokemon --output preview
```

Output:

```text
pixel_ops/output/preview.png
```

## Local GIF

```bash
python pixel_ops/main.py --plugin pokemon --output gif --seconds 8
```

## Display

```bash
python pixel_ops/main.py --plugin pokemon --output turzx --seconds 30 --fps 12
```

Run continuously:

```bash
python pixel_ops/main.py --plugin pokemon --output turzx --forever --fps 10 --offline
```

Legacy aliases still work:

- `--preview` is equivalent to `--output preview`
- `--gif` is equivalent to `--output gif`
- `--display` is equivalent to `--output turzx`

## Outputs

The core generates `PIL.Image` frames. File and hardware transports are isolated behind the `DisplayOutput.start/send/stop` interface.

```text
core/render -> PIL.Image -> DisplayOutput.send(frame)
```

Current outputs:

- `preview`: saves a local PNG without hardware.
- `gif`: saves a short animated GIF.
- `turzx`: sends frames to TURZX/Turing via USB bulk.

## Config

- People and time zones: `pixel_ops/config/people.yaml`
- Display/FPS/palette: `pixel_ops/config/display.yaml`
- Game loop/scene: `pixel_ops/plugins/pokemon/game.yaml`
- PokeAPI/cache/sprites: `pixel_ops/plugins/pokemon/pokemon.yaml`

## Overworld Scene

The plugin runs `scenes/overworld_scene.py`, split into:

- `game/state_machine.py`: `WALKING -> ENCOUNTER_START -> POKEMON_APPEARS -> ASH_THROWS -> BALL_SHAKE -> CAUGHT -> RESUME_WALKING`
- `game/encounter.py`: random spawn flow for the original 151 Pokemon
- `game/world.py`: simple scrolling/parallax and area switching between town, route, grass, village, and Pokemon Center-like areas
- `game/day_night.py`: palettes based on the primary local time
- `render/hud.py`: compact time zone and next-meeting HUD
- `render/text_box.py`: game-style text box
- `render/tiles.py`: generated tile/prop visual fallbacks

Local validation:

```bash
python pixel_ops/main.py --plugin pokemon --gif --seconds 12 --fps 10 --offline
```

## Pokemon Assets And Cache

Download/cache official PokeAPI metadata plus front and animated sprites for the original 151 Pokemon:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache
```

Limit the cache warmup during development:

```bash
python pixel_ops/main.py --plugin pokemon --warm-cache --pokemon-limit 25
```

Local cache:

```text
pixel_ops/plugins/pokemon/assets/cache/api/
pixel_ops/plugins/pokemon/assets/cache/pokemon/front/
pixel_ops/plugins/pokemon/assets/cache/pokemon/animated/
```

Run without network access:

```bash
python pixel_ops/main.py --plugin pokemon --display --offline
```

Sprite sources:

- Front: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png`
- Animated Gen V: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-v/black-white/animated/{id}.gif`

## Trainer And UI Sprites

The trainer and battle UI sprites used by the Pokemon plugin are already included under:

```text
pixel_ops/plugins/pokemon/assets/sprites/ash/
```

No manual download is required to run the plugin. The shipped `manifest.yaml` points at the bundled sheets.

If you replace the bundled trainer sheet and need to regenerate `ash_overworld.png` plus `manifest.yaml`, use the extractor:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py path/to/player_sprites.png
```

If no trainer sheet exists, the plugin can fall back to generated pixel sprites so preview/display still run. To fail fast instead, set `require_ash_sprite: true` in `pixel_ops/plugins/pokemon/game.yaml`.

## Calendar

Current event sources:

- automatic mock events for development
- local `.ics` file via `--ics path/to/calendar.ics`

Google Calendar API support can be added later in `data_sources/calendar.py` without changing the scene or display backend.

## GitHub

To list open PRs in the HUD and generate review encounters, configure:

```env
PIXEL_OPS_GITHUB_ENABLED=true
PIXEL_OPS_GITHUB_TOKEN=github_pat_...
PIXEL_OPS_GITHUB_REPOS=owner/repo
PIXEL_OPS_GITHUB_POLL_SECONDS=60
PIXEL_OPS_GITHUB_MAX_PRS=4
```

The token only needs read access to the configured repositories.

## Credits

The display protocol layer used by Pixel OPs is adapted from [`mathoudebine/turing-smart-screen-python`](https://github.com/mathoudebine/turing-smart-screen-python), which decoded and implemented support for Turing Smart Screen style devices.
