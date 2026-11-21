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
    return next(i for i in view(db)["items"] if i["status"] == "open")


def test_due_ideas_and_a_full_problem_with_a_hint(env):
    db, jobs, runner = env
    setup(db, jobs, runner)
    due = practice.due(db)
    assert due[0]["nodeId"] == "c-vectors" and due[0]["reason"] == "new"
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
    ev = db.one("SELECT * FROM evidence WHERE item_id=?", (f"{v['id']}-{done['id']}",))
    assert ev["concept_id"] == "c-vectors" and ev["kind"] == "practice" and ev["score"] == 0.7
    assert db.one("SELECT due FROM node_reviews WHERE node_id='c-vectors'")
    assert practice.due(db) == [] or practice.due(db)[0]["nodeId"] != "c-vectors"  # scheduled for later now

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


def test_practice_is_evidence_on_the_idea_and_reviews_once_learned(env):
    db, jobs, runner = env
    setup(db, jobs, runner)
    act(db, jobs, type="startPractice", nodeIds=["c-vectors"])
    for _ in range(3):  # three clean solves on the same idea
        VERDICTS[:] = [{"verdict": "solved", "feedback": "ok"}]
        act(db, jobs, type="practiceSubmit", itemId=open_item(db)["id"], text="done")
    kinds = [r["kind"] for r in db.q("SELECT kind FROM evidence WHERE item_id LIKE 'p-%' ORDER BY id")]
    assert kinds[0] == "practice"
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
    assert state.snapshot(db)["practiceDue"] == 0
