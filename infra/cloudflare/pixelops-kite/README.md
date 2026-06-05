# PixelOpsKite

PixelOpsKite is the webhook relay for Pixel OPs. It receives provider webhooks in Cloudflare Workers and streams normalized envelopes to the local Pixel Ops runtime over WebSocket.

Like a kite in a storm, it flies outside the local network, catches webhook lightning, and sends only compact ambient signals back down the line.

## Deploy

```bash
cd infra/cloudflare/pixelops-kite
npm install
npx wrangler login
npx wrangler secret put PIXEL_OPS_KITE_TOKEN
npx wrangler secret put ZOOM_WEBHOOK_SECRET_TOKEN
npx wrangler deploy
```

After deploy:

- Use `https://<worker-host>/webhooks/zoom` as the Zoom Event Subscription endpoint.
- Use `wss://<worker-host>/connect` in `pixel_ops/config/integrations.json`.
- Use the same `PIXEL_OPS_KITE_TOKEN` locally in `.env`.

## Endpoints

- `POST /webhooks/zoom`: Zoom Meeting webhook receiver.
- `GET /state`: compact relay state for diagnostics.
- `GET /connect`: authenticated WebSocket stream for local Pixel Ops.
- `GET /health`: health check.

PixelOpsKite stores only compact ambient state. It does not keep raw webhook payloads.
