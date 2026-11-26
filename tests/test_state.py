from radar import state as st


def test_unseen_filters_seen_and_batch_duplicates():
    s = st._defaults()
    s["seen"] = ["a"]
    items = [{"id": "a"}, {"id": "b"}, {"id": "b"}, {"id": None}, {"id": "c"}]
    assert [i["id"] for i in st.unseen(items, s)] == ["b", "c"]


def test_mark_seen_no_duplicates():
    s = st._defaults()
    st.mark_seen(s, ["a", "b"])
    st.mark_seen(s, ["b", "c", None])
    assert s["seen"] == ["a", "b", "c"]


def test_pop_note_fifo_and_empty():
    s = st._defaults()
    s["note_queue"] = [{"text": "1"}, {"text": "2"}]
    assert st.pop_note(s)["text"] == "1"
    assert s["note_queue"] == [{"text": "2"}]
    assert s["posted_notes"] == [{"text": "1"}]
    st.pop_note(s)
    assert st.pop_note(s) is None


def test_save_load_roundtrip_and_bound(tmp_path):
    path = tmp_path / "state.json"
    s = st._defaults()
    s["seen"] = [str(i) for i in range(st.SEEN_LIMIT + 50)]
    st.save(s, path)
    loaded = st.load(path)
    assert len(loaded["seen"]) == st.SEEN_LIMIT and loaded["seen"][-1] == str(st.SEEN_LIMIT + 49)


def test_load_old_state_gets_new_keys(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"seen": [], "note_queue": [], "posted_notes": []}')
    s = st.load(path)
    assert s["rejected_writers"] == [] and s["last_lanes"] == [] and s["essays"] == {}
