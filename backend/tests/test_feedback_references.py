"""Feedback on a chosen part of a lesson, lesson guidelines from feedback patterns, writing the next lesson
when one is finished, and remedial lessons (SPEC §12). The agent is a fake (conftest.FakeRunner)."""

from dsc import actions, lesson, remedial, state
from dsc.jobs import APPLY_SCHEMA, GUIDE_SCHEMA

CID = "c-vectors"


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def give(db, jobs, **a):
    act(db, jobs, type="feedback", conceptId=CID, **{"tags": [], "text": "", "kind": "lesson", **a})
    return db.one("SELECT MAX(id) AS id FROM feedback")["id"]


def by_schema(apply=None, guide=None):
    """One fake for the "Feedback" route, which serves several jobs: answer by the schema asked for."""
    def reply(call):
        if call.schema is APPLY_SCHEMA:
            return apply(call)
        if call.schema is GUIDE_SCHEMA:
            return guide(call) if callable(guide) else guide
        return {"kind": "lesson", "why": "test"}
    return reply


def change(sid, ids, related=""):
    return {"section_id": sid, "feedback_ids": ids, "why": "w", "how": f"rewrote {sid}", "technique": "t",
            "related_because": related}


# ---------------------------------------------------------------- feedback on a chosen part

def test_feedback_keeps_its_reference_and_apply_is_scoped_to_it(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, text="what do the bars mean here?", ref={"kind": "formula", "quote": "\\lVert v \\rVert", "sectionId": "s-length"})
    f = next(x for x in state.snapshot(db)["feedback"] if x["id"] == a)
    assert f["sectionId"] == "s-length" and f["ref"] == {"kind": "formula", "quote": "\\lVert v \\rVert", "sectionId": "s-length"}

    runner.responses["Feedback"] = by_schema(apply=lambda call: {
        "items": [{"id": a, "kind": "lesson", "why": ""}],
        "sections": [{"id": "s-length", "body": "The double bars mean length."},
                     {"id": "s-misc", "body": "Here too: the bars mean length."},
                     {"id": "s-ops", "body": "Unrelated rewrite."}],
        "changes": [change("s-length", [a]), change("s-misc", [a], related="uses the same notation without explaining it"),
                    change("s-ops", [a])],
        "summary": "Explained the bars"})
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    prompt = [c for r, c in runner.calls if r == "Feedback"][-1].prompt
    assert 'about the formula "\\\\lVert v \\\\rVert"' in prompt and "related_because" in prompt
    v = lesson.view(db, CID)
    body = {s["id"]: s["body"] for s in v["sections"]}
    assert body["s-length"] == "The double bars mean length." and body["s-misc"] == "Here too: the bars mean length."
    assert body["s-ops"] != "Unrelated rewrite."  # outside the target, no reason: dropped
    from dsc import versions
    ch = {c["sectionId"]: c for c in versions.get(db, CID, v["head"])["changes"]}
    assert ch["s-misc"]["relatedBecause"] and not ch["s-length"]["relatedBecause"] and "s-ops" not in ch
    assert "outside the part" in " ".join(state.jobs(db)[0]["progress"])


def test_whole_lesson_feedback_may_change_any_section(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, text="too wordy overall")
    runner.responses["Feedback"] = by_schema(apply=lambda call: {
        "items": [], "sections": [{"id": "s-ops", "body": "Short."}, {"id": "s-why", "body": "Shorter."}],
        "changes": [change("s-ops", [a]), change("s-why", [a])], "summary": "Shorter"})
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    body = {s["id"]: s["body"] for s in lesson.view(db, CID)["sections"]}
    assert body["s-ops"] == "Short." and body["s-why"] == "Shorter."


def test_bad_references_are_ignored(env):
    db, jobs, _ = env
    a = give(db, jobs, text="hm", ref={"kind": "script", "quote": "x"})
    assert db.one("SELECT ref FROM feedback WHERE id=?", (a,))["ref"] is None
    b = give(db, jobs, text="this graph", ref={"kind": "viz", "quote": "", "sectionId": "s-ops"})
    assert next(x for x in state.snapshot(db)["feedback"] if x["id"] == b)["ref"]["kind"] == "viz"


# ---------------------------------------------------------------- guidelines and the next lesson

def test_finishing_a_lesson_distills_guidelines_then_writes_the_next_lesson_with_them(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, text="start with a tiny example please")
    b = give(db, jobs, text="again: a small numeric example first")
    runner.responses["Feedback"] = by_schema(guide={
        "items": [{"text": "Start each idea with a tiny numeric example", "why": "asked twice", "feedback_ids": [a, b],
                   "by_learner": False}], "summary": "first guidelines"})
    runner.responses["Renditions"] = lambda call: {"sections": [
        {"id": line.split()[1], "body": "written"} for line in call.prompt.splitlines() if line.startswith("- s-")]}
    s = act(db, jobs, type="markStudied", conceptId=CID)
    g = s["guidelines"]
    assert g["version"] == 1 and g["items"][0]["feedbackIds"] == [a, b]
    guide_call = [c for r, c in runner.calls if r == "Feedback" and c.schema is GUIDE_SCHEMA][0]
    assert "start with a tiny example please" in guide_call.prompt
    render = [c for r, c in runner.calls if r == "Renditions"]
    assert render and "Start each idea with a tiny numeric example" in render[-1].prompt  # c-lincomb, written ahead
    assert state.rendition_row(db, "c-lincomb") is not None
    # marking it studied again does nothing more
    n = len(runner.calls)
    act(db, jobs, type="markStudied", conceptId=CID)
    assert len(runner.calls) == n


def test_the_learners_guideline_lines_are_kept(env):
    db, jobs, runner = env
    act(db, jobs, type="editGuidelines", lines=["Use cooking examples", "  "])
    give(db, jobs, text="x")
    runner.responses["Feedback"] = by_schema(guide={"items": [
        {"text": "Explain symbols before formulas", "why": "p", "feedback_ids": [], "by_learner": False}], "summary": "s"})
    s = act(db, jobs, type="distillGuidelines")
    texts = [i["text"] for i in s["guidelines"]["items"]]
    assert texts == ["Use cooking examples", "Explain symbols before formulas"] and s["guidelines"]["version"] == 2
    assert s["guidelines"]["items"][0]["byLearner"]


def test_offline_the_next_lesson_is_still_written(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    give(db, jobs, text="x")
    runner.unavailable = True
    s = act(db, jobs, type="markStudied", conceptId=CID)
    assert s["guidelines"] is None
    assert any(j["kind"] == "render" and j["input"].get("concept_id") == "c-lincomb" for j in s["jobs"])


# ---------------------------------------------------------------- remedial lessons

def wrong(db, jobs, item="q-norm"):
    card = state.latest_card(db, CID)
    check = next(s["check"] for s in card["sections"] if s.get("check", {}).get("id") == item)
    act(db, jobs, type="answer", conceptId=CID, checkId=item, choice=(check["answer"] + 1) % len(check["options"]))


def test_struggle_offers_an_extra_lesson_once_and_again_after_more_struggle(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    wrong(db, jobs)
    wrong(db, jobs, "q-ops")
    assert lesson.view(db, CID)["remedial"] is None
    runner.responses["Tutor chat"] = "Think about it."
    act(db, jobs, type="chat", conceptId=CID, text="why is the length a square root?")
    act(db, jobs, type="chat", conceptId=CID, text="I still don't get it")
    wrong(db, jobs)
    offer = lesson.view(db, CID)["remedial"]
    assert offer and offer["id"] == "c-vectors-rb" and offer["title"] == "Vectors (b)"
    assert any("wrong answer" in r for r in offer["reasons"]) and any("tutor" in r for r in offer["reasons"])

    act(db, jobs, type="dismissRemedial", conceptId=CID)
    assert lesson.view(db, CID)["remedial"] is None
    for _ in range(3):
        wrong(db, jobs)
    assert lesson.view(db, CID)["remedial"]


def test_adding_the_extra_lesson_inserts_it_after_the_lesson_and_researches_the_confusion(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    give(db, jobs, tags=["confused"], text="lost at the length formula")
    runner.responses["Roadmap review"] = {"reason": "r", "changes": [{"op": "deepen", "title": "x", "detail": "y"}]}
    wrong(db, jobs)
    wrong(db, jobs)
    assert lesson.view(db, CID)["remedial"]
    module = db.one("SELECT module_id FROM concepts WHERE id=?", (CID,))["module_id"]
    runner.unavailable = True  # research offline: the module must stay researched
    s = act(db, jobs, type="addRemedial", conceptId=CID)
    ids = [c["id"] for c in s["concepts"]]
    assert ids[ids.index(CID) + 1] == "c-vectors-rb"
    research = [c for r, c in runner.calls if r == "Research"][-1].prompt
    assert "Vectors (b)" in research and "lost at the length formula" in research and "Wrong answer to" in research
    assert db.one("SELECT research FROM modules WHERE id=?", (module,))["research"] == "ready"
    assert lesson.view(db, CID)["extraLessons"] == [{"id": "c-vectors-rb", "title": "Vectors (b)"}]
    assert lesson.view(db, CID)["remedial"] is None  # the extra lesson is open: no second offer
    assert remedial.root_of("c-vectors-rb") == CID and remedial.next_letter(db, CID) == "c"
