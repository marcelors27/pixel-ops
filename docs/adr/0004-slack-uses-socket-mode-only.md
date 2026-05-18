# 0004 - Slack Uses Socket Mode Only

Status: Accepted

## Context

Opening a public IP, tunnel, TLS endpoint, or reverse proxy just to receive Slack events is impractical for a local ambient display.

Slack supports Socket Mode, where the app opens an outbound WebSocket connection to Slack.

## Decision

Slack integration uses Socket Mode only.

The implementation lives in:

- `pixel_ops/integrations/slack/socket_mode.py`
- `pixel_ops/integrations/slack/plugin.py`
- `pixel_ops/integrations/slack/classifier.py`

Webhook/Event Subscription HTTP fallback is intentionally not implemented.

## Consequences

Required secrets:

- `PIXEL_OPS_SLACK_APP_TOKEN`
- `PIXEL_OPS_SLACK_BOT_TOKEN`

Slack app setup must enable Socket Mode and create an app-level token with `connections:write`.

If webhook support is ever needed, it should be introduced through a new ADR because it changes local deployment assumptions.

