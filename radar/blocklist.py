"""Pseudonymity guard: reject drafts containing any term from blocklist.txt (gitignored).

blocklist.txt: one term per line (real name, employer, city, ...). '#' starts a comment.
Matching is case-insensitive and on word boundaries, so 'Ann' doesn't hit 'annual'.
The terms themselves are never sent to the LLM.
"""
from __future__ import annotations

import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "blocklist.txt"


def load(path: Path = PATH) -> list[str]:
    if not path.exists():
        return []
    terms = []
    for line in path.read_text().splitlines():
        term = line.split("#", 1)[0].strip()
        if term:
            terms.append(term)
    return terms


def hits(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms
            if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, re.IGNORECASE)]
