# 0018 - ClickUp Tasks Are Planning Snapshots

Status: Accepted

## Context

Pixel OPs needs to show assigned ClickUp work with due dates and remaining time without turning the display into a task feed or ClickUp clone.

ClickUp task data is provider-owned operational planning state. It has secrets, polling policy, filtering, and API failure modes that belong in the integration layer, not in the Pokemon visual plugin.

## Decision

ClickUp is a runtime integration loaded by JSON config under `pixel_ops/config/integrations.json`.

Secrets stay in `.env` through `PIXEL_OPS_CLICKUP_TOKEN`. Non-secret settings such as workspace ID, assignee ID, polling interval, task limit, due horizon, and closed/subtask filters stay in JSON so Config Studio can edit them.

The integration polls ClickUp through `pixel_ops/data_sources/clickup.py` and exposes a compact provider-neutral `TaskSnapshot`. Visual plugins consume the snapshot through `PixelOpsApp` and may render a `tasks` layout window with task pressure, due date, and remaining time.

## Consequences

Layout visibility must not enable or disable ClickUp polling. Removing the `tasks` window only hides the HUD region.

The HUD may show compact task names and due pressure, but it must not render task comments, descriptions, activity logs, or notification streams.

If ClickUp credentials, workspace, or network access are unavailable, the data source returns an empty cached snapshot instead of crashing the display loop.
