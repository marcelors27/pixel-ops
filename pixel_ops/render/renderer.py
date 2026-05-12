from __future__ import annotations

from PIL import Image, ImageDraw


class PixelRenderer:
    def __init__(self, width: int = 320, height: int = 480):
        self.width = width
        self.height = height

    def canvas(self, color: tuple[int, int, int]) -> Image.Image:
        return Image.new("RGB", (self.width, self.height), color)

    @staticmethod
    def draw_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, shadow, ink) -> None:
        x0, y0, x1, y1 = box
        draw.rectangle((x0 + 4, y0 + 4, x1 + 4, y1 + 4), fill=shadow)
        draw.rectangle(box, fill=fill, outline=ink, width=3)
        draw.rectangle((x0 + 5, y0 + 5, x1 - 5, y1 - 5), outline=ink, width=1)

    @staticmethod
    def apply_scanlines(image: Image.Image) -> Image.Image:
        px = image.load()
        for y in range(1, image.height, 3):
            for x in range(image.width):
                r, g, b = px[x, y]
                px[x, y] = (int(r * 0.82), int(g * 0.82), int(b * 0.82))
        return image
