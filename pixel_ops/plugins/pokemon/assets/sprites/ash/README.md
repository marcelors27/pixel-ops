# Ash sprites

Place Ash/trainer spritesheets here. The app does not vendor third-party rips.

Recommended sources to inspect manually:

- The Spriters Resource > Game Boy Advance > Pokemon FireRed / LeafGreen > Player Sprites
- The Spriters Resource > Game Boy Advance > Pokemon Emerald

Current target source:

```text
https://www.spriters-resource.com/game_boy_advance/pokemonfireredleafgreen/asset/52432/
```

The Spriters Resource exposes this as an asset page/download, not as a stable
JSON API like PokeAPI. Download the PNG from that page and save it locally as:

```text
pixel_ops/plugins/pokemon/assets/sprites/ash/ash_overworld.png
```

Use an overworld trainer/Ash sheet, not a battle portrait. The scene expects a
small top-down/side overworld character, usually around `16x20` or `16x24`
pixels before scaling.

Default convention without a manifest:

```text
walk_right.png
idle.png
catch.png
```

Each PNG may be a horizontal strip of frames. If the strip width is divisible
by its height, frames are sliced as `height x height`. For non-square GBA
overworld frames, use `manifest.yaml`.

Manifest example:

```yaml
scale: 3
frame_width: 16
frame_height: 20
spacing: 0
margin: 0
transparent_color: [0, 255, 0]
animations:
  walk_right:
    file: ash_overworld.png
    frames: [0, 1, 2, 3]
    fps: 6
  idle:
    file: ash_overworld.png
    frames: [0]
    fps: 1
  catch:
    file: ash_overworld.png
    frames: [4, 5, 6]
    fps: 8
```

The frame index order is left-to-right, top-to-bottom.

If the downloaded sheet is not a regular grid, use explicit boxes:

```yaml
animations:
  walk_right:
    file: ash_overworld.png
    boxes:
      - [0, 0, 16, 20]
      - [16, 0, 16, 20]
      - [32, 0, 16, 20]
      - [48, 0, 16, 20]
    fps: 6
```

You can also generate `ash_overworld.png` and `manifest.yaml` from the full
sheet with:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py caminho/para/player_sprites.png
```

The default crop targets the first character row. If the frame alignment is off,
pass explicit boxes:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py caminho/para/player_sprites.png \
  --box 6,31,16,20 \
  --box 18,31,16,20 \
  --box 30,31,16,20 \
  --box 42,31,16,20
```

To require a real local spritesheet and fail fast when it is missing, set this
in `pixel_ops/plugins/pokemon/game.yaml`:

```yaml
game:
  require_ash_sprite: true
```
