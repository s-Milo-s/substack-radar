"""Recent posts from Substack RSS (<pub>/feed) and Google News RSS for watched companies."""
from __future__ import annotations

import calendar
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser

from . import net

log = logging.getLogger("radar.sources")


def _clean(s: str, limit: int = 1200) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return html.unescape(re.sub(r"\s+", " ", s)).strip()[:limit]


def _published(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc) if t else None


def feed_url(pub_url: str) -> str:
    return pub_url.rstrip("/") + "/feed"


def parse_feed(body: bytes, pub: dict, cutoff: datetime) -> list[dict]:
    feed = feedparser.parse(body)
    posts = []
    for e in feed.entries[:10]:
        when = _published(e)
        if not when or when < cutoff:
            continue
        posts.append({
            "id": e.get("id") or e.get("link"),
            "publication": pub["name"],
            "tier": pub.get("tier", "peer"),
            "lane": pub.get("lane") or "other",
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "published": when.isoformat(),
            "summary": _clean(e.get("summary", "")),
        })
    return posts


def recent_posts(publications: list[dict], hours: int = 48) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []
    for pub in publications:
        body = net.get(feed_url(pub["url"]), ttl=3600)
        if body is None:
            log.warning("skipping %s: feed unavailable", pub["name"])
            continue
        try:
            posts.extend(parse_feed(body, pub, cutoff))
        except Exception as e:  # malformed feed: skip it, keep the run
            log.warning("skipping %s: feed parse error %s", pub["name"], e)
    return posts


def news_url(query: str, days: int = 2) -> str:
    return ("https://news.google.com/rss/search?q=" + quote_plus(f"{query} when:{days}d")
            + "&hl=en-US&gl=US&ceid=US:en")


def parse_news(body: bytes, watch: dict, cutoff: datetime) -> list[dict]:
    items = []
    for e in feedparser.parse(body).entries[:5]:
        when = _published(e)
        if when and when < cutoff:
            continue
        items.append({
            "id": e.get("id") or e.get("link"),
            "company": watch["company"],
            "essay_url": watch.get("essay_url", ""),
            "title": e.get("title", ""),
            "url": e.get("link", ""),
        })
    return items


def company_news(watch: list[dict], hours: int = 48) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for w in watch:
        body = net.get(news_url(w["query"], days=max(1, hours // 24)), ttl=3600)
        if body is None:
            log.warning("skipping news for %s: fetch failed", w["company"])
            continue
        try:
            items.extend(parse_news(body, w, cutoff))
        except Exception as e:
            log.warning("skipping news for %s: parse error %s", w["company"], e)
    return items
