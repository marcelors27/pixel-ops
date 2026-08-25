# ADR 0025: E-ink displays are hybrid network outputs

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
refresh mode and health endpoints. It does not know about Pokemon, provider
integrations or Pixel OPs events.

The E213 is a hybrid output. While the host is healthy, the host remains the
authoritative renderer and sends complete frames. The host and firmware
maintain a bidirectional watchdog using heartbeats, short leases, acknowledgments
and an active callback probe. The lease timeout is a final safety bound, not the
only availability signal.

When the host is unavailable, firmware renders a compact monochrome HUD from
device-owned state. Internet reachability is tracked independently through
Wi-Fi state, DNS resolution and an HTTP connectivity response. The autonomous
renderer therefore distinguishes host mode, standalone-online mode, standalone-
local mode and captive portals.

Device-owned sources must be small and provider-neutral. Battery voltage, local
time and network state are local. Open-Meteo current weather is fetched directly
from configured coordinates and cached in ESP32 preferences. Provider secrets,
OAuth credentials, raw messages and visual-plugin rules must not move into the
firmware. Sources requiring those credentials use cached host snapshots or a
future authenticated relay.

Host-owned HUDs such as PC metrics, token usage, tasks, GitHub state and media
are intentionally absent in autonomous mode. Losing the host removes those HUDs
rather than replacing them with incomplete device-side copies.

Autonomous refresh and connectivity probes are energy-aware. Battery sampling
does not imply a panel refresh, confirmed outages use slower probes, and Wi-Fi
modem sleep remains enabled in the connected profile.

Battery-powered operation is opt-in through `device.eink.battery_powered`.
When enabled, the host exposes the latest encoded frame on a small authenticated
pull endpoint. The first direct frame bootstraps and persists the host address,
port and sleep interval. The ESP32 then enters deep sleep, wakes on its timer,
connects to Wi-Fi, requests the current digest, refreshes only when it changed,
and sleeps again. Mains-powered network outputs keep the connected push and
watchdog behavior.

The default minimum frame interval is 15 seconds. Every hundredth changed frame
is a full refresh; intervening frames use the panel's partial-window mode. The
longer cadence favors a calm display and accepts more ghosting between cleanups.
The E213 compositor uses a white canvas by default and preserves only configured
layout regions, so unused canvas does not inherit the visual plugin background.

## Consequences

- The display can run anywhere on the same Wi-Fi network.
- The display keeps a useful clock, battery, connectivity and cached-weather HUD
  when the host is off.
- Host and internet failures are independent and visible in `/status`.
- Visual plugins remain independent of the Heltec hardware.
- Frames are intentionally monochrome and low-frequency.
- Wi-Fi credentials stay in ESP32 preferences and secrets remain out of JSON.
- mDNS is convenient but deployments may use a fixed IP in `device.eink.url`.
- Autonomous configuration is synchronized by authenticated heartbeats and is
  written only when values change to limit flash wear.
- `battery_powered` belongs only to the e-ink output profile and defaults to
  enabled in the supplied E213 configuration.
- `deep_sleep_seconds` defaults to 300 seconds and `pull_port` defaults to 8765.
  The configured port must be reachable from the ESP32 on the local network.
- If Wi-Fi or the host is unavailable during a battery wake cycle, the retained
  e-ink image is left untouched and the device returns to sleep.
- Device-owned telemetry uses the shared layout vocabulary. `eink_battery`,
  `eink_wireless` and `eink_status` are positioned in Config Studio, rendered
  as monochrome HUDs while the PC owns the frame, and persisted as firmware HUD
  boxes for autonomous mode. Firmware does not reserve or overwrite a fixed
  corner for operational status.
- Autonomous rendering intentionally covers a compact subset of HUD semantics;
  it is not a second Pokemon renderer.
- A manually selected diagnostic page exposes only device-local health such as
  battery trend, RSSI, IP, uptime and reset reason.
