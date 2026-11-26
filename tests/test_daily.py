from datetime import date

from radar.__main__ import check_plan, render_daily, rotate_by_lane
from radar.schemas import Comment, DailyPlan, NewsHook, Restack


def post(i, lane):
    return {"id": str(i), "lane": lane, "url": f"https://x/{i}", "publication": "P", "title": f"T{i}"}


def test_rotate_by_lane_interleaves_and_rotates():
    posts = [post(1, "a"), post(2, "a"), post(3, "b"), post(4, "c")]
    day0 = date.fromordinal(3 * 1000)       # ordinal % 3 == 0 -> starts at lane a
    assert [p["lane"] for p in rotate_by_lane(posts, ["a", "b", "c"], day0)] == ["a", "b", "c", "a"]
    day1 = date.fromordinal(3 * 1000 + 1)
    assert [p["lane"] for p in rotate_by_lane(posts, ["a", "b", "c"], day1)][0] == "b"


def test_rotate_caps_per_lane():
    posts = [post(i, "a") for i in range(9)] + [post(99, "b")]
    out = rotate_by_lane(posts, ["a", "b"], date.today(), per_lane=3)
    assert sum(p["lane"] == "a" for p in out) == 3 and any(p["lane"] == "b" for p in out)


def test_check_plan_flags_bad_index_and_same_lane():
    posts = [post(0, "a"), post(1, "a"), post(2, "b")]
    plan = DailyPlan(comments=[Comment(post=0, why="", comment=""), Comment(post=1, why="", comment="")],
                     restack=Restack(post=7, take=""), news_hooks=[NewsHook(news=3, note="")])
    problems = check_plan(plan, posts, news=[])
    assert any("post index 7" in p for p in problems)
    assert any("news index 3" in p for p in problems)
    assert any("different lanes" in p for p in problems)


def test_render_drops_out_of_range_items():
    posts = [post(0, "a")]
    plan = DailyPlan(comments=[Comment(post=0, why="w", comment="good"), Comment(post=5, why="", comment="bad")],
                     restack=Restack(post=9, take="x"), reactive_note="note")
    text = "\n".join(render_daily(plan, posts, news=[]))
    assert "good" in text and "bad" not in text and "Restack" not in text and "note" in text


def test_render_none_plan():
    assert render_daily(None, [], []) == []
