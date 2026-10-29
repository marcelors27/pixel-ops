import unittest
from unittest.mock import Mock, patch
import zlib

from PIL import Image
from pixel_ops.outputs.lcd_usb import LcdUsbOutput
from pixel_ops.outputs.lcd_http import encode_lcd_frame


class LcdUsbTests(unittest.TestCase):
    def test_frame_chunks_crc_and_ack_before_deduplication(self):
        output = LcdUsbOutput(min_frame_interval_seconds=0)
        connection = Mock()
        connection.readline.side_effect = [b"PXOPS READY\n"] + [b"PXOPS NEXT\n"] * 107 + [b"PXOPS OK\n"]
        connection.write.side_effect = lambda value: len(value)
        output.connection = connection
        frame = Image.new("RGB", (172, 320), "red")
        output.send(frame)
        writes = [call.args[0] for call in connection.write.call_args_list]
        payload = b"".join(writes[1:])
        self.assertEqual(payload, encode_lcd_frame(frame).payload)
        self.assertEqual(writes[0], f"PXOPS2 {len(payload)} {zlib.crc32(payload):08x}\n".encode())
        self.assertLessEqual(max(map(len, writes[1:])), 1024)
        count = connection.write.call_count
        output.send(frame)
        self.assertEqual(connection.write.call_count, count)

    def test_rejected_frame_is_not_marked_as_delivered(self):
        output = LcdUsbOutput(min_frame_interval_seconds=0)
        output.connection = Mock()
        output.connection.write.side_effect = lambda value: len(value)
        output.connection.readline.side_effect = [b"PXOPS READY\n"] + [b"PXOPS NEXT\n"] * 107 + [b"PXOPS ERROR checksum\n"]
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            output.send(Image.new("RGB", (172, 320)))
        self.assertEqual(output._last_digest, "")

    def test_partial_write_fails(self):
        output = LcdUsbOutput(min_frame_interval_seconds=0)
        output.connection = Mock()
        output.connection.readline.return_value = b"PXOPS READY\n"
        output.connection.write.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "incompleto"):
            output.send(Image.new("RGB", (172, 320)))
        self.assertEqual(output._last_digest, "")

    def test_missing_start_fails(self):
        with self.assertRaisesRegex(RuntimeError, "start"):
            LcdUsbOutput().send(Image.new("RGB", (1, 1)))

    def test_auto_detection_refuses_multiple_boards(self):
        boards = [Mock(vid=0x303A, pid=0x1001, device="/dev/a"), Mock(vid=0x303A, pid=0x1001, device="/dev/b")]
        with patch("serial.tools.list_ports.comports", return_value=boards), patch("serial.Serial") as serial_class:
            with self.assertRaisesRegex(RuntimeError, "vários"):
                LcdUsbOutput().start()
            serial_class.assert_not_called()

    def test_handshake_identifies_board_without_resetting_it(self):
        connection = Mock()
        connection.readline.side_effect = [b"boot message\n", b"PXOPS LCD 172 320 2\n"]
        with patch("serial.Serial", return_value=connection):
            output = LcdUsbOutput("/dev/waveshare")
            output.start()
        self.assertFalse(connection.dtr)
        self.assertFalse(connection.rts)
        connection.write.assert_called_once_with(b"PXOPS?\n")
        output.stop()
        connection.close.assert_called_once()
