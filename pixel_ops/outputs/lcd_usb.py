"""USB CDC transport for the Waveshare RGB565 output terminal."""
from __future__ import annotations

import time
import zlib

from pixel_ops.outputs.base import DisplayOutput
from pixel_ops.outputs.lcd_http import encode_lcd_frame


class LcdUsbOutput(DisplayOutput):
    def __init__(self, port: str = "", *, timeout_seconds: float = 10,
                 min_frame_interval_seconds: float = 0.1):
        self.port = port
        self.timeout = max(1, float(timeout_seconds))
        self.interval = max(0, float(min_frame_interval_seconds))
        self.connection = None
        self._last_digest = ""
        self._last_sent_at = 0.0

    @classmethod
    def from_config(cls, width: int, height: int, cfg: dict):
        return cls(str(cfg.get("port") or ""),
                   timeout_seconds=cfg.get("timeout_seconds", 10),
                   min_frame_interval_seconds=cfg.get("min_frame_interval_seconds", 0.1))

    def _expect(self, expected: bytes):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            line = self.connection.readline().strip()
            if line == expected:
                return
            if line.startswith(b"PXOPS ERROR"):
                raise RuntimeError(line.decode("ascii", errors="replace"))
        raise RuntimeError("Waveshare USB não respondeu. Instale o firmware com suporte USB e verifique a porta.")

    def start(self):
        import serial
        from serial.tools import list_ports

        port = self.port
        if not port:
            candidates = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x303A, 0x1001)]
            if len(candidates) != 1:
                raise RuntimeError("Selecione a porta USB do Waveshare: nenhum dispositivo ou vários ESP32 detectados.")
            port = candidates[0]
        try:
            self.connection = serial.Serial(port=None, baudrate=115200, timeout=0.25, write_timeout=self.timeout)
            self.connection.dtr = False
            self.connection.rts = False
            self.connection.port = port
            self.connection.open()
            self.connection.reset_input_buffer()
            self.connection.write(b"PXOPS?\n")
            self._expect(b"PXOPS LCD 172 320 2")
            self._last_digest = ""
        except Exception:
            self.stop()
            raise

    def send(self, frame):
        if self.connection is None:
            raise RuntimeError("LcdUsbOutput.start() must be called before send().")
        if time.monotonic() - self._last_sent_at < self.interval:
            return
        encoded = encode_lcd_frame(frame)
        if encoded.digest == self._last_digest:
            return
        checksum = zlib.crc32(encoded.payload)
        self.connection.write(f"PXOPS2 {len(encoded.payload)} {checksum:08x}\n".encode("ascii"))
        self._expect(b"PXOPS READY")
        for offset in range(0, len(encoded.payload), 1024):
            chunk = encoded.payload[offset:offset + 1024]
            if self.connection.write(chunk) != len(chunk):
                raise RuntimeError("Envio USB incompleto; reinicie a ligação.")
            self._expect(b"PXOPS OK" if offset + len(chunk) == len(encoded.payload) else b"PXOPS NEXT")
        self._last_digest = encoded.digest
        self._last_sent_at = time.monotonic()

    def stop(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
