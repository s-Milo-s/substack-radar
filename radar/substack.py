"""Substack's public-but-undocumented JSON endpoints, isolated in one place.

If Substack changes an endpoint, only this file should need to change. Each fetcher
has a pure `parse_*` twin so tests can run against recorded fixtures with no network.
See docs/endpoints.md for what each endpoint actually returns.

Read-only: nothing here (or anywhere in radar/) writes to Substack.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from . import net

DAY = 86400


def base_url(url: str) -> str:
    """https://host for any publication URL (with or without scheme/path)."""
    u = urlparse(url if "://" in url else "https://" + url)
    return f"https://{u.netloc.lower()}"


# --- archive: <pub>/api/v1/archive ------------------------------------------------

def parse_archive(data: Any) -> list[dict]:
    """Archive returns {"posts": [...], "nextCursor": ...}; older shape was a bare list."""
    if isinstance(data, dict):
        data = data.get("posts")
    return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []


def archive(pub_url: str, limit: int = 1) -> list[dict]:
    data = net.get_json(f"{base_url(pub_url)}/api/v1/archive?sort=new&limit={limit}", ttl=DAY)
    return parse_archive(data)


def publication_id(pub_url: str) -> int | None:
    posts = archive(pub_url, limit=1)
    return posts[0].get("publication_id") if posts else None


# --- recommendations: substack.com/api/v1/recommendations/from/<id> ----------------

@dataclass
class Rec:
    name: str
    url: str
    about: str
    pub_id: int | None
    handle: str | None   # author's handle, used for the size lookup


def parse_recommendations(data: Any) -> list[Rec]:
    out = []
    for rec in data if isinstance(data, list) else []:
        pub = rec.get("recommendedPublication") or {}
        sub, custom = pub.get("subdomain"), pub.get("custom_domain")
        url = f"https://{custom}" if custom else (f"https://{sub}.substack.com" if sub else None)
        if not url:
            continue
        user = pub.get("primaryUser") or pub.get("author") or {}
        out.append(Rec(
            name=pub.get("name") or sub or url,
            url=base_url(url),
            about=(pub.get("hero_text") or rec.get("description") or "")[:300],
            pub_id=pub.get("id") or rec.get("recommended_publication_id"),
            handle=user.get("handle"),
        ))
    return out


def recommendations(pub_id: int) -> list[Rec]:
    data = net.get_json(f"https://substack.com/api/v1/recommendations/from/{pub_id}", ttl=7 * DAY)
    return parse_recommendations(data)


# --- size: substack.com/api/v1/user/<handle>/public_profile ------------------------

@dataclass
class Size:
    subscribers: int | None   # rough public count, e.g. 284000 for "284K+"
    bestseller_tier: int | None


def parse_profile(data: Any) -> Size:
    if not isinstance(data, dict):
        return Size(None, None)
    subs = data.get("subscriberCountNumber") or data.get("rough_num_free_subscribers_int")
    tier = data.get("bestseller_tier") or (data.get("status") or {}).get("bestsellerTier")
    return Size(int(subs) if subs else None, int(tier) if tier else None)


def size(handle: str | None) -> Size:
    if not handle:
        return Size(None, None)
    return parse_profile(net.get_json(
        f"https://substack.com/api/v1/user/{handle}/public_profile", ttl=7 * DAY))
