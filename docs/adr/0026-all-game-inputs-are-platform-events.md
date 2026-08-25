# 0026 - All Game Inputs Are Platform Events

Status: Accepted

Supersedes the runtime shape described by ADRs [0008](0008-pokemon-visual-plugin-boundary.md) and [0010](0010-shared-integration-runtime-boundary.md).

## Context

Pokemon was registered as a visual plugin, but the core application still assembled a Pokemon-shaped render call. `PixelOpsApp` queried dedicated pull request, weather, AI usage, PC stats, task, media, calendar, and companion sources and passed their snapshots directly to the scene.

That made provider state bypass the event boundary. A second visual world would need to reproduce the same constructor and render signature, while additions to an integration required changes in the core, integration runtime, plugin entry point, and scene.

## Decision

Every external fact or observation enters the selected game engine through an event source.

Pixel Ops recognizes two compatible event forms:

- `WorkEvent` for discrete operational and social facts;
- `PixelOpsEvent` for versioned observations, lifecycle facts, and clock ticks.

`PixelOpsEvent` carries a stable type, occurrence time, source, payload, kind, schema version, and identity. Snapshot-oriented providers use `ObservationEventSource` to publish events such as:

- `calendar.next_updated` and `calendar.today_updated`;
- `github.pull_requests_updated`;
- `weather.conditions_updated`;
- `ai.usage_updated`;
- `system.metrics_updated`;
- `tasks.snapshot_updated`;
- `media.playback_updated`;
- `social.companions_updated`.

`IntegrationContribution` exposes event sources and lifecycle callbacks, not provider-specific snapshot channels. Calendar paths remain integration-owned transport configuration and are converted to calendar observation events at the platform boundary.

`PixelOpsApp` is an event pump. Per frame, it drains/polls its event sources, delivers every event to the selected `GameEngine`, emits `runtime.tick`, and requests an image. It does not interpret or aggregate provider state.

Each game engine owns its projections. `PokemonEngine` maintains the state needed by the Pokemon scene, converts `WorkEvent` instances into encounters, derives meeting companions and gamification inside its boundary, and calls the Pokemon renderer with Pokemon-owned state.

The extension boundaries are:

- integration plugins produce neutral events;
- game engines consume events and produce frames;
- output drivers deliver frames to files, windows, or hardware.

## Consequences

Adding a game does not require adding its concepts to the core or integrations.

Adding an observation type requires a neutral event name and schema, plus optional projections in interested games. It must not add another dedicated source field to `IntegrationContribution` or another render parameter to `PixelOpsApp`.

Games may interpret the same event differently and may ignore events they do not support. Provider transports must not import a game package.

Observation events currently carry normalized Python value objects in-process. Persistence or cross-process transport will require explicit serializable payload schemas and version migrations.

Multiple providers for the same observation type require deterministic projection/merge rules in the game or a future platform projector; they must not be merged by reaching back into provider clients.

