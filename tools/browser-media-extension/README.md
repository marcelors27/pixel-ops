# Pixel OPs Browser Media Extension

Local Chrome/Brave/Edge/Arc extension that sends compact now-playing state to Pixel OPs.

## Install

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click "Load unpacked".
4. Select this folder: `tools/browser-media-extension`.
5. Keep Pixel OPs running with the `media` integration enabled.

The default endpoint is:

```text
http://127.0.0.1:47832/media/now-playing
```

If you set `integrations.media.browser_extension.token`, put the same value in `PIXEL_OPS_TOKEN` inside `service-worker.js`.

## Data sent

The extension sends only current local media presence: provider, title, artist/source, album, URL, artwork URL, and playing state. It does not send comments, playlists, recommendations, page contents, or browser history.
