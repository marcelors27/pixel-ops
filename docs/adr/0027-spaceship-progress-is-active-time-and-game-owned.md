# 0027 - Spaceship Progress Is Active-Time And Game-Owned

Status: Accepted

## Context

The spaceship game needs a long-lived sense of voyage without turning Pixel OPs into a streak tracker or granting progress while another game is selected. GitHub pull requests also need a diegetic role without leaking spaceship rules into the GitHub integration.

## Decision

The spaceship engine owns its projection and durable state. It interprets `github.pull_requests_updated` observations as discoverable asteroids and GitHub `WorkEvent` facts as mining, sampling, certification, abandonment, and refinement transitions.

Progress is based only on runtime time observed while the spaceship engine is active. A process restart, a long shutdown, or time spent in another game grants no offline progress and applies no penalty. Tick gaps are capped, progress is flushed periodically and on close, and event receipts make material rewards idempotent.

State is stored in plugin-owned `spaceship_*` tables in the shared local SQLite database. PixelLab is a development-time asset source only: generated sprites are committed under the plugin and the runtime never calls PixelLab.

## Consequences

- Returning months later restores the exact voyage, cargo, asteroids, level, and sector.
- Selecting another game freezes the voyage naturally because no spaceship ticks are delivered.
- GitHub remains provider-neutral; another game may interpret the same PR events differently or ignore them.
- Duplicate polling and replayed work events cannot duplicate rewards.
- Schema changes to spaceship state require additive migrations owned by the plugin.
- Time-based progression is calm and cumulative, with no streaks, decay, or absence punishment.
