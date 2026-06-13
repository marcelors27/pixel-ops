from __future__ import annotations

import json
import struct
import sys
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    import usb.core
    import usb.util
except ImportError:  # pragma: no cover - exercised only on systems without PyUSB.
    usb = None  # type: ignore[assignment]


THERMALRIGHT_DEFAULT_OUT_ENDPOINT = 0x09
THERMALRIGHT_DEFAULT_IN_ENDPOINT = 0x81
THERMALRIGHT_OBSERVED_VID = 0x0416
THERMALRIGHT_OBSERVED_PID = 0x5408
POSSIBLE_MAGIC_HEADER = bytes([0xFF, 0x0C, 0xAA, 0x02])
DEFAULT_MAX_PACKET_SIZE = 8192
DEFAULT_MAX_FRAME_SIZE = 8 * 1024 * 1024
THERMALRIGHT_IMAGE_WIDTH = 1920
THERMALRIGHT_IMAGE_HEIGHT = 462
THERMALRIGHT_IMAGE_METADATA_WIDTH = 496
THERMALRIGHT_IMAGE_CHUNK_DATA_SIZE = 4080
THERMALRIGHT_IMAGE_PACKET_SIZE = 4096
THERMALRIGHT_IMAGE_FINAL_PACKET_SIZE = 2048


@dataclass(frozen=True)
class UsbEndpointInfo:
    address: int
    direction: str
    transfer_type: str
    max_packet_size: int | None = None


@dataclass(frozen=True)
class UsbInterfaceInfo:
    number: int
    alternate_setting: int
    interface_class: int | None = None
    interface_subclass: int | None = None
    interface_protocol: int | None = None
    endpoints: list[UsbEndpointInfo] = field(default_factory=list)


@dataclass(frozen=True)
class ThermalrightDeviceInfo:
    vid: int
    pid: int
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    bus: int | None = None
    address: int | None = None
    interfaces: list[UsbInterfaceInfo] = field(default_factory=list)
    candidate_reasons: tuple[str, ...] = ()

    @property
    def has_default_endpoints(self) -> bool:
        endpoints = {endpoint.address for interface in self.interfaces for endpoint in interface.endpoints}
        return THERMALRIGHT_DEFAULT_OUT_ENDPOINT in endpoints and THERMALRIGHT_DEFAULT_IN_ENDPOINT in endpoints


@dataclass(frozen=True)
class ReplayPacket:
    endpoint: int
    direction: str
    transfer_type: str
    payload: bytes


@dataclass(frozen=True)
class ReplayOptions:
    delay_ms: int = 0
    dry_run: bool = True
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE


@dataclass(frozen=True)
class FrameBufferOptions:
    chunk_size: int = 4096
    header_prefix: bytes = b""
    footer: bytes = b""
    delay_ms: int = 0
    dry_run: bool = True
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE


@dataclass(frozen=True)
class ThermalrightJpegOptions:
    width: int = THERMALRIGHT_IMAGE_WIDTH
    height: int = THERMALRIGHT_IMAGE_HEIGHT
    quality: int = 85
    metadata_width: int = THERMALRIGHT_IMAGE_METADATA_WIDTH
    chunk_data_size: int = THERMALRIGHT_IMAGE_CHUNK_DATA_SIZE
    packet_size: int = THERMALRIGHT_IMAGE_PACKET_SIZE
    final_packet_size: int = THERMALRIGHT_IMAGE_FINAL_PACKET_SIZE
    packet_delay_ms: int = 0
    chunk_command: int = 1
    send_init_command: bool = True
    read_ack: bool = True


@dataclass(frozen=True)
class ThermalrightImageChunkInfo:
    opcode: int
    marker: int
    declared_size: int
    chunk_payload_length: int
    total_chunks: int
    mode: int
    chunk_index: int
    data_offset: int
    data_length: int


def scan_thermalright_devices(
    known_vid_pids: set[tuple[int, int]] | None = None,
    include_all: bool = False,
    log=print,
) -> list[ThermalrightDeviceInfo]:
    """Enumerate USB devices and return likely Thermalright bulk candidates."""
    if usb is None:
        raise RuntimeError("PyUSB is not installed; install pyusb/libusb to scan USB devices")
    devices = []
    known_vid_pids = known_vid_pids or set()
    for dev in usb.core.find(find_all=True) or []:
        info = _device_info(dev, known_vid_pids)
        if include_all or info.candidate_reasons:
            devices.append(info)
            _log_device(info, log)
    return devices


class ThermalrightUsbTransport:
    def __init__(
        self,
        device: ThermalrightDeviceInfo | None = None,
        vid: int | None = None,
        pid: int | None = None,
        serial_number: str = "",
        bus: int | None = None,
        address: int | None = None,
        interface_number: int | None = None,
        out_endpoint: int = THERMALRIGHT_DEFAULT_OUT_ENDPOINT,
        in_endpoint: int = THERMALRIGHT_DEFAULT_IN_ENDPOINT,
        timeout_ms: int = 1000,
        debug: bool = False,
        max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
    ):
        self.device_info = device
        self.vid = vid if vid is not None else (device.vid if device else None)
        self.pid = pid if pid is not None else (device.pid if device else None)
        self.serial_number = serial_number or (device.serial_number if device else "")
        self.bus = bus if bus is not None else (device.bus if device else None)
        self.address = address if address is not None else (device.address if device else None)
        self.interface_number = interface_number
        self.out_endpoint = out_endpoint
        self.in_endpoint = in_endpoint
        self.timeout_ms = timeout_ms
        self.debug = debug
        self.max_packet_size = max_packet_size
        self.dev = None
        self.interface = None

    def open(self) -> None:
        if usb is None:
            raise RuntimeError("PyUSB is not installed; install pyusb/libusb to use Thermalright USB transport")
        if self.is_open():
            return
        if self.vid is None or self.pid is None:
            raise RuntimeError("ThermalrightUsbTransport requires vid/pid or a ThermalrightDeviceInfo")
        selector = _device_selector_suffix(serial_number=self.serial_number, bus=self.bus, address=self.address)
        self._debug(f"opening {self.vid:04x}:{self.pid:04x}{selector}")
        self.dev = _find_usb_device(self.vid, self.pid, serial_number=self.serial_number, bus=self.bus, address=self.address)
        if self.dev is None:
            raise RuntimeError(f"USB device {self.vid:04x}:{self.pid:04x}{selector} not found")
        try:
            self.dev.set_configuration()
        except usb.core.USBError as error:
            self._debug(f"set_configuration ignored: {error}")
        self.claim_interface()

    def close(self) -> None:
        if not self.dev:
            return
        try:
            self.release_interface()
        finally:
            usb.util.dispose_resources(self.dev)
            self.dev = None
            self.interface = None
            self._debug("closed")

    def is_open(self) -> bool:
        return self.dev is not None

    def claim_interface(self) -> None:
        if not self.dev:
            raise RuntimeError("USB device is not open")
        interface_number = self.interface_number
        if interface_number is None:
            interface_number = _find_interface_for_endpoint(self.dev, self.out_endpoint)
        if interface_number is None:
            raise RuntimeError(f"Could not find interface with OUT endpoint 0x{self.out_endpoint:02x}")
        try:
            if self.dev.is_kernel_driver_active(interface_number):
                self._debug(f"detaching kernel driver interface={interface_number}")
                self.dev.detach_kernel_driver(interface_number)
        except (NotImplementedError, usb.core.USBError):
            pass
        usb.util.claim_interface(self.dev, interface_number)
        self.interface_number = interface_number
        self.interface = _find_interface(self.dev, interface_number)
        self._debug(f"claimed interface={interface_number}")

    def release_interface(self) -> None:
        if not self.dev or self.interface_number is None:
            return
        try:
            usb.util.release_interface(self.dev, self.interface_number)
            self._debug(f"released interface={self.interface_number}")
        except usb.core.USBError as error:
            self._debug(f"release ignored: {error}")

    def write_bulk(self, endpoint: int, buffer: bytes) -> int:
        self._validate_packet(buffer)
        if not self.dev:
            raise RuntimeError("USB device is not open")
        endpoint_obj = _find_endpoint(self.dev, endpoint)
        if endpoint_obj is None:
            raise RuntimeError(f"Endpoint 0x{endpoint:02x} not found")
        self._debug(f"bulk write endpoint=0x{endpoint:02x} len={len(buffer)} preview={hex_preview(buffer)}")
        return int(endpoint_obj.write(buffer, timeout=self.timeout_ms))

    def read_bulk(self, endpoint: int, length: int = 64, timeout: int | None = None) -> bytes:
        if not self.dev:
            raise RuntimeError("USB device is not open")
        endpoint_obj = _find_endpoint(self.dev, endpoint)
        if endpoint_obj is None:
            raise RuntimeError(f"Endpoint 0x{endpoint:02x} not found")
        self._debug(f"bulk read endpoint=0x{endpoint:02x} len={length}")
        data = endpoint_obj.read(length, timeout=timeout or self.timeout_ms)
        result = bytes(data)
        self._debug(f"bulk read result len={len(result)} preview={hex_preview(result)}")
        return result

    def reset(self) -> None:
        if not self.dev:
            return
        for endpoint in (self.out_endpoint, self.in_endpoint):
            try:
                self.dev.clear_halt(endpoint)
                self._debug(f"clear_halt endpoint=0x{endpoint:02x}")
            except (AttributeError, usb.core.USBError) as error:
                self._debug(f"clear_halt ignored endpoint=0x{endpoint:02x}: {error}")
        try:
            self.dev.reset()
            self._debug("device reset")
        except usb.core.USBError as error:
            self._debug(f"reset ignored: {error}")

    def _validate_packet(self, buffer: bytes) -> None:
        if len(buffer) > self.max_packet_size:
            raise ValueError(f"Refusing packet of {len(buffer)} bytes; max is {self.max_packet_size}")

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[thermalright-usb] {message}", file=sys.stderr)


class ThermalrightProtocol:
    def __init__(
        self,
        transport: ThermalrightUsbTransport | None = None,
        out_endpoint: int = THERMALRIGHT_DEFAULT_OUT_ENDPOINT,
        in_endpoint: int = THERMALRIGHT_DEFAULT_IN_ENDPOINT,
        dry_run: bool = True,
        debug: bool = False,
        max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ):
        self.transport = transport
        self.out_endpoint = out_endpoint
        self.in_endpoint = in_endpoint
        self.dry_run = dry_run
        self.debug = debug
        self.max_packet_size = max_packet_size
        self.max_frame_size = max_frame_size

    def send_raw(self, buffer: bytes, endpoint: int | None = None, dry_run: bool | None = None) -> int:
        endpoint = self.out_endpoint if endpoint is None else endpoint
        dry_run = self.dry_run if dry_run is None else dry_run
        self._validate_packet(buffer)
        self._debug(f"send_raw endpoint=0x{endpoint:02x} len={len(buffer)} dry_run={dry_run} preview={hex_preview(buffer)}")
        if dry_run:
            return len(buffer)
        if self.transport is None:
            raise RuntimeError("Transport is required for non-dry-run sends")
        return self.transport.write_bulk(endpoint, buffer)

    def read_status(self, length: int = 64) -> bytes | None:
        if self.transport is None or not self.transport.is_open():
            self._debug("read_status skipped; transport is not open")
            return None
        return self.transport.read_bulk(self.in_endpoint, length)

    def send_command(self, command_buffer: bytes, dry_run: bool | None = None) -> int:
        return self.send_raw(command_buffer, dry_run=dry_run)

    def send_chunked_frame(self, buffer: bytes, options: FrameBufferOptions | None = None) -> int:
        options = options or FrameBufferOptions(dry_run=self.dry_run)
        chunks = split_frame_chunks(buffer, options)
        sent = 0
        self._debug(
            f"send_chunked_frame frame_len={len(buffer)} chunks={len(chunks)} "
            f"chunk_size={options.chunk_size} dry_run={options.dry_run}"
        )
        for chunk in chunks:
            sent += self.send_raw(chunk, dry_run=options.dry_run)
            if options.delay_ms > 0:
                time.sleep(options.delay_ms / 1000)
        return sent

    def parse_response(self, buffer: bytes) -> dict[str, Any]:
        return self.inspect_packet(buffer)

    def inspect_packet(self, buffer: bytes) -> dict[str, Any]:
        return inspect_packet(buffer)

    def send_image(self, buffer: bytes, format_options: dict[str, Any] | None = None) -> int:
        options = ThermalrightJpegOptions(**(format_options or {}))
        if hasattr(buffer, "save"):
            jpeg_bytes = encode_thermalright_jpeg(buffer, options)
        elif isinstance(buffer, bytes):
            jpeg_bytes = buffer
        else:
            raise TypeError("send_image expects JPEG bytes or a PIL.Image-like object")
        return self.send_jpeg(jpeg_bytes, options)

    def send_jpeg(self, jpeg_bytes: bytes, options: ThermalrightJpegOptions | None = None) -> int:
        options = options or ThermalrightJpegOptions()
        packets = build_thermalright_jpeg_packets(jpeg_bytes, options)
        sent = 0
        if options.send_init_command:
            try:
                sent += self.send_raw(build_thermalright_init_command(), dry_run=self.dry_run)
            except Exception as error:
                raise RuntimeError("Thermalright init write failed") from error
            if options.read_ack and not self.dry_run:
                try:
                    self.read_status(512)
                except Exception as error:
                    raise RuntimeError("Thermalright init ACK read failed") from error
        for index, packet in enumerate(packets):
            try:
                sent += self.send_raw(packet, dry_run=self.dry_run)
            except Exception as error:
                raise RuntimeError(
                    f"Thermalright packet write failed at {index + 1}/{len(packets)} "
                    f"(len={len(packet)})"
                ) from error
            if options.packet_delay_ms > 0:
                time.sleep(options.packet_delay_ms / 1000)
        if options.read_ack and not self.dry_run:
            try:
                self.read_status(512)
            except Exception as error:
                raise RuntimeError("Thermalright frame ACK read failed") from error
        return sent

    def send_frame_buffer(self, buffer: bytes, width: int, height: int, pixel_format: str, dry_run: bool | None = None) -> int:
        if pixel_format.lower() not in {"rgb565", "rgb888", "bgr565", "bgr888"}:
            raise ValueError(f"Unsupported experimental pixel format: {pixel_format}")
        options = FrameBufferOptions(dry_run=self.dry_run if dry_run is None else dry_run)
        return self.send_chunked_frame(buffer, options)

    def encode_rgb565(self, image) -> bytes:
        raise NotImplementedError("RGB565 encoding for Thermalright is experimental; no final image path is decoded yet")

    def encode_rgb888(self, image) -> bytes:
        raise NotImplementedError("RGB888 encoding for Thermalright is experimental; no final image path is decoded yet")

    def _validate_packet(self, buffer: bytes) -> None:
        if len(buffer) > self.max_packet_size:
            raise ValueError(f"Refusing packet of {len(buffer)} bytes; max is {self.max_packet_size}")

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[thermalright-protocol] {message}", file=sys.stderr)


class ThermalrightPlugin:
    def __init__(self, dry_run: bool = True, debug: bool = False):
        self.dry_run = dry_run
        self.debug = debug
        self.transport: ThermalrightUsbTransport | None = None
        self.protocol = ThermalrightProtocol(dry_run=dry_run, debug=debug)

    def scan(self) -> list[ThermalrightDeviceInfo]:
        return scan_thermalright_devices(log=self._log)

    def connect(self, device: ThermalrightDeviceInfo) -> None:
        self.transport = ThermalrightUsbTransport(device=device, debug=self.debug)
        self.transport.open()
        self.protocol.transport = self.transport

    def disconnect(self) -> None:
        if self.transport:
            self.transport.close()
        self.transport = None
        self.protocol.transport = None

    def send_raw(self, data: bytes) -> int:
        return self.protocol.send_raw(data, dry_run=self.dry_run)

    def read_status(self) -> bytes | None:
        return self.protocol.read_status()

    def replay_capture(self, path: str | Path, options: ReplayOptions | None = None) -> int:
        packets = load_replay_file(path)
        return replay_packets(self.protocol, packets, options or ReplayOptions(dry_run=True))

    def _log(self, message: str) -> None:
        if self.debug:
            print(message, file=sys.stderr)


def inspect_packet(buffer: bytes) -> dict[str, Any]:
    image_chunk = parse_image_chunk_header(buffer)
    header_offset = buffer[:32].find(POSSIBLE_MAGIC_HEADER)
    starts_with_header = header_offset == 0
    possible_opcode = buffer[header_offset + len(POSSIBLE_MAGIC_HEADER)] if header_offset >= 0 and len(buffer) > header_offset + len(POSSIBLE_MAGIC_HEADER) else (buffer[0] if header_offset < 0 and buffer else None)
    result = {
        "length": len(buffer),
        "startsWithKnownHeader": starts_with_header,
        "knownHeaderOffset": header_offset if header_offset >= 0 else None,
        "possibleOpcode": possible_opcode,
        "possibleCommand": _possible_command(possible_opcode),
        "rawHexPreview": hex_preview(buffer),
    }
    if image_chunk is not None:
        result["thermalrightImageChunk"] = {
            "opcode": image_chunk.opcode,
            "marker": image_chunk.marker,
            "declaredSize": image_chunk.declared_size,
            "chunkPayloadLength": image_chunk.chunk_payload_length,
            "totalChunks": image_chunk.total_chunks,
            "mode": image_chunk.mode,
            "chunkIndex": image_chunk.chunk_index,
            "dataOffset": image_chunk.data_offset,
            "dataLength": image_chunk.data_length,
        }
    return result


def parse_image_chunk_header(buffer: bytes) -> ThermalrightImageChunkInfo | None:
    """Parse the observed Thermalright JPEG chunk header, if present."""
    if len(buffer) < 16 or buffer[0] != 0x01 or buffer[1] != 0xFF:
        return None
    return ThermalrightImageChunkInfo(
        opcode=buffer[0],
        marker=buffer[1],
        declared_size=int.from_bytes(buffer[2:6], "little"),
        chunk_payload_length=int.from_bytes(buffer[6:8], "little"),
        total_chunks=int.from_bytes(buffer[9:11], "little"),
        mode=buffer[10],
        chunk_index=int.from_bytes(buffer[11:13], "little"),
        data_offset=16,
        data_length=max(0, min(len(buffer) - 16, int.from_bytes(buffer[6:8], "little"))),
    )


def build_thermalright_init_command(length: int = 2048) -> bytes:
    if length < 9:
        raise ValueError("Thermalright init command length must be at least 9 bytes")
    command = bytearray(length)
    command[0] = 0x02
    command[1] = 0xFF
    command[8] = 0x01
    return bytes(command)


def encode_thermalright_jpeg(image, options: ThermalrightJpegOptions | None = None) -> bytes:
    options = options or ThermalrightJpegOptions()
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover - Pillow is a runtime dependency.
        raise RuntimeError("Pillow is required to encode Thermalright JPEG images") from error
    if not hasattr(image, "convert"):
        raise TypeError("encode_thermalright_jpeg expects a PIL.Image-like object")
    image = image.convert("RGB")
    if image.size != (options.width, options.height):
        image = image.resize((options.width, options.height), Image.Resampling.LANCZOS)
    out = BytesIO()
    image.save(out, format="JPEG", quality=options.quality, optimize=False, progressive=False)
    return out.getvalue()


def build_thermalright_jpeg_packets(
    jpeg_bytes: bytes,
    options: ThermalrightJpegOptions | None = None,
) -> list[bytes]:
    options = options or ThermalrightJpegOptions()
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        raise ValueError("Thermalright image packets expect JPEG bytes")
    if options.metadata_width <= 0:
        raise ValueError("metadata_width must be positive")
    if options.chunk_data_size <= 0:
        raise ValueError("chunk_data_size must be positive")
    num_chunks = len(jpeg_bytes) // options.metadata_width + 1
    chunks = bytearray(num_chunks * 512)
    for index in range(num_chunks):
        chunk_offset = index * 512
        data_offset = index * options.metadata_width
        chunk = jpeg_bytes[data_offset:data_offset + options.metadata_width]
        data_len = len(chunk)
        header = (
            bytes([0x01, 0xFF])
            + len(jpeg_bytes).to_bytes(4, "little")
            + data_len.to_bytes(2, "little")
            + bytes([options.chunk_command & 0xFF])
            + num_chunks.to_bytes(2, "little")
            + index.to_bytes(2, "little")
            + b"\x00\x00\x00"
        )
        chunks[chunk_offset:chunk_offset + 16] = header
        chunks[chunk_offset + 16:chunk_offset + 16 + data_len] = chunk

    padded_chunks = num_chunks
    remainder = padded_chunks % 4
    if remainder:
        padded_chunks += 4 - remainder
    send_buf = bytes(chunks) + bytes((padded_chunks - num_chunks) * 512)

    packets: list[bytes] = []
    for offset in range(0, len(send_buf), options.packet_size):
        remaining = len(send_buf) - offset
        write_size = options.packet_size if remaining >= options.packet_size else min(options.final_packet_size, remaining)
        packets.append(send_buf[offset:offset + write_size])
    return packets


def split_frame_chunks(buffer: bytes, options: FrameBufferOptions | None = None) -> list[bytes]:
    options = options or FrameBufferOptions()
    if len(buffer) > options.max_frame_size:
        raise ValueError(f"Refusing frame of {len(buffer)} bytes; max is {options.max_frame_size}")
    if options.chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    chunks: list[bytes] = []
    for offset in range(0, len(buffer), options.chunk_size):
        chunk = options.header_prefix + buffer[offset:offset + options.chunk_size] + options.footer
        if len(chunk) > options.max_packet_size:
            raise ValueError(f"Refusing chunk of {len(chunk)} bytes; max is {options.max_packet_size}")
        chunks.append(chunk)
    return chunks


def load_replay_file(path: str | Path) -> list[ReplayPacket]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Replay JSON must be a list of packet objects")
        return [_replay_packet_from_json(item) for item in raw]
    if path.suffix.lower() == ".pcap":
        return load_usbpcap_bulk_packets(path)
    return [
        ReplayPacket(
            endpoint=THERMALRIGHT_DEFAULT_OUT_ENDPOINT,
            direction="out",
            transfer_type="bulk",
            payload=path.read_bytes(),
        )
    ]


def load_usbpcap_bulk_packets(
    path: str | Path,
    endpoint: int = THERMALRIGHT_DEFAULT_OUT_ENDPOINT,
    direction: str = "out",
) -> list[ReplayPacket]:
    """Extract USBPcap BULK payloads from a classic .pcap file."""
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError("PCAP file is too small")
    magic = data[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    else:
        raise ValueError("Only classic PCAP files are supported for USBPcap extraction")
    offset = 24
    packets: list[ReplayPacket] = []
    while offset + 16 <= len(data):
        _ts_sec, _ts_usec, captured_len, _original_len = struct.unpack_from(f"{endian}IIII", data, offset)
        offset += 16
        frame = data[offset:offset + captured_len]
        offset += captured_len
        parsed = _parse_usbpcap_frame(frame, endian)
        if parsed is None:
            continue
        if parsed["transfer_type"] != 3:
            continue
        if parsed["endpoint"] != endpoint:
            continue
        if _endpoint_direction(parsed["endpoint"]) != direction:
            continue
        payload = parsed["payload"]
        if not payload:
            continue
        packets.append(
            ReplayPacket(
                endpoint=parsed["endpoint"],
                direction=direction,
                transfer_type="bulk",
                payload=payload,
            )
        )
    return packets


def export_replay_json(packets: list[ReplayPacket], path: str | Path) -> None:
    path = Path(path)
    payload = [
        {
            "endpoint": f"0x{packet.endpoint:02x}",
            "direction": packet.direction,
            "transferType": packet.transfer_type,
            "payloadHex": packet.payload.hex(),
        }
        for packet in packets
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def replay_packets(protocol: ThermalrightProtocol, packets: list[ReplayPacket], options: ReplayOptions | None = None) -> int:
    options = options or ReplayOptions()
    sent = 0
    for index, packet in enumerate(packets, start=1):
        if packet.transfer_type.lower() != "bulk" or packet.direction.lower() != "out":
            protocol._debug(f"skip replay packet {index}: direction={packet.direction} type={packet.transfer_type}")
            continue
        if len(packet.payload) > options.max_packet_size:
            raise ValueError(f"Refusing replay packet {index} of {len(packet.payload)} bytes; max is {options.max_packet_size}")
        protocol._debug(
            f"replay packet {index}/{len(packets)} endpoint=0x{packet.endpoint:02x} "
            f"len={len(packet.payload)} dry_run={options.dry_run} preview={hex_preview(packet.payload)}"
        )
        sent += protocol.send_raw(packet.payload, endpoint=packet.endpoint, dry_run=options.dry_run)
        if options.delay_ms > 0:
            time.sleep(options.delay_ms / 1000)
    return sent


def dry_run_replay(path: str | Path, debug: bool = True) -> int:
    protocol = ThermalrightProtocol(dry_run=True, debug=debug)
    return replay_packets(protocol, load_replay_file(path), ReplayOptions(dry_run=True))


def hex_preview(buffer: bytes, preview_bytes: int = 32, full: bool = False) -> str:
    if full or len(buffer) <= preview_bytes * 2:
        return buffer.hex()
    return f"{buffer[:preview_bytes].hex()}...{buffer[-preview_bytes:].hex()}"


def _replay_packet_from_json(item: Any) -> ReplayPacket:
    if not isinstance(item, dict):
        raise ValueError("Replay packet must be an object")
    endpoint = _parse_int(item.get("endpoint", THERMALRIGHT_DEFAULT_OUT_ENDPOINT))
    payload_hex = str(item.get("payloadHex") or item.get("payload_hex") or "")
    if not payload_hex:
        raise ValueError("Replay packet requires payloadHex")
    return ReplayPacket(
        endpoint=endpoint,
        direction=str(item.get("direction", "out")).lower(),
        transfer_type=str(item.get("transferType") or item.get("transfer_type") or "bulk").lower(),
        payload=bytes.fromhex(payload_hex),
    )


def _parse_usbpcap_frame(frame: bytes, endian: str) -> dict[str, Any] | None:
    if len(frame) < 27:
        return None
    header_len = struct.unpack_from(f"{endian}H", frame, 0)[0]
    if header_len < 27 or len(frame) < header_len:
        return None
    endpoint = frame[21]
    transfer_type = frame[22]
    data_length = struct.unpack_from(f"{endian}I", frame, 23)[0]
    payload = frame[header_len:header_len + data_length]
    return {
        "header_len": header_len,
        "endpoint": endpoint,
        "transfer_type": transfer_type,
        "data_length": data_length,
        "payload": payload,
    }


def _device_info(dev, known_vid_pids: set[tuple[int, int]]) -> ThermalrightDeviceInfo:
    vid = int(dev.idVendor)
    pid = int(dev.idProduct)
    manufacturer = _safe_usb_string(dev, getattr(dev, "iManufacturer", 0))
    product = _safe_usb_string(dev, getattr(dev, "iProduct", 0))
    serial = _safe_usb_string(dev, getattr(dev, "iSerialNumber", 0))
    interfaces = _interfaces_for_device(dev)
    endpoint_addresses = {endpoint.address for interface in interfaces for endpoint in interface.endpoints}
    reasons = []
    identity = f"{manufacturer} {product}".lower()
    if "thermalright" in identity:
        reasons.append("manufacturer/product contains Thermalright")
    if (vid, pid) in known_vid_pids:
        reasons.append("known VID/PID")
    if THERMALRIGHT_DEFAULT_OUT_ENDPOINT in endpoint_addresses and THERMALRIGHT_DEFAULT_IN_ENDPOINT in endpoint_addresses:
        reasons.append("default endpoints 0x09/0x81 present")
    return ThermalrightDeviceInfo(
        vid=vid,
        pid=pid,
        manufacturer=manufacturer,
        product=product,
        serial_number=serial,
        bus=getattr(dev, "bus", None),
        address=getattr(dev, "address", None),
        interfaces=interfaces,
        candidate_reasons=tuple(reasons),
    )


def _interfaces_for_device(dev) -> list[UsbInterfaceInfo]:
    interfaces: list[UsbInterfaceInfo] = []
    try:
        for cfg in dev:
            for interface in cfg:
                endpoints = [
                    UsbEndpointInfo(
                        address=int(endpoint.bEndpointAddress),
                        direction=_endpoint_direction(endpoint.bEndpointAddress),
                        transfer_type=_endpoint_type(endpoint.bmAttributes),
                        max_packet_size=getattr(endpoint, "wMaxPacketSize", None),
                    )
                    for endpoint in interface
                ]
                interfaces.append(
                    UsbInterfaceInfo(
                        number=int(interface.bInterfaceNumber),
                        alternate_setting=int(interface.bAlternateSetting),
                        interface_class=getattr(interface, "bInterfaceClass", None),
                        interface_subclass=getattr(interface, "bInterfaceSubClass", None),
                        interface_protocol=getattr(interface, "bInterfaceProtocol", None),
                        endpoints=endpoints,
                    )
                )
    except Exception:
        return interfaces
    return interfaces


def _safe_usb_string(dev, index: int) -> str:
    if not index or usb is None:
        return ""
    try:
        return str(usb.util.get_string(dev, index) or "")
    except Exception:
        return ""


def _find_interface_for_endpoint(dev, endpoint_address: int) -> int | None:
    try:
        cfg = dev.get_active_configuration()
        for interface in cfg:
            for endpoint in interface:
                if int(endpoint.bEndpointAddress) == endpoint_address:
                    return int(interface.bInterfaceNumber)
    except Exception:
        return None
    return None


def _find_interface(dev, interface_number: int):
    cfg = dev.get_active_configuration()
    return usb.util.find_descriptor(cfg, bInterfaceNumber=interface_number)


def _find_endpoint(dev, endpoint_address: int):
    cfg = dev.get_active_configuration()
    for interface in cfg:
        endpoint = usb.util.find_descriptor(interface, bEndpointAddress=endpoint_address)
        if endpoint is not None:
            return endpoint
    return None


def _find_usb_device(
    vid: int,
    pid: int,
    *,
    serial_number: str = "",
    bus: int | None = None,
    address: int | None = None,
):
    selector_active = bool(serial_number or bus is not None or address is not None)
    if not selector_active:
        return usb.core.find(idVendor=vid, idProduct=pid)
    for dev in usb.core.find(find_all=True, idVendor=vid, idProduct=pid) or []:
        if bus is not None and getattr(dev, "bus", None) != bus:
            continue
        if address is not None and getattr(dev, "address", None) != address:
            continue
        if serial_number and _safe_usb_string(dev, getattr(dev, "iSerialNumber", 0)) != serial_number:
            continue
        return dev
    return None


def _device_selector_suffix(*, serial_number: str = "", bus: int | None = None, address: int | None = None) -> str:
    parts = []
    if serial_number:
        parts.append(f"serial={serial_number}")
    if bus is not None:
        parts.append(f"bus={bus}")
    if address is not None:
        parts.append(f"address={address}")
    return f" ({', '.join(parts)})" if parts else ""


def _endpoint_direction(address: int) -> str:
    if usb is None:
        return "in" if address & 0x80 else "out"
    return "in" if usb.util.endpoint_direction(address) == usb.util.ENDPOINT_IN else "out"


def _endpoint_type(attributes: int) -> str:
    if usb is None:
        endpoint_type = attributes & 0x03
    else:
        endpoint_type = usb.util.endpoint_type(attributes)
    return {
        0: "control",
        1: "isochronous",
        2: "bulk",
        3: "interrupt",
    }.get(endpoint_type, f"unknown:{endpoint_type}")


def _parse_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    return int(text, 16) if text.startswith("0x") else int(text)


def _possible_command(opcode: int | None) -> str | None:
    if opcode is None:
        return None
    if opcode == 0xFF:
        return "possible sync/header byte"
    if opcode == 0x02:
        return "possible frame/chunk marker"
    return None


def _log_device(info: ThermalrightDeviceInfo, log) -> None:
    log(
        f"USB {info.vid:04x}:{info.pid:04x} manufacturer={info.manufacturer or '-'} "
        f"product={info.product or '-'} serial={info.serial_number or '-'} "
        f"reasons={', '.join(info.candidate_reasons) or '-'}"
    )
    for interface in info.interfaces:
        log(
            f"  interface={interface.number} alt={interface.alternate_setting} "
            f"class={_hex_or_dash(interface.interface_class)} subclass={_hex_or_dash(interface.interface_subclass)} "
            f"protocol={_hex_or_dash(interface.interface_protocol)}"
        )
        for endpoint in interface.endpoints:
            log(
                f"    endpoint=0x{endpoint.address:02x} dir={endpoint.direction} "
                f"type={endpoint.transfer_type} max_packet={endpoint.max_packet_size or '-'}"
            )


def _hex_or_dash(value: int | None) -> str:
    return "-" if value is None else f"0x{value:02x}"
