"""Step lessons (SPEC §43): an approved plan is taught one step at a time, each step written just ahead of the learner:
predict, the step, a check, and a repair after a miss."""

import re

import pytest

from dsc import actions, lesson, lesson_steps, state
from test_bookstudy import book, prose_reply  # noqa: F401 - fixtures are used by name
from test_lesson_graph import planned  # noqa: F401 - the fixture is used by name


def step_reply(call):
    if "You write ONE step of a lesson" not in call.prompt:
        return prose_reply(call)
    step_reply.prompts.append(call.prompt)
    title = re.search(r"This step: \d+ of \d+: \[(\w+)\] ([^.]+)\.", call.prompt)
    kind, name = title.group(1), title.group(2)
    out = {"predict": {"prompt": f"What will {name} show?", "options": ["a", "b", "c"], "answer": 1, "explanation": "b, because."},
           "body": f"The step {name}: one fact.", "check": {"prompt": f"Check {name}?", "options": ["w", "x", "y", "z"], "answer": 2,
                                                             "explanation": "y."},
           "repair": f"Repair for {name}."}
    if kind == "goal":
        out["explain"] = {"prompt": "Explain attention.", "rubric": ["weights", "sum"], "work": False}
    if kind == "step":
        out["viz"] = {"type": "nonsense"}  # a broken widget is dropped, not shown
    return out


@pytest.fixture
def steps(planned):  # noqa: F811
    db, jobs, runner, bid, cid, prompts, research = planned
    step_reply.prompts = []
    runner.responses["Renditions"] = step_reply
    runner.responses["Lesson assets"] = lambda call: {"type": "nonsense"}
    lesson.open_lesson(db, jobs, cid)
    actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    return db, jobs, runner, cid


def ids(card):
    return [s["id"] for s in card["sections"]]


def answer(db, jobs, cid, sid, right=True):
    card = state.latest_card(db, cid)
    chk = next(s for s in card["sections"] if s["id"] == sid)["check"]
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": cid, "checkId": chk["id"],
                                "choice": chk["answer"] if right else (chk["answer"] + 1) % len(chk["options"])})


def test_approving_makes_a_step_lesson_and_writes_only_the_first_two_steps(steps):
    db, jobs, runner, cid = steps
    card = state.latest_card(db, cid)
    assert card["steps"] and card["held"] == ["Softmax"]
    assert ids(card) == ["s-scores", "s-weights", "s-weighted-sum", "s-goal"]  # held left out, in the plan's order
    assert [s["form"] for s in card["sections"]] == ["example", "interactive", "derivation", "text"]
    v = lesson.view(db, cid)
    st = v["steps"]
    assert st["current"] == 0 and [n["written"] for n in st["nodes"]] == [True, True, False, False]
    s0 = v["sections"][0]
    assert s0["body"] == "The step Scores from dot products: one fact." and s0["repair"] == "Repair for Scores from dot products."
    assert s0["predict"]["prompt"] and "answer" not in s0["predict"] and s0["check"]["id"] == "q-s-scores"
    assert "viz" not in card["sections"][1] or v["sections"][1]["viz"] is None  # the broken widget is dropped
    p = step_reply.prompts[0]
    assert "This step: 1 of 4: [foundation] Scores from dot products." in p and "(none: this is the first step)" in p
    assert "Its form: example (numbers make it concrete)" in p and "[Inference Book, p. 4]" in p
    assert not [c for r, c in runner.calls if r == "Research" and "lesson cards" in c.prompt.lower()]  # no batch writing
    lesson.ensure_prose(db, jobs, cid)
    assert len(step_reply.prompts) == 2  # opening again writes nothing new
    assert not db.q("SELECT error FROM jobs WHERE kind='lesson_step' AND status != 'done'")  # every step job ends well


def test_answers_open_the_next_steps_and_the_writer_sees_how_the_learner_did(steps):
    db, jobs, runner, cid = steps
    actions.dispatch(db, jobs, {"type": "predictStep", "conceptId": cid, "sectionId": "s-scores", "choice": 0,
                                "thinking": "I guess the first"})
    pred = lesson.view(db, cid)["steps"]["predictions"]["s-scores"]
    card = state.latest_card(db, cid)
    assert pred["choice"] == 0 and pred["correct"] is (card["sections"][0]["predict"]["answer"] == 0) and "answer" in pred
    answer(db, jobs, cid, "s-scores", right=False)
    st = lesson.view(db, cid)["steps"]
    assert st["current"] == 1 and st["nodes"][0]["done"] and st["nodes"][2]["written"]  # one step ahead again
    p = step_reply.prompts[-1]
    assert "This step: 3 of 4" in p and "Check: WRONG (the repair was shown)" in p and "I guess the first" in p
    answer(db, jobs, cid, "s-weights")
    answer(db, jobs, cid, "s-weighted-sum")
    v = lesson.view(db, cid)
    goal = v["sections"][3]
    assert v["steps"]["current"] == 3 and goal["explain"]["id"] == "e-s-goal" and not goal["check"] is None
    actions.dispatch(db, jobs, {"type": "explain", "conceptId": cid, "itemId": "e-s-goal",
                                "answer": "Attention weighs the values by softmax of the scores."})
    assert lesson.view(db, cid)["steps"]["current"] == 4  # done


def test_explain_differently_writes_one_step_again_with_the_note(steps):
    db, jobs, runner, cid = steps
    n = len(step_reply.prompts)
    actions.dispatch(db, jobs, {"type": "rewriteStep", "conceptId": cid, "sectionId": "s-weights", "note": "Use a picture."})
    assert len(step_reply.prompts) == n + 1 and "Use a picture." in step_reply.prompts[-1]
    actions.dispatch(db, jobs, {"type": "explainDifferently", "conceptId": cid, "sectionId": "s-scores"})
    assert "Explain it another way" in step_reply.prompts[-1]
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "rewriteStep", "conceptId": cid, "sectionId": "s-nope"})
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "predictStep", "conceptId": cid, "sectionId": "s-scores", "choice": 9})
    assert lesson_steps.current(db, cid, state.latest_card(db, cid)) == 0
