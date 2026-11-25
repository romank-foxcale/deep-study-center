"""End-to-end flows through actions, lessons and jobs (with a fake provider)."""

import pytest

from dsc import actions, lesson, state
from dsc.providers import parse_claude_output


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def angles(db, cid="c-vectors"):
    return {s["id"]: s["angle"] for s in lesson.view(db, cid)["sections"]}


def test_seed_snapshot_serves_vectors_without_a_provider(env):
    db, jobs, runner = env
    s = state.snapshot(db)
    assert s["goal"]["title"].startswith("Become")
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "learning"
    v = lesson.open_lesson(db, jobs, "c-vectors")
    assert all(sec["body"] for sec in v["sections"]) and not runner.calls
    # answer keys are hidden until answered
    assert all("answer" not in (sec["check"] or {}) for sec in v["sections"])


def test_section_feedback_pins_that_section_and_repeated_feedback_flips_the_lesson_on_open(env):
    db, jobs, _ = env
    lesson.open_lesson(db, jobs, "c-vectors")
    a0 = angles(db)
    geometric = lambda a: sum(1 for x in a.values() if x == "geometric")  # noqa: E731
    # a mix that follows the playbook: the liked angle leads, but not everywhere
    assert len(set(a0.values())) >= 2 and geometric(a0) > len(a0) / 2
    avail = ["geometric", "algebraic", "computational"]

    s = act(db, jobs, type="feedback", conceptId="c-vectors", sectionId="s-idea", angle="geometric",
            available=avail, tags=["framing-off"], text="")
    a1 = angles(db)
    assert a1["s-idea"] != "geometric" and {k: v for k, v in a1.items() if k != "s-idea"} == \
        {k: v for k, v in a0.items() if k != "s-idea"}  # only the targeted section changed
    assert next(r for r in s["renditions"] if r["conceptId"] == "c-vectors")["stale"]
    assert "This section now uses" in s["feedback"][0]["effects"][0]

    act(db, jobs, type="feedback", conceptId="c-vectors", sectionId="s-ops", angle="geometric",
        available=avail, tags=["framing-off"], text="arrows don't help me")
    assert {k: v for k, v in angles(db).items() if k != "s-ops"} == {k: v for k, v in a1.items() if k != "s-ops"}  # not rewritten while reading
    v = lesson.open_lesson(db, jobs, "c-vectors")  # reopen: re-rendered with the new playbook
    assert v["refreshed"]
    after = angles(db)
    assert geometric(after) < geometric(a0) and after["s-idea"] == a1["s-idea"]  # pins survive
    geo = next(e for e in state.playbook(db)["entries"] if e["value"] == "geometric")
    assert geo["verdict"] == "trying" and geo["note"] == "arrows don't help me"


def test_studied_lesson_is_not_rewritten_silently(env):
    db, jobs, _ = env
    lesson.open_lesson(db, jobs, "c-vectors")
    act(db, jobs, type="markStudied", conceptId="c-vectors")
    act(db, jobs, type="adjust", key="pace", value=-2)
    v = lesson.open_lesson(db, jobs, "c-vectors")
    assert not v["refreshed"] and v["rendition"]["stale"] and v["rendition"]["studied"]


def test_new_style_renders_through_provider_and_falls_back_to_cached_prose_meanwhile(env):
    db, jobs, runner = env
    runner.responses["Renditions"] = lambda call: {"sections": [
        {"id": line.split()[1], "body": f"rendered {line.split()[1]}"} for line in call.prompt.splitlines() if line.startswith("- s-")]}
    act(db, jobs, type="adjust", key="rigor", value=2)
    v = lesson.open_lesson(db, jobs, "c-vectors")
    prose = [c for r, c in runner.calls if r == "Renditions"]
    assert prose and "rigor 2" in prose[0].prompt
    assert v["sections"][0]["body"].startswith("rendered") and not v["sections"][0]["approximate"]


def test_lesson_without_prose_renders_on_open(env):
    db, jobs, runner = env
    runner.responses["Renditions"] = lambda call: {"sections": [
        {"id": line.split()[1], "body": "text"} for line in call.prompt.splitlines() if line.startswith("- s-")]}
    v = lesson.open_lesson(db, jobs, "c-lincomb")
    assert len(v["sections"]) == 6 and all(s["body"] == "text" for s in v["sections"])


def test_render_failure_is_reported(env):
    db, jobs, runner = env
    runner.unavailable = True
    v = lesson.open_lesson(db, jobs, "c-lincomb")
    assert v["renderError"] and all(s["body"] is None for s in v["sections"])


def test_answers_are_graded_on_the_server_and_learning_needs_the_explain_back(env):
    db, jobs, runner = env
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=1, angle="geometric")
    assert s["answers"]["c-vectors:q-ops"]["correct"] is False and s["answers"]["c-vectors:q-ops"]["answer"] == 0
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        s = act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice, angle="geometric")
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "learning"  # explain-back still missing
    runner.responses["Grading"] = {"score": 1, "feedback": "Clear.", "missing": [], "followup": ""}
    s = act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", angle="geometric",
            answer="Moving right doesn't change how far up you are, so each coordinate adds on its own.")
    states = {c["id"]: c["state"] for c in s["concepts"]}
    assert states["c-vectors"] == "learned" and states["c-dot"] == "ready"
    assert "reviews" not in s and not db.one("SELECT 1 FROM sqlite_master WHERE name='reviews'")  # no schedule (SPEC §48)
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "review", "conceptId": "c-vectors", "checkId": "q-norm", "choice": 0})


def test_offline_fallbacks_keep_the_app_usable(env):
    db, jobs, runner = env
    runner.unavailable = True
    s = act(db, jobs, type="chat", conceptId="c-vectors", text="why?")
    assert s["chats"]["c-vectors"][-1]["role"] == "tutor"
    s = act(db, jobs, type="feedback", conceptId="c-vectors", tags=["confused"], text="")
    assert s["feedback"] and "diffs" not in s  # no roadmap review any more: the feedback is kept
    assert any(j["status"] == "failed" and "fallback" in j["error"] for j in s["jobs"])


def test_new_goal_outline_then_first_module_research(env):
    db, jobs, runner = env
    runner.responses["Curriculum"] = {"title": "Learn RL", "why": "w", "done": "d", "tracks": [
        {"title": "Basics", "summary": "s", "modules": [{"title": "MDPs", "summary": "m", "planned": 2}]}]}
    runner.responses["Research"] = {"concepts": [
        {"key": "mdp", "title": "MDP", "objective": "o", "minutes": 20, "prereq_keys": [],
         "card": {"bloom": "understand", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                  "misconceptions": [], "sources": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}]}},
        {"key": "policy", "title": "Policy", "objective": "o", "minutes": 20, "prereq_keys": ["mdp"],
         "card": {"bloom": "understand", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                  "misconceptions": [], "sources": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}]}}]}
    runner.responses["Fact-check"] = {"results": []}
    s = act(db, jobs, type="createGoal", layout="list", answers=[{"q": "goal", "a": "learn RL"}, {"q": "know", "a": "python"},
                                                                  {"q": "why", "a": "job"}, {"q": "time", "a": "6 hours"}])
    assert s["goal"]["layout"] == "list"
    assert s["goal"]["title"] == "Learn RL" and s["goal"]["hoursPerWeek"] == 6
    assert s["modules"][0]["research"] == "ready"
    states = {c["title"]: c["state"] for c in s["concepts"]}
    assert states == {"MDP": "ready", "Policy": "locked"}
    assert len(s["goals"]) == 2
    s = act(db, jobs, type="setGoal", id="g-ai")
    assert s["goal"]["id"] == "g-ai"


def test_parse_claude_output():
    ok = '{"type":"result","subtype":"success","is_error":false,"result":"{}","structured_output":{"n":4}}'
    assert parse_claude_output(ok, "", 0, structured=True) == {"n": 4}
    assert parse_claude_output('{"type":"result","subtype":"success","result":"hi"}', "", 0, structured=False) == "hi"
    import pytest
    from dsc.providers import ProviderError, ProviderUnavailable
    with pytest.raises(ProviderUnavailable):
        parse_claude_output('{"is_error":true,"result":"5-hour limit reached"}', "", 1, structured=False)
    with pytest.raises(ProviderError):
        parse_claude_output("", "boom", 1, structured=False)


def test_api_smoke(env):
    from fastapi.testclient import TestClient
    from dsc.api import create_app
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    assert client.get("/api/state").json()["goal"]["id"] == "g-ai"
    assert client.post("/api/lesson/c-vectors/open").json()["sections"][0]["body"]
    r = client.post("/api/action", json={"type": "addNote", "conceptId": "c-vectors", "text": "norm = length"})
    assert r.json()["notes"][0]["text"] == "norm = length"
    assert client.post("/api/action", json={"type": "nope"}).status_code == 400
    assert client.get("/api/lesson/missing").status_code == 404
