# 0023 - PixelOpsKite Relays Webhooks Over WebSocket

Status: Accepted

## Context

Some providers require a public webhook endpoint, but Pixel OPs is designed to run locally without exposing the user's machine to the internet.

Zoom Pro can use Meeting webhooks for live participant joins/leaves, while live participant polling requires Dashboard APIs that are not available to all accounts.

## Decision

PixelOpsKite is the public webhook relay for Pixel OPs.

The name is intentional: Kite is the small public surface that flies outside the local network, catches webhook lightning, and sends compact ambient signals back to the local runtime.

Kite runs as a Cloudflare Worker. Providers send webhooks to Kite, and local Pixel OPs opens an outbound WebSocket connection to Kite. Kite streams compact provider envelopes to the local runtime.

Kite must not store raw webhook payloads. It should keep only compact, provider-neutral or provider-minimal state with short TTLs. The local runtime remains responsible for normalizing envelopes into `AmbientSignal`, `WorkEvent`, and `CompanionSnapshot`.

## Consequences

The local runtime does not need a public IP, tunnel, or inbound firewall rule.

Webhook-only providers can integrate without leaking provider-specific UI into visual plugins.

Cloudflare and provider credentials remain secrets. Runtime URLs, enables, and reconnect settings stay in JSON config.
