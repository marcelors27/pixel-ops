from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from pixel_ops.plugins.pokemon.render.sprites import NpcSpriteSet


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "pixel_ops/cache/config_studio/npc_sprites"
    output_dir.mkdir(parents=True, exist_ok=True)
    sprites = NpcSpriteSet(ROOT / "pixel_ops/plugins/pokemon/assets/sprites/ash", scene_fps=8, scale=2)
    directions = ("idle_down", "idle_right", "idle_up", "idle_left")
    for variant in range(sprites.count):
        frames = []
        for direction in directions:
            frame = sprites.frame(variant, direction, 0)
            canvas = Image.new("RGBA", (40, 48), (0, 0, 0, 0))
            canvas.alpha_composite(frame, ((canvas.width - frame.width) // 2, 3))
            frames.append(canvas)
        frames[0].save(
            output_dir / f"{variant}.gif",
            save_all=True,
            append_images=frames[1:],
            duration=1500,
            loop=0,
            disposal=2,
            transparency=0,
        )
    (output_dir / "manifest.json").write_text(
        json.dumps({"count": sprites.count, "variants": list(range(sprites.count))}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
