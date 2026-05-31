from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from pixel_ops.hardware.thermalright_usb import (
    FrameBufferOptions,
    POSSIBLE_MAGIC_HEADER,
    ReplayOptions,
    ThermalrightDeviceInfo,
    ThermalrightJpegOptions,
    ThermalrightProtocol,
    UsbEndpointInfo,
    UsbInterfaceInfo,
    build_thermalright_init_command,
    build_thermalright_jpeg_packets,
    inspect_packet,
    load_replay_file,
    parse_image_chunk_header,
    replay_packets,
    split_frame_chunks,
)
from pixel_ops.outputs.thermalright import ThermalrightOutput


class ThermalrightUsbTests(unittest.TestCase):
    def test_device_info_detects_default_bulk_endpoints(self):
        info = ThermalrightDeviceInfo(
            vid=0x1234,
            pid=0x5678,
            interfaces=[
                UsbInterfaceInfo(
                    number=0,
                    alternate_setting=0,
                    endpoints=[
                        UsbEndpointInfo(0x09, "out", "bulk"),
                        UsbEndpointInfo(0x81, "in", "bulk"),
                    ],
                )
            ],
        )

        self.assertTrue(info.has_default_endpoints)

    def test_packet_inspection_marks_candidate_header(self):
        result = inspect_packet(POSSIBLE_MAGIC_HEADER + bytes([0x17, 0x00]))

        self.assertEqual(result["length"], 6)
        self.assertTrue(result["startsWithKnownHeader"])
        self.assertEqual(result["knownHeaderOffset"], 0)
        self.assertEqual(result["possibleOpcode"], 0x17)
        self.assertIn("ff0caa02", result["rawHexPreview"])

    def test_packet_inspection_reports_candidate_header_offset(self):
        result = inspect_packet(bytes([0x01]) + POSSIBLE_MAGIC_HEADER + bytes([0x00]))

        self.assertFalse(result["startsWithKnownHeader"])
        self.assertEqual(result["knownHeaderOffset"], 1)

    def test_packet_inspection_decodes_observed_image_chunk_header(self):
        packet = bytes.fromhex("01ff2cac0200f0010162010800000000ffd8")

        chunk = parse_image_chunk_header(packet)
        result = inspect_packet(packet)

        self.assertIsNotNone(chunk)
        assert chunk is not None
        self.assertEqual(chunk.declared_size, 175148)
        self.assertEqual(chunk.chunk_payload_length, 496)
        self.assertEqual(chunk.total_chunks, 354)
        self.assertEqual(chunk.mode, 1)
        self.assertEqual(chunk.chunk_index, 8)
        self.assertEqual(result["thermalrightImageChunk"]["dataLength"], 2)

    def test_jpeg_packet_builder_matches_observed_header_shape(self):
        jpeg = b"\xff\xd8" + (b"a" * 494) + b"bb" + b"\xff\xd9"

        packets = build_thermalright_jpeg_packets(jpeg, ThermalrightJpegOptions())

        self.assertEqual(len(packets), 1)
        self.assertEqual(len(packets[0]), 2048)
        first = parse_image_chunk_header(packets[0])
        second = parse_image_chunk_header(packets[0][512:])
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.declared_size, len(jpeg))
        self.assertEqual(first.chunk_payload_length, 496)
        self.assertEqual(first.total_chunks, 2)
        self.assertEqual(first.chunk_index, 0)
        self.assertEqual(second.chunk_payload_length, 4)
        self.assertEqual(second.chunk_index, 1)

    def test_init_command_matches_observed_prefix(self):
        command = build_thermalright_init_command()

        self.assertEqual(len(command), 2048)
        self.assertEqual(command[:9], bytes.fromhex("02ff00000000000001"))

    def test_thermalright_output_handshakes_on_start_and_sends_frame_by_default(self):
        protocol = mock.Mock()
        protocol.read_status.return_value = bytes.fromhex("03ff00000000000001") + bytes(503)
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ), mock.patch("pixel_ops.outputs.thermalright.time.sleep"):
            output = ThermalrightOutput()
            output.start()
            output.send(Image.new("RGB", (8, 8), (255, 0, 0)))
            output.stop()

        self.assertEqual(transport.open.call_count, 2)
        transport.reset.assert_called_once()
        protocol.send_raw.assert_called_once()
        protocol.read_status.assert_called_once_with(512)
        protocol.send_jpeg.assert_called_once()
        sent_options = protocol.send_jpeg.call_args.args[1]
        self.assertTrue(sent_options.read_ack)
        self.assertEqual(sent_options.packet_delay_ms, 0)
        self.assertEqual(sent_options.packet_size, 4096)
        self.assertEqual(transport.close.call_count, 2)

    def test_thermalright_output_can_validate_start_ack(self):
        protocol = mock.Mock()
        protocol.read_status.return_value = bytes.fromhex("03ff00000000000001") + bytes(503)
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ):
            output = ThermalrightOutput(send_start_init=True, read_start_ack=True, hard_reset_on_start=False)
            output.start()

        protocol.send_raw.assert_called_once()
        protocol.read_status.assert_called_once_with(512)

    def test_thermalright_output_can_continue_when_optional_handshake_times_out(self):
        protocol = mock.Mock()
        protocol.send_raw.side_effect = OSError("Operation timed out")
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ):
            output = ThermalrightOutput(
                send_start_init=False,
                handshake_on_first_frame=True,
                require_handshake=False,
                hard_reset_on_start=False,
            )
            output.start()
            output.send(Image.new("RGB", (8, 8), (255, 0, 0)))

        protocol.send_raw.assert_called_once()
        protocol.send_jpeg.assert_called_once()
        self.assertEqual(transport.open.call_count, 2)
        transport.reset.assert_called_once()

    def test_thermalright_output_can_require_handshake(self):
        protocol = mock.Mock()
        protocol.send_raw.side_effect = OSError("Operation timed out")
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ):
            output = ThermalrightOutput(
                send_start_init=False,
                handshake_on_first_frame=True,
                require_handshake=True,
                hard_reset_on_start=False,
            )
            output.start()
            with self.assertRaisesRegex(RuntimeError, "init write failed"):
                output.send(Image.new("RGB", (8, 8), (255, 0, 0)))

    def test_thermalright_output_can_enable_frame_ack_and_pacing(self):
        output = ThermalrightOutput(min_frame_interval_ms=250, packet_delay_ms=7, packet_size=4096, read_frame_ack=True)

        self.assertEqual(output.min_frame_interval_ms, 250)
        self.assertEqual(output.jpeg_options.packet_delay_ms, 7)
        self.assertEqual(output.jpeg_options.packet_size, 4096)
        self.assertTrue(output.jpeg_options.read_ack)

    def test_thermalright_output_retries_start_once(self):
        protocol = mock.Mock()
        protocol.send_raw.side_effect = [OSError("Operation timed out"), None]
        protocol.read_status.return_value = bytes.fromhex("03ff00000000000001") + bytes(503)
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ), mock.patch("pixel_ops.outputs.thermalright.time.sleep"):
            output = ThermalrightOutput(send_start_init=True, start_retries=1, hard_reset_on_start=False)
            output.start()

        self.assertEqual(transport.open.call_count, 2)
        self.assertEqual(protocol.send_raw.call_count, 2)
        transport.close.assert_called_once()

    def test_thermalright_output_reports_send_failure_without_reconnect_by_default(self):
        protocol = mock.Mock()
        protocol.read_status.return_value = bytes.fromhex("03ff00000000000001") + bytes(503)
        protocol.send_jpeg.side_effect = OSError("Operation timed out")
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ):
            output = ThermalrightOutput(hard_reset_on_start=False)
            output.start()
            with self.assertRaisesRegex(RuntimeError, "Operation timed out"):
                output.send(Image.new("RGB", (8, 8), (255, 0, 0)))

        self.assertEqual(protocol.send_jpeg.call_count, 1)
        self.assertEqual(protocol.send_raw.call_count, 1)
        self.assertEqual(protocol.read_status.call_count, 1)
        transport.open.assert_called_once()
        transport.reset.assert_not_called()

    def test_thermalright_output_can_disable_hard_reset_on_start(self):
        protocol = mock.Mock()
        protocol.read_status.return_value = bytes.fromhex("03ff00000000000001") + bytes(503)
        transport = mock.Mock()

        with mock.patch("pixel_ops.outputs.thermalright.ThermalrightUsbTransport", return_value=transport), mock.patch(
            "pixel_ops.outputs.thermalright.ThermalrightProtocol", return_value=protocol
        ):
            output = ThermalrightOutput(hard_reset_on_start=False)
            output.start()

        transport.open.assert_called_once()
        transport.reset.assert_not_called()
        protocol.send_raw.assert_called_once()

    def test_thermalright_protocol_reports_packet_write_index(self):
        transport = mock.Mock()
        transport.write_bulk.side_effect = [4096, OSError("Operation timed out")]
        protocol = ThermalrightProtocol(transport=transport, dry_run=False, max_packet_size=8192)
        jpeg = b"\xff\xd8" + (b"a" * 5000) + b"\xff\xd9"

        with self.assertRaisesRegex(RuntimeError, r"packet write failed at 2/2"):
            protocol.send_jpeg(
                jpeg,
                ThermalrightJpegOptions(send_init_command=False, read_ack=False, packet_size=4096),
            )

    def test_chunk_splitting_applies_optional_header_and_limits(self):
        chunks = split_frame_chunks(
            b"abcdef",
            FrameBufferOptions(chunk_size=2, header_prefix=b"H", footer=b"F", max_packet_size=4),
        )

        self.assertEqual(chunks, [b"HabF", b"HcdF", b"HefF"])
        with self.assertRaises(ValueError):
            split_frame_chunks(b"abc", FrameBufferOptions(chunk_size=2, header_prefix=b"HH", max_packet_size=3))

    def test_replay_file_parses_json_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "endpoint": "0x09",
                            "direction": "out",
                            "transferType": "bulk",
                            "payloadHex": "ff0caa02",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            packets = load_replay_file(path)

        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].endpoint, 0x09)
        self.assertEqual(packets[0].payload, POSSIBLE_MAGIC_HEADER)

    def test_replay_file_parses_usbpcap_bulk_out_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.pcap"
            frame = _usbpcap_frame(endpoint=0x09, transfer_type=3, payload=bytes([0x01]) + POSSIBLE_MAGIC_HEADER)
            path.write_bytes(_pcap_file(frame))

            packets = load_replay_file(path)

        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].endpoint, 0x09)
        self.assertEqual(packets[0].payload, bytes([0x01]) + POSSIBLE_MAGIC_HEADER)

    def test_dry_run_replay_does_not_require_transport(self):
        packets = [
            load_replay_file_from_object(
                {
                    "endpoint": "0x09",
                    "direction": "out",
                    "transferType": "bulk",
                    "payloadHex": "010203",
                }
            )
        ]
        protocol = ThermalrightProtocol(dry_run=True)

        sent = replay_packets(protocol, packets, ReplayOptions(dry_run=True))

        self.assertEqual(sent, 3)

    def test_safety_limit_rejects_large_dry_run_packet(self):
        protocol = ThermalrightProtocol(dry_run=True, max_packet_size=4)

        with self.assertRaises(ValueError):
            protocol.send_raw(b"12345")


def load_replay_file_from_object(item):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "capture.json"
        path.write_text(json.dumps([item]), encoding="utf-8")
        return load_replay_file(path)[0]


def _pcap_file(frame: bytes) -> bytes:
    header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 249)
    packet = struct.pack("<IIII", 1, 0, len(frame), len(frame)) + frame
    return header + packet


def _usbpcap_frame(endpoint: int, transfer_type: int, payload: bytes) -> bytes:
    header_len = 27
    header = bytearray(header_len)
    struct.pack_into("<H", header, 0, header_len)
    header[21] = endpoint
    header[22] = transfer_type
    struct.pack_into("<I", header, 23, len(payload))
    return bytes(header) + payload


if __name__ == "__main__":
    unittest.main()
