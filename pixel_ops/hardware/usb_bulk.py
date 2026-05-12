from __future__ import annotations

import time
from enum import IntEnum

import usb.core
import usb.util
from PIL import Image

from pixel_ops.hardware.rgb565 import image_to_rgb565

VENDOR_ID = 0x1A86
PRODUCT_ID = 0x5722
CDC_DATA_INTERFACE = 1
OUT_ENDPOINT = 0x03


class Command(IntEnum):
    SET_ORIENTATION = 121
    DISPLAY_BITMAP = 197


class UsbBulkRevA:
    """Minimal USB bulk transport for TURZX/Turing Rev. A style displays."""

    def __init__(
        self,
        width: int = 320,
        height: int = 480,
        vid: int = VENDOR_ID,
        pid: int = PRODUCT_ID,
        timeout_ms: int = 5000,
    ):
        self.width = width
        self.height = height
        self.timeout_ms = timeout_ms
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        if self.dev is None:
            raise RuntimeError(f"USB device {vid:04x}:{pid:04x} not found")

        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            pass

        try:
            if self.dev.is_kernel_driver_active(CDC_DATA_INTERFACE):
                self.dev.detach_kernel_driver(CDC_DATA_INTERFACE)
        except (NotImplementedError, usb.core.USBError):
            pass

        usb.util.claim_interface(self.dev, CDC_DATA_INTERFACE)
        self.endpoint = self._find_out_endpoint()
        self._portrait_ready = False

    def close(self) -> None:
        try:
            usb.util.release_interface(self.dev, CDC_DATA_INTERFACE)
        except usb.core.USBError:
            pass
        usb.util.dispose_resources(self.dev)

    def set_orientation_portrait(self) -> None:
        byte_buffer = bytearray(16)
        byte_buffer[5] = Command.SET_ORIENTATION
        byte_buffer[6] = 100
        byte_buffer[7] = self.width >> 8
        byte_buffer[8] = self.width & 255
        byte_buffer[9] = self.height >> 8
        byte_buffer[10] = self.height & 255
        self.endpoint.write(bytes(byte_buffer), timeout=self.timeout_ms)

    def prepare_portrait_fullscreen(self) -> None:
        if self._portrait_ready:
            return
        self.set_orientation_portrait()
        time.sleep(0.05)
        self._portrait_ready = True

    def display_image(
        self,
        image: Image.Image,
        chunk_size: int = 307200,
        delay_ms: int = 0,
        prepare_each_frame: bool = False,
    ) -> None:
        image = image.convert("RGB")
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)

        payload = image_to_rgb565(image, "little")
        self.display_rgb565_payload(
            payload,
            chunk_size=chunk_size,
            delay_ms=delay_ms,
            prepare_each_frame=prepare_each_frame,
        )

    def display_rgb565_payload(
        self,
        payload: bytes,
        chunk_size: int = 307200,
        delay_ms: int = 0,
        prepare_each_frame: bool = False,
    ) -> None:
        if prepare_each_frame:
            self.set_orientation_portrait()
            time.sleep(0.05)
        else:
            self.prepare_portrait_fullscreen()

        self._send_command(Command.DISPLAY_BITMAP, 0, 0, self.width - 1, self.height - 1)
        for offset in range(0, len(payload), chunk_size):
            self.endpoint.write(payload[offset:offset + chunk_size], timeout=self.timeout_ms)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)

    def _send_command(self, cmd: int, x: int, y: int, ex: int, ey: int) -> None:
        byte_buffer = bytearray(6)
        byte_buffer[0] = x >> 2
        byte_buffer[1] = ((x & 3) << 6) + (y >> 4)
        byte_buffer[2] = ((y & 15) << 4) + (ex >> 6)
        byte_buffer[3] = ((ex & 63) << 2) + (ey >> 8)
        byte_buffer[4] = ey & 255
        byte_buffer[5] = cmd
        self.endpoint.write(bytes(byte_buffer), timeout=self.timeout_ms)

    def _find_out_endpoint(self):
        cfg = self.dev.get_active_configuration()
        interface = usb.util.find_descriptor(cfg, bInterfaceNumber=CDC_DATA_INTERFACE)
        if interface is None:
            raise RuntimeError(f"USB interface {CDC_DATA_INTERFACE} not found")

        endpoint = usb.util.find_descriptor(
            interface,
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
            and ep.bEndpointAddress == OUT_ENDPOINT,
        )
        if endpoint is None:
            raise RuntimeError(f"OUT endpoint 0x{OUT_ENDPOINT:02x} not found")
        return endpoint
