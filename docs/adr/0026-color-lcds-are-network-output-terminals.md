# ADR 0026: Color LCDs are network output terminals

## Status

Accepted

## Context

The Waveshare ESP32-C6-LCD-1.47 combines an ESP32-C6 with a 172×320 ST7789
color panel. The Pixel OPs renderer already produces complete PIL frames and
keeps hardware transports behind the `DisplayOutput` boundary. Driving the
panel directly from a visual plugin would couple Pokemon or Spaceship rules to
one board and would bypass multi-display composition.

Unlike e-ink, this panel supports frequent color updates and does not need
partial refresh or ghosting policy. Its SPI bus is local to the ESP32, while
the host and device may communicate over the existing Wi-Fi network.

## Decision

Pixel Ops treats small ESP32 color LCDs as network output terminals. The host
owns rendering, resize, RGB565 encoding, frame deduplication, and pacing. It
sends a complete frame to an authenticated HTTP endpoint. Firmware owns Wi-Fi
provisioning, mDNS, the ST7789 transport, backlight safety, and a small status
endpoint. It does not consume platform events or implement game rules.

The initial hardware profile is `lcd`, fixed at 172×320 for the Waveshare
ESP32-C6-LCD-1.47. The on-wire format is row-major, big-endian RGB565. A frame
is transported as a multipart file so the ESP32 web server can receive it in
bounded chunks before one panel update.

## Consequences

- Color LCD output remains replaceable and game-neutral.
- The device works untethered after its initial USB flash and Wi-Fi setup.
- The host may update at up to ten frames per second by default.
- Frames are deduplicated to avoid unnecessary network and SPI traffic.
- The firmware limits the backlight to 50%, following the hardware vendor's
  thermal guidance.
- Device-local fallback rendering is limited to setup and health text; it does
  not become a second Pixel Ops renderer.

