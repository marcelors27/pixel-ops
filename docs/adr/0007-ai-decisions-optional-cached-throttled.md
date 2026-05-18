# 0007 - AI Decisions Are Optional, Cached, And Throttled

Status: Accepted

## Context

AI can improve contextual Pokemon encounter selection, but Slack or Discord activity can arrive in bursts. Calling OpenAI for every social message would be expensive, noisy, and vulnerable to loops.

The ambient display must keep working without network or API keys.

## Decision

AI decisions are optional and throttled.

Provider-neutral AI call code lives in `pixel_ops/plugins/ai/plugin.py`.

Pokemon-specific selection logic lives in `pixel_ops/plugins/pokemon/game/ai_selector.py`.

Default throttle policy in `pixel_ops/plugins/pokemon/game.json`:

- enabled;
- 90 second cooldown;
- 15 minute rolling window;
- 4 requests per window;
- max 1 pending request;
- skip Slack and Discord sources.

Successful AI decisions are cached under `pixel_ops/cache/ai_decisions`.

## Consequences

Ambient encounters never require OpenAI.

If AI is disabled, missing, throttled, or fails, the system falls back to local knowledge and deterministic selection.

Future AI usage must define throttle behavior before subscribing to high-volume event sources.

