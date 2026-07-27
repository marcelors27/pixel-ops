from __future__ import annotations

import base64
import unittest
from unittest import mock

from PIL import Image

from pixel_ops.outputs.eink_http import EINK_FRAME_BYTES, EInkHttpOutput, encode_eink_frame


class EInkHttpOutputTests(unittest.TestCase):
    def test_encoder_packs_black_pixels_msb_first_with_row_padding(self):
        image = Image.new("1", (250, 122), 255)
        image.putpixel((0, 0), 0)
        image.putpixel((7, 0), 0)
        image.putpixel((8, 0), 0)
        image.putpixel((249, 121), 0)

        encoded = encode_eink_frame(image, dither=False, threshold=128)

        self.assertEqual(len(encoded.payload), EINK_FRAME_BYTES)
        self.assertEqual(encoded.payload[0], 0b10000001)
        self.assertEqual(encoded.payload[1], 0b10000000)
        self.assertEqual(encoded.payload[-1], 0b01000000)

    def test_encoder_preserves_colored_accents_as_diagonal_hatching(self):
        image = Image.new("RGB", (250, 122), (80, 120, 200))

        encoded = encode_eink_frame(image, dither=False, threshold=175, accent_pattern=True)

        self.assertEqual(encoded.payload[0], 0b11001100)
        self.assertEqual(encoded.payload[32], 0b10011001)

    def test_encoder_maps_yellow_gauge_accents_to_solid_black(self):
        image = Image.new("RGB", (250, 122), (255, 220, 70))

        encoded = encode_eink_frame(image, dither=False, threshold=175, accent_pattern=True)

        self.assertEqual(encoded.payload[0], 0b11111111)

    def test_encoder_maps_thin_colored_title_strokes_to_solid_black(self):
        image = Image.new("RGB", (250, 122), "white")
        for x in range(8):
            image.putpixel((x, 0), (80, 120, 200))

        encoded = encode_eink_frame(image, dither=False, threshold=175, accent_pattern=True)

        self.assertEqual(encoded.payload[0], 0b11111111)

    def test_start_validates_remote_dimensions_and_send_posts_binary_frame(self):
        session = mock.Mock()
        status = mock.Mock()
        status.json.return_value = {"width": 250, "height": 122}
        frame_response = mock.Mock()
        session.get.return_value = status
        session.post.return_value = frame_response

        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local", token="secret", min_frame_interval_seconds=0)
            output.start()
            output.send(Image.new("RGB", (250, 122), "white"))

        status.raise_for_status.assert_called_once()
        frame_response.raise_for_status.assert_called_once()
        request = session.post.call_args
        self.assertEqual(request.args[0], "http://e213.local/frame")
        self.assertEqual(len(base64.b64decode(request.kwargs["data"])), EINK_FRAME_BYTES)
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Refresh"], "full")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Encoding"], "base64")

    def test_send_skips_identical_frames_and_rate_limits_changes(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session), mock.patch(
            "pixel_ops.outputs.eink_http.time.monotonic", side_effect=[100.0, 101.0, 120.0]
        ):
            output = EInkHttpOutput("http://e213.local", min_frame_interval_seconds=15)
            output.start()
            white = Image.new("RGB", (250, 122), "white")
            black = Image.new("RGB", (250, 122), "black")
            output.send(white)
            output.send(black)
            output.send(black)

        self.assertEqual(session.post.call_count, 2)

    def test_full_refresh_is_periodic(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local", min_frame_interval_seconds=0, full_refresh_every=2)
            output.start()
            output.send(Image.new("RGB", (250, 122), "white"))
            output.send(Image.new("RGB", (250, 122), "black"))
            split = Image.new("RGB", (250, 122), "white")
            split.paste("black", (0, 0, 125, 122))
            output.send(split)

        refreshes = [call.kwargs["headers"]["X-Pixel-Ops-Refresh"] for call in session.post.call_args_list]
        self.assertEqual(refreshes, ["full", "partial", "full"])

    def test_start_rejects_wrong_device_dimensions(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 296, "height": 128}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local")
            with self.assertRaisesRegex(RuntimeError, "296x128"):
                output.start()
        session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
