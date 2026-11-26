from datetime import datetime

from radar import scorecard

CSV = """Title,Type,Post date,Views,New free subscriptions,New paid subscriptions,Unsubscribes
Nominal teardown,post,2026-11-20,1200,30,2,4
Dashboards are not a moat,note,2026-11-22,800,12,0,0
Space thing,post,2026-11-10,300,5,0,1
Quiet note,note,2026-11-23,100,0,0,0
"""


def test_scorecard_parse_and_report(tmp_path):
    path = tmp_path / "stats.csv"
    path.write_text(CSV)
    lane_for = {"nominal": "hard-tech", "dashboards": "hard-tech", "space": "space"}
    rows, cols = scorecard.parse(path, lane_for)
    assert cols == ["New free subscriptions", "New paid subscriptions"]
    assert rows[0].subs == 32 and rows[0].lane == "hard-tech" and rows[0].kind == "post"
    assert rows[3].lane == "unknown"
    text = scorecard.report(rows, cols, today=datetime(2026, 11, 24))
    assert text.splitlines()[2].startswith("• +32 post: Nominal teardown")
    assert "Growing fastest: *hard-tech*" in text
    assert "Quiet note" not in text


def test_scorecard_lane_column_and_no_dates(tmp_path):
    path = tmp_path / "stats.csv"
    path.write_text("name,lane,subscribes\nA,defense,3\nB,space,1\n")
    rows, cols = scorecard.parse(path)
    text = scorecard.report(rows, cols)
    assert "defense +3 (75%)" in text and "No date column" in text


def test_scorecard_without_subscriber_column(tmp_path):
    path = tmp_path / "stats.csv"
    path.write_text("title,views\nA,10\n")
    rows, cols = scorecard.parse(path)
    assert cols == [] and "couldn't find" in scorecard.report(rows, cols)
