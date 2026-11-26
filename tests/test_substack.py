import json

from radar import discover, substack
from radar.substack import Size


def load(fixture_bytes, name):
    return json.loads(fixture_bytes(name))


def test_parse_archive_current_shape(fixture_bytes):
    posts = substack.parse_archive(load(fixture_bytes, "archive.json"))
    assert posts[0]["publication_id"] == 2302974


def test_parse_archive_legacy_list_and_junk():
    assert substack.parse_archive([{"publication_id": 1}]) == [{"publication_id": 1}]
    assert substack.parse_archive(None) == []
    assert substack.parse_archive({"error": "nope"}) == []


def test_parse_recommendations(fixture_bytes):
    recs = substack.parse_recommendations(load(fixture_bytes, "recommendations.json"))
    assert len(recs) == 4
    r = recs[0]
    assert r.name == "early days"
    assert r.url == "https://earlydaysbymerlin.substack.com"
    assert r.handle == "merlindotinc"
    assert isinstance(r.pub_id, int)
    assert r.about.startswith("learn about silicon valley")


def test_parse_recommendations_custom_domain_and_junk():
    data = [
        {"recommendedPublication": {"name": "Big", "subdomain": "big", "custom_domain": "www.Big.com", "id": 7}},
        {"recommendedPublication": {"name": "No url"}},
        {"something": "else"},
    ]
    recs = substack.parse_recommendations(data)
    assert [r.url for r in recs] == ["https://www.big.com"]
    assert recs[0].pub_id == 7 and recs[0].handle is None
    assert substack.parse_recommendations({"not": "a list"}) == []


def test_parse_profile(fixture_bytes):
    size = substack.parse_profile(load(fixture_bytes, "public_profile.json"))
    assert size == Size(subscribers=284000, bestseller_tier=100)
    assert substack.parse_profile(None) == Size(None, None)


def test_size_tier():
    assert discover.size_tier(Size(None, 100), my_subs=50) == "anchor"
    assert discover.size_tier(Size(20000, None), my_subs=500) == "anchor"
    assert discover.size_tier(Size(800, None), my_subs=500) == "peer"
    assert discover.size_tier(Size(None, None), my_subs=500) is None


def test_base_url():
    assert substack.base_url("x.substack.com/p/post") == "https://x.substack.com"
    assert substack.base_url("https://WWW.Site.com/") == "https://www.site.com"
