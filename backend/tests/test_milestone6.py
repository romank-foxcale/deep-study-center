"""Daily-use readiness: first run, goal removal, backups, undo, time tracking, share suggestions,
Docker runner mode, live research progress."""

import json
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from dsc import actions, backup, planner, providers, runner, state
from dsc.api import create_app
from dsc.db import DB


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def learn_vectors(db, jobs, runner_fake):
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice)
    runner_fake.responses["Grading"] = {"score": 1, "feedback": "ok", "missing": [], "followup": ""}
    return act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer="Each axis moves independently, so the parts add up.")


def test_first_run_is_empty_and_offers_the_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("DSC_WORKSPACE", str(tmp_path))
    db = DB(tmp_path / "study.db")
    client = TestClient(create_app(db=db))
    s = client.get("/api/state").json()
    assert s["goal"] is None and s["firstRun"] and len(s["routes"]) >= 12
    s = client.post("/api/action", json={"type": "loadDemo"}).json()
    assert s["goal"]["id"] == "g-ai" and not s["firstRun"]
    assert client.post("/api/action", json={"type": "loadDemo"}).status_code == 400  # never over existing goals


def test_delete_goal_removes_its_data_keeps_the_playbook_and_backs_up_first(env):
    db, jobs, _ = env
    act(db, jobs, type="addNote", conceptId="c-vectors", text="mine")
    pb = state.playbook(db)
    s = act(db, jobs, type="deleteGoal", id="g-ai")
    assert s["goal"] is None and not s["concepts"] and not db.q("SELECT * FROM notes")
    assert not db.q("SELECT * FROM cards") and not db.q("SELECT * FROM tracks")
    assert state.playbook(db)["entries"] == pb["entries"]  # the learner model is about you, not the goal
    assert len(backup.listing()) == 1


def test_backups_are_daily_and_capped(env):
    db, jobs, _ = env
    assert backup.maybe_backup(db) is not None
    assert backup.maybe_backup(db) is None  # not again within a day
    for i in range(16):
        (backup.folder() / f"study-2026-01-{i + 1:02d}_000000.db").write_bytes(b"x")
    backup.backup_now(db)
    names = [b["name"] for b in backup.listing()]
    assert len(names) == backup.KEEP and names[-1] == "study-2026-01-04_000000.db"  # oldest ones pruned
    import sqlite3
    newest = backup.folder() / names[0]
    assert sqlite3.connect(newest).execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 10  # a real, consistent copy


def test_undo_answer_reopens_the_item_and_unlearns_if_needed(env):
    db, jobs, runner_fake = env
    s = learn_vectors(db, jobs, runner_fake)
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "learned" and s["reviews"]
    s = act(db, jobs, type="undoAnswer", conceptId="c-vectors", itemId="e-ops")
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "learning"
    assert "c-vectors:e-ops" not in s["answers"] and s["gradings"]["c-vectors:e-ops"]["status"] == "voided"
    assert not s["reviews"]  # no longer learned: the confirmation review is gone
    s = act(db, jobs, type="undoAnswer", conceptId="c-vectors", itemId="q-ops")
    assert "c-vectors:q-ops" not in s["answers"]
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="undoAnswer", conceptId="c-vectors", itemId="q-ops")


def test_activity_heartbeats_show_as_actual_time(env):
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    for _ in range(4):
        assert client.post("/api/activity", json={"conceptId": "c-vectors", "seconds": 30}).status_code == 200
    assert client.post("/api/activity", json={"conceptId": "c-vectors", "seconds": 999}).status_code == 400
    assert client.post("/api/activity", json={"conceptId": "nope", "seconds": 30}).status_code == 400
    p = planner.plan_week(db, date.today())
    assert p["days"][0]["actualMinutes"] == 2 and p["actualLast7"][-1]["minutes"] == 2


def test_share_suggestions_are_learned_and_fact_checked(env):
    db, jobs, runner_fake = env
    assert state.share_suggestions(db) == []
    learn_vectors(db, jobs, runner_fake)
    assert state.share_suggestions(db) == ["c-vectors"]
    s = act(db, jobs, type="promoteSuggested")
    assert [l["key"] for l in s["library"]] == ["vectors"] and s["shareSuggestions"] == []


def test_per_goal_hours(env):
    db, jobs, _ = env
    act(db, jobs, type="setPlanSettings", goalId="g-ai", hours=4)
    assert planner.plan_week(db)["goals"][0]["hours"] == 4
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="setPlanSettings", goalId="g-ai", hours=0)


def test_docker_mode_command_and_guards(env, monkeypatch, tmp_path):
    db, jobs, _ = env
    monkeypatch.setattr(runner, "docker_available", lambda: False)
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="setRunnerMode", mode="docker")
    monkeypatch.setattr(runner, "docker_available", lambda: True)
    monkeypatch.setattr(runner, "docker_ready", lambda: False)
    s = act(db, jobs, type="setRunnerMode", mode="docker")
    assert s["runner"]["mode"] == "docker" and not s["runner"]["dockerReady"]
    client = TestClient(create_app(db=db, jobs=jobs))
    r = client.post("/api/run", json={"conceptId": "c-lincomb", "itemId": "x-neuron", "code": ""}).json()
    assert r == {"status": "needs_setup", "mode": "docker"}
    cmd = runner.docker_command(tmp_path)
    for flag in (["--network", "none"], ["--read-only"], ["--cap-drop", "ALL"], ["--pids-limit", "256"]):
        assert cmd[cmd.index(flag[0]):cmd.index(flag[0]) + len(flag)] == flag
    assert f"{tmp_path}:/work:ro" in cmd and cmd[-1] == "exercise.py"
    assert "USER learner" in runner.DOCKERFILE


def test_stream_events_become_progress():
    search = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "best SVD explanation"}},
        {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://example.org/svd"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "rm -rf /"}}]}})
    assert providers.describe_event(search) == ["searching: best SVD explanation", "reading: https://example.org/svd"]
    assert providers.describe_event('{"type":"system","subtype":"init"}') == []
    assert providers.describe_event("not json") == []
