"""Recall practice (SPEC §24): problems over ideas, judged from the learner's thinking, with a schedule per idea."""

import pytest

from dsc import actions, graph, practice, state


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def problem(call):
    problem.prompt = call.prompt
    return {"title": "Walk the dog", "prompt": "You walk 3 m east and 4 m north. How far are you from the start?",
            "node_ids": ["c-vectors", "not-a-node"], "solution": "5 m, by Pythagoras on the sum vector (3, 4).",
            "steps": ["add the moves as vectors", "length of (3, 4)"]}


VERDICTS = []


def judge(call):
    judge.prompt = call.prompt
    return VERDICTS.pop(0)


def setup(db, jobs, runner):
    act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=0)  # c-vectors is now being learned
    runner.responses["Practice"] = lambda call: judge(call) if "read a learner's thinking" in call.prompt else problem(call)


def view(db):
    return practice.view(db, db.meta("last_practice"))


def open_item(db):
    """The open problem; after a solve the next one waits for "Next problem" (SPEC §44), so press it."""
    if not any(i["status"] == "open" for i in view(db)["items"]) and view(db)["status"] == "active":
        practice.advance(db, db.meta("last_practice"))
    return next(i for i in view(db)["items"] if i["status"] == "open")


def test_weakest_ideas_by_default_and_a_full_problem_with_a_hint(env):
    db, jobs, runner = env
    setup(db, jobs, runner)
    assert practice.weakest(db)[0]["nodeId"] == "c-vectors"  # nothing picked: the weakest ideas (no schedule)
    s = act(db, jobs, type="startPractice")
    assert s["practices"][0]["id"] == db.meta("last_practice")
    v = view(db)
    assert v["ideas"][0]["id"] == "c-vectors" and len(v["items"]) == 1
    it = v["items"][0]
    assert it["ideas"] == [{"id": "c-vectors", "title": "Vectors"}]  # an unknown id is dropped
    assert it["solution"] is None and "Pythagoras" not in str(it)  # hidden while open
    assert "Difficulty level 1" in problem.prompt and "c-vectors: Vectors" in problem.prompt

    VERDICTS[:] = [{"verdict": "progress", "feedback": "Good start.", "hint": "should be ignored"},
                   {"verdict": "stuck", "feedback": "You stopped.", "hint": "What is the length of an arrow?"},
                   {"verdict": "solved", "feedback": "Yes, 5 m."}]
    act(db, jobs, type="practiceSubmit", itemId=it["id"], text="I add (3,0) and (0,4)")
    assert open_item(db)["chunks"][0]["verdict"] == "progress" and not open_item(db)["chunks"][0]["hint"]
    assert "I add (3,0) and (0,4)" in judge.prompt and "Pythagoras" in judge.prompt  # the judge sees the hidden solution
    act(db, jobs, type="practiceSubmit", itemId=it["id"], text="", hint=True)
    assert open_item(db)["hints"] == 1
    act(db, jobs, type="practiceSubmit", itemId=it["id"], text="length is sqrt(9+16) = 5")
    v = view(db)
    done = v["items"][0]
    assert done["status"] == "solved" and done["score"] == 0.7 and done["solution"].startswith("5 m")
    assert len(v["items"]) == 2 and v["level"] == 1  # one hint: same level; the next problem is written
    nxt = v["items"][1]
    assert nxt["status"] == "waiting" and nxt["prompt"] == "" and nxt["title"] == ""  # hidden until "Next problem"
    act(db, jobs, type="practiceNext", practiceId=v["id"])
    assert view(db)["items"][1]["status"] == "open" and view(db)["items"][1]["prompt"]
    ev = db.one("SELECT * FROM evidence WHERE item_id=?", (f"{v['id']}-{done['id']}",))
    assert ev["concept_id"] == "c-vectors" and ev["kind"] == "practice" and ev["score"] == 0.7
    assert not db.q("SELECT 1 FROM node_reviews")  # no schedule (SPEC §48)

    # a clean solve raises the level, giving up lowers it again and shows the solution
    VERDICTS[:] = [{"verdict": "solved", "feedback": "Clean."}]
    act(db, jobs, type="practiceSubmit", itemId=open_item(db)["id"], text="5 m by Pythagoras")
    assert view(db)["level"] == 2
    act(db, jobs, type="practiceGiveUp", itemId=open_item(db)["id"])
    v = view(db)
    assert v["level"] == 1 and v["items"][2]["status"] == "given_up" and v["items"][2]["score"] == 0 and v["items"][2]["solution"]
    act(db, jobs, type="practiceStop", practiceId=v["id"])
    v = view(db)
    assert v["status"] == "done" and all(i["status"] != "open" or i["chunks"] for i in v["items"])


def test_practice_is_evidence_on_the_idea(env):
    db, jobs, runner = env
    setup(db, jobs, runner)
    act(db, jobs, type="startPractice", nodeIds=["c-vectors"])
    for _ in range(3):  # three clean solves on the same idea
        VERDICTS[:] = [{"verdict": "solved", "feedback": "ok"}]
        act(db, jobs, type="practiceSubmit", itemId=open_item(db)["id"], text="done")
    kinds = [r["kind"] for r in db.q("SELECT kind FROM evidence WHERE item_id LIKE 'p-%' ORDER BY id")]
    assert set(kinds) == {"practice"}  # also once learned: there is no "review" kind any more
    st = graph.states(db)["c-vectors"]
    assert st.mastery > 0.5


def test_own_problem_and_errors(env):
    db, jobs, runner = env
    setup(db, jobs, runner)
    act(db, jobs, type="startPractice", own="Two force vectors of 3 N east and 4 N north act on a box. What is the total force?")
    v = view(db)
    assert v["count"] == 1 and "Two force vectors" in problem.prompt and "c-vectors" in problem.prompt  # the graph match
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "practiceSubmit", "itemId": open_item(db)["id"], "text": ""})
    runner.responses["Practice"] = {"title": "t", "prompt": "", "node_ids": [], "solution": "", "steps": []}
    act(db, jobs, type="startPractice", nodeIds=["c-vectors"])
    v = view(db)
    assert v["items"] == [] and ("empty" in v["error"] or "none of the ideas" in v["error"])
    setup(db, jobs, runner)
    act(db, jobs, type="practiceRetry", practiceId=v["id"])
    assert len(view(db)["items"]) == 1 and not view(db)["error"]
    assert "practiceDue" not in state.snapshot(db)  # no schedule (SPEC §48)


def test_pick_by_lesson_focus_and_formula_switch_ideas_hint_ladder_and_retests(env):
    """SPEC §44: practise from a picked lesson, its parts and a formula; ideas switch; hints climb a ladder; the end
    retests what was missed."""
    db, jobs, runner = env
    setup(db, jobs, runner)
    from dsc import formulas
    db.x("""INSERT INTO formula_notes(concept_id, key, tex, body, created_at, kind, formula_id, matched_at) VALUES(?,?,?,?,?,?,?,?)""",
         ("c-lincomb", formulas.key("w = c_1 v_1"), "w = c_1 v_1", '{"name": "Linear combination"}', "2026-01-01", "idea", None,
          "2026-01-01"))
    db.x("INSERT INTO formula_fields(key, fields, at) VALUES(?,?,?)", (formulas.key("w = c_1 v_1"), '["linalg"]', "2026-01-01"))
    t = practice.targets(db)
    lin = next(f for f in t["fields"] if f["id"] == "linalg")
    assert lin["formulas"][0]["name"] == "Linear combination"
    assert t["weakest"] and t["weakest"][0]["nodeId"] == "c-vectors"  # the idea being learned is the weakest
    act(db, jobs, type="startPractice", nodeIds=["c-vectors"], focus={"c-vectors": ["Adding arrows"], "c-nope": ["x"]},
        formulas=[lin["formulas"][0]["key"]], count=2, surface="applied", title="My pick")
    v = view(db)
    assert v["title"] == "My pick" and v["count"] == 2 and v["surface"] == "applied"
    assert v["focus"] == {"c-vectors": ["Adding arrows"]} and v["formulas"] == [{"name": "Linear combination", "tex": "w = c_1 v_1"}]
    assert {i["id"] for i in v["ideas"]} == {"c-vectors", "c-lincomb"}  # the formula brings its lesson's idea
    p = problem.prompt
    assert "Vectors (c-vectors): Adding arrows" in p and "Linear combination: $w = c_1 v_1$" in p and "prefers applied" in p
    assert "Never the same idea as the last problem" in p and "The idea(s) of the last problem: (none)" in p

    # the hint ladder: the judge is told which rung comes next, and the rung is kept
    VERDICTS[:] = [{"verdict": "stuck", "feedback": "Stuck.", "hint": "Re-read the second given.", "rung": 0},
                   {"verdict": "stuck", "feedback": "Still.", "hint": "It is a sum of moves.", "rung": 1}]
    it = open_item(db)
    act(db, jobs, type="practiceSubmit", itemId=it["id"], text="", hint=True)
    assert 'rung 0 ("look again at a given")' in judge.prompt
    act(db, jobs, type="practiceSubmit", itemId=it["id"], text="", hint=True)
    assert 'rung 1 ("name the kind of pattern")' in judge.prompt and [c["rung"] for c in open_item(db)["chunks"]] == [0, 1]
    act(db, jobs, type="practiceGiveUp", itemId=it["id"])

    # "Next problem" pressed before the next one is written: it opens as soon as it is written
    db.x("DELETE FROM practice_items WHERE status='waiting'")
    practice.advance(db, v["id"])
    assert practice.view(db, v["id"])["wantNext"]
    practice.next_problem(db, jobs, v["id"])
    v2 = practice.view(db, v["id"])
    assert v2["items"][-1]["status"] == "open" and not v2["wantNext"]
    assert "The idea(s) of the last problem: c-vectors" in problem.prompt
    VERDICTS[:] = [{"verdict": "solved", "feedback": "Clean."}]
    act(db, jobs, type="practiceSubmit", itemId=open_item(db)["id"], text="5 m")
    # both problems are done: the given-up one comes back once as a retest, in a new setting
    assert "This is a RETEST of a problem the learner gave up on" in problem.prompt
    act(db, jobs, type="practiceNext", practiceId=v["id"])
    v3 = view(db)
    assert v3["retests"] == 1 and v3["count"] == 3 and v3["items"][-1]["retest"] and v3["items"][-1]["status"] == "open"
    VERDICTS[:] = [{"verdict": "solved", "feedback": "Yes."}]
    act(db, jobs, type="practiceSubmit", itemId=v3["items"][-1]["id"], text="done")
    assert view(db)["status"] == "done"  # one retest each: then the run ends
