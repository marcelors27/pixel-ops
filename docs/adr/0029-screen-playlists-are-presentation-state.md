# 0029 - Screen Playlists Are Presentation State

Status: Accepted

## Context

The physical displays cannot show every useful ambient projection at once. Pixel OPs needs multiple configurable compositions that rotate over time, can be selected immediately, and can remain fixed under manual control.

Rebuilding the selected game engine for every screen change would discard encounter, movement, projection, and integration state. Treating screen selection as a platform event would also mix operator presentation commands with ambient world facts.

## Decision

Screens are presentation state owned by a `ScreenRotationController` attached to `PixelOpsApp`.

Each screen contains a provider-neutral layout, theme, duration, label, enabled state, and optional visual plugin. A playlist supplies order, initial screen, and default duration. The existing top-level layout remains the backward-compatible fallback when no screens are configured. Pokemon and Spaceship are both presented as rotating HUD pages rather than separate runtime modes.

The controller supports automatic and pinned modes. Selecting a screen manually pins it until rotation is explicitly resumed. Hot reload preserves the active screen and pinned mode when that screen still exists.

Game engines expose `set_presentation(layout, layout_theme)`. Configured engines stay alive together: `PixelOpsApp` fans the same provider-neutral events and clock ticks to each one, then renders only the engine selected by the active HUD page. Presentation changes therefore do not reset event projections or durable state, and integrations remain unaware of screens.

A loopback-only HTTP control surface exposes screen status and selection commands. Config Studio, the standalone `/remote` interface, and the optional macOS Electron menu-bar control all use that same surface. Manual commands do not rewrite JSON configuration.

## Consequences

- Screen changes keep encounters, observations, integrations, and game progress alive.
- Pokemon and Spaceship HUDs share one event pump without polling integrations twice.
- The Studio can display an accurate deadline while animating its countdown locally.
- Browser, touch, and menu-bar controls stay consistent because command semantics live in one controller.
- The control endpoint is local by default and is not an internet-facing remote-control API.
- Per-output independent playlists remain a future extension because the current multi-display runtime renders one virtual canvas and crops it for outputs.
