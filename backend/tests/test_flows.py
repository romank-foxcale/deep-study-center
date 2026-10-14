"""End-to-end flows through actions, lessons and jobs (with a fake provider)."""

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
    assert set(angles(db).values()) == {"geometric"}
    avail = ["geometric", "algebraic", "computational"]

    s = act(db, jobs, type="feedback", conceptId="c-vectors", sectionId="s-idea", angle="geometric",
            available=avail, tags=["framing-off"], text="")
    a1 = angles(db)
    assert a1["s-idea"] != "geometric" and a1["s-ops"] == "geometric"  # only the targeted section changed
    assert next(r for r in s["renditions"] if r["conceptId"] == "c-vectors")["stale"]
    assert "This section now uses" in s["feedback"][0]["effects"][0]

    act(db, jobs, type="feedback", conceptId="c-vectors", sectionId="s-ops", angle="geometric",
        available=avail, tags=["framing-off"], text="arrows don't help me")
    assert angles(db)["s-length"] == "geometric"  # not rewritten while reading
    v = lesson.open_lesson(db, jobs, "c-vectors")  # reopen: re-rendered with the new playbook
    assert v["refreshed"]
    after = angles(db)
    assert after["s-length"] != "geometric" and after["s-idea"] == a1["s-idea"]  # pins survive
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
    assert runner.calls and runner.calls[0][0] == "Renditions"
    assert "rigor 2" in runner.calls[0][1].prompt
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


def test_answers_are_graded_on_the_server_and_learning_schedules_a_review(env):
    db, jobs, _ = env
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=1, angle="geometric")
    assert s["answers"]["c-vectors:q-ops"]["correct"] is False and s["answers"]["c-vectors:q-ops"]["answer"] == 0
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        s = act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice, angle="geometric")
    states = {c["id"]: c["state"] for c in s["concepts"]}
    assert states["c-vectors"] == "learned" and states["c-dot"] == "ready"
    assert s["reviews"][0]["conceptId"] == "c-vectors" and not s["reviews"][0]["isDue"]
    s = act(db, jobs, type="review", conceptId="c-vectors", checkId="q-norm", choice=0)
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "rusty"


def test_confusion_proposes_a_diff_and_approval_inserts_and_researches_a_concept(env):
    db, jobs, runner = env
    runner.responses["Roadmap review"] = {"reason": "Coordinates first.", "changes": [
        {"op": "insert", "title": "Coordinates & the plane (before Vectors)", "detail": "Axes and points."}]}
    runner.responses["Research"] = {"concepts": [{
        "key": "coords", "title": "Coordinates", "objective": "Plot points.", "minutes": 10, "prereq_keys": [],
        "card": {"bloom": "apply", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [], "misconceptions": [],
                 "sources": [], "sections": [{"id": "s-a", "heading": "A", "purpose": "p", "angles": ["geometric"],
                                              "check": {"prompt": "?", "options": ["x", "y"], "answer": 1, "explanation": "e"}}]}}]}
    runner.responses["Fact-check"] = lambda call: {"results": [{"key": "m-la-ins-coordinates-the-plane", "verdict": "passed", "issues": []}]}

    s = act(db, jobs, type="feedback", conceptId="c-vectors", tags=["confused"], text="lost at coordinates")
    pending = [d for d in s["diffs"] if d["status"] == "pending"]
    assert pending and pending[0]["reason"] == "Coordinates first."
    s = act(db, jobs, type="decideDiff", id=pending[0]["id"], approve=True)
    ids = [c["id"] for c in s["concepts"]]
    assert ids.index("m-la-ins-coordinates-the-plane") == ids.index("c-vectors") - 1
    card = next(c for c in s["cards"] if c["conceptId"] == "m-la-ins-coordinates-the-plane")
    assert card["factCheck"] == "passed" and "answer" not in card["sections"][0]["check"]
    assert card["sections"][0]["check"]["id"] == "q-s-a"


def test_offline_fallbacks_keep_the_app_usable(env):
    db, jobs, runner = env
    runner.unavailable = True
    s = act(db, jobs, type="chat", conceptId="c-vectors", text="why?")
    assert s["chats"]["c-vectors"][-1]["role"] == "tutor"
    s = act(db, jobs, type="feedback", conceptId="c-vectors", tags=["confused"], text="")
    assert any(d["status"] == "pending" for d in s["diffs"])
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
    s = act(db, jobs, type="createGoal", answers=[{"q": "goal", "a": "learn RL"}, {"q": "know", "a": "python"},
                                                   {"q": "why", "a": "job"}, {"q": "time", "a": "6 hours"}])
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
