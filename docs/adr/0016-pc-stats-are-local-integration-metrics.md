# 0016 - PC Stats Are Local Integration Metrics

Status: Accepted

## Context

Host machine state is useful on a small ambient screen, but it should not become a raw process table or a visual-plugin-specific feature.

Users need to compose which system metrics appear, and the screen layout should expose windows only when the integration is enabled.

## Decision

PC stats are implemented as an integration plugin named `pc_stats`.

The integration owns local collection of CPU, RAM, top memory process, temperature, GPU identity, disk, uptime, battery, and load metrics. It exposes a compact snapshot to the core runtime.

The selected metrics live in `pixel_ops/config/integrations.json` under `integrations.pc_stats.fields`. Config Studio edits that list and exposes a `pc_stats` layout window only when the integration is enabled.

Visual plugins receive the normalized snapshot and decide how to render it. The Pokemon HUD renders it as a compact panel in configured screen layout windows.

## Consequences

The runtime can add other visual interpretations later without changing the system metrics collector.

The integration works without mandatory native dependencies. It uses `psutil` when installed and falls back to standard library or local system commands where practical.

Some metrics, especially temperature and GPU utilization, may be unavailable on locked-down systems or without platform-specific tooling; unavailable metrics render as unknown rather than failing the display.
