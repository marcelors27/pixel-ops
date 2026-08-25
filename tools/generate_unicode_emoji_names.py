from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


LINE = re.compile(r"^([0-9A-F ]+)\s*;\s*[^#]+#\s+\S+\s+E\d+(?:\.\d+)?\s+(.+?)\s*$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the CrossHero HUD Unicode emoji name table.")
    parser.add_argument("source", type=Path, help="Official Unicode emoji-test.txt")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    names: dict[str, str] = {}
    for line in args.source.read_text(encoding="utf-8").splitlines():
        match = LINE.match(line)
        if not match:
            continue
        key = "-".join(f"{int(codepoint, 16):X}" for codepoint in match.group(1).split())
        names[key] = match.group(2)
    args.destination.write_text(
        json.dumps(names, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
