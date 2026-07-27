# ADR 0025: E-ink displays are network output terminals

## Status

Accepted

## Context

The Heltec Vision Master E213 combines an ESP32-S3 and a 250×122 monochrome
panel. Driving it from the host over a serial protocol would couple the runtime
to USB enumeration and require the display to remain physically attached.
E-ink also needs a slower cadence and periodic full refreshes.

## Decision

Pixel OPs treats the E213 as a hardware-neutral `DisplayOutput` reached over
HTTP. The host performs resize, monochrome conversion, dithering, deduplication
and refresh scheduling. It sends a fixed row-aligned bitmap to firmware.

The firmware owns Wi-Fi provisioning, optional bearer authentication, panel
refresh mode and a small health endpoint. It does not know about Pokemon,
integrations, layouts or Pixel OPs events.

The default minimum frame interval is 15 seconds. Every tenth changed frame is
a full refresh; intervening frames may use the panel's partial mode.

## Consequences

- The display can run anywhere on the same Wi-Fi network.
- Visual plugins remain independent of the Heltec hardware.
- Frames are intentionally monochrome and low-frequency.
- Wi-Fi credentials stay in ESP32 preferences and secrets remain out of JSON.
- mDNS is convenient but deployments may use a fixed IP in `device.eink.url`.
