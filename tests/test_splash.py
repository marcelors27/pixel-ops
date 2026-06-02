from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pixel_ops.render.splash import _contain_resize, render_splash


class SplashTests(unittest.TestCase):
    def test_contain_resize_preserves_entire_image_inside_frame(self):
        image = Image.new("RGBA", (200, 100), (255, 0, 0, 255))

        resized = _contain_resize(image, 100, 100)

        self.assertEqual(resized.size, (100, 50))

    def test_render_splash_centers_contained_logo_without_cropping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo_path = root / "logo.png"
            Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo_path)

            frame = render_splash(
                root,
                {"splash": {"enabled": True, "logo_path": "logo.png", "background": (0, 0, 0)}},
                100,
                100,
            )

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.getpixel((50, 50)), (255, 0, 0))
        self.assertNotEqual(frame.getpixel((50, 10)), (255, 0, 0))
        self.assertNotEqual(frame.getpixel((50, 90)), (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
