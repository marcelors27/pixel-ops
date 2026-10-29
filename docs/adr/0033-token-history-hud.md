# 0033 — Token history HUD

## Decision

Extend the existing `ai.usage_updated` observation snapshot with daily token totals,
request count and the model with the largest token total for the last 30 calendar
days. Reuse the existing enabled provider collectors and polling cadence. Codex
history uses one set of usage rows, independently of its overlapping 5-hour and
weekly gauges. Cumulative records are converted to deltas before window filtering.
Daily boundaries follow the collection timestamp timezone.

The `token_usage` presentation region consumes this observation in both visual
plugins. It shows a compact calendar heatmap, total tokens, active days, request
count, favorite model and current streak. The streak accepts activity yesterday
when today has no usage yet, and is bounded by the 30-day reporting window.
Unavailable observations have an explicit waiting state. Each panel clips to its
configured region. No prompts, responses, logs or billing tables are rendered.

The Waveshare 320 × 172 profile adds a Tokens screen to the existing rotation.
Removing the region or screen does not affect telemetry collection.

## Consequences

The history reflects available local Codex/Claude records and configured OpenAI
API usage. It is not an account-wide usage ledger. Request counts represent usage
records/API requests, not chat messages or sessions. Existing gauge semantics and
threshold events remain unchanged.
