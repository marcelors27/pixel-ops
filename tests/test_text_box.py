from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pixel_ops.plugins.pokemon.render.text_box import text_box_visible_lines
from pixel_ops.render.fonts import font, font_scale_for_canvas


class TextBoxTests(unittest.TestCase):
    def test_visible_lines_follow_configured_box_height(self):
        self.assertEqual(text_box_visible_lines((0, 0, 320, 92), ""), 3)
        self.assertEqual(text_box_visible_lines((0, 0, 480, 128), ""), 5)
        self.assertEqual(text_box_visible_lines((0, 0, 320, 48), ""), 1)

    def test_visible_lines_respect_custom_text_origin(self):
        self.assertEqual(text_box_visible_lines((0, 100, 320, 200), "", text_y=120), 3)
        self.assertEqual(text_box_visible_lines((0, 100, 320, 200), "", text_y=106), 4)

    def test_fonts_scale_for_large_canvas_context(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        normal_width = draw.textbbox((0, 0), "Timezone", font=font(10))[2]

        with font_scale_for_canvas(1920, 462):
            large_width = draw.textbbox((0, 0), "Timezone", font=font(10))[2]

        self.assertGreater(large_width, normal_width)


if __name__ == "__main__":
    unittest.main()
