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
    assert {"mastered", "learned", "learning", "rusty", "ready", "locked"} <= set(states)
    kinds = Counter(c["kind"] for c in v["clusters"])
    assert kinds["book"] == 4 and kinds["goal"] == 1
    shared = [n for n in v["nodes"] if n["also"]]
    assert {n["title"] for n in shared} >= {"KV cache", "Softmax", "Quantization"}
    assert all(n["cluster"] not in n["also"] for n in v["nodes"])  # its own cluster is never in "also"
    statuses = {s["status"] for s in db.q("SELECT status FROM sessions")}
    assert statuses == {"done", "teaching", "probing"}
    done = db.one("SELECT id FROM sessions WHERE status='done'")["id"]
    bodies = [i["body"] for i in session.view(db, done)["items"] if i["phase"] == "explain"]
    assert any("$$" in b for b in bodies) and any("#idea/" in b for b in bodies)
    dot = lesson.view(db, "c-dot")
    assert any(sec.get("viz") for sec in dot["card"]["sections"])
    assert db.one("SELECT COUNT(*) AS n FROM node_reviews")["n"] > 0
    assert (folder / "MOCK").exists() and db.meta("map_view") == "territory"


def test_clusters_give_chapters_and_reading_order(mocked):
    _, db = mocked
    v = graph.view(db)
    ie = [n for n in v["nodes"] if n["cluster"] == "book:b-mock0"]
    assert ie and {n["chapterTitle"] for n in ie} >= {"Models", "Hardware"}
    orders = sorted(n["order"] for n in ie)
    assert orders[0] == 0.0 and orders[-1] == 1.0
    first = min(ie, key=lambda n: n["order"])
    assert first["chapterTitle"] == "Inference"


def test_the_mock_never_writes_into_a_real_workspace(tmp_path):
    (tmp_path / "study.db").write_text("real data")
    with pytest.raises(mock.MockError):
        mock.build(tmp_path)
    assert (tmp_path / "study.db").read_text() == "real data"


def test_the_map_view_is_saved(env):
    db, jobs, _ = env
    assert state.snapshot(db)["mapView"] == "territory"  # the default (SPEC §30)
    actions.dispatch(db, jobs, {"type": "setMapView", "view": "globe"})
    assert state.snapshot(db)["mapView"] == "globe"
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setMapView", "view": "spiral"})


def test_today_shows_where_to_continue_what_is_due_and_the_books(mocked):
    from dsc import bookstudy, today
    _, db = mocked
    t = today.view(db)
    assert t["continue"]["kind"] in ("session", "lesson")
    assert t["due"]["count"] > 0 and t["due"]["items"] and {"learned", "strong", "answers", "sessions"} <= set(t["week"])
    assert t["recent"] and len(t["recent"]) <= 4
    shelf = {b["title"]: b for b in bookstudy.listing(db)}
    ie = shelf["Inference Engineering"]
    assert ie["author"] == "Philip Kiely" and 0 < ie["strong"] <= ie["known"] <= ie["ideas"]
    assert ie["goalId"] not in {g["id"] for g in state.snapshot(db)["goals"]}
    v = bookstudy.view(db, ie["id"])
    assert len(v["chapters"]) == 8 and all(c["summary"] and c["lessons"] for c in v["chapters"])
    nxt = next(x for c in v["chapters"] for x in c["lessons"] if x["conceptId"] == v["next"])
    assert nxt["started"] and nxt["state"] not in ("learned", "mastered")  # the lesson in progress comes first


def test_the_mock_has_a_saved_book_lesson(mocked):
    from dsc import bookstudy
    _, db = mocked
    les = next(x for c in bookstudy.view(db, "b-mock0")["chapters"] for x in c["lessons"] if x["title"] == "Scaled dot-product attention")
    assert les["written"] and les["carded"]
    v = lesson.view(db, les["conceptId"])
    assert v["book"]["bookTitle"] == "Inference Engineering" and all(sec["book"]["summary"] for sec in v["sections"])
    assert any("#idea/" in sec["body"] for sec in v["sections"]) and any((sec["explain"] or {}).get("work") for sec in v["sections"])
