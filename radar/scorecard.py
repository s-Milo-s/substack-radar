"""Weekly scorecard from a Substack stats CSV export.

Substack's export columns vary by report, so columns are matched loosely:
  title   : title | post title | name | note | text
  date    : date | post date | published | publish date | sent | created
  url     : url | link | post url
  type    : type | content type
  lane    : lane (optional; otherwise inferred from the essays you queued Notes for)
  subs    : every column mentioning new/gained + subscriber/signup/subscription (summed;
            'unsubscribe' columns are ignored)
  views   : views | opens | impressions | recipients (first match)
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ALIASES = {
    "title": ["title", "post title", "name", "note", "text", "subject"],
    "date": ["date", "post date", "published", "publish date", "published at", "sent", "sent at",
             "created", "created at"],
    "url": ["url", "link", "post url"],
    "type": ["type", "content type", "post type"],
    "lane": ["lane"],
    "views": ["views", "total views", "opens", "impressions", "recipients"],
}


@dataclass
class Row:
    title: str
    date: datetime | None
    url: str
    kind: str
    lane: str
    subs: float
    views: float


def _norm(h: str) -> str:
    return re.sub(r"[^a-z ]", "", h.lower().replace("_", " ")).strip()


def _num(v: str | None) -> float:
    v = (v or "").replace(",", "").replace("%", "").strip()
    try:
        return float(v)
    except ValueError:
        return 0.0


def _date(v: str | None) -> datetime | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%d %b %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _subs_columns(headers: list[str]) -> list[str]:
    cols = []
    for h in headers:
        n = _norm(h)
        if "unsub" in n:
            continue
        if n in ("subscribes", "signups", "subscribers gained", "new subscribers") or (
                re.search(r"\b(new|gained?)\b", n) and re.search(r"sub|signup|sign up", n)):
            cols.append(h)
    return cols


def parse(path: Path, lane_for: dict[str, str] | None = None) -> tuple[list[Row], list[str]]:
    """Returns rows and the subscriber columns used (empty -> nothing to score)."""
    lane_for = lane_for or {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        by_norm = {_norm(h): h for h in headers}
        col = {k: next((by_norm[a] for a in names if a in by_norm), None) for k, names in ALIASES.items()}
        subs_cols = _subs_columns(headers)
        rows = []
        for r in reader:
            title = (r.get(col["title"]) or "") if col["title"] else ""
            url = (r.get(col["url"]) or "") if col["url"] else ""
            lane = (r.get(col["lane"]) or "").strip() if col["lane"] else ""
            rows.append(Row(
                title=title.strip(), url=url.strip(),
                date=_date(r.get(col["date"])) if col["date"] else None,
                kind=((r.get(col["type"]) or "") if col["type"] else "").strip().lower() or "post",
                lane=lane or _infer_lane(title, url, lane_for),
                subs=sum(_num(r.get(c)) for c in subs_cols),
                views=_num(r.get(col["views"])) if col["views"] else 0.0,
            ))
    return rows, subs_cols


def _infer_lane(title: str, url: str, lane_for: dict[str, str]) -> str:
    """lane_for maps essay URLs and essay slugs (e.g. 'nominal') to lanes."""
    if url and url.rstrip("/") in lane_for:
        return lane_for[url.rstrip("/")]
    text = f"{title} {url}".lower()
    for key, lane in lane_for.items():
        if "://" not in key and key.lower() in text:
            return lane
    return "unknown"


def report(rows: list[Row], subs_cols: list[str], today: datetime | None = None, top: int = 5) -> str:
    if not subs_cols:
        return ("*Scorecard*: couldn't find a new-subscribers column in this export. "
                "Columns need a name like 'New subscribers' or 'Subscribes'.")
    lines = ["*Weekly scorecard*"]
    best = sorted((r for r in rows if r.subs > 0), key=lambda r: -r.subs)[:top]
    if best:
        lines.append("Top drivers of new subscribers:")
        for r in best:
            label = r.title[:70] or r.url or "(untitled)"
            lines.append(f"• +{r.subs:g} {r.kind}: {label} [{r.lane}]")
    else:
        lines.append("No row drove new subscribers in this export.")

    by_lane: dict[str, float] = defaultdict(float)
    for r in rows:
        by_lane[r.lane] += r.subs
    total = sum(by_lane.values()) or 1
    lines.append("By lane: " + ", ".join(
        f"{lane} +{n:g} ({n / total:.0%})" for lane, n in sorted(by_lane.items(), key=lambda x: -x[1])))

    dated = [r for r in rows if r.date]
    if dated:
        today = today or max(r.date for r in dated)
        week, prev = today - timedelta(days=7), today - timedelta(days=14)
        cur, old = defaultdict(float), defaultdict(float)
        for r in dated:
            if r.date > week:
                cur[r.lane] += r.subs
            elif r.date > prev:
                old[r.lane] += r.subs
        growth = sorted(((lane, cur[lane] - old[lane]) for lane in set(cur) | set(old)), key=lambda x: -x[1])
        if growth:
            lane, delta = growth[0]
            lines.append(f"Growing fastest: *{lane}* ({cur[lane]:g} this week vs {old[lane]:g} the week before, "
                         f"{delta:+g})")
    else:
        lines.append("(No date column, so no week-over-week growth.)")
    return "\n".join(lines)
