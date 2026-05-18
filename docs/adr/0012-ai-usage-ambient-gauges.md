# 0012 - AI Usage Becomes Ambient Gauges And Events

Status: Accepted

## Context

CodexBar tracks AI provider limits by separating provider-specific collection from normalized usage snapshots and compact bars. Pixel OPs needs similar awareness, but the output must remain ambient and world-like instead of becoming a billing dashboard.

Initial sources:

- Codex local JSONL session logs;
- Claude local JSONL project logs;
- OpenAI API organization usage/cost endpoints.

## Decision

AI usage is implemented as an optional integration plugin named `ai_usage`.

The plugin contributes:

- an `AIUsageSource` for current gauges;
- an event source that emits `ai_usage` work events when usage spikes or crosses configured thresholds.

The Pokemon plugin renders tiny HUD gauges and maps `ai_usage` to Electric/Psychic encounter pressure.

## Consequences

Provider-specific parsing lives outside the visual plugin.

The display shows compact provider meters, not raw prompts, responses, logs, or detailed billing tables.

OpenAI Admin API usage requires `OPENAI_ADMIN_KEY`. Local Codex and Claude usage can work without network access when their logs exist.
