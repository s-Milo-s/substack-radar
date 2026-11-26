"""Paths, .env loading and feeds.yaml reading."""
from __future__ import annotations

import os
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / "feeds.yaml"


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value lines). Real env vars win over the file."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_feeds(path: Path = FEEDS) -> dict:
    data = YAML(typ="safe").load(path.read_text()) or {}
    data.setdefault("publications", [])
    data.setdefault("watch", [])
    data.setdefault("lanes", [])
    data.setdefault("me", {})
    return data
