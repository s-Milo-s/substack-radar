"""Tiny JSON state: seen ids, the essay Note queue, writers already suggested."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "state.json"
SEEN_LIMIT = 2000


def _defaults() -> dict:
    return {"seen": [], "note_queue": [], "posted_notes": [], "rejected_writers": [],
            "last_lanes": [], "essays": {}}


def load(path: Path = PATH) -> dict:
    state = _defaults()
    if path.exists():
        state.update(json.loads(path.read_text()))
    return state


def save(state: dict, path: Path = PATH) -> None:
    state["seen"] = state["seen"][-SEEN_LIMIT:]
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def unseen(items: list[dict], state: dict) -> list[dict]:
    """Items whose id isn't in state['seen'], de-duplicated within the batch too."""
    seen = set(state["seen"])
    out = []
    for item in items:
        if item["id"] and item["id"] not in seen:
            seen.add(item["id"])
            out.append(item)
    return out


def mark_seen(state: dict, ids: list[str]) -> None:
    known = set(state["seen"])
    state["seen"].extend(i for i in ids if i and i not in known)


def pop_note(state: dict) -> dict | None:
    """Take the next queued Note (FIFO) and move it to posted_notes."""
    if not state["note_queue"]:
        return None
    note = state["note_queue"].pop(0)
    state["posted_notes"].append(note)
    return note
