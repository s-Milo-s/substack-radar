"""
Find new writers by crawling Substack's recommendation graph out from your seeds.

Signal: a publication recommended by several of your seeds shares their audience.
Claude then checks topical fit and lane from recent post titles. Tier comes from the
public subscriber count / bestseller badge when Substack exposes it, else from Claude.

All endpoint access goes through radar.substack; any failure skips that publication.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import llm, substack
from .schemas import Picks
from .substack import Rec, Size, base_url

log = logging.getLogger("radar.discover")

ACTIVE_DAYS = 60          # skip candidates with no post in this many days
ANCHOR_MULTIPLE = 10      # anchor = at least this many times your subscriber count
DEFAULT_MY_SUBS = 500     # used when feeds.yaml has no me.subscribers


@dataclass
class Candidate:
    rec: Rec
    voters: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)
    last_post: str | None = None


def crawl(seeds: list[str], hops: int = 2, exclude: set[str] = frozenset(),
          hop2_limit: int = 30) -> dict[str, Candidate]:
    """Breadth-first over 'recommends' edges. Returns candidate url -> Candidate."""
    known = {base_url(u) for u in seeds} | {base_url(u) for u in exclude}
    cands: dict[str, Candidate] = {}
    # frontier entries: (recommender url, publication id). Resolve seed ids up front so a
    # seed listed as x.substack.com isn't re-suggested under its custom domain.
    frontier = [(base_url(u), substack.publication_id(u)) for u in seeds]
    for url, pid in frontier:
        if not pid:
            log.info("no publication id for %s, skipping", url)
    frontier = [(u, pid) for u, pid in frontier if pid]
    known_ids = {pid for _, pid in frontier}
    for hop in range(hops):
        found = []
        for url, pid in frontier:
            for rec in substack.recommendations(pid):
                if rec.url in known or rec.pub_id in known_ids:
                    continue
                c = cands.setdefault(rec.url, Candidate(rec))
                c.voters.add(url)
                found.append(rec.url)
        # only expand the next hop from candidates that look strong
        strong = sorted({u for u in found if len(cands[u].voters) >= 2},
                        key=lambda u: -len(cands[u].voters))[:hop2_limit]
        frontier = [(u, cands[u].rec.pub_id) for u in strong]
        log.info("hop %d: %d candidates so far, expanding %d", hop + 1, len(cands), len(frontier))
    return cands


def enrich(c: Candidate, n: int = 8) -> None:
    posts = substack.archive(c.rec.url, limit=n)
    c.titles = [p.get("title") or "" for p in posts]
    c.last_post = posts[0].get("post_date") if posts else None


def is_active(c: Candidate, now: datetime | None = None) -> bool:
    if not c.last_post:
        return False
    now = now or datetime.now(timezone.utc)
    when = datetime.fromisoformat(c.last_post.replace("Z", "+00:00"))
    return now - when < timedelta(days=ACTIVE_DAYS)


def size_tier(size: Size, my_subs: int | None) -> str | None:
    """anchor/peer from real size data, or None if Substack didn't expose any."""
    if size.bestseller_tier:
        return "anchor"
    if size.subscribers is None:
        return None
    return "anchor" if size.subscribers >= ANCHOR_MULTIPLE * (my_subs or DEFAULT_MY_SUBS) else "peer"


def discover(publications: list[dict], hops: int = 2, max_candidates: int = 25,
             exclude: list[str] = ()) -> list[Candidate]:
    seeds = [p["url"] for p in publications]
    cands = crawl(seeds, hops=hops, exclude=set(exclude))
    ranked = sorted(cands.values(), key=lambda c: -len(c.voters))[:max_candidates]
    for c in ranked:
        enrich(c)
    active = [c for c in ranked if is_active(c)]
    log.info("%d of %d top candidates posted in the last %d days",
             len(active), len(ranked), ACTIVE_DAYS)
    return active


def check_picks(picks: Picks, n: int, lanes: list[str]) -> list[str]:
    problems = [f"pick index {p.i} out of range 0..{n - 1}" for p in picks.picks if not 0 <= p.i < n]
    allowed = set(lanes) | {"other"}
    problems += [f"lane '{p.lane}' is not one of {sorted(allowed)}"
                 for p in picks.picks if lanes and p.lane not in allowed]
    return problems


def score(cands: list[Candidate], topics_hint: str, lanes: list[str],
          my_subs: int | None = None, limit: int = 8) -> list[dict]:
    if not cands:
        return []
    listing = "\n".join(
        f"{i}: {c.rec.name} ({c.rec.url}) | recommended by {len(c.voters)} of the writer's "
        f"publications | about: {c.rec.about} | recent: {'; '.join(c.titles[:6])}"
        for i, c in enumerate(cands))
    lane_list = ", ".join(lanes) or "(none configured)"
    out = llm.ask(f"""The writer publishes teardowns of startups across sectors (AI, infra, hard tech, fintech) from a software engineer's lens.
Their topics so far: {topics_hint}
Their sector lanes: {lane_list}

Candidate Substacks found through their niche's recommendation graph:
{listing}

Pick the ones worth following and engaging with. Judge topical fit from titles, and treat
'recommended by' as audience-overlap strength. Skip off-topic ones. For each pick give the
lane it fits best (one of the lanes above, or "other") and a tier guess
(anchor = much bigger audience, peer = similar small writer, news = news/link roundup).
Spread picks across lanes where quality allows. Sort best first, at most {limit}.""",
        Picks, check=lambda p: check_picks(p, len(cands), lanes))
    if out is None:
        return []
    picks = []
    for p in out.picks:
        if not 0 <= p.i < len(cands):
            continue
        c = cands[p.i]
        sz = substack.size(c.rec.handle)
        tier = size_tier(sz, my_subs)
        picks.append({
            "name": c.rec.name, "url": c.rec.url, "recommended_by": len(c.voters),
            "fit": p.fit, "why": p.why,
            "lane": p.lane if p.lane in lanes else "other",
            "tier": tier or p.tier,
            "tier_source": "size" if tier else "llm",
            "subscribers": sz.subscribers, "bestseller": sz.bestseller_tier,
        })
    return picks[:limit]
