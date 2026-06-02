# 0014 - Discord Voice Companions Are Provider State With Visual Mapping

Status: Accepted

## Context

Discord voice presence is useful ambient state, but the provider integration must not encode Pokemon rendering details.

The display should show who is currently in voice with the focus user, while keeping Discord-specific identity tracking separate from Pokemon-specific sprite choices.

## Decision

The Discord integration owns Discord identity and voice state:

- recent Discord people are stored in `pixel_ops/config/discord_people.json`;
- Discord voice state is converted to the provider-neutral `CompanionSnapshot` contract before visual plugins see it;
- companion snapshots expose normalized members, group IDs/names, display names, streaming state, and mute/deaf state;
- voice channel joins and switches emit provider-neutral work events;
- online presence changes alone do not emit Pokemon or channel-access events.

The Pokemon plugin owns visual interpretation:

- provider user to NPC sprite mapping lives in `pixel_ops/plugins/pokemon/companions.json` and is flattened before the scene consumes it;
- Config Studio shows recent Discord people from the Discord sidecar and writes sprite choices to the Pokemon companion config;
- Pokemon renders voice members as map companions, using NPC sprites and local wandering behavior.

Muted or deafened Discord members are represented visually by the Pokemon plugin as darker, idle companions. The provider only supplies the muted state.

## Consequences

Discord remains reusable by future visual plugins.

Pokemon-specific fields such as `sprite_variant` do not leak into `pixel_ops/integrations/discord/`.

If future visual plugins want a different social metaphor, they can consume the same `CompanionSnapshot` and ignore Pokemon companion config.

The UI must keep Discord identity management and Pokemon visual mapping in separate panels even when they reference the same Discord user IDs.
