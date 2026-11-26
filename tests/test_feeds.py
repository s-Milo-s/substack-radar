from radar import feeds

SAMPLE = """# top comment
lanes: [ai-infra, defense]
publications:
  - {name: A, url: https://a.substack.com, tier: anchor, lane: defense}   # keep me
# Companies
watch:
  - company: X
    query: 'x'
"""


def test_add_publication_preserves_comments(tmp_path):
    path = tmp_path / "feeds.yaml"
    path.write_text(SAMPLE)
    out = feeds.add_publication("https://new.substack.com/p/some-post", "New One", tier="peer",
                                lane="ai-infra", path=path)
    assert "# top comment" in out and "# keep me" in out and "# Companies" in out
    assert "{name: New One, url: https://new.substack.com, tier: peer, lane: ai-infra}" in out
    assert out.index("New One") < out.index("watch:")


def test_add_publication_dedupes(tmp_path):
    path = tmp_path / "feeds.yaml"
    path.write_text(SAMPLE)
    assert feeds.add_publication("a.substack.com", "A again", path=path) is None


def test_real_feeds_yaml_round_trips(tmp_path):
    from radar.config import FEEDS
    path = tmp_path / "feeds.yaml"
    original = FEEDS.read_text()
    path.write_text(original)
    out = feeds.add_publication("https://zz.substack.com", "ZZ", path=path)
    # exactly one line added; every original line (comments included) survives
    assert all(l in out.splitlines() for l in original.splitlines())
    added = [l for l in out.splitlines() if l not in original.splitlines()]
    assert added == ["  - {name: ZZ, url: https://zz.substack.com, tier: peer}"]
