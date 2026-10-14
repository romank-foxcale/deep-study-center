"""Weekly plan across goals and card refresh."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dsc import actions, lesson, planner, state
from dsc.api import create_app, maybe_refresh_cards
from dsc.db import dumps


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


MONDAY = date(2026, 10, 19)


# ---------------------------------------------------------------- weekly plan

def test_plan_fills_study_days_in_roadmap_order_with_reviews_first(env):
    db, jobs, _ = env
    act(db, jobs, type="setPlanSettings", weeklyHours=5, studyDays=[0, 2, 4], startTime="07:30")
    p = planner.plan_week(db, MONDAY)
    days = {d["date"]: d for d in p["days"]}
    assert [d["study"] for d in p["days"]] == [True, False, True, False, True, False, False]
    assert days["2026-10-19"]["budget"] == 100 and not days["2026-10-20"]["items"]
    lessons = [i for d in p["days"] for i in d["items"] if i["kind"] == "lesson"]
    titles = [i["title"] for i in lessons]
    assert titles[:2] == ["Vectors", "Linear combinations"]  # roadmap order, prerequisites first
    assert titles.index("Span, basis & dimension") > titles.index("Linear combinations")
    assert lessons[0]["note"] == "continue" and any(i["note"] == "needs research" for i in lessons)
    wed = days["2026-10-21"]["items"]
    first_lesson = next(i for i, it in enumerate(wed) if it["kind"] == "lesson")
    assert all(it["kind"] == "review" for it in wed[:first_lesson]) and first_lesson > 0  # confirmations come first
    assert {it["title"] for it in wed[:first_lesson]} >= {"Vectors", "Linear combinations"}
    for d in p["days"]:
        assert d["minutes"] <= max(d["budget"] * 1.15, max((i["minutes"] for i in d["items"]), default=0))
    assert p["upcomingResearch"][0]["moduleId"] == "m-calc"


def test_plan_shares_time_between_goals_and_skips_known_modules(env):
    db, jobs, _ = env
    # a second goal with one researched module of three 20-minute lessons
    db.x("INSERT INTO goals(id, title, hours, created_at) VALUES('g-rl', 'Learn RL', 5, '2026-10-15')")
    db.x("INSERT INTO tracks VALUES('t-rl', 'g-rl', 0, 'RL', '')")
    db.x("INSERT INTO modules(id, track_id, ord, title, research, planned) VALUES('m-mdp', 't-rl', 0, 'MDPs', 'ready', 3)")
    for i in range(3):
        db.x("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,0)", (f"rl{i}", "m-mdp", i, f"RL {i}", "o", 20, dumps([]), 0.1))
        db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,1,?, 'passed', '2026-10-15')",
             (f"rl{i}", dumps({"sections": []})))
    act(db, jobs, type="setPlanSettings", weeklyHours=10, studyDays=[0, 1, 2, 3, 4, 5, 6])
    p = planner.plan_week(db, MONDAY)
    goals = {g["id"]: g for g in p["goals"]}
    assert goals["g-ai"]["share"] == pytest.approx(10 / 15, abs=0.01)  # demo goal: 10 h/week, RL: 5 h/week
    rl = [i for d in p["days"] for i in d["items"] if i["goalId"] == "g-rl" and i["kind"] == "lesson"]
    assert [i["title"] for i in rl] == ["RL 0", "RL 1", "RL 2"]
    first_day = [i["goalId"] for i in p["days"][0]["items"]]
    assert "g-rl" in first_day and "g-ai" in first_day  # time is interleaved, not one goal first

    db.x("UPDATE modules SET known=1 WHERE id='m-la'")
    p = planner.plan_week(db, MONDAY)
    assert not any(i["title"] == "Vectors" for d in p["days"] for i in d["items"] if i["kind"] == "lesson")


def test_plan_settings_validation_and_ics(env):
    db, jobs, _ = env
    for bad in ({"weeklyHours": 0}, {"studyDays": []}, {"startTime": "25:00"}):
        with pytest.raises(actions.ActionError):
            act(db, jobs, type="setPlanSettings", **bad)
    act(db, jobs, type="setPlanSettings", startTime="06:45", studyDays=[0])
    ics = planner.to_ics(planner.plan_week(db, MONDAY))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 1 and "DTSTART:20261019T064500" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert "Vectors\\, Linear combinations" in ics.replace("\r\n ", "")
    client = TestClient(create_app(db=db, jobs=jobs))
    r = client.get("/api/plan.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert client.get("/api/plan").json()["settings"]["start_time"] == "06:45"


# ---------------------------------------------------------------- card refresh

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
    maybe_refresh_cards(db, jobs)
    assert not [r for r, _ in runner.calls if r == "Card refresh"]  # seed cards are fresh
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    db.x("UPDATE cards SET checked_at=?", (old,))
    for _ in range(5):
        maybe_refresh_cards(db, jobs)
    assert len([r for r, _ in runner.calls if r == "Card refresh"]) == 2  # both demo cards, then nothing left
    db.x("UPDATE cards SET refreshed_at=?", (old,))
    for _ in range(5):
        maybe_refresh_cards(db, jobs)
    assert len([r for r, _ in runner.calls if r == "Card refresh"]) == 3  # daily cap of 3
