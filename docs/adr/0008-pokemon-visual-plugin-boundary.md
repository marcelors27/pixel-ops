# 0008 - Pokemon Is A Visual Plugin, Not The Integration Model

Status: Superseded by [ADR 0026](0026-all-game-inputs-are-platform-events.md)

## Context

The current visual interface is Pokemon-inspired, but Pixel OPs / GACO should support other visual worlds in the future.

Provider integrations must not depend on Pokemon concepts such as Pokemon types, encounters, battle ambience, or overworld mood.

## Decision

Pokemon is a visual plugin under `pixel_ops/plugins/pokemon/`.

Integrations emit core events. The Pokemon plugin interprets those events into:

- encounter type pressure;
- Pokemon selection;
- social weather;
- battle ambience;
- text boxes;
- meeting ceremonies.

The plugin entry point is `pixel_ops/plugins/pokemon/plugin.py`.

## Consequences

Future visual plugins can reuse the same integration runtime and event vocabulary.

If an integration needs new semantic information, add it to `AmbientSignal`, `WorkEvent`, or metadata in a provider-neutral form.

Do not add Pokemon imports to `pixel_ops/integrations/`.
