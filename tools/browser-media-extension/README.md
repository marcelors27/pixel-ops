# Pixel OPs Browser Bridge Extension

Local Chrome/Brave/Edge/Arc extension that sends compact now-playing state to Pixel OPs and can import a CrossHero browser session into Config Studio.

## Install

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click "Load unpacked".
4. Select this folder: `tools/browser-media-extension`.
5. Reload the extension whenever its files change.

## CrossHero session

1. Keep CrossHero signed in in the same browser profile.
2. Open Config Studio at `http://localhost:5174`.
3. Open or refresh an authenticated CrossHero tab. The session is imported automatically.
4. Alternatively, when Studio itself is open in Chrome, select CrossHero and click **Importar sessão do navegador**.

The cookie is sent only to the local Config Studio endpoint and stored in the repository `.env`. It is never displayed or written to JSON configuration. An open CrossHero tab refreshes the local session periodically, so the flow also works when Config Studio runs as an Electron app.

The default endpoint is:

```text
http://127.0.0.1:47832/media/now-playing
```

If you set `integrations.media.browser_extension.token`, put the same value in `PIXEL_OPS_TOKEN` inside `service-worker.js`.

## Data sent

For media, the extension sends only current local presence: provider, title, artist/source, album, URL, artwork URL, and playing state. For CrossHero, it sends only cookies for `crosshero.com`, only after the explicit import action, and only to the fixed local Studio endpoint. It does not send comments, playlists, recommendations, page contents, or browser history.
