# ADR 0028: Project Radar Uses Provider-Neutral Observations

## Status

Accepted

## Context

Long-running work and personal projects need to resurface without turning the ambient display into a task feed. Capacities is the first remote system used for capture and structured project state, but games and renderers must not depend on its object model.

Projects also differ from tasks: they have a next action, a deliberate incubation or waiting state, a review date, and an age since last attention. Flattening them into `TaskSnapshot` would lose those semantics.

## Decision

- Integrations publish `projects.snapshot_updated` with a provider-neutral `ProjectSnapshot`.
- Capacities discovery and property-name mapping stay under `pixel_ops/data_sources/` and `pixel_ops/integrations/capacities/`.
- The runtime only pumps the observation event. It does not score or render projects.
- The selected game engine owns the projection and may ignore the event.
- The shared Project Radar HUD deterministically selects one focus project and one resurfacing project. It never calls AI while rendering.
- Secrets remain in `.env`; non-secret polling and structure-name settings remain in `integrations.json`.
- A missing Capacities project type or unavailable provider produces an explicit empty snapshot so the display remains functional.

## Consequences

Other providers can produce the same project snapshot later without changing the HUD. Capacities can change its API representation without leaking provider fields into the game contract. Users need a read-only personal API token for unattended Pixel Ops polling even when an AI client separately connects through OAuth/MCP.
