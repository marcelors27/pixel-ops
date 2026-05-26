from __future__ import annotations

import unittest

from pixel_ops.plugins.pokemon.render.text_box import text_box_visible_lines


class TextBoxTests(unittest.TestCase):
    def test_visible_lines_follow_configured_box_height(self):
        self.assertEqual(text_box_visible_lines((0, 0, 320, 92), ""), 3)
        self.assertEqual(text_box_visible_lines((0, 0, 480, 128), ""), 5)
        self.assertEqual(text_box_visible_lines((0, 0, 320, 48), ""), 1)

    def test_visible_lines_respect_custom_text_origin(self):
        self.assertEqual(text_box_visible_lines((0, 100, 320, 200), "", text_y=120), 3)
        self.assertEqual(text_box_visible_lines((0, 100, 320, 200), "", text_y=106), 4)


if __name__ == "__main__":
    unittest.main()
