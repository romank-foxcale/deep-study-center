"""Ohtani table roadmaps: 8 areas x 8 steps around the goal, 8 merge steps that join ring neighbours."""

from dsc import actions, ohtani, planner, progress, state


def outline(requires=None, waves=None):
    areas = [{"title": f"Area {a + 1}", "summary": "s", "pair_reason": "fits",
              "steps": [{"title": f"A{a + 1} step {k + 1}", "summary": "s", "done_when": "check", "planned": 3,
                         "wave": (waves or {}).get((a, k), k + 1)} for k in range(8)]} for a in range(8)]
    merges = [{"title": f"Merge {i + 1}", "summary": "m", "done_when": "build", "planned": 2,
               "requires": (requires or {}).get(i, [{"area": i + 1, "step": 2}, {"area": (i + 1) % 8 + 1, "step": 2}])}
              for i in range(8)]
    return {"title": "Top AI researcher", "why": "w", "done": "d", "areas": areas, "merges": merges}


def card(key, prereqs=()):
    return {"key": key, "title": key, "objective": "o", "minutes": 20, "prereq_keys": list(prereqs),
            "card": {"bloom": "understand", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                     "misconceptions": [], "sources": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}]}}


def test_build_places_areas_on_the_ring_and_merges_neighbours():
    tracks, modules = ohtani.build("g", outline(requires={
        0: [{"area": 1, "step": 3}, {"area": 2, "step": 1}, {"area": 5, "step": 1}],  # area 5 is not a neighbour: dropped
        7: [{"area": 8, "step": 4}]}))  # nothing from area 1: its capstone is required
    assert [t["pos"] for t in tracks] == ohtani.RING + ["C"]
    by = {m["id"]: m for m in modules}
    assert len(modules) == 72
    assert by["g-tc-m0"]["requires"] == ["g-t0-m2", "g-t1-m0"]
    assert by["g-tc-m7"]["requires"] == ["g-t7-m3", "g-t0-m7"]
    # global order: wave by wave across areas; each merge after everything it requires
    assert by["g-t0-m0"]["seq"] < by["g-t1-m0"]["seq"] < by["g-t0-m1"]["seq"]
    for m in modules:
        assert all(by[r]["seq"] < m["seq"] for r in m["requires"])
    assert sorted(m["seq"] for m in modules) == list(range(1, 73))


def test_waves_never_go_down_within_an_area():
    _, modules = ohtani.build("g", outline(waves={(0, 0): 5, (0, 1): 2}))
    by = {m["id"]: m for m in modules}
    assert by["g-t0-m0"]["seq"] < by["g-t0-m1"]["seq"]  # step 2 is not pulled before step 1


def test_new_ohtani_goal_researches_in_global_order_and_locks_merges(env):
    db, jobs, runner = env
    runner.responses["Curriculum"] = outline()
    runner.responses["Research"] = {"concepts": [card("a"), card("b", ["a"])]}
    runner.responses["Fact-check"] = {"results": []}
    runner.responses["Placement"] = {"items": []}
    actions.dispatch(db, jobs, {"type": "createGoal", "answers": [{"q": "goal", "a": "AI"}, {"q": "k", "a": ""},
                                                                  {"q": "w", "a": ""}, {"q": "t", "a": "8 hours"}]})
    s = state.snapshot(db)
    gid = s["goal"]["id"]
    assert s["goal"]["layout"] == "ohtani"
    assert [t["pos"] for t in s["tracks"]] == ohtani.RING + ["C"]
    first = s["modules"][0]
    assert first["id"] == f"{gid}-t0-m0" and first["research"] == "ready" and first["doneWhen"] == "check"
    # the curriculum call used the Ohtani prompt and the placement quiz skips merge steps
    curriculum = next(c for r, c in runner.calls if r == "Curriculum")
    assert "Ohtani table" in curriculum.prompt
    placement = next(c for r, c in runner.calls if r == "Placement")
    assert "Merge 1" not in placement.prompt and "A1 step 1" in placement.prompt

    # research the merge's requirements and the merge itself: the merge stays locked until both are learned
    merge = f"{gid}-tc-m0"
    for mid in (f"{gid}-t0-m1", f"{gid}-t1-m1", merge):
        jobs.enqueue("research_module", "r", {"module_id": mid})
    research = [c for r, c in runner.calls if r == "Research"][-1]
    assert "It merges what these steps taught: A1 step 2, A2 step 2" in research.prompt
    states = {c["id"]: c["state"] for c in state.snapshot(db)["concepts"]}
    assert states[f"{merge}-a"] == "locked"
    for mid in (f"{gid}-t0-m1", f"{gid}-t1-m1"):
        for k in ("a", "b"):
            for item in ("i1", "i2", "i3", "i4", "i5"):
                progress.record_evidence(db, f"{mid}-{k}", item, 1.0)
    states = {c["id"]: c["state"] for c in state.snapshot(db)["concepts"]}
    assert states[f"{merge}-a"] == "ready" and states[f"{merge}-b"] == "locked"
    # placeholders for unresearched requirements never leak into the snapshot
    assert all(not p.startswith("module:") for c in state.snapshot(db)["concepts"] for p in c["prereqs"])


def test_merge_with_unresearched_requirement_is_locked(env):
    db, jobs, runner = env
    runner.responses["Curriculum"] = outline()
    runner.responses["Research"] = {"concepts": [card("a")]}
    runner.responses["Fact-check"] = {"results": []}
    runner.responses["Placement"] = {"items": []}
    actions.dispatch(db, jobs, {"type": "createGoal", "answers": [{"q": "goal", "a": "AI"}]})
    gid = state.active_goal(db)
    jobs.enqueue("research_module", "r", {"module_id": f"{gid}-tc-m0"})
    states = {c["id"]: c["state"] for c in state.snapshot(db)["concepts"]}
    assert states[f"{gid}-tc-m0-a"] == "locked"
    lessons = [i for d in planner.plan_week(db)["days"] for i in d["items"] if i["kind"] == "lesson"]
    assert f"{gid}-tc-m0-a" not in {i["conceptId"] for i in lessons}
