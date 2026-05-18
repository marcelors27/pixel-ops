# 0001 - Ambient Social Observability, Not Feeds

Status: Accepted

## Context

GACO needs to integrate Slack, Discord, meetings, GitHub, calendar, and weather without becoming another dashboard, chat client, feed, or notification wall.

The goal is a living operational world: social and operational energy should alter atmosphere, mood, encounters, and small bits of diegetic storytelling.

## Decision

Provider activity is represented as ambient state.

The display must not show full Slack or Discord messages. It should instead map activity into:

- world mood;
- social weather;
- encounter rate and type pressure;
- subtle overlays and particles;
- short text boxes;
- meeting ceremonies;
- companion emotion.

## Consequences

Integrations can emit facts and semantic signals, but they must not drive provider-specific UI.

Renderer changes should be judged against the ambient principle. If a change looks like a notification feed, a Slack mirror, or a dense telemetry dashboard, it violates this ADR.

