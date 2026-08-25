from __future__ import annotations

from unittest import TestCase, mock

from PIL import Image

from pixel_ops.outputs.lcd_http import LCD_FRAME_BYTES, LcdHttpOutput, encode_lcd_frame


class LcdHttpOutputTests(TestCase):
    def test_encodes_rgb565_big_endian(self) -> None:
        image = Image.new("RGB", (2, 1))
        image.putdata([(255, 0, 0), (0, 255, 0)])
        encoded = encode_lcd_frame(image, width=2, height=1)
        self.assertEqual(encoded.payload, b"\xf8\x00\x07\xe0")

    def test_native_frame_has_expected_size(self) -> None:
        encoded = encode_lcd_frame(Image.new("RGB", (172, 320), "blue"))
        self.assertEqual(len(encoded.payload), LCD_FRAME_BYTES)

    def test_config_uses_native_panel_size_when_host_canvas_is_larger(self) -> None:
        output = LcdHttpOutput.from_config(2650, 462, {})
        self.assertEqual((output.width, output.height), (172, 320))

    def test_posts_multipart_frame_and_deduplicates(self) -> None:
        session = mock.Mock()
        session.get.return_value.raise_for_status.return_value = None
        session.post.return_value.raise_for_status.return_value = None
        with mock.patch("pixel_ops.outputs.lcd_http.requests.Session", return_value=session), mock.patch(
            "pixel_ops.outputs.lcd_http.time.monotonic", side_effect=[10.0, 11.0]
        ):
            output = LcdHttpOutput("http://pixelops-lcd.local", token="secret", min_frame_interval_seconds=0)
            output.start()
            frame = Image.new("RGB", (172, 320), "red")
            output.send(frame)
            output.send(frame)
        self.assertEqual(session.post.call_count, 1)
        request = session.post.call_args
        self.assertEqual(request.args[0], "http://pixelops-lcd.local/frame")
        self.assertEqual(request.kwargs["headers"], {"Authorization": "Bearer secret"})
        self.assertEqual(len(request.kwargs["files"]["frame"][1]), LCD_FRAME_BYTES)

    def test_start_wraps_network_failure_for_runtime_retry(self) -> None:
        session = mock.Mock()
        session.get.side_effect = __import__("requests").ConnectionError("offline")
        with mock.patch("pixel_ops.outputs.lcd_http.requests.Session", return_value=session):
            output = LcdHttpOutput("http://pixelops-lcd.local")
            with self.assertRaisesRegex(RuntimeError, "LCD status check failed"):
                output.start()
