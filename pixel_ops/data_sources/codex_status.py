from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from pixel_ops.data_sources.ai_activity import AIActivitySnapshot, AIActivityTask


def thread_activity(status: dict, last_turn: str | None = None) -> tuple[str, str]:
    kind = status.get("type")
    flags = status.get("activeFlags", [])
    if kind == "systemError":
        return "attention", "system_error"
    if kind == "active":
        if "waitingOnApproval" in flags:
            return "attention", "approval"
        if "waitingOnUserInput" in flags:
            return "attention", "input"
        return "processing", "running"
    if kind == "idle":
        if last_turn in ("failed", "interrupted"):
            return "attention", "error" if last_turn == "failed" else "interrupted"
        if last_turn == "completed":
            return "ready", "completed"
        if last_turn == "inProgress":
            return "processing", "running"
    return "unknown", "no_session"


def activity_snapshot(states: list[tuple[str, str]], now: datetime) -> AIActivitySnapshot:
    counts = {key: sum(state == key for state, _ in states) for key in ("attention", "processing", "ready")}
    # Pending requests are actionable now; interrupted/failed turns are history.
    for state, reason in states:
        if state == "attention" and reason in ("approval", "input", "system_error"):
            return AIActivitySnapshot("codex", state, reason, now, **counts)
    for key in ("processing", "attention", "unknown", "ready"):
        reason = next((reason for state, reason in states if state == key), None)
        if reason is not None:
            return AIActivitySnapshot("codex", key, reason, now, **counts)
    return AIActivitySnapshot("codex", "unknown", "no_session", now)


class CodexStatusSource:
    """Observe local turn metadata and the existing shared daemon.

    Never starts/resumes threads or answers server requests. Polls only loaded
    root sessions, with turn items explicitly excluded from history queries.
    """

    def __init__(self, socket_path: str = "", thread_id: str = "", poll_seconds: float = 2, timeout_seconds: float = 4):
        codex_dir = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        self.codex_dir = codex_dir
        self.observe_desktop = not socket_path
        self.socket_path = str(Path(socket_path).expanduser()) if socket_path else str(codex_dir / "app-server-control/app-server-control.sock")
        self.thread_id = thread_id.strip()
        self.poll_seconds = max(1.0, float(poll_seconds))
        self.timeout_seconds = max(0.5, float(timeout_seconds))

    def current(self, now: datetime) -> AIActivitySnapshot:
        states = {}
        if self.observe_desktop:
            try:
                states.update(self._desktop_states(now))
            except (OSError, sqlite3.Error, ValueError):
                # A separate daemon's completed session cannot prove the desktop
                # is ready when its local state could not be observed.
                states["desktop-unavailable"] = ("unknown", "disconnected")
        desktop_observed = bool(states)
        server_states = self._server_states()
        if server_states is not None:
            for tid, state in server_states.items():
                # Desktop metadata includes the current stdio runner. Old idle
                # daemon results must not replace its most recent outcome.
                if desktop_observed and state in (
                    ("ready", "completed"), ("attention", "interrupted"),
                    ("attention", "error"),
                ):
                    continue
                if tid in states:
                    combined = activity_snapshot([states[tid], state], now)
                    state = (combined.state, combined.reason)
                states[tid] = state
        elif not states:
            return AIActivitySnapshot("codex", "unknown", "disconnected", now)
        snapshot = activity_snapshot(list(states.values()), now)
        tasks = tuple(AIActivityTask(tid, *state) for tid, state in sorted(states.items())
                      if tid != "desktop-unavailable")
        return replace(snapshot, tasks=tasks)

    def _desktop_states(self, now: datetime) -> dict[str, tuple[str, str]]:
        """Read only lifecycle columns; desktop stdio sessions aren't in the daemon.

        The IPC connection is a liveness check, without sending requests. Recent
        non-archived root sessions participate for 30 minutes after activity.
        Persisted turns do not expose approval/input flags; those require the
        live app-server transport.
        """
        endpoint = self.codex_dir / "ipc/ipc.sock"
        if not endpoint.exists():
            return {}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(min(self.timeout_seconds, 0.5))
            probe.connect(str(endpoint))
        state_uri = (self.codex_dir / "state_5.sqlite").resolve().as_uri() + "?mode=ro"
        history_uri = (self.codex_dir / "thread_history_1.sqlite").resolve().as_uri() + "?mode=ro"
        db = sqlite3.connect(history_uri, uri=True, timeout=0.1)
        try:
            db.execute("ATTACH DATABASE ? AS metadata", (state_uri,))
            rows = db.execute("""
                SELECT t.id, (
                    SELECT status FROM thread_turns h WHERE h.thread_id = t.id
                    ORDER BY rollout_ordinal DESC LIMIT 1
                )
                FROM metadata.threads t
                WHERE t.archived = 0 AND t.source IN ('cli', 'vscode')
                  AND t.updated_at >= ? AND (? = '' OR t.id = ?)
                ORDER BY t.updated_at DESC LIMIT 100
            """, (now.timestamp() - 1800, self.thread_id, self.thread_id)).fetchall()
        finally:
            db.close()
        states = {}
        for index, (tid, status) in enumerate(rows):
            state = thread_activity({"type": "idle"}, status)
            # Retain every running root, but only the newest root's terminal
            # result. Finishing a new task must not resurrect an older failure.
            if index == 0 or state[0] in ("processing", "unknown"):
                states[tid] = state
        return states

    def _server_states(self) -> dict[str, tuple[str, str]] | None:
        import websocket

        raw = None
        connection = None
        deadline = time.monotonic() + self.timeout_seconds
        sequence = 0
        try:
            raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            raw.settimeout(self.timeout_seconds)
            raw.connect(self.socket_path)
            connection = websocket.create_connection("ws://localhost", socket=raw, timeout=self.timeout_seconds)

            def call(method: str, params: dict) -> dict:
                nonlocal sequence
                sequence += 1
                request_id = sequence
                connection.send(json.dumps({"id": request_id, "method": method, "params": params}))
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Codex status deadline")
                    connection.settimeout(remaining)
                    message = json.loads(connection.recv())
                    if message.get("id") == request_id and ("result" in message or "error" in message):
                        if "error" in message:
                            raise ValueError("Codex status RPC failed")
                        return message["result"]

            call("initialize", {"clientInfo": {"name": "pixel_ops_status", "version": "1.0"}, "capabilities": {"experimentalApi": True}})
            connection.send(json.dumps({"method": "initialized"}))
            ids = []
            cursor = None
            while True:
                page = call("thread/loaded/list", {"cursor": cursor, "limit": 100})
                ids.extend(page["data"])
                cursor = page.get("nextCursor")
                if not cursor:
                    break
                if len(ids) >= 500:
                    raise ValueError("Too many sessions to observe safely")
            if self.thread_id:
                ids = [tid for tid in ids if tid == self.thread_id]
            states = {}
            for tid in ids:
                thread = call("thread/read", {"threadId": tid, "includeTurns": False})["thread"]
                source = thread.get("source")
                if not self.thread_id and (thread.get("ephemeral") or (isinstance(source, dict) and "subAgent" in source)):
                    continue
                status = thread.get("status", {})
                last_turn = None
                if status.get("type") == "idle" and not thread.get("ephemeral"):
                    turns = call("thread/turns/list", {"threadId": tid, "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"}).get("data", [])
                    last_turn = turns[0].get("status") if turns else None
                states[tid] = thread_activity(status, last_turn)
            return states
        except (OSError, ValueError, KeyError, TypeError, websocket.WebSocketException):
            return None
        finally:
            if connection is not None:
                connection.close(timeout=0)
            if raw is not None:
                raw.close()
