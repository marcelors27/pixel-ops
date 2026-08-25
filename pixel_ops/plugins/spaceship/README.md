# Spaceship game

Spaceship is a persistent ambient voyage for Pixel OPs. The PXS Wayfarer advances only while this game is selected. Pull requests appear as mineral asteroids: discovery adds raw ore, review activity produces samples, approval certifies data fragments, and merge refines alloy.

Run a preview:

```bash
python pixel_ops/main.py --plugin spaceship --output preview
```

Run continuously:

```bash
python pixel_ops/main.py --plugin spaceship --output window --forever
```

## Persistence

The plugin stores profiles, cargo, asteroids, and idempotent event receipts in `pixel_ops/state/pixel_ops.sqlite`. Only active runtime ticks count. Restarting after any length of time restores state without adding offline time or applying a penalty.

## Procedural layout

`game.json` accepts `layout_seed`. Use an integer or a memorable string to reproduce a room layout. Leave it as `null` to generate a random seed once; that value is stored with the ship profile and survives restarts.

```json
{
  "game": {
    "layout_seed": "minha-wayfarer"
  }
}
```

## Assets

PixelLab-generated assets live under `assets/`. `assets/pixellab-manifest.json` records generation IDs, seeds, sizes, and local files. Generation is a development workflow; running the game is fully local and does not require PixelLab credentials or network access.

The mining bay advances once per 60 merged PR asteroids by default. The durable `refined_alloy` total drives both the bay level and the PixelLab-backed HUD progress meter; change `prs_per_bay_tier` in `game.json` to tune the long-term milestone.

Crew movement uses PixelLab-authored walk cycles for all eight isometric directions. Seeded adjacent rooms use a compact 40x20 isometric step so their module walls directly overlap instead of leaving an intermediate span. Only the active shared wall opens: the renderer selects a smooth segment of the actual common wall, uses that same coordinate for the crew route, expands the gap in four sliding steps before the crossing, and closes it afterward. Every other wall remains closed. The enclosing wall faces are partially translucent so crew remains readable behind them, while the floor and furniture stay opaque. The connected room behind remains intact and supplies the visible floor/interior, never treating black space as a passage. No corridor, frame, jamb, portal, or intermediate structure is rendered. Animation frames share one union crop so pose changes cannot pulse the character scale.

The operations officer is a single actor rather than a stationary sprite plus a roaming duplicate. Her destination comes from the current PR asteroid lifecycle: detected work stays on the bridge, sampling goes to the lab, certification goes to cargo, and an unstable build calls her to engineering. She follows the shortest connected-room route, works at the destination, and returns to the bridge; routes can contain rooms and shared-wall doors only, never black space.

Manual crew tasks live in `game.json`. The `operations_officer: working_on_computer` task selects the real PixelLab character state `856bcf8b-addf-4972-b6b7-2ab8a8abd6e9` and its native `typing` animation. The official's eight-direction `walk` animation belongs to the sibling `Idle` state `0f8563d3-df1c-4957-a582-1a6376c92b29`. Both are imported from the PixelLab character bundle, so states and animations remain visible and maintainable in PixelLab.
