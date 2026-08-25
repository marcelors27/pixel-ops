from __future__ import annotations

import base64
import http.client
import unittest
from unittest import mock

import requests
from PIL import Image

from pixel_ops.outputs.eink_http import EINK_FRAME_BYTES, EInkHttpOutput, _PullFrameServer, compose_eink_white_background, encode_eink_frame, find_eink_dirty_region


class EInkHttpOutputTests(unittest.TestCase):
    def test_white_background_preserves_only_configured_layout_regions(self):
        frame = Image.new("RGB", (20, 12), "black")
        composed = compose_eink_white_background(
            frame,
            {"hud": {"x": 4, "y": 3, "width": 6, "height": 5}},
        )

        self.assertEqual(composed.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(composed.getpixel((4, 3)), (0, 0, 0))
        self.assertEqual(composed.getpixel((9, 7)), (0, 0, 0))
        self.assertEqual(composed.getpixel((10, 8)), (255, 255, 255))

    def test_dirty_region_is_smallest_changed_pixel_rectangle(self):
        previous = encode_eink_frame(Image.new("1", (250, 122), 255), dither=False).payload
        current_image = Image.new("1", (250, 122), 255)
        current_image.putpixel((17, 8), 0)
        current_image.putpixel((29, 12), 0)
        current = encode_eink_frame(current_image, dither=False).payload

        region = find_eink_dirty_region(previous, current)

        self.assertIsNotNone(region)
        self.assertEqual((region.x, region.y, region.width, region.height), (17, 8, 13, 5))

    def test_dirty_region_returns_none_for_identical_payloads(self):
        payload = bytes(EINK_FRAME_BYTES)
        self.assertIsNone(find_eink_dirty_region(payload, payload))

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
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Battery-Powered"], "0")

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

    def test_partial_refresh_sends_changed_rectangle(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local", min_frame_interval_seconds=0, full_refresh_every=10)
            output.start()
            frame = Image.new("1", (250, 122), 255)
            output.send(frame)
            frame.putpixel((42, 33), 0)
            output.send(frame)

        headers = session.post.call_args_list[1].kwargs["headers"]
        self.assertEqual(headers["X-Pixel-Ops-Refresh"], "partial")
        self.assertEqual(headers["X-Pixel-Ops-Dirty-X"], "42")
        self.assertEqual(headers["X-Pixel-Ops-Dirty-Y"], "33")
        self.assertEqual(headers["X-Pixel-Ops-Dirty-Width"], "1")
        self.assertEqual(headers["X-Pixel-Ops-Dirty-Height"], "1")

    def test_watchdog_can_force_identical_frame_after_standalone_takeover(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local", min_frame_interval_seconds=0)
            output.start()
            frame = Image.new("RGB", (250, 122), "white")
            output.send(frame)
            output._force_resend.set()
            output.send(frame)

        self.assertEqual(session.post.call_count, 2)

    def test_start_rejects_wrong_device_dimensions(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 296, "height": 128}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local")
            with self.assertRaisesRegex(RuntimeError, "296x128"):
                output.start()
        session.close.assert_called_once()

    def test_start_negotiates_pc_watchdog_with_supported_firmware(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122, "watchdog_protocol": 1}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session), mock.patch.object(
            EInkHttpOutput, "_start_watchdog"
        ) as start_watchdog:
            output = EInkHttpOutput("http://e213.local")
            output.start()

        start_watchdog.assert_called_once_with()

    def test_battery_powered_mode_skips_watchdog_and_marks_frames(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122, "watchdog_protocol": 1}
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session), mock.patch.object(
            EInkHttpOutput, "_start_watchdog"
        ) as start_watchdog:
            output = EInkHttpOutput("http://e213.local", battery_powered=True, min_frame_interval_seconds=0, pull_port=0)
            output.start()
            output.send(Image.new("RGB", (250, 122), "white"))

        start_watchdog.assert_not_called()
        self.assertEqual(session.post.call_args.kwargs["headers"]["X-Pixel-Ops-Battery-Powered"], "1")
        self.assertEqual(session.post.call_args.kwargs["headers"]["X-Pixel-Ops-Battery-Lease-Seconds"], "60")
        self.assertEqual(session.post.call_args.kwargs["headers"]["X-Pixel-Ops-Deep-Sleep-Seconds"], "300")
        output.stop()

    def test_pull_server_returns_frame_then_not_modified(self):
        server = _PullFrameServer(0, "secret", 300)
        frame = encode_eink_frame(Image.new("RGB", (250, 122), "white"), dither=False)
        server.state.publish(frame)
        server.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=2)
            connection.request("GET", "/eink/frame", headers={"Authorization": "Bearer secret"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), frame.payload)
            self.assertEqual(response.getheader("X-Pixel-Ops-Sleep-Seconds"), "300")
            connection.close()

            connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=2)
            connection.request(
                "GET",
                "/eink/frame",
                headers={"Authorization": "Bearer secret", "If-None-Match": f'"{frame.digest}"'},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 304)
            response.read()
            connection.close()
        finally:
            server.stop()

    def test_deep_sleep_device_is_bootstrapped_once_then_pulls_latest_frame(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {
            "width": 250,
            "height": 122,
            "deep_sleep_protocol": 1,
        }
        output = EInkHttpOutput(
            "http://e213.local",
            battery_powered=True,
            min_frame_interval_seconds=0,
            pull_port=0,
        )
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output.start()
            output.send(Image.new("RGB", (250, 122), "white"))
            output.send(Image.new("RGB", (250, 122), "black"))

        self.assertEqual(session.post.call_count, 1)
        expected = encode_eink_frame(Image.new("RGB", (250, 122), "black"), dither=False).payload
        self.assertEqual(output._pull_server.state.frame.payload, expected)
        output.stop()

    def test_battery_start_accepts_sleeping_device(self):
        session = mock.Mock()
        session.get.side_effect = requests.Timeout("device asleep")
        output = EInkHttpOutput("http://e213.local", battery_powered=True, pull_port=0)
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output.start()
        try:
            self.assertTrue(output._pull_capable)
        finally:
            output.stop()

    def test_from_config_applies_watchdog_intervals(self):
        output = EInkHttpOutput.from_config(
            250,
            122,
            {
                "url": "http://e213.local",
                "heartbeat_interval_seconds": 4,
                "heartbeat_lease_seconds": 15,
                "standalone_weather_enabled": True,
                "standalone_latitude": -30.0346,
                "standalone_longitude": -51.2177,
                "standalone_utc_offset_minutes": -180,
                "battery_powered": True,
            },
        )

        self.assertEqual(output.heartbeat_interval_seconds, 4)
        self.assertEqual(output.heartbeat_lease_seconds, 15)
        self.assertTrue(output.standalone_weather_enabled)
        self.assertAlmostEqual(output.standalone_latitude, -30.0346)
        self.assertAlmostEqual(output.standalone_longitude, -51.2177)
        self.assertTrue(output.battery_powered)

    def test_heartbeat_sends_sequence_lease_health_port_and_token(self):
        session = mock.Mock()
        session.post.return_value.json.return_value = {"needs_frame": True}
        health_server = mock.Mock()
        health_server.port = 43210
        output = EInkHttpOutput(
            "http://e213.local",
            token="secret",
            heartbeat_interval_seconds=3,
            heartbeat_lease_seconds=12,
            layout={"battery": {"kind": "eink_battery", "x": 4, "y": 94, "width": 76, "height": 26}},
        )
        output._health_server = health_server

        self.assertTrue(output._send_heartbeat(session))

        request = session.post.call_args
        self.assertEqual(request.args[0], "http://e213.local/heartbeat")
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Sequence"], "1")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Lease-Seconds"], "12")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Health-Port"], "43210")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Weather-Enabled"], "0")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Hud-Battery"], "4,94,76,26")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Hud-Wireless"], "off")
        self.assertEqual(request.kwargs["headers"]["X-Pixel-Ops-Hud-Status"], "off")
        self.assertTrue(output._force_resend.is_set())

    def test_heartbeat_telemetry_is_used_by_next_frame(self):
        session = mock.Mock()
        session.post.return_value.json.return_value = {
            "needs_frame": False,
            "battery_percent": 73,
            "rssi": -58,
            "pc_available": True,
            "mode": "pc",
        }
        output = EInkHttpOutput("http://e213.local")

        self.assertTrue(output._send_heartbeat(session))

        self.assertEqual(output._device_status["battery_percent"], 73)
        self.assertEqual(output._device_status["rssi"], -58)
        self.assertTrue(output._device_status["pc_available"])

    def test_heartbeat_failure_is_recoverable(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout("heartbeat timed out")
        output = EInkHttpOutput("http://e213.local")

        self.assertFalse(output._send_heartbeat(session))

    def test_send_wraps_http_timeout_as_recoverable_runtime_error(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = {"width": 250, "height": 122}
        session.post.side_effect = requests.Timeout("panel refresh timed out")
        with mock.patch("pixel_ops.outputs.eink_http.requests.Session", return_value=session):
            output = EInkHttpOutput("http://e213.local", min_frame_interval_seconds=0)
            output.start()
            with self.assertRaisesRegex(RuntimeError, "frame delivery failed"):
                output.send(Image.new("RGB", (250, 122), "white"))


if __name__ == "__main__":
    unittest.main()
