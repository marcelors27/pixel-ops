# 0031 - Waveshare LCD supports USB frame delivery

Status: Accepted

## Context

The Waveshare ESP32-C6-LCD-1.47 previously accepted rendered frames only over
HTTP. A locally attached panel should also update without Wi-Fi.

## Decision

The existing `lcd` device gains `transport: "http" | "usb"` and an optional
serial `port`. HTTP remains the default. Both outputs consume complete rendered
images through `DisplayOutput`; integrations and game projections are unchanged.
USB uses the same native big-endian RGB565 format, a versioned handshake,
fixed frame length, CRC32, and ready/completion acknowledgements. Firmware bounds
receive work per loop and refuses incomplete or corrupt frames. HTTP handling
pauses while USB owns the shared receive buffer. Wi-Fi provisioning runs without
blocking the USB receiver. USB is a local physical transport, without HTTP tokens.

Config Studio exposes transport selection and separate firmware targets for the
Heltec E213 and Waveshare. Firmware build/upload uses an allowlisted target;
USB ports must be discovered locally before upload.

## Consequences

Existing network configurations retain their behavior. USB requires updated
firmware and pyserial. Automatic selection requires exactly one native ESP32 USB
candidate and validates the firmware identity before sending pixels. Multiple
boards require an explicit port. Connection changes require a runtime restart.
Game engines retain ownership of all interpretation and rendering.

USB protocol v2 acknowledges every 1024-byte block before the host continues.
The ESP32 allocates a 4096-byte receive buffer. Physical testing showed that
streaming a whole frame without these acknowledgements overflows reception.
