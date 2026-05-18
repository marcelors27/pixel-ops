# 0011 - Graphify Artifacts Document The Codebase Map

Status: Accepted

## Context

The codebase has grown from a single Pokemon-style dashboard into a plugin runtime with integrations, event normalization, hot reload, and ambient world simulation.

Agents need a compact map of relationships before making changes.

## Decision

Graphify artifacts are generated under `graphify-out/`.

Current outputs:

- `graphify-out/graph.html`
- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/manifest.json`
- `graphify-out/cost.json`

`.graphifyignore` excludes cache, generated outputs, heavy assets, and secrets from graph generation.

## Consequences

Agents should use `graphify-out/GRAPH_REPORT.md` or `graphify-out/graph.json` as a navigation aid when working across modules.

The current graph is AST-only because no LLM API key was available in the shell during generation. It is still useful for structural coupling and bridge nodes.

Regenerate the graph after meaningful architecture changes.

