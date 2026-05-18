# 0003 - Provider-Neutral Ambient Signals

Status: Accepted

## Context

Slack, Discord, Teams, Zoom, calendar, and GitHub expose different event payloads, but GACO needs one common ambient vocabulary.

Pokemon-specific concepts must not leak into provider integrations.

## Decision

Provider classifiers normalize external events into `AmbientSignal` in `pixel_ops/events/ambient_signals.py`.

`AmbientSignal` is then converted into a core `WorkEvent`. The shared vocabulary includes:

- direct messages;
- mentions;
- reactions;
- activity spikes;
- quiet periods;
- presence changes;
- voice activity;
- meeting soon/started/ended;
- participant joins/leaves;
- incident, deploy, and review signals.

## Consequences

Slack, Discord, Teams, Zoom, and future providers should emit `AmbientSignal` or `WorkEvent`, not Pokemon encounter details.

Visual plugins are free to interpret `WorkEvent.metadata`, `dominant_types`, priority, source, and category in their own style.

