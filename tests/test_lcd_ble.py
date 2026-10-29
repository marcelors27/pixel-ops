import asyncio
import struct
import unittest
import zlib
from unittest.mock import AsyncMock, Mock

from pixel_ops.outputs.lcd_ble import LcdBleOutput, pack_frame, changed_region, COMMAND, DATA


def unpack(payload):
    return b''.join(payload[i+2:i+4] * int.from_bytes(payload[i:i+2], 'big') for i in range(0, len(payload), 4))


class BleEncodingTests(unittest.TestCase):
    def test_solid_frame_roundtrip_and_compression(self):
        raw = b'\xf8\x00' * (172 * 320)
        kind, packed = pack_frame(raw)
        self.assertEqual(kind, 1)
        self.assertEqual(len(packed), 4)
        self.assertEqual(unpack(packed), raw)

    def test_detailed_frame_uses_raw_without_expansion(self):
        raw = b'\x00\x01\xff\xff' * 50
        self.assertEqual(pack_frame(raw), (0, raw))

    def test_run_count_does_not_overflow(self):
        raw = b'\xab\xcd' * 70000
        kind, packed = pack_frame(raw)
        self.assertEqual(kind, 1)
        self.assertEqual(len(packed), 8)
        self.assertEqual(unpack(packed), raw)

    def test_rejects_incomplete_pixel(self):
        with self.assertRaises(ValueError):
            pack_frame(b'\xff')


class BleDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_negotiated_mtu_and_crc(self):
        output = LcdBleOutput()
        output._acks = asyncio.Queue()
        output._partial_updates = True
        client = Mock(is_connected=True, mtu_size=23)
        output._client = client
        raw = b'\x00\x01\xff\xff' * 26
        received = bytearray()
        async def write(uuid, payload, response):
            self.assertTrue(response)
            if uuid == COMMAND:
                kind, length, crc, x, y, w, h = struct.unpack('>BIIHHHH', payload)
                self.assertEqual((x, y, w, h), (0, 0, 172, 320))
                self.assertEqual((kind, length, crc), (0, len(raw), zlib.crc32(raw)))
                await output._acks.put(b'READY')
            else:
                self.assertEqual(uuid, DATA)
                self.assertLessEqual(len(payload), 20)
                received.extend(payload)
                await output._acks.put(b'OK' if len(received) == len(raw) else b'NEXT')
        client.write_gatt_char = AsyncMock(side_effect=write)
        await output._send(raw)
        self.assertEqual(bytes(received), raw)

    async def test_rejected_header_stops_before_pixels(self):
        output = LcdBleOutput()
        output._acks = asyncio.Queue()
        output._client = Mock(is_connected=True, mtu_size=247)
        async def write(*args, **kwargs):
            await output._acks.put(b'ERROR busy')
        output._client.write_gatt_char = AsyncMock(side_effect=write)
        with self.assertRaisesRegex(RuntimeError, 'busy'):
            await output._send(b'\x00\x00' * 100)
        self.assertEqual(output._client.write_gatt_char.call_count, 1)

    async def test_disconnect_fails_before_writing(self):
        output = LcdBleOutput()
        output._client = Mock(is_connected=False)
        with self.assertRaisesRegex(RuntimeError, 'desligada'):
            await output._send(b'\x00\x00')


class ChangedRegionTests(unittest.TestCase):
    def test_one_pixel_does_not_send_entire_screen(self):
        original = bytes(172 * 320 * 2)
        updated = bytearray(original)
        offset = (100 * 172 + 50) * 2
        updated[offset:offset+2] = b'\xff\xff'
        self.assertEqual(changed_region(original, bytes(updated)), ((50, 100, 1, 1), b'\xff\xff'))

    def test_bounding_rows_include_unchanged_pixels_between_changes(self):
        old = bytes(4 * 3 * 2)
        new = bytearray(old)
        new[2:4] = b'\xff\x00'
        new[20:22] = b'\x00\xff'
        region, data = changed_region(old, bytes(new), 4, 3)
        self.assertEqual(region, (1, 0, 2, 3))
        self.assertEqual(data, bytes(new[2:6] + new[10:14] + new[18:22]))

    def test_initial_frame_is_full_and_identical_frame_is_skipped(self):
        raw = bytes(172 * 320 * 2)
        self.assertEqual(changed_region(b'', raw), ((0, 0, 172, 320), raw))
        self.assertIsNone(changed_region(raw, raw))


class BluetoothLoopLifetimeTests(unittest.TestCase):
    def test_reconnect_and_reload_keep_callback_loop_alive(self):
        from pixel_ops.outputs.lcd_ble import bluetooth_loop
        loop = bluetooth_loop()
        first = LcdBleOutput()
        first._loop = loop
        first._client = Mock()
        first._client.disconnect = AsyncMock()
        first.stop()
        self.assertTrue(loop.is_running())
        self.assertFalse(loop.is_closed())
        # A late native callback must still have a live dispatch target.
        import threading
        called = threading.Event()
        loop.call_soon_threadsafe(called.set)
        self.assertTrue(called.wait(1))
        second = LcdBleOutput()
        second._loop = bluetooth_loop()
        self.assertIs(second._loop, loop)
        second.stop()
        self.assertTrue(loop.is_running())
