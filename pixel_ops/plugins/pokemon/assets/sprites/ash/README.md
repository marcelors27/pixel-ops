# Trainer And UI Sprites

The Pokemon plugin ships with the trainer and battle UI sprites required by the current scene. No manual download is required to run the dashboard.

The active manifest is:

```text
pixel_ops/plugins/pokemon/assets/sprites/ash/manifest.yaml
```

It points at the bundled sheets in this directory, including `ash_overworld.png`.

## Regenerating From A Replacement Sheet

If you replace the bundled trainer sheet, regenerate `ash_overworld.png` and `manifest.yaml` with:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py path/to/player_sprites.png
```

If the frame alignment is off, pass explicit boxes:

```bash
python pixel_ops/plugins/pokemon/tools/extract_ash_from_sheet.py path/to/player_sprites.png \
  --box 6,31,16,20 \
  --box 18,31,16,20 \
  --box 30,31,16,20 \
  --box 42,31,16,20
```

To require a real local spritesheet and fail fast when it is missing, set this in `pixel_ops/plugins/pokemon/game.yaml`:

```yaml
game:
  require_ash_sprite: true
```
