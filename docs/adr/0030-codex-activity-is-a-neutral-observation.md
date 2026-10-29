# 0030 - Codex activity is a neutral observation

## Status

Accepted.

## Context

Usage gauges measure consumption, not whether the user should wait or respond. A compact semaphore needs explicit execution and approval state, independent of token usage and the selected game.

## Decision

The optional `codex_status` integration queries the existing local Codex app-server over its Unix WebSocket and, in automatic mode, reads local desktop lifecycle metadata. It emits `ai.activity_updated` observations containing an `AIActivitySnapshot`. Core continues to deliver events without owning projections or provider-specific fields.

The desktop can run a separate stdio app-server whose active sessions are absent from the shared daemon. A completed daemon session therefore does not establish desktop completion. With Socket Path empty, the integration also checks desktop IPC connectivity and opens `state_5.sqlite` and `thread_history_1.sqlite` in read-only mode. It selects only root-session identifiers, archival/source/recency metadata, and the latest turn status; it never queries conversation items, prompts, responses, or error bodies. Up to 100 non-archived CLI/desktop roots updated within 30 minutes participate. An explicit socket path selects daemon-only mode. Session ID filters both sources.

States are deduplicated by thread ID. Live approval/input requests and system errors have priority, followed by running work. Interrupted/failed turns are terminal history and cannot override active work. Desktop observations retain all running roots and only the newest root’s terminal outcome; idle daemon outcomes are ignored when desktop metadata is available, so an older failure cannot reappear after a newer task completes. An unavailable desktop database/schema or failed desktop liveness check contributes unknown, preventing an unrelated completed daemon session from turning the HUD green. Persisted desktop metadata exposes execution/completion/failure but not pending approval or input flags; those flags remain available only for sessions observed through the live WebSocket. This compatibility path depends on local database schemas and reports unavailable if they change. It does not start a daemon or send IPC commands.

Only read methods are used: `thread/loaded/list`, `thread/read` without turns, and `thread/turns/list` with `itemsView: notLoaded`. No session is started, resumed, or approved. No conversation content is retained or rendered. Temporary and subagent sessions are excluded by default. A configured `thread_id` selects one session.

The HUD maps active work to yellow, approval/input/system errors or failed/interrupted turns to red, and completed idle turns to green. Only live actionable red states have priority over processing across observed sessions. Missing, unsupported, disconnected, or stale observations show a gray question-mark dot; silence never proves completion. Ordinary prose questions after a completed turn cannot be distinguished from other completions; explicit waiting flags are required for input detection.

Collection runs through the existing asynchronous event-source wrapper. Removing the HUD only affects presentation. The configurable `codex_status` HUD works in Pokémon and Spaceship. Integration toggles and socket/session settings belong in JSON, independently of the AI usage integration.

## Consequences

This requires a Codex version exposing the shared local app-server or the supported local desktop databases (validated with 0.153.4 on macOS). Older installations and Windows report unavailable. Polling defaults to two seconds; a last-good observation is hidden after 15 seconds. A new turn clears a prior completed or interrupted state. Shared-daemon sessions must be loaded; desktop metadata must be recent and non-archived. The 30-minute desktop recency bound also limits stale states after an unclean runner exit, but cannot prove liveness of each individual turn.

Protocol reference: https://learn.chatgpt.com/docs/app-server

## Per-task HUD

`AIActivitySnapshot.tasks` carries immutable provider-neutral task IDs, states, and reasons. The source deduplicates sessions before publishing; renderer code never queries Codex. Each eligible task has one colored dot with a centered state letter (P/A/R/E/I/C), plus an opaque short ID suffix when space permits. Active tasks take display precedence over completions. When idle, the latest eligible result remains visible. Empty/stale observations use a gray ? or no-session dash. Fixed-size cells are ordered by task ID and paginate every four seconds when the configured region is full, rather than silently dropping tasks. The existing aggregate fields remain compatible with other consumers. No titles or conversation content are added.
