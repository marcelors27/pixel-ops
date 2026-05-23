# 0013 - Config Studio Discovers Plugin-Owned Config

Status: Accepted

## Context

Config Studio originally loaded a fixed list of JSON files. That made the UI tightly coupled to the Pokemon plugin and made new visual plugins require code changes in the Studio before their config could be edited.

The runtime already treats visual plugins and integrations as discoverable boundaries. The configuration UI should follow that model.

## Decision

Config Studio exposes a local development API that builds a config manifest from the repository:

- core configs are always available;
- visual plugins are detected from `pixel_ops/plugins/*/plugin.py`;
- plugin JSON files are loaded only when that visual plugin is selected;
- integration plugins are detected from `pixel_ops/integrations/*/plugin.py`;
- integration sidecar configs are loaded only when the related integration is enabled.

The React app loads `/api/config-manifest` first, lets the user select visual plugins, and then loads `/api/config?plugins=...`.

Saving still writes only known JSON config files in the repo. It does not write secrets or arbitrary paths.

## Consequences

Config Studio can support future visual plugins without hard-coding every plugin config in the frontend.

Plugin-specific panels can remain specialized, but the config loading contract is no longer Pokemon-only.

Core config stays stable and always loaded:

- display;
- integrations;
- people.

New integration sidecar files need an explicit manifest mapping so the UI does not accidentally expose unrelated files.
