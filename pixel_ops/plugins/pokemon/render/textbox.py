from __future__ import annotations


def ambient_text(message: str, limit: int = 84) -> str:
    compact = " ".join(message.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."
