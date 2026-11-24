"""Gaps on the map (SPEC §51): ideas missing between two cells, found by an agent, checked by code, added by the learner."""

import pytest

from dsc import actions, gaps, graph

FOUND = {"gaps": [
    {"between": ["c-vectors", "c-dot"], "ideas": [
        {"title": "Vector length", "says": "The length of an arrow, from Pythagoras."},
        {"title": "Vectors", "says": "already on the map: dropped"},
        {"title": "Angle between vectors", "says": "How far two arrows turn from each other."}]},
    {"between": ["c-vectors", "c-nope"], "ideas": [{"title": "Ghost", "says": "an unknown end: dropped"}]},
    {"between": ["c-dot", "c-dot"], "ideas": [{"title": "Self", "says": "the same end twice: dropped"}]},
]}


@pytest.fixture
def mapped(env):
    db, jobs, runner = env
    prompts = []

    def finder(call):
        prompts.append(call.prompt)
        if "Look only at the arrow" in call.prompt:
            return {"gaps": [{"between": ["c-vectors", "c-dot"], "ideas": [
                {"title": "Unit vectors", "says": "A vector of length one."}, {"title": "Vector length", "says": "a repeat: dropped"}]}]}
        return FOUND
    runner.responses["Research"] = finder
    db.x("INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score) VALUES('2026-01-01', 'c-vectors', 'q', 'practice', 1, 1.0)")
    return db, jobs, prompts


def view_gap(db):
    return graph.view(db)["gaps"]


def test_found_gaps_are_checked_and_shown_between_their_two_ideas(mapped):
    db, jobs, prompts = mapped
    actions.dispatch(db, jobs, {"type": "findGaps"})
    g = view_gap(db)
    assert len(g) == 1 and g[0]["between"] == ["c-vectors", "c-dot"]
    assert [i["title"] for i in g[0]["ideas"]] == ["Vector length", "Angle between vectors"]  # an idea on the map is dropped
    assert "c-vectors: Vectors -> c-dot: Dot product" in prompts[0] and "(learning)" in prompts[0]
    actions.dispatch(db, jobs, {"type": "findGaps"})  # the same gap again: no second gap, no repeated idea
    assert len(view_gap(db)) == 1 and len(view_gap(db)[0]["ideas"]) == 2


def test_adding_an_idea_makes_a_cell_and_the_gap_shrinks_then_closes(mapped):
    db, jobs, prompts = mapped
    actions.dispatch(db, jobs, {"type": "findGaps"})
    gid = view_gap(db)[0]["id"]
    actions.dispatch(db, jobs, {"type": "acceptGap", "gapId": gid, "index": 0})
    v = graph.view(db)
    new = next(n for n in v["nodes"] if n["title"] == "Vector length")
    assert new["state"] in ("ready", "locked") and db.meta("last_gap_idea") == new["id"]
    pairs = {(x["src"], x["dst"]) for x in v["links"]}
    assert ("c-vectors", new["id"]) in pairs and (new["id"], "c-dot") in pairs
    assert v["gaps"][0]["between"] == [new["id"], "c-dot"] and [i["title"] for i in v["gaps"][0]["ideas"]] == ["Angle between vectors"]
    actions.dispatch(db, jobs, {"type": "acceptGap", "gapId": gid, "index": 0})
    assert view_gap(db) == [] and db.one("SELECT status FROM gaps WHERE id=?", (gid,))["status"] == "filled"
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "acceptGap", "gapId": gid, "index": 0})


def test_find_more_grows_a_gap_and_not_missing_closes_it_for_good(mapped):
    db, jobs, prompts = mapped
    actions.dispatch(db, jobs, {"type": "findGaps"})
    gid = view_gap(db)[0]["id"]
    actions.dispatch(db, jobs, {"type": "findGaps", "gapId": gid})
    assert "Look only at the arrow c-vectors: Vectors -> c-dot: Dot product" in prompts[-1] and "Vector length" in prompts[-1]
    g = view_gap(db)[0]
    assert [i["title"] for i in g["ideas"]] == ["Vector length", "Angle between vectors", "Unit vectors"] and not g["busy"]
    actions.dispatch(db, jobs, {"type": "findGaps", "gapId": gid})  # full (3): nothing more is added
    assert len(view_gap(db)[0]["ideas"]) == gaps.MAX_IDEAS
    actions.dispatch(db, jobs, {"type": "dismissGap", "gapId": gid})
    assert view_gap(db) == []
    actions.dispatch(db, jobs, {"type": "findGaps"})  # a dismissed arrow is not proposed again
    assert view_gap(db) == []


def test_a_book_that_finishes_mapping_looks_for_gaps(env):
    from test_bookstudy import add_book, cards_reply, map_reply
    db, jobs, runner = env
    add_book(db)
    db.set_meta("auto_gaps", "1")
    map_reply.prompts, map_reply.fail_chapter_2 = [], False
    seen = []
    runner.responses["Book map"] = map_reply
    runner.responses["Research"] = lambda call: seen.append(call.prompt) or ({"gaps": []} if "You look for gaps" in call.prompt else cards_reply(call))
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-1"})
    assert any("You look for gaps" in p for p in seen) or db.q("SELECT 1 FROM jobs WHERE kind='find_gaps'")
