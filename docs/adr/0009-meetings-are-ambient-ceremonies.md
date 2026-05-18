# 0009 - Meetings Are Ambient Ceremonies

Status: Accepted

## Context

Meetings should be visible in the world without becoming a minigame or interruptive battle UI.

The desired behavior is ritualized and symbolic: sprint reviews, 1:1s, incidents, architecture meetings, retros, and deploy meetings should change the scene mood.

## Decision

Meetings are modeled as ambient ceremonies.

Core meeting classification lives in `pixel_ops/events/meeting_events.py`.

Pokemon-facing compatibility exports live in `pixel_ops/plugins/pokemon/game/meeting_ceremonies.py`.

Meeting events carry metadata such as:

- `meeting_type`;
- `meeting_mood`;
- `dominant_types`;
- `companion_emotion`.

## Consequences

Renderers can create gym, rest, legendary, psychic, campfire, or deploy-like ambience without taking over the whole display.

The HUD should remain visible during meeting ambience.

Adding a new meeting type should update core meeting classification first, then visual interpretation.

