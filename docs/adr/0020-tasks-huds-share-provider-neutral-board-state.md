# 0020 - Tasks HUDs Share Provider-Neutral Board State

## Status

Accepted

## Context

Pixel OPs already treats ClickUp tasks as planning snapshots rather than activity feeds. Adding more task providers should not create provider-specific HUDs or duplicate dashboard surfaces.

## Decision

Task integrations normalize into `TaskSnapshot` and `TaskItem`. `TaskItem.status` and `TaskItem.column` carry provider-neutral board state for visual plugins. ClickUp maps task status to the board column. Todoist maps section name to the board column and project name to the task group.

The runtime merges multiple task providers into one task source, so ClickUp and Todoist can feed the same `tasks` list HUD and the same `tasks_board` HUD.

## Consequences

Visual plugins consume task snapshots only; they do not call ClickUp, Todoist, or other task APIs directly. Layout visibility only controls rendering. Removing a task HUD must not disable task polling or snapshot production.
