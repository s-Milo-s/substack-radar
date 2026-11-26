"""Edit feeds.yaml in place (round-trip: comments and formatting survive)."""
from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from .config import FEEDS
from .substack import base_url


def _yaml() -> YAML:
    y = YAML()  # round-trip mode
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def add_publication(url: str, name: str, tier: str = "peer", lane: str | None = None,
                    path: Path = FEEDS) -> str | None:
    """Append a publication. Returns the new YAML text, or None if it's already there."""
    y = _yaml()
    doc = y.load(path.read_text())
    pubs = doc["publications"]
    url = base_url(url)
    if any(base_url(p["url"]) == url for p in pubs):
        return None
    entry = CommentedMap(name=name, url=url, tier=tier)
    if lane:
        entry["lane"] = lane
    entry.fa.set_flow_style()
    pubs.append(entry)
    out = StringIO()
    y.dump(doc, out)
    return out.getvalue()
