"""The mock workspace (`dsc mock`) and the map views' data (SPEC §29)."""

from collections import Counter

import pytest

from dsc import actions, graph, lesson, mock, session, state
from dsc.db import DB


@pytest.fixture(scope="module")
def mocked(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mock")
    path = mock.build(folder)
    return folder, DB(path)


def test_the_mock_has_every_state_books_sessions_and_lessons(mocked):
    folder, db = mocked
    v = graph.view(db)
    states = Counter(n["state"] for n in v["nodes"])
    assert {"learned", "learning", "ready", "locked"} <= set(states) and not {"mastered", "rusty"} & set(states)
    assert "clusters" not in v and len(v["books"]) == 4  # no countries (SPEC §50)
    shared = [n for n in v["nodes"] if len(n["books"]) > 1]
    assert {n["title"] for n in shared} >= {"KV cache", "Softmax", "Quantization"}
    statuses = {s["status"] for s in db.q("SELECT status FROM sessions")}
    assert statuses == {"done", "teaching", "probing"}
    done = db.one("SELECT id FROM sessions WHERE status='done'")["id"]
    bodies = [" ".join(i["parts"]) for i in session.view(db, done)["items"] if i["phase"] == "explain"]
    assert any("$$" in b for b in bodies) and any("#idea/" in b for b in bodies)
    dot = lesson.view(db, "c-dot")
    assert any(sec.get("viz") for sec in dot["card"]["sections"])
    assert not db.one("SELECT 1 FROM sqlite_master WHERE name='node_reviews'")  # no schedule (SPEC §48)
    assert (folder / "MOCK").exists() and db.meta("map_view") == "hex"


def test_the_mock_never_writes_into_a_real_workspace(tmp_path):
    (tmp_path / "study.db").write_text("real data")
    with pytest.raises(mock.MockError):
        mock.build(tmp_path)
    assert (tmp_path / "study.db").read_text() == "real data"


def test_the_map_view_is_saved(env):
    db, jobs, _ = env
    assert state.snapshot(db)["mapView"] == "hex"  # the default (SPEC §50)
    actions.dispatch(db, jobs, {"type": "setMapView", "view": "tree"})
    assert state.snapshot(db)["mapView"] == "tree"
    db.set_meta("map_view", "territory")  # a country view, removed with the hex map
    assert state.snapshot(db)["mapView"] == "hex"
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setMapView", "view": "cells"})
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setMapView", "view": "spiral"})


def test_today_shows_where_to_continue_and_the_books(mocked):
    from dsc import bookstudy, today
    _, db = mocked
    t = today.view(db)
    assert t["continue"]["kind"] in ("session", "lesson")
    assert "due" not in t and set(t["week"]) == {"learned", "answers", "sessions"}
    assert t["recent"] and len(t["recent"]) <= 4
    shelf = {b["title"]: b for b in bookstudy.listing(db)}
    ie = shelf["Inference Engineering"]
    assert ie["author"] == "Philip Kiely" and 0 < ie["known"] <= ie["ideas"] and "strong" not in ie
    assert ie["goalId"] not in {g["id"] for g in state.snapshot(db)["goals"]}
    v = bookstudy.view(db, ie["id"])
    assert len(v["chapters"]) == 8 and all(c["summary"] and c["lessons"] for c in v["chapters"])
    nxt = next(x for c in v["chapters"] for x in c["lessons"] if x["conceptId"] == v["next"])
    assert nxt["state"] != "learned" and nxt["ready"]  # a lesson whose parts you hold (the outer fringe)


def test_the_mock_has_a_saved_book_lesson(mocked):
    from dsc import bookstudy
    _, db = mocked
    les = next(x for c in bookstudy.view(db, "b-mock0")["chapters"] for x in c["lessons"] if x["title"] == "Scaled dot-product attention")
    assert les["written"] and les["carded"]
    v = lesson.view(db, les["conceptId"])
    assert v["book"]["bookTitle"] == "Inference Engineering" and all(sec["book"]["summary"] for sec in v["sections"])
    assert any("#idea/" in sec["body"] for sec in v["sections"]) and any((sec["explain"] or {}).get("work") for sec in v["sections"])
