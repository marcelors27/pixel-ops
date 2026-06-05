from __future__ import annotations

import sys
import time

from PIL import Image

from pixel_ops.hardware.thermalright_usb import (
    THERMALRIGHT_OBSERVED_PID,
    THERMALRIGHT_OBSERVED_VID,
    ThermalrightJpegOptions,
    ThermalrightProtocol,
    ThermalrightUsbTransport,
    build_thermalright_init_command,
    encode_thermalright_jpeg,
)
from pixel_ops.outputs.base import DisplayOutput


class ThermalrightOutput(DisplayOutput):
    """USB output for Thermalright LY LCD devices such as 0416:5408."""

    def __init__(
        self,
        vid: int = THERMALRIGHT_OBSERVED_VID,
        pid: int = THERMALRIGHT_OBSERVED_PID,
        timeout_ms: int = 5000,
        jpeg_quality: int = 85,
        image_width: int = 1920,
        image_height: int = 462,
        min_frame_interval_ms: int = 0,
        packet_delay_ms: int = 0,
        packet_size: int = 4096,
        hard_reset_on_start: bool = True,
        hard_reset_wait_ms: int = 1500,
        handshake_on_first_frame: bool = False,
        require_handshake: bool = True,
        send_start_init: bool = True,
        read_start_ack: bool = True,
        read_frame_ack: bool = True,
        start_retries: int = 0,
        frame_retries: int = 0,
        debug: bool = False,
    ):
        self.vid = vid
        self.pid = pid
        self.timeout_ms = timeout_ms
        self.min_frame_interval_ms = max(0, min_frame_interval_ms)
        self.packet_delay_ms = max(0, packet_delay_ms)
        self.packet_size = max(512, packet_size)
        self.hard_reset_on_start = hard_reset_on_start
        self.hard_reset_wait_ms = max(0, hard_reset_wait_ms)
        self.handshake_on_first_frame = handshake_on_first_frame
        self.require_handshake = require_handshake
        self.send_start_init = send_start_init
        self.read_start_ack = read_start_ack
        self.read_frame_ack = read_frame_ack
        self.start_retries = max(0, start_retries)
        self.frame_retries = max(0, frame_retries)
        self.jpeg_options = ThermalrightJpegOptions(
            width=image_width,
            height=image_height,
            quality=jpeg_quality,
            packet_size=self.packet_size,
            final_packet_size=min(2048, self.packet_size),
            packet_delay_ms=self.packet_delay_ms,
            send_init_command=False,
            read_ack=read_frame_ack,
        )
        self.debug = debug
        self._transport: ThermalrightUsbTransport | None = None
        self._protocol: ThermalrightProtocol | None = None
        self._last_send_at: float | None = None
        self._handshake_done = False

    def start(self) -> None:
        last_error: Exception | None = None
        for attempt in range(self.start_retries + 1):
            try:
                self._start_once()
                return
            except Exception as error:
                last_error = error
                self.stop()
                if attempt < self.start_retries:
                    time.sleep(0.5)
        raise RuntimeError(f"Thermalright output failed to start: {last_error}") from last_error

    def _start_once(self) -> None:
        self._open_transport()
        if self.hard_reset_on_start:
            self._hard_reset_before_handshake()
        self._protocol = ThermalrightProtocol(
            transport=self._transport,
            dry_run=False,
            debug=self.debug,
            max_packet_size=8192,
        )
        if not self.send_start_init:
            return
        self._send_handshake()

    def _open_transport(self) -> None:
        self._transport = ThermalrightUsbTransport(
            vid=self.vid,
            pid=self.pid,
            timeout_ms=self.timeout_ms,
            debug=self.debug,
            max_packet_size=8192,
        )
        self._transport.open()

    def _hard_reset_before_handshake(self) -> None:
        if self._transport is None:
            return
        self._transport.reset()
        self._transport.close()
        self._transport = None
        if self.hard_reset_wait_ms > 0:
            time.sleep(self.hard_reset_wait_ms / 1000)
        self._open_transport()

    def send(self, frame: Image.Image) -> None:
        if self._protocol is None:
            raise RuntimeError("ThermalrightOutput.start() must be called before send().")
        last_error: Exception | None = None
        for attempt in range(self.frame_retries + 1):
            try:
                self._send_once(frame)
                return
            except Exception as error:
                last_error = error
                if attempt >= self.frame_retries:
                    break
                print(f"Thermalright frame send failed; reconnecting and retrying: {error}", file=sys.stderr)
                self._recover_after_send_failure()
        raise RuntimeError(f"Thermalright frame send failed: {last_error}") from last_error

    def _send_once(self, frame: Image.Image) -> None:
        try:
            self._pace_frame()
            self._ensure_handshake()
            jpeg_bytes = encode_thermalright_jpeg(frame, self.jpeg_options)
            self._protocol.send_jpeg(jpeg_bytes, self.jpeg_options)
            self._last_send_at = time.perf_counter()
        except Exception as error:
            raise RuntimeError(str(error)) from error

    def _recover_after_send_failure(self) -> None:
        if self._transport is not None:
            try:
                self._transport.reset()
            except Exception as error:
                if self.debug:
                    print(f"Thermalright reset after send failure ignored: {error}", file=sys.stderr)
        self.stop()
        self.start()

    def _ensure_handshake(self) -> None:
        if not self.handshake_on_first_frame or self._handshake_done:
            return
        try:
            self._send_handshake()
        except Exception as error:
            if self.require_handshake:
                raise
            print(f"Thermalright handshake failed; continuing without handshake: {error}", file=sys.stderr)
            if "init write failed" in str(error) and self._transport is not None:
                self._transport.reset()
                self.stop()
                self.start()
            self._handshake_done = True

    def _send_handshake(self) -> None:
        if self._protocol is None:
            raise RuntimeError("ThermalrightOutput.start() must be called before handshake.")
        try:
            self._protocol.send_raw(build_thermalright_init_command(), dry_run=False)
        except Exception as error:
            raise RuntimeError(f"Thermalright init write failed: {error}") from error
        if self.read_start_ack:
            try:
                response = self._protocol.read_status(512)
            except Exception as error:
                raise RuntimeError(f"Thermalright init ACK read failed: {error}") from error
            if not response or len(response) < 9 or response[0] != 0x03 or response[1] != 0xFF or response[8] != 0x01:
                preview = bytes(response[:16]).hex(" ") if response else ""
                raise RuntimeError(f"Thermalright init ACK invalid: len={len(response) if response else 0} preview={preview}")
        self._handshake_done = True

    def _pace_frame(self) -> None:
        if self.min_frame_interval_ms <= 0 or self._last_send_at is None:
            return
        elapsed = time.perf_counter() - self._last_send_at
        remaining = self.min_frame_interval_ms / 1000 - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._protocol = None
        self._last_send_at = None
        self._handshake_done = False
