"""The lesson plan graph (SPEC §42): a book lesson is planned, the learner changes and approves the plan, and the lesson is
then written from it."""

import pytest

from dsc import actions, bookstudy, lesson, lesson_graph, state
from test_bookstudy import book, cards_reply, lessons  # noqa: F401 - the fixture is used by name

PLAN = {
    "approach": "You hold softmax. We build attention on it, one step at a time.",
    "goal": "Attention is a softmax-weighted sum of values.",
    "nodes": [
        {"key": "softmax", "kind": "held", "title": "Softmax", "says": "Turns scores into weights.", "form": "none"},
        {"key": "scores", "kind": "foundation", "title": "Scores from dot products", "says": "$q \\cdot k$ is a score.",
         "form": "example", "why_form": "numbers make it concrete"},
        {"key": "weights", "kind": "step", "title": "Weights from scores", "says": "Softmax of the scores.", "form": "interactive"},
        {"key": "Weighted Sum!", "kind": "formula", "title": "The weighted sum", "says": "$\\sum_i w_i v_i$", "form": "derivation"},
        {"key": "goal", "kind": "nonsense", "title": "Attention", "says": "The goal.", "form": "teleport"},
        {"key": "weights", "kind": "step", "title": "A duplicate key", "says": "dropped", "form": "text"},
    ],
    "edges": [["softmax", "weights"], ["scores", "weights"], ["weights", "weighted-sum"], ["weighted-sum", "goal"],
              ["goal", "scores"], ["nope", "goal"]],
}


@pytest.fixture
def planned(book):  # noqa: F811
    db, jobs, runner = book
    prompts = []

    def research(call):
        if "You plan one lesson of a book" in call.prompt:
            prompts.append(call.prompt)
            if research.during:  # the learner sends a note while this version is being made
                note, research.during = research.during, None
                lesson_graph.note(db, jobs, research.cid, "steer", note)
            return PLAN
        return cards_reply(call)
    research.during = None
    runner.responses["Research"] = research
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-1"})
    bid = state.snapshot(db)["studyBooks"][0]["id"]
    cid = lessons(db, bid)["Attention"]["conceptId"]
    research.cid = cid
    return db, jobs, runner, bid, cid, prompts, research


def test_opening_an_unwritten_book_lesson_plans_it_first(planned):
    db, jobs, runner, bid, cid, prompts, _ = planned
    v = lesson.open_lesson(db, jobs, cid)
    assert v["lessonPlan"] == {"version": 1, "status": "ready"} and not v["card"]
    assert not any(lessons(db, bid)[t]["carded"] for t in ("Softmax", "Attention", "KV cache"))  # nothing written yet
    assert lessons(db, bid)["Attention"]["plan"] == "ready"
    p = prompts[0]
    assert "[p. 4]" in p and "Attention" in p and "(none: this is the first version)" in p
    view = lesson_graph.view(db, cid)
    plan = view["plan"]
    assert [n["key"] for n in plan["nodes"]] == ["softmax", "scores", "weights", "weighted-sum", "goal"]  # duplicate dropped
    goal = plan["nodes"][-1]
    assert goal["kind"] == "goal" and goal["form"] == "text"  # unknown kind and form fixed
    assert ["goal", "scores"] not in plan["edges"] and ["weighted-sum", "goal"] in plan["edges"]  # the cycle is cut
    assert not any("nope" in e for e in plan["edges"])
    lesson.open_lesson(db, jobs, cid)
    assert lesson_graph.view(db, cid)["versions"] == [1]  # opening again does not plan again


def test_notes_and_a_new_version_then_approve_makes_only_this_lesson(planned):
    db, jobs, runner, bid, cid, prompts, _ = planned
    lesson.open_lesson(db, jobs, cid)
    act = lambda **a: actions.dispatch(db, jobs, a)  # noqa: E731
    act(type="lessonPlanNote", conceptId=cid, kind="cut", node="scores")
    act(type="lessonPlanNote", conceptId=cid, kind="cut", node="weights")
    act(type="lessonPlanNote", conceptId=cid, kind="cut", node="weights")  # pressed twice: taken back
    act(type="lessonPlanNote", conceptId=cid, kind="other", node="weighted-sum", text="with a picture")
    act(type="lessonPlanNote", conceptId=cid, kind="plan", text="Fewer steps, more numbers.")
    with pytest.raises(actions.ActionError):
        act(type="lessonPlanNote", conceptId=cid, kind="note", node="no-such-node", text="x")
    assert lesson_graph.view(db, cid)["pending"] == 3
    act(type="planLesson", conceptId=cid)
    p = prompts[-1]
    assert "Version 1." in p and 'I already know this' in p and '"Scores from dot products"' in p
    assert "show this another way with a picture" in p and "Fewer steps, more numbers." in p
    assert '"Weights from scores"' not in p.split("New notes on the plan")[1].split("<book>")[0]
    assert "Notes the learner gave on earlier versions" in p and p.split("Notes the learner gave on earlier versions")[1].split("New notes")[0].strip().endswith("(none)")
    view = lesson_graph.view(db, cid)
    assert view["versions"] == [1, 2] and view["pending"] == 0 and all(n["used"] == 2 for n in view["notes"])
    assert all(n.get("change", "") == "" for n in view["plan"]["nodes"])  # the same plan came back: nothing marked
    act(type="lessonPlanNote", conceptId=cid, kind="note", node="goal", text="Name the formula.")
    act(type="planLesson", conceptId=cid)  # version 3: the notes of version 2 still hold
    earlier = prompts[-1].split("Notes the learner gave on earlier versions")[1].split("New notes")[0]
    assert "Fewer steps, more numbers." in earlier and "I already know this" in earlier
    assert "Name the formula." in prompts[-1].split("New notes on the plan")[1]
    act(type="approveLessonPlan", conceptId=cid)
    assert lesson_graph.latest(db, cid)["status"] == "approved"
    ls = lessons(db, bid)
    assert ls["Attention"]["carded"] and not ls["Softmax"]["carded"] and not ls["KV cache"]["carded"]
    assert not cards_reply.prompts  # no batch writing: the plan becomes a step lesson (SPEC §43, test_lesson_steps)
    v = lesson.view(db, cid)
    assert v["card"] and v["lessonPlan"]["status"] == "approved" and v["steps"]["total"] == 4


def test_a_note_sent_while_planning_starts_the_next_version(planned):
    db, jobs, runner, bid, cid, prompts, research = planned
    research.during = "Use a coin-flip example."
    lesson.open_lesson(db, jobs, cid)
    view = lesson_graph.view(db, cid)
    assert view["versions"] == [1, 2] and len(prompts) == 2
    assert "Use a coin-flip example." in prompts[1] and view["notes"][0]["used"] == 2


def test_approve_needs_a_finished_plan_and_no_plan_writes_at_once(planned):
    db, jobs, runner, bid, cid, prompts, _ = planned
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    kv = lessons(db, bid)["KV cache"]["conceptId"]
    lesson.open_lesson(db, jobs, cid)  # Attention is planned
    lesson.open_lesson(db, jobs, kv, plan=False)  # "Write it now": the chapter is written, but not the planned lesson
    ls = lessons(db, bid)
    assert ls["KV cache"]["carded"] and ls["Softmax"]["carded"] and not ls["Attention"]["carded"]
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "planLesson", "conceptId": "c-vectors"})  # not a book lesson
    assert bookstudy.get(db, bid)
