# Thermalright USB Plugin

This is an experimental reverse-engineering skeleton for Thermalright USB devices that appear as WinUSB/libusb-style bulk devices.

## Known Observations

- The device is not treated as HID.
- USBPcap/Wireshark showed proprietary USB BULK transfers.
- Main observed OUT endpoint: `0x09`.
- Main observed IN endpoint: `0x81`.
- OUT payloads are large and repeated, often near `4096` bytes plus protocol/header overhead.
- Some packets were around `4123` bytes.
- Standard enumeration/control traffic appears first: `GET_DESCRIPTOR`, `CONFIGURATION`, `INTERFACE`.
- Candidate protocol marker seen near payload/header: `ff 0c aa 02`.
- A later USBPcap sample showed a clearer display path:
  - endpoint `0x09` receives one padded `2048` byte command beginning `02 ff ...`;
  - endpoint `0x81` responds with `512` byte status packets beginning `03 ff ...`;
  - image updates are sent as JPEG payload fragments, not raw RGB framebuffer bytes;
  - each logical image chunk is `512` bytes: `16` header bytes plus up to `496` JPEG bytes;
  - logical chunks are grouped into `4096` byte USB bulk writes, 8 chunks at a time;
  - final writes may be `2048` bytes;
  - chunk count is padded to a multiple of 4 for PID `0416:5408`.

Observed image chunk header:

```text
01 ff <jpeg-size-le32> <chunk-payload-len-le16> 01 <total-chunks-le16> <chunk-index-le16> 00 00 00 <jpeg-bytes...>
```

Example:

```text
01 ff 2c ac 02 00 f0 01 01 62 01 08 00 00 00 00 ...
```

Decoded as opcode `0x01`, marker `0xff`, JPEG size `175148`, chunk payload length `496`, mode `1`, total chunks `354`, chunk index `8`.

The Linux implementation in `Lexonight1/thermalright-trcc-linux` confirms this LY format for PID `0416:5408`: handshake `02 ff`, 512-byte chunks, 496-byte payload per chunk, 4096-byte writes, and a 512-byte ACK after the frame.

## Safety Model

The tooling is dry-run by default. It will not write to USB unless explicitly run with `--write`.

Safety checks include:

- configurable endpoints;
- max packet size validation;
- max frame size validation;
- optional replay delay;
- short hex previews instead of full payload dumps;
- no automatic replay or writes on startup.

## CLI

Run the developer CLI as a module:

```bash
python -m pixel_ops.thermalright_cli scan --debug
python -m pixel_ops.thermalright_cli inspect ff0caa02
python -m pixel_ops.thermalright_cli connect --vid 1234 --pid abcd
python -m pixel_ops.thermalright_cli send-raw ff0caa02 --vid 1234 --pid abcd
python -m pixel_ops.thermalright_cli send-test-image --write
python -m pixel_ops.thermalright_cli replay ./capture.json --delay 5
```

`send-raw` and `replay` are dry-run unless `--write` is supplied:

```bash
python -m pixel_ops.thermalright_cli replay ./capture.json --vid 1234 --pid abcd --delay 5 --write
```

Use `--write` only after reviewing the capture and confirming the target device.

## Pixel OPs Output

The runtime can send rendered frames directly to a Thermalright LY LCD:

```bash
python pixel_ops/main.py --plugin pokemon --output thermalright --forever --fps 2 --offline
```

The output opens `0416:5408` by default, performs the LY handshake at startup, JPEG-encodes each rendered frame, sends chunks on endpoint `0x09`, and reads the frame ACK on `0x81`.

Optional JSON config under `display.device.thermalright`:

```json
{
  "vid": "0x0416",
  "pid": "0x5408",
  "timeout_ms": 5000,
  "jpeg_quality": 85,
  "image_width": 1920,
  "image_height": 462,
  "min_frame_interval_ms": 0,
  "packet_delay_ms": 0,
  "packet_size": 4096,
  "hard_reset_on_start": true,
  "hard_reset_wait_ms": 1500,
  "handshake_on_first_frame": false,
  "require_handshake": true,
  "send_start_init": true,
  "read_start_ack": true,
  "read_frame_ack": true,
  "start_retries": 0,
  "debug": false
}
```

Keep FPS conservative while testing. JPEG encoding plus USB transfer is heavier than local preview/window output.

## Replay Format

Classic USBPcap `.pcap` parsing is supported for BULK OUT extraction:

```bash
python -m pixel_ops.thermalright_cli extract-pcap ./thermalright.pcap ./thermalright-replay.json
```

The extractor keeps payload ordering and filters to endpoint `0x09` by default. You can also provide an already extracted JSON replay file:

```json
[
  {
    "endpoint": "0x09",
    "direction": "out",
    "transferType": "bulk",
    "payloadHex": "ff0caa02..."
  }
]
```

The replay loader ignores non-OUT/non-BULK packets during replay.

## Capturing More Data

On Windows:

1. Install USBPcap.
2. Start a capture before opening the vendor software.
3. Perform one clear action at a time, such as changing the screen image.
4. Stop capture and inspect in Wireshark.
5. Filter for bulk transfers on endpoints `0x09` and `0x81`.
6. Export only payload bytes needed for replay experiments.

Avoid long captures with mixed actions. Short, labeled captures are easier to decode.

## Current Python API

Low-level transport:

```python
from pixel_ops.hardware.thermalright_usb import ThermalrightUsbTransport

transport = ThermalrightUsbTransport(vid=0x1234, pid=0xabcd, debug=True)
transport.open()
transport.write_bulk(0x09, bytes.fromhex("ff0caa02"))
transport.close()
```

Protocol layer:

```python
from pixel_ops.hardware.thermalright_usb import ThermalrightProtocol

protocol = ThermalrightProtocol(dry_run=True, debug=True)
protocol.inspect_packet(bytes.fromhex("ff0caa02"))
```

Plugin facade:

```python
from pixel_ops.hardware.thermalright_usb import ThermalrightPlugin

plugin = ThermalrightPlugin(dry_run=True, debug=True)
plugin.scan()
plugin.replay_capture("capture.json")
```

## Future Work

- Identify stable VID/PID list.
- Decode opcodes.
- Decode ACK/status responses from endpoint `0x81`.
- Identify exact display resolution.
- Identify pixel format.
- Identify checksum/header/footer.
- Support brightness control.
- Support rotation/orientation.
- Support fan/RGB control if present.
- Support Linux/macOS setup details.
- Add direct pcap/pcapng parsing.
- Consider OpenRGB-like abstractions if the project grows RGB/fan control boundaries.
