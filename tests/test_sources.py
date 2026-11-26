import json
from datetime import datetime, timezone

from radar import sources

PUB = {"name": "DTVC", "url": "https://dtvc.substack.com", "tier": "peer", "lane": "defense"}
LONG_AGO = datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_parse_feed_fields(fixture_bytes):
    posts = sources.parse_feed(fixture_bytes("substack_feed.xml"), PUB, LONG_AGO)
    assert len(posts) == 3
    p = posts[0]
    assert p["id"] == "https://dtvc.substack.com/p/defense-tech-spotlight-allen-control"
    assert p["url"].startswith("https://dtvc.substack.com/p/")
    assert p["title"] and p["publication"] == "DTVC"
    assert p["tier"] == "peer" and p["lane"] == "defense"
    assert p["published"].startswith("2024-11-14")


def test_parse_feed_respects_cutoff(fixture_bytes):
    future = datetime(2100, 1, 1, tzinfo=timezone.utc)
    assert sources.parse_feed(fixture_bytes("substack_feed.xml"), PUB, future) == []


def test_parse_feed_missing_lane_is_other(fixture_bytes):
    pub = {"name": "X", "url": "https://x.substack.com"}
    posts = sources.parse_feed(fixture_bytes("substack_feed.xml"), pub, LONG_AGO)
    assert {p["lane"] for p in posts} == {"other"} and {p["tier"] for p in posts} == {"peer"}


def test_parse_feed_garbage_is_empty():
    assert sources.parse_feed(b"<html>not a feed</html>", PUB, LONG_AGO) == []


def test_parse_google_news(fixture_bytes):
    watch = {"company": "Nominal", "query": "x", "essay_url": "https://me/p/nominal"}
    items = sources.parse_news(fixture_bytes("google_news.xml"), watch, LONG_AGO)
    assert len(items) == 3
    assert all(i["company"] == "Nominal" and i["essay_url"] == "https://me/p/nominal" for i in items)
    assert "Nominal" in items[0]["title"]


def test_news_url_format():
    url = sources.news_url('"Nominal" startup', days=2)
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "when%3A2d" in url and "ceid=US:en" in url


def test_recent_posts_skips_broken_feed(monkeypatch, fixture_bytes):
    bodies = {"https://ok.substack.com/feed": fixture_bytes("substack_feed.xml")}
    monkeypatch.setattr(sources.net, "get", lambda url, ttl=0: bodies.get(url))
    monkeypatch.setattr(sources, "datetime", type("D", (), {
        "now": staticmethod(lambda tz=None: datetime(2024, 11, 15, tzinfo=timezone.utc)),
        "fromtimestamp": staticmethod(datetime.fromtimestamp)}))
    pubs = [{"name": "Broken", "url": "https://broken.substack.com"},
            {"name": "OK", "url": "https://ok.substack.com"}]
    posts = sources.recent_posts(pubs, hours=48)
    assert posts and {p["publication"] for p in posts} == {"OK"}
