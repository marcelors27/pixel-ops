"""Bluetooth LE frame output for the Waveshare Pixel OPs terminal."""
from __future__ import annotations

import asyncio
import struct
import time
import threading
import zlib

from pixel_ops.outputs.base import DisplayOutput
from pixel_ops.outputs.lcd_http import encode_lcd_frame

SERVICE = "c0de0001-504f-4c43-8000-000000000001"
COMMAND = "c0de0002-504f-4c43-8000-000000000001"
DATA = "c0de0003-504f-4c43-8000-000000000001"
STATUS = "c0de0004-504f-4c43-8000-000000000001"
INFO = "c0de0005-504f-4c43-8000-000000000001"
IDENTITY = b"PXOPS LCD BLE 2 172 320"


# CoreBluetooth may invoke retained callbacks after disconnect. Keep one event
# loop alive for the process lifetime, including reconnects and config reloads.
_ble_loop = None
_ble_loop_lock = threading.Lock()


def bluetooth_loop():
    global _ble_loop
    with _ble_loop_lock:
        if _ble_loop is None:
            loop = asyncio.new_event_loop()
            ready = threading.Event()
            def run():
                asyncio.set_event_loop(loop)
                loop.call_soon(ready.set)
                loop.run_forever()
            threading.Thread(target=run, name="pixel-ops-bluetooth", daemon=True).start()
            ready.wait()
            _ble_loop = loop
        return _ble_loop


def pack_frame(raw: bytes) -> tuple[int, bytes]:
    """Use RGB565 runs when smaller; retain raw pixels for detailed images."""
    if not raw or len(raw) % 2:
        raise ValueError("RGB565 requires complete pixels.")
    runs = bytearray()
    pixel = raw[:2]
    count = 0
    for offset in range(0, len(raw), 2):
        current = raw[offset:offset + 2]
        if current != pixel or count == 65535:
            runs.extend(struct.pack(">H", count) + pixel)
            pixel, count = current, 0
        count += 1
    runs.extend(struct.pack(">H", count) + pixel)
    return (1, bytes(runs)) if len(runs) < len(raw) else (0, raw)


def changed_region(previous: bytes, current: bytes, width: int = 172, height: int = 320):
    """Return native pixel bounds and packed rows for the changed rectangle."""
    if len(current) != width * height * 2:
        raise ValueError("Invalid native frame length.")
    if len(previous) != len(current):
        return (0, 0, width, height), current
    x0, y0, x1, y1 = width, height, -1, -1
    stride = width * 2
    for y in range(height):
        row = y * stride
        if previous[row:row + stride] == current[row:row + stride]:
            continue
        for x in range(width):
            offset = row + x * 2
            if previous[offset:offset + 2] != current[offset:offset + 2]:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 < 0:
        return None
    data = b"".join(current[(y * width + x0) * 2:(y * width + x1 + 1) * 2]
                    for y in range(y0, y1 + 1))
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1), data


class LcdBleOutput(DisplayOutput):
    def __init__(self, address: str = "", *, timeout_seconds: float = 15,
                 min_frame_interval_seconds: float = 1):
        self.address = address
        self.timeout = max(5, float(timeout_seconds))
        self.interval = max(0, float(min_frame_interval_seconds))
        self._loop = None
        self._client = None
        self._acks = None
        self._last_digest = ""
        self._partial_updates = False
        self._last_payload = b""
        self._last_sent_at = 0.0

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict):
        return cls(str(cfg.get("bluetooth_address") or ""),
                   timeout_seconds=cfg.get("timeout_seconds", 15),
                   min_frame_interval_seconds=cfg.get("bluetooth_frame_interval_seconds", 1))

    async def _start(self):
        from bleak import BleakClient, BleakScanner
        if self.address:
            device = await BleakScanner.find_device_by_address(self.address, timeout=self.timeout,
                                                              service_uuids=[SERVICE])
        else:
            devices = await BleakScanner.discover(timeout=self.timeout, service_uuids=[SERVICE], return_adv=True)
            matches = [device for device, adv in devices.values() if SERVICE in [u.lower() for u in adv.service_uuids]]
            if len(matches) != 1:
                raise RuntimeError("Bluetooth: nenhum painel ou vários PixelOps-LCD encontrados. Indique o identificador do painel.")
            device = matches[0]
        if device is None:
            raise RuntimeError("Waveshare não encontrado por Bluetooth.")
        self._client = BleakClient(device, timeout=self.timeout)
        await self._client.connect()
        identity = bytes(await self._client.read_gatt_char(INFO))
        if identity not in (IDENTITY, b"PXOPS LCD BLE 1 172 320"):
            raise RuntimeError("Firmware Bluetooth incompatível com Pixel OPs.")
        self._partial_updates = identity == IDENTITY
        self.address = device.address
        acks = asyncio.Queue(maxsize=8)
        self._acks = acks
        def notified(_characteristic, data):
            if not acks.full():
                acks.put_nowait(bytes(data))
        await self._client.start_notify(STATUS, notified)
        self._last_digest = ""
        self._last_payload = b""

    def start(self):
        self.stop()
        self._loop = bluetooth_loop()
        try:
            self._run(asyncio.wait_for(self._start(), self.timeout * 3))
        except Exception as error:
            self.stop()
            raise RuntimeError(f"Bluetooth connection failed: {error}") from error

    def _run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    async def _expect(self, expected: bytes):
        reply = await asyncio.wait_for(self._acks.get(), timeout=self.timeout)
        if reply != expected:
            raise RuntimeError(f"Bluetooth: {reply.decode('ascii', errors='replace')}; esperado {expected.decode()}.")

    async def _send(self, raw: bytes, region=(0, 0, 172, 320)):
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Ligação Bluetooth desligada.")
        while not self._acks.empty():
            self._acks.get_nowait()
        encoding, payload = pack_frame(raw)
        header = (struct.pack(">BIIHHHH", encoding, len(payload), zlib.crc32(raw), *region)
                  if self._partial_updates else struct.pack(">BII", encoding, len(payload), zlib.crc32(raw)))
        await asyncio.wait_for(self._client.write_gatt_char(COMMAND, header, response=True), self.timeout)
        await self._expect(b"READY")
        chunk_size = min(240, self._client.mtu_size - 3) // 4 * 4
        if chunk_size < 4:
            raise RuntimeError("Bluetooth MTU inválido.")
        for offset in range(0, len(payload), chunk_size):
            chunk = payload[offset:offset + chunk_size]
            await asyncio.wait_for(self._client.write_gatt_char(DATA, chunk, response=True), self.timeout)
            await self._expect(b"OK" if offset + len(chunk) == len(payload) else b"NEXT")

    def send(self, frame):
        if not self._loop or not self._client:
            raise RuntimeError("LcdBleOutput.start() must be called before send().")
        if time.monotonic() - self._last_sent_at < self.interval:
            return
        encoded = encode_lcd_frame(frame)
        if encoded.digest == self._last_digest:
            return
        region, pixels = changed_region(self._last_payload if self._partial_updates else b"", encoded.payload)
        try:
            self._run(asyncio.wait_for(self._send(pixels, region), 180))
        except Exception as error:
            self._last_payload = b""
            self._last_digest = ""
            raise RuntimeError(f"Bluetooth frame delivery failed: {error}") from error
        self._last_payload = encoded.payload
        self._last_digest = encoded.digest
        self._last_sent_at = time.monotonic()

    def stop(self):
        if self._loop:
            try:
                if self._client:
                    self._run(asyncio.wait_for(self._client.disconnect(), self.timeout))
            finally:
                self._loop = self._client = self._acks = None
