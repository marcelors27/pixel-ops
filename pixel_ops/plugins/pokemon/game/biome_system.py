from __future__ import annotations


DEFAULT_REPO_BIOMES = {
    "backend": ("rock", "steel", "ground"),
    "frontend": ("electric", "psychic", "fairy"),
    "infra": ("dragon", "ghost", "dark"),
}

TIME_TYPES = {
    "morning": ("grass", "normal"),
    "afternoon": ("fire", "fighting", "normal"),
    "dawn": ("ghost", "psychic"),
    "night": ("ghost", "dark"),
}


def repo_types(repo: str | None, config: dict | None = None) -> tuple[str, ...]:
    if not repo:
        return ()
    repo_key = repo.lower()
    configured = (config or {}).get(repo_key)
    if configured:
        return tuple(str(item) for item in configured)
    return DEFAULT_REPO_BIOMES.get(repo_key, ())


def time_types(phase: str) -> tuple[str, ...]:
    return TIME_TYPES.get(phase, ())
