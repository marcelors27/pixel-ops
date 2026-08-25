# ADR 0008: CrossHero fitness data enters as a daily observation

## Status

Accepted

## Context

The Pokemon HUD needs the current CrossHero workout and today's classes with reservation counts. CrossHero publicly documents the center identifier and access-token headers, but not workout or schedule endpoints. Those routes can differ from the public athlete API and must not be embedded in a visual plugin.

## Decision

The optional `crosshero` integration owns HTTP polling and emits one provider-neutral `fitness.crosshero_day_updated` observation. Its snapshot contains a workout plus ordered class occupancy summaries. The Pokemon engine may project that observation into `crosshero_wod` and `crosshero_classes` layout windows.

The integration supports the authenticated `/dashboard/classes` HTML contract used by CrossHero itself: the index supplies today's class identifiers and each class detail supplies occupancy and the daily WOD. The dashboard URL is JSON configuration; the session cookie remains a secret referenced through an environment-variable name. The earlier configurable JSON endpoints remain available as a fallback for boxes that receive them from CrossHero. Removing either HUD never stops polling or event production.

Config Studio may request that the local Pixel OPs browser extension import the CrossHero cookie after an explicit user click. The extension has host access limited to CrossHero and fixed local Studio/receiver ports. It sends the cookie directly to the local backend, which stores it in `.env`; neither the UI nor runtime JSON receives the secret. Once enabled, cookie changes may refresh the local secret automatically.

The CrossHero source rereads this specific secret from `.env` on polling, so an extension refresh becomes effective without restarting the long-running display process.

Because Config Studio may run as an Electron app where a Chrome extension cannot inject, the browser bridge originates synchronization from an authenticated CrossHero tab as well as from the optional Studio button. The Studio polls only non-secret connection status.

## Consequences

Other game engines can interpret or ignore the same fitness observation. A CrossHero endpoint change is isolated to the source adapter or JSON configuration. The runtime remains usable when credentials, endpoints, or data are unavailable: the HUD renders an ambient waiting state.
