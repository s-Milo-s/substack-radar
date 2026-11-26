import pytest

from radar import blocklist, llm
from radar.schemas import DailyPlan, NoteList

GOOD = '{"notes": ["Dashboards are not a moat."]}'


@pytest.fixture
def replies(monkeypatch):
    """Queue up raw model replies; each _complete call pops one (an Exception is raised)."""
    queue, calls = [], []

    def fake(prompt, schema, max_tokens):
        calls.append(prompt)
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(llm, "_complete", fake)
    return queue, calls


def test_valid_json(replies):
    queue, calls = replies
    queue.append(GOOD)
    assert llm.ask("p", NoteList, terms=[]).notes == ["Dashboards are not a moat."]
    assert len(calls) == 1


def test_code_fences_are_stripped(replies):
    queue, _ = replies
    queue.append("```json\n" + GOOD + "\n```")
    assert llm.ask("p", NoteList, terms=[]) is not None


def test_malformed_json_retries_once(replies):
    queue, calls = replies
    queue += ['{"notes": ["unterminated', GOOD]
    assert llm.ask("p", NoteList, terms=[]).notes
    assert len(calls) == 2 and "not valid JSON" in calls[1]


def test_malformed_twice_drops_section(replies):
    queue, calls = replies
    queue += ["nope", '{"wrong": 1}']
    assert llm.ask("p", NoteList, terms=[]) is None
    assert len(calls) == 2


def test_refusal_or_api_error_retries(replies):
    queue, calls = replies
    queue += [llm.Refused("declined"), GOOD]
    assert llm.ask("p", NoteList, terms=[]) is not None


def test_check_problem_retries_then_returns_for_filtering(replies):
    queue, calls = replies
    bad = '{"comments": [{"post": 9, "why": "w", "comment": "c"}]}'
    queue += [bad, bad]
    check = lambda p: [f"index {c.post} out of range" for c in p.comments if c.post > 1]
    plan = llm.ask("p", DailyPlan, check=check, terms=[])
    assert len(calls) == 2 and "out of range" in calls[1]
    assert plan is not None and plan.comments[0].post == 9   # caller drops the bad item


def test_blocklist_rejects_and_regenerates_once(replies):
    queue, calls = replies
    queue += ['{"notes": ["Back at Acme Corp we did this."]}', GOOD]
    out = llm.ask("p", NoteList, terms=["Acme Corp"])
    assert out.notes == ["Dashboards are not a moat."]
    assert len(calls) == 2
    assert "Acme" not in calls[1]          # the secret term is never sent back to the model


def test_blocklist_twice_drops(replies):
    queue, _ = replies
    queue += ['{"notes": ["acme corp rules"]}', '{"notes": ["ACME CORP again"]}']
    assert llm.ask("p", NoteList, terms=["Acme Corp"]) is None


def test_blocklist_matching(tmp_path):
    path = tmp_path / "blocklist.txt"
    path.write_text("# my secrets\nAnn\nSpringfield  # city\n\n")
    terms = blocklist.load(path)
    assert terms == ["Ann", "Springfield"]
    assert blocklist.hits("Hi, ann here", terms) == ["Ann"]
    assert blocklist.hits("annual report", terms) == []
    assert blocklist.load(tmp_path / "missing.txt") == []


def test_voice_is_in_system_prompt():
    assert llm.VOICE.strip() and llm.SYSTEM.startswith(llm.VOICE)
    assert "Pseudonymous" in llm.VOICE
