# 0021 - Local Runtime State Uses SQLite

Status: Accepted

## Context

JSON remains the primary runtime configuration format because it is easy to edit, diff, hot reload, and expose through Config Studio.

Some data now behaves differently from configuration:

- recently discovered Discord companions;
- Pokemon captured during ambient encounters;
- runtime cache entries that may need TTL or cleanup;
- saved layout profiles for quickly switching equipment, resolution, and window placement.

These values are learned or created during runtime. Keeping them in config files makes the config directory carry local state and makes future query, retention, and cleanup behavior awkward.

## Decision

Local runtime state and structured cache use SQLite under:

```text
pixel_ops/state/pixel_ops.sqlite
```

The state boundary is:

- JSON config remains the source of truth for declarative runtime settings and the active display configuration.
- SQLite stores local state, cache indexes, captured Pokemon, recently seen provider people, and saved layout profiles.
- Large blobs such as sprites, GIFs, thumbnails, and downloaded API payloads remain filesystem cache files.

The initial state tables cover:

- `discord_people`;
- `pokemon_captures`;
- `runtime_cache`;
- `layout_profiles`.

Legacy JSON state files may be imported for compatibility, but runtime code should not add new cache/state files under `pixel_ops/config/`.

## Consequences

The Config Studio can keep writing known JSON config files while future state-oriented APIs read and write SQLite records.

Layout profiles are user state, not cache. Applying a layout profile should still update the active JSON display config so the runtime can keep its current hot reload behavior.

SQLite files are local runtime artifacts and should not be committed.
