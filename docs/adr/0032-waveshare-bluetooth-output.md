# 0032 - Waveshare Bluetooth frame transport

Status: Accepted

## Context

The Waveshare ESP32-C6 has BLE hardware. The user needs to update the ambient
panel wirelessly from the Mac, alongside existing USB and HTTP options.

## Decision

Add `lcd.transport: "bluetooth"` with optional `bluetooth_address` and a default
one-second minimum interval (`bluetooth_frame_interval_seconds`). The host uses
Bleak and the firmware uses NimBLE. Discovery filters a Pixel OPs service UUID;
automatic selection requires exactly one matching panel. On macOS the stored
identifier is the CoreBluetooth UUID, not the board's MAC address.

The host still renders complete frames. BLE carries RGB565 pixels, optionally
run-length encoded, with bounded writes, per-block notifications, decoded size
checks, and CRC32. A successful final acknowledgement follows the display update.
The firmware permits one BLE client. BLE callbacks enqueue packets; only the
Arduino loop decodes or writes to display memory. USB/HTTP cannot share that
buffer during a BLE frame. Stalled and disconnected transfers release it.

Bluetooth remains optional and dependencies are imported only when selected.
The firmware uses the existing 4 MB flash envelope with a 3 MB application
partition (`huge_app.csv`) to fit Wi-Fi and BLE together. NVS stays at the same
address. This firmware does not implement OTA updates.

## Consequences

Game engines, layouts, provider events, USB and HTTP transports keep their
contracts. Bluetooth is slower than USB for full detailed frames; compression
and deduplication reduce traffic for compact HUDs. The Mac must grant Bluetooth
permission to the host application. BLE service access is currently unpaired;
only one nearby client can update the display at a time. This does not grant
access to host integrations, secrets, or platform events.

## Partial updates (BLE v2)

BLE v2 extends the command to 17 bytes with x/y/width/height uint16 big-endian
coordinates. The host compares native RGB565 pixels against the last acknowledged
frame and sends only the changed bounding rectangle. The receiver validates all
bounds, decoded length and CRC before drawing that rectangle. Reconnection or a
failed transfer clears the host baseline and forces a full frame. The host still
supports v1 devices by sending complete frames with the original 9-byte header.
This reduces HUD update traffic without changing rendering or event semantics.

## macOS reconnect lifecycle

Use one continuously running Bluetooth asyncio loop per host process, shared by
output instances across disconnects and config reloads. CoreBluetooth can retain
callbacks after disconnect; closing an instance's loop caused a native exception
and terminated Pixel OPs, leaving the panel showing the last activity indicator.
Disconnect releases the BLE client without closing the process loop. Notification
callbacks capture their own acknowledgement queue so late deliveries cannot target
a cleared or replacement connection's queue.
