# 0022 - Zoom Meeting Companions Use Provider Neutral Snapshots

Status: Accepted

## Context

Zoom meeting participants can enrich the ambient display as live companions, but Zoom payloads must not leak into the Pokemon renderer or create a provider-specific meeting UI.

The runtime can also have more than one live companion provider enabled, such as Discord voice and Zoom meetings.

## Decision

Zoom participant state is normalized at the integration boundary. Business-and-higher accounts can poll Zoom live meeting metrics APIs. Pro accounts should receive Meeting webhook events through PixelOpsKite and stream those events to the local runtime over WebSocket.

The Zoom integration tracks live meeting participants and exposes them through the shared `CompanionSource` contract as `CompanionSnapshot` and `CompanionMember` values. Polling diffs can also emit provider-neutral ambient meeting events through the event bus when participants appear or disappear.

The integration runtime merges multiple companion sources with `MergedCompanionSource` instead of letting the last loaded provider replace earlier companion state.

## Consequences

Visual plugins continue to render companions from provider-neutral snapshots.

Zoom-specific identifiers remain integration state. Pokemon sprite mappings can still be configured by provider-owned IDs in `companions.json`.

Discord voice companions and Zoom meeting companions can coexist in the same runtime.
