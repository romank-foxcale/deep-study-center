"""Daily roadmap: curriculum data, planner rules and the CLI progress log."""

import json
from datetime import date, timedelta

import pytest

from dsc.roadmap import plan as P
from dsc.roadmap.cli import main

START = date(2026, 11, 12)  # a Thursday


@pytest.fixture(scope="module")
def cur():
    return P.load_curriculum()


def config(**over):
    raw = {"start_date": START.isoformat(), "tracks": {t: {} for t in P.TOPIC_FILES}}
    raw.update(over)
    return P.normalize_config(raw)


def ev(uid, day, result="done"):
    return {"id": uid, "date": day.isoformat(), "result": result}


def test_curriculum_is_complete(cur):
    problems = [u for u in cur.units.values() if u.kind == "problem"]
    assert len(problems) >= 150
    assert set(cur.tracks) == {"ml", "earth", "agents", "sysdesign", "public"}
    for u in cur.units.values():
        assert u.resources, u.id
        assert all(r.url.startswith("https://") for r in u.resources), u.id


def test_example_config_loads():
    cfg = P.load_config(P.EXAMPLE_CONFIG)
    assert cfg["dsa"]["enabled"] and set(cfg["tracks"]) == set(P.TOPIC_FILES)


def test_day_one_has_coding_and_a_topic(cur):
    items = P.plan_day(cur, config(), [], START)
    kinds = [it.unit.kind for it in items]
    assert kinds[:2] == ["pattern", "problem"]
    assert "unit" in kinds


def test_review_comes_back_after_interval_and_next_day_after_fail(cur):
    cfg = config(posts={"enabled": False})
    events = [ev("dsa-contains-duplicate", START)]
    reviews = lambda day: [it.unit.id for it in P.plan_day(cur, cfg, events, day) if it.review]  # noqa: E731
    assert reviews(START + timedelta(days=2)) == []
    assert reviews(START + timedelta(days=3)) == ["dsa-contains-duplicate"]
    events.append(ev("dsa-contains-duplicate", START + timedelta(days=3), "fail"))
    assert reviews(START + timedelta(days=4)) == ["dsa-contains-duplicate"]


def test_problem_retires_after_all_intervals():
    hist = [ev("x", START)]
    day = START
    for gap in [3, 7, 21, 60]:
        assert P._problem_due(hist, [3, 7, 21, 60]) == day + timedelta(days=gap)
        day += timedelta(days=gap)
        hist.append(ev("x", day))
    assert P._problem_due(hist, [3, 7, 21, 60]) is None


def test_missed_work_rolls_forward(cur):
    cfg = config()
    first = [it.unit.id for it in P.plan_day(cur, cfg, [], START)]
    later = [it.unit.id for it in P.plan_day(cur, cfg, [], START + timedelta(days=5))]
    assert first[:2] == later[:2]  # nothing done yet: same coding units


def test_plan_is_stable_during_the_day(cur):
    cfg = config()
    before = [it.unit.id for it in P.plan_day(cur, cfg, [], START)]
    done = [ev(i, START) for i in before]
    assert [it.unit.id for it in P.plan_day(cur, cfg, done, START)] == before


def test_rest_days_and_disabled_tracks(cur):
    cfg = config(time={"study_days": ["mon", "tue", "wed", "thu", "fri"]},
                 tracks={"ml": {"enabled": False}, "public": {"enabled": False}})
    assert P.plan_day(cur, cfg, [], START + timedelta(days=2)) == []  # Saturday
    plan, _ = P.simulate(cur, cfg, [], START, 60)
    tracks = {it.unit.track for _, items in plan for it in items}
    assert "ml" not in tracks and "public" not in tracks


def test_skip_basics_and_skip_patterns(cur):
    cfg = config(tracks={"ml": {"skip_basics": True}}, dsa={"skip_patterns": ["arrays-hashing"]})
    plan, _ = P.simulate(cur, cfg, [], START, 30)
    ids = {it.unit.id for _, items in plan for it in items}
    assert "ml-env" not in ids and "ml-optimization" in ids
    assert not any(cur.units[i].pattern == "arrays-hashing" for i in ids if i in cur.units)


def test_weekly_post_lists_the_week_and_carries_over(cur):
    cfg = config()
    sunday = START + timedelta(days=3)
    events = [ev("ml-env", START)]
    post = [it for it in P.plan_day(cur, cfg, events, sunday) if it.unit.kind == "post"]
    assert len(post) == 1 and "Set up your ML workspace" in post[0].unit.exercise
    monday = sunday + timedelta(days=1)
    assert any(it.unit.id == post[0].unit.id for it in P.plan_day(cur, cfg, events, monday))
    events.append(ev(post[0].unit.id, sunday))
    assert not any(it.unit.kind == "post" for it in P.plan_day(cur, cfg, events, monday))


def test_full_simulation_respects_prerequisites_and_finishes(cur):
    cfg = config()
    plan, events = P.simulate(cur, cfg, [], START, 500)
    first_day = {}
    for e in events:
        first_day.setdefault(e["id"], e["date"])
    for uid in cur.units:
        assert uid in first_day, f"{uid} is never planned"
        for req in cur.units[uid].requires:
            assert first_day[req] < first_day[uid], f"{uid} planned before {req}"
    end = P.finish_date(cur, cfg, [], START)
    assert START + timedelta(days=120) < end < START + timedelta(days=366)


def test_cli_logs_progress_outside_the_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DSC_WORKSPACE", str(tmp_path))
    main(["init", "--start", START.isoformat()])
    main(["done", "dsa-two-sum", "--date", START.isoformat()])
    main(["done", "dsa-two-sum", "--fail", "--date", "2026-11-15"])
    main(["undo", "dsa-two-sum"])
    data = json.loads((tmp_path / "roadmap" / "progress.json").read_text(encoding="utf-8"))
    assert data["events"] == [{"id": "dsa-two-sum", "date": START.isoformat(), "result": "done"}]
    with pytest.raises(SystemExit):
        main(["done", "no-such-unit"])
    main(["plan", "--days", "3", "--start", START.isoformat(), "--brief"])
    assert "## Day 3" in capsys.readouterr().out
