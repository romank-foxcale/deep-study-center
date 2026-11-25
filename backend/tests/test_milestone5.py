"""Weekly plan across goals and card refresh."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dsc import actions, lesson, state
from dsc.api import create_app, maybe_refresh_cards
from dsc.db import dumps


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)




def _revised(call):
    assert "web" in call.prompt.lower() and "q-norm" in call.prompt
    import json
    card = json.loads(call.prompt.split("<card>\n", 1)[1].split("\n</card>", 1)[0])
    card["core"] = card["core"] + " Updated."
    card["sources"] = card["sources"][:2] + [{"title": "New canonical", "url": "https://example.org/new", "kind": "article", "why": "better"}]
    for s in card["sections"]:
        if s.get("check"):
            s["check"].pop("id", None)  # the model may drop ids; they must be restored
    return {"changed": True, "summary": "Better source found.", "changes": ["Replaced a dead link"], "card": card}


def test_refresh_proposes_a_diff_and_approval_creates_a_new_version(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, "c-vectors")
    runner.responses["Card refresh"] = _revised
    runner.responses["Fact-check"] = lambda call: {"results": [{"key": "c-vectors", "verdict": "passed", "issues": []}]}
    s = act(db, jobs, type="refreshCard", conceptId="c-vectors")
    assert state.latest_card(db, "c-vectors")["version"] == 2  # nothing changes until approved
    prop = s["cardProposals"][0]
    fields = {d["field"] for d in prop["diff"]}
    assert {"core", "sources"} <= fields and "New canonical" in next(d["after"] for d in prop["diff"] if d["field"] == "sources")
    assert prop["changes"] == ["Replaced a dead link"]

    s = act(db, jobs, type="decideCardProposal", id=prop["id"], approve=True)
    card = state.latest_card(db, "c-vectors")
    assert card["version"] == 3 and card["factCheck"] == "passed" and card["core"].endswith("Updated.")
    assert next(sec for sec in card["sections"] if sec["id"] == "s-length")["check"]["id"] == "q-norm"  # ids kept
    assert next(r for r in s["renditions"] if r["conceptId"] == "c-vectors")["stale"]  # lessons re-render
    assert not s["cardProposals"]


def test_refresh_without_changes_and_reject_and_stale_proposals(env):
    db, jobs, runner = env
    runner.responses["Card refresh"] = {"changed": False, "summary": "Checked sources; all current.", "changes": []}
    s = act(db, jobs, type="refreshCard", conceptId="c-vectors")
    assert not s["cardProposals"]
    assert db.one("SELECT refreshed_at FROM cards WHERE concept_id='c-vectors' AND version=2")["refreshed_at"]

    runner.responses["Card refresh"] = _revised
    s = act(db, jobs, type="refreshCard", conceptId="c-vectors")
    pid = s["cardProposals"][0]["id"]
    s = act(db, jobs, type="decideCardProposal", id=pid, approve=False)
    assert not s["cardProposals"] and state.latest_card(db, "c-vectors")["version"] == 2

    s = act(db, jobs, type="refreshCard", conceptId="c-vectors")
    pid = s["cardProposals"][0]["id"]
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) SELECT concept_id, 3, body, 'passed', checked_at FROM cards WHERE concept_id='c-vectors' AND version=2")
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="decideCardProposal", id=pid, approve=True)  # card moved on since the proposal


def test_auto_refresh_picks_old_cards_a_few_per_day(env):
    db, jobs, runner = env
    runner.responses["Card refresh"] = {"changed": False, "summary": "ok", "changes": []}
    db.set_meta("auto_refresh", "1")
    db.x("UPDATE cards SET checked_at=?", (datetime.now(timezone.utc).isoformat(),))  # the seed's date ages; pin it to now
    maybe_refresh_cards(db, jobs)
    assert not [r for r, _ in runner.calls if r == "Card refresh"]  # fresh cards are not refreshed
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    db.x("UPDATE cards SET checked_at=?", (old,))
    for _ in range(5):
        maybe_refresh_cards(db, jobs)
    assert len([r for r, _ in runner.calls if r == "Card refresh"]) == 2  # both demo cards, then nothing left
    db.x("UPDATE cards SET refreshed_at=?", (old,))
    for _ in range(5):
        maybe_refresh_cards(db, jobs)
    assert len([r for r, _ in runner.calls if r == "Card refresh"]) == 3  # daily cap of 3
