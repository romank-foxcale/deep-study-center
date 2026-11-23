"""Generated interactive demos (SPEC §45): built from a brief, checked by code, tested by the page, fixed once."""

import pytest

from dsc import actions, demos, lesson, state
from test_bookstudy import book  # noqa: F401 - fixtures are used by name
from test_lesson_graph import planned  # noqa: F401
import test_lesson_steps

GOOD = """<!doctype html><html><body><input type="range" id="k" min="1" max="8" value="2"><canvas id="c"></canvas>
<script>const k = document.getElementById('k'); k.addEventListener('input', () => draw()); function draw() {}</script></body></html>"""
BAD = GOOD.replace("function draw() {}", "function draw() { fetch('/api/state') }")


def test_the_check_keeps_demos_self_contained_and_offline():
    assert demos.check(GOOD) == []
    assert demos.check(GOOD.replace("<canvas", "<svg xmlns='http://www.w3.org/2000/svg'></svg><canvas")) == []
    assert "uses fetch(): demos may not load anything" in demos.check(BAD)
    assert any("outside script" in p for p in demos.check('<script src="x.js"></script><button>b</button>'))
    assert any("browser storage" in p for p in demos.check(GOOD.replace("draw() {}", "draw() { localStorage.x = 1 }")))
    assert any("out of its frame" in p for p in demos.check(GOOD.replace("draw() {}", "draw() { window.parent.x = 1 }")))
    assert any("no control" in p for p in demos.check("<canvas></canvas><script>1</script>"))
    assert demos.check("") == ["the demo is empty"]
    assert any("larger" in p for p in demos.check(GOOD + "x" * demos.MAX_BYTES))


@pytest.fixture
def demo_lesson(planned, monkeypatch):  # noqa: F811
    """A step lesson whose interactive step asks for a demo (no built-in widget fits)."""
    db, jobs, runner, bid, cid, prompts, research = planned
    built = []

    def step_reply(call):
        out = test_lesson_steps.step_reply(call)
        if isinstance(out, dict) and "[step] Weights from scores" in call.prompt:
            out.pop("viz", None)
            out["demo_brief"] = "A slider for the score gap; show both softmax weights as bars and as numbers."
        return out

    def builder(call):
        if "You build ONE small interactive demo" in call.prompt:
            built.append(call.prompt)
            return {"title": "Score gap", "html": builder.queue.pop(0), "watch": "Drag the gap and watch the weights."}
        return {"type": "nonsense"}
    builder.queue = []
    test_lesson_steps.step_reply.prompts = []
    runner.responses["Renditions"] = step_reply
    runner.responses["Lesson assets"] = builder
    return db, jobs, runner, cid, builder, built


def demo_of(db, cid, sid="s-weights"):
    return next(s for s in lesson.view(db, cid)["sections"] if s["id"] == sid)["demo"]


def test_a_demo_is_built_checked_fixed_once_and_shown_after_the_page_tested_it(demo_lesson):
    db, jobs, runner, cid, builder, built = demo_lesson
    builder.queue = [BAD, GOOD]  # the first build fails the check: one fix round with the exact problem
    lesson.open_lesson(db, jobs, cid)
    actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    d = demo_of(db, cid)
    assert d["status"] == "ready" and d["html"] == GOOD and d["version"] == 1 and not d["tested"]
    assert len(built) == 2 and "uses fetch()" in built[1] and "A slider for the score gap" in built[0]
    assert demo_of(db, cid, "s-scores") is None  # other steps have no demo
    actions.dispatch(db, jobs, {"type": "demoResult", "conceptId": cid, "sectionId": "s-weights", "version": 1, "ok": True})
    assert demo_of(db, cid)["tested"]


def test_a_demo_that_fails_in_the_page_is_fixed_once_then_left_out(demo_lesson):
    db, jobs, runner, cid, builder, built = demo_lesson
    builder.queue = [GOOD, GOOD]
    lesson.open_lesson(db, jobs, cid)
    actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    assert demo_of(db, cid)["version"] == 1
    act = lambda **a: actions.dispatch(db, jobs, {"type": "demoResult", "conceptId": cid, "sectionId": "s-weights", **a})  # noqa: E731
    act(version=1, ok=False, errors=["TypeError: x is undefined (line 3)"])
    d = demo_of(db, cid)
    assert d["status"] == "ready" and d["version"] == 2 and "TypeError: x is undefined (line 3)" in built[-1]
    act(version=1, ok=False, errors=["old"])  # a result for an old version is ignored
    assert demo_of(db, cid)["status"] == "ready"
    act(version=2, ok=False, errors=["RangeError"])
    d = demo_of(db, cid)
    assert d["status"] == "failed" and "html" not in d and len(built) == 2  # no third build: the step text stands alone
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "demoResult", "conceptId": cid, "sectionId": "s-scores", "version": 1, "ok": True})
    assert state.latest_card(db, cid)["sections"][1]["demo"]["errors"] == ["RangeError"]
