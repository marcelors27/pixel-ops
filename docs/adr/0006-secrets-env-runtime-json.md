# 0006 - Secrets Stay In Env, Runtime Toggles Move To JSON

Status: Accepted

## Context

The system needs tokens for Slack, Discord, GitHub, and OpenAI, but most runtime settings are not secrets and should be editable from JSON.

Keeping all config in `.env` makes future graphical editing difficult and increases the chance of exposing secrets when sharing examples.

## Decision

`.env` and `.env.example` are reserved for secrets.

Current secret env vars:

- `PIXEL_OPS_SLACK_APP_TOKEN`
- `PIXEL_OPS_SLACK_BOT_TOKEN`
- `PIXEL_OPS_DISCORD_BOT_TOKEN`
- `PIXEL_OPS_GITHUB_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_ADMIN_KEY`
- `OPENWEATHERMAP_API_KEY`

Runtime toggles, provider enables, polling intervals, calendar URLs, repo lists, weather city, and AI behavior live in JSON config.

## Consequences

Provider plugins can still name the env var that contains a secret, for example `token_env`.

New non-secret settings should not be added to `.env`.

The graphify ignore rules exclude `.env` and `.env.example` from the architecture graph.
