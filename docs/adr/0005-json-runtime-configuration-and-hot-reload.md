# 0005 - JSON Runtime Configuration And Hot Reload

Status: Accepted

## Context

The project is expected to have a future React configuration UI. Environment variables are awkward for graphical editing and cannot represent nested runtime settings well.

The display should also be adjustable while running where safe.

## Decision

JSON is the primary runtime config format.

Primary config files:

- `pixel_ops/config/display.json`
- `pixel_ops/config/people.json`
- `pixel_ops/config/integrations.json`
- `pixel_ops/plugins/pokemon/game.json`
- `pixel_ops/plugins/pokemon/pokemon.json`

`pixel_ops/config_loader.py` prefers JSON when both JSON and YAML versions exist. Long-running app modes use `ConfigWatcher` to detect changes.

When integration config changes, `pixel_ops/main.py` closes and rebuilds the integration runtime.

## Consequences

The React UI can eventually edit JSON directly or through an API.

Some changes still require restart:

- output mode;
- display dimensions;
- CLI choices;
- dependency installation;
- process-level secrets.

YAML files should be treated as compatibility fallback, not the source of truth.

