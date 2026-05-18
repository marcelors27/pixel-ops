# 0010 - Weather, Calendar, GitHub, Slack, Discord Share The Same Runtime Boundary

Status: Accepted

## Context

Different integrations contribute different kinds of data:

- GitHub contributes pull request state and work events.
- Google Calendar and ICS contribute meetings.
- Weather contributes current environmental state.
- Slack and Discord contribute social activity.

The main loop needs a consistent way to combine these without hard-coded provider branches everywhere.

## Decision

All integrations are merged into one `IntegrationRuntime`.

`IntegrationRuntime` owns:

- event sources;
- calendar paths;
- startup callbacks;
- warmup callbacks;
- close callbacks;
- pull request source;
- weather source;
- loaded plugin names.

`pixel_ops/main.py` builds the visual app from the current runtime contribution.

## Consequences

The display loop stays small and provider-agnostic.

Runtime rebuild on config changes can close old background receivers before starting new ones.

Future Teams and Zoom support should use the same contribution model.

