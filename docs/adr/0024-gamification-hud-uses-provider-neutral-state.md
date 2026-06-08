# 0024 - Gamification HUD Uses Provider-Neutral State

Status: Accepted

## Context

Pixel OPs can expose game-like ambient state, such as player HP, without turning provider activity into a feed or coupling integrations to the Pokemon visual plugin.

Meetings, task completion, and live companion presence are already normalized as runtime snapshots. The gamification layer should consume those shared snapshots instead of importing provider clients or provider-specific payloads.

## Decision

Gamification state lives behind a provider-neutral `GamificationSource`. The source reads calendar events, task snapshots, and companion snapshots from the core runtime and produces a compact `GamificationSnapshot` for visual surfaces.

The first metric is player HP:

- finished meetings consume HP once per day;
- delivered or completed tasks consume HP once per day;
- live companions gradually recover HP, with recovery scaling by companion count up to a configured cap.

The Pokemon plugin wires the source into `PixelOpsApp`, but the snapshot can be consumed by other display plugins or game systems later.

## Consequences

Visual renderers consume `GamificationSnapshot`; they do not call Calendar, ClickUp, Discord, Zoom, or other provider APIs directly.

Layout visibility controls only presentation. Removing the HP HUD must not disable calendar, task, companion, or gamification state production.

The HP rules are configurable through runtime JSON, while secrets and provider credentials stay in `.env`.
