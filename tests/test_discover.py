from radar import discover
from radar.schemas import Pick, Picks
from radar.substack import Rec


def rec(url, pid, name=None):
    return Rec(name=name or url, url=url, about="", pub_id=pid, handle=None)


def test_crawl_votes_and_dedupes_by_publication_id(monkeypatch):
    seeds = ["https://a.substack.com", "https://b.substack.com"]
    ids = {"https://a.substack.com": 1, "https://b.substack.com": 2}
    graph = {
        1: [rec("https://new.com", 10), rec("https://www.b-custom.com", 2)],  # b under its custom domain
        2: [rec("https://new.com", 10), rec("https://other.com", 11)],
        10: [rec("https://hop2.com", 12)],
    }
    monkeypatch.setattr(discover.substack, "publication_id", lambda u: ids.get(u))
    monkeypatch.setattr(discover.substack, "recommendations", lambda pid: graph.get(pid, []))
    cands = discover.crawl(seeds, hops=2)
    assert "https://www.b-custom.com" not in cands       # seed, even on another domain
    assert len(cands["https://new.com"].voters) == 2
    assert "https://hop2.com" in cands                    # expanded from the 2-vote candidate
    assert "https://other.com" in cands


def test_crawl_skips_seed_without_id(monkeypatch):
    monkeypatch.setattr(discover.substack, "publication_id", lambda u: None)
    monkeypatch.setattr(discover.substack, "recommendations", lambda pid: 1 / 0)
    assert discover.crawl(["https://dead.substack.com"]) == {}


def test_check_picks():
    picks = Picks(picks=[Pick(i=0, fit=8, tier="peer", lane="defense", why=""),
                         Pick(i=5, fit=8, tier="peer", lane="cooking", why="")])
    problems = discover.check_picks(picks, n=2, lanes=["defense"])
    assert any("out of range" in p for p in problems)
    assert any("cooking" in p for p in problems)
