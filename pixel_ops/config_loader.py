from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml


def load_config(path: Path) -> dict:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def config_path(path: Path) -> Path:
    if path.suffix in (".yaml", ".yml"):
        json_path = path.with_suffix(".json")
        if json_path.exists():
            return json_path
    return path


def load_config_prefer_json(path: Path) -> dict:
    return load_config(config_path(path))


@dataclass
class ConfigWatcher:
    paths_fn: Callable[[], list[Path]]
    _snapshot: dict[Path, int | None] | None = None

    def paths(self) -> list[Path]:
        return [config_path(path) for path in self.paths_fn()]

    def changed(self) -> bool:
        current = self._current_snapshot()
        if self._snapshot is None:
            self._snapshot = current
            return False
        if current != self._snapshot:
            self._snapshot = current
            return True
        return False

    def reset(self) -> None:
        self._snapshot = self._current_snapshot()

    def _current_snapshot(self) -> dict[Path, int | None]:
        snapshot: dict[Path, int | None] = {}
        for path in self.paths():
            try:
                stat = path.stat()
            except OSError:
                snapshot[path] = None
                continue
            snapshot[path] = stat.st_mtime_ns
        return snapshot
