# 0019 - Media Now Playing Is Local Presence

Status: Accepted

## Context

Pixel OPs can benefit from showing what is currently playing without turning the screen into a music app, browser monitor, or notification feed.

Spotify and YouTube playback state is local user presence. It may come from desktop automation or browser state, and it should not expose watch history, playlists, comments, recommendations, or raw browser activity.

## Decision

Media now-playing is a runtime integration loaded from JSON config under `pixel_ops/config/integrations.json`.

The integration owns local collection in `pixel_ops/data_sources/media.py` and exposes a compact provider-neutral `MediaNowPlaying` snapshot. Visual plugins consume the snapshot through `PixelOpsApp` and may render a `media` / `now_playing` layout window with provider, track title, and artist/source.

Spotify is read locally on macOS through AppleScript. YouTube browser support is best-effort local automation and only reads the current watch tab title when browser automation allows it.

## Consequences

Layout visibility must not enable or disable polling. Removing the `media` window only hides the HUD region.

If Spotify, a browser, or automation permission is unavailable, the data source returns no snapshot instead of crashing the display loop.

The display remains ambient: no playlists, queues, recommendations, comments, lyrics, thumbnails, or browser feed content are rendered.
