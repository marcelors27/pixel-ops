from __future__ import annotations

import argparse
from pathlib import Path

from pixel_ops.hardware.thermalright_usb import (
    ReplayOptions,
    THERMALRIGHT_IMAGE_HEIGHT,
    THERMALRIGHT_IMAGE_WIDTH,
    THERMALRIGHT_OBSERVED_PID,
    THERMALRIGHT_OBSERVED_VID,
    ThermalrightJpegOptions,
    ThermalrightPlugin,
    ThermalrightProtocol,
    ThermalrightUsbTransport,
    build_thermalright_jpeg_packets,
    encode_thermalright_jpeg,
    export_replay_json,
    inspect_packet,
    load_replay_file,
    load_usbpcap_bulk_packets,
    replay_packets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thermalright USB reverse-engineering tools.")
    parser.add_argument("--debug", action="store_true", help="Print verbose transport/protocol logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan", help="List candidate Thermalright USB devices.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one hex payload.")
    inspect_parser.add_argument("payload_hex")

    connect_parser = subparsers.add_parser("connect", help="Open and close a device safely.")
    connect_parser.add_argument("--vid", required=True, type=_hex_int)
    connect_parser.add_argument("--pid", required=True, type=_hex_int)
    connect_parser.add_argument("--timeout-ms", type=int, default=1000)

    raw_parser = subparsers.add_parser("send-raw", help="Send one raw hex payload. Dry-run unless --write is passed.")
    raw_parser.add_argument("payload_hex")
    raw_parser.add_argument("--vid", type=_hex_int)
    raw_parser.add_argument("--pid", type=_hex_int)
    raw_parser.add_argument("--write", action="store_true", help="Actually write to USB. Without this, dry-run only.")
    raw_parser.add_argument("--endpoint", type=_hex_int, default=None)
    raw_parser.add_argument("--timeout-ms", type=int, default=1000)

    replay_parser = subparsers.add_parser("replay", help="Replay a JSON or binary capture export.")
    replay_parser.add_argument("path", type=Path)
    replay_parser.add_argument("--vid", type=_hex_int)
    replay_parser.add_argument("--pid", type=_hex_int)
    replay_parser.add_argument("--delay", type=int, default=0, help="Delay between packets in milliseconds.")
    replay_parser.add_argument("--write", action="store_true", help="Actually write to USB. Without this, dry-run only.")
    replay_parser.add_argument("--max-packet-size", type=int, default=8192)
    replay_parser.add_argument("--timeout-ms", type=int, default=1000)

    extract_parser = subparsers.add_parser("extract-pcap", help="Extract USBPcap BULK OUT payloads to replay JSON.")
    extract_parser.add_argument("pcap", type=Path)
    extract_parser.add_argument("output", type=Path)
    extract_parser.add_argument("--endpoint", type=_hex_int, default=0x09)

    test_image_parser = subparsers.add_parser("send-test-image", help="Generate and send a Thermalright JPEG test image.")
    test_image_parser.add_argument("--vid", type=_hex_int, default=THERMALRIGHT_OBSERVED_VID)
    test_image_parser.add_argument("--pid", type=_hex_int, default=THERMALRIGHT_OBSERVED_PID)
    test_image_parser.add_argument("--output", type=Path, default=Path("/private/tmp/thermalright-test.jpg"))
    test_image_parser.add_argument("--write", action="store_true", help="Actually write to USB. Without this, dry-run only.")
    test_image_parser.add_argument("--quality", type=int, default=85)
    test_image_parser.add_argument("--timeout-ms", type=int, default=3000)
    test_image_parser.add_argument("--no-init", action="store_true", help="Skip the observed 02 ff init command.")
    test_image_parser.add_argument("--no-ack", action="store_true", help="Do not read 0x81 acknowledgements after writes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        ThermalrightPlugin(debug=args.debug).scan()
        return 0
    if args.command == "inspect":
        print(inspect_packet(bytes.fromhex(args.payload_hex)))
        return 0
    if args.command == "connect":
        transport = ThermalrightUsbTransport(vid=args.vid, pid=args.pid, debug=args.debug, timeout_ms=args.timeout_ms)
        transport.open()
        transport.close()
        return 0
    if args.command == "send-raw":
        dry_run = not args.write
        transport = None
        if not dry_run:
            if args.vid is None or args.pid is None:
                raise SystemExit("--vid and --pid are required with --write")
            transport = ThermalrightUsbTransport(vid=args.vid, pid=args.pid, debug=args.debug, timeout_ms=args.timeout_ms)
            transport.open()
        try:
            protocol = ThermalrightProtocol(transport=transport, dry_run=dry_run, debug=args.debug)
            protocol.send_raw(bytes.fromhex(args.payload_hex), endpoint=args.endpoint, dry_run=dry_run)
        finally:
            if transport:
                transport.close()
        return 0
    if args.command == "replay":
        dry_run = not args.write
        transport = None
        if not dry_run:
            if args.vid is None or args.pid is None:
                raise SystemExit("--vid and --pid are required with --write")
            transport = ThermalrightUsbTransport(
                vid=args.vid,
                pid=args.pid,
                debug=args.debug,
                max_packet_size=args.max_packet_size,
                timeout_ms=args.timeout_ms,
            )
            transport.open()
        try:
            protocol = ThermalrightProtocol(
                transport=transport,
                dry_run=dry_run,
                debug=True if dry_run else args.debug,
                max_packet_size=args.max_packet_size,
            )
            replay_packets(
                protocol,
                load_replay_file(args.path),
                ReplayOptions(delay_ms=args.delay, dry_run=dry_run, max_packet_size=args.max_packet_size),
            )
        finally:
            if transport:
                transport.close()
        return 0
    if args.command == "extract-pcap":
        packets = load_usbpcap_bulk_packets(args.pcap, endpoint=args.endpoint)
        export_replay_json(packets, args.output)
        total = sum(len(packet.payload) for packet in packets)
        print(f"Extracted {len(packets)} packets · {total} bytes -> {args.output}")
        return 0
    if args.command == "send-test-image":
        dry_run = not args.write
        options = ThermalrightJpegOptions(
            quality=args.quality,
            send_init_command=not args.no_init,
            read_ack=not args.no_ack,
        )
        image = _build_test_image(options.width, options.height)
        jpeg_bytes = encode_thermalright_jpeg(image, options)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(jpeg_bytes)
        packets = build_thermalright_jpeg_packets(jpeg_bytes, options)
        total_payload = sum(len(packet) for packet in packets)
        print(
            f"Prepared {args.output} · jpeg={len(jpeg_bytes)} bytes · "
            f"packets={len(packets)} · bulk_payload={total_payload} bytes · dry_run={dry_run}"
        )
        transport = None
        if not dry_run:
            transport = ThermalrightUsbTransport(
                vid=args.vid,
                pid=args.pid,
                debug=args.debug,
                max_packet_size=8192,
                timeout_ms=args.timeout_ms,
            )
            transport.open()
        try:
            protocol = ThermalrightProtocol(
                transport=transport,
                dry_run=dry_run,
                debug=True if dry_run else args.debug,
                max_packet_size=8192,
            )
            sent = protocol.send_jpeg(jpeg_bytes, options)
            print(f"Sent {sent} bytes")
        finally:
            if transport:
                transport.close()
        return 0
    raise SystemExit(f"Unsupported command: {args.command}")


def _hex_int(value: str) -> int:
    text = value.strip().lower()
    return int(text, 16) if text.startswith("0x") else int(text, 16)


def _build_test_image(width: int, height: int):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), (18, 24, 32))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        shade = int(48 + 80 * y / max(1, height - 1))
        draw.line((0, y, width, y), fill=(shade // 2, shade, 92))
    stripe_width = max(1, width // 12)
    colors = [
        (239, 68, 68),
        (245, 158, 11),
        (250, 204, 21),
        (34, 197, 94),
        (20, 184, 166),
        (59, 130, 246),
        (139, 92, 246),
        (236, 72, 153),
    ]
    for index, color in enumerate(colors):
        x0 = index * stripe_width
        draw.rectangle((x0, height - 72, x0 + stripe_width - 1, height), fill=color)
    font = ImageFont.load_default()
    draw.rectangle((72, 70, width - 72, height - 118), outline=(235, 245, 255), width=4)
    draw.text((108, 112), "THERMALRIGHT USB TEST", fill=(255, 255, 255), font=font)
    draw.text((108, 152), "JPEG bulk protocol 01 ff / endpoint 0x09", fill=(210, 230, 255), font=font)
    draw.text((108, 192), f"{width}x{height}", fill=(210, 230, 255), font=font)
    draw.ellipse((width - 250, 98, width - 110, 238), fill=(255, 255, 255), outline=(18, 24, 32), width=6)
    draw.ellipse((width - 212, 136, width - 148, 200), fill=(59, 130, 246))
    return image


if __name__ == "__main__":
    raise SystemExit(main())
