"""Feedback you can apply (SPEC §11): lesson versions, editable feedback with replay, apply with the fact
guard, revert as a learning signal, and the prose diff. The agent is a fake (conftest.FakeRunner)."""

from fastapi.testclient import TestClient

from dsc import actions, lesson, state, versions
from dsc.api import create_app
from dsc.db import dumps, loads

CID = "c-vectors"


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def fb_item(db, fid):
    return next(f for f in state.snapshot(db)["feedback"] if f["id"] == fid)


def give(db, jobs, **a):
    act(db, jobs, type="feedback", conceptId=CID, **{"tags": [], "text": "", **a})
    return db.one("SELECT MAX(id) AS id FROM feedback")["id"]


def apply_reply(sid="s-idea", body="A vector is a list of numbers. Picture a recipe: 2 eggs, 1 cup of flour.",
                ids=None, technique="cooking analogy", items=None):
    """A fake agent that rewrites one section for the given feedback ids."""
    def reply(call):
        fids = ids if ids is not None else [int(x) for x in __import__("re").findall(r"- #(\d+)", call.prompt)]
        return {"items": items or [{"id": i, "kind": "lesson", "why": "about this lesson"} for i in fids],
                "sections": [{"id": sid, "body": body}],
                "changes": [{"section_id": sid, "feedback_ids": fids, "why": "You asked for a concrete picture",
                             "how": "Opened with a recipe as a list of numbers", "technique": technique}],
                "summary": "A concrete example first"}
    return reply


# ---------------------------------------------------------------- versions

def test_rendered_lesson_becomes_v1_and_a_new_angle_adds_v2_keeping_other_sections(env):
    db, jobs, _ = env
    v = lesson.open_lesson(db, jobs, CID)
    assert v["head"] == 1 and [x["version"] for x in v["versions"]] == [1]
    assert v["versions"][0]["source"] == "render"
    act(db, jobs, type="explainDifferently", conceptId=CID, sectionId="s-idea")
    v = lesson.view(db, CID)
    assert v["head"] == 2
    two = versions.get(db, CID, 2)
    assert two["parent"] == 1 and [c["sectionId"] for c in two["changes"]] == ["s-idea"]
    one = versions.get(db, CID, 1)
    assert two["sections"]["s-ops"] == one["sections"]["s-ops"] and two["sections"]["s-idea"] != one["sections"]["s-idea"]


# ---------------------------------------------------------------- kinds, edit, delete

def test_kinds_decide_whether_the_playbook_changes(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    runner.responses["Feedback"] = {"kind": "lesson", "why": "about this example"}
    pb0 = state.playbook(db)["version"]
    fid = give(db, jobs, text="the example in this section confused me")
    f = fb_item(db, fid)
    assert f["kind"] == "lesson" and f["kindSource"] == "agent" and f["status"]["state"] == "pending"
    assert state.playbook(db)["version"] == pb0  # about this lesson: no playbook change

    fid2 = give(db, jobs, tags=["too-fast"])
    assert fb_item(db, fid2)["kind"] == "me" and state.playbook(db)["adjust"]["pace"] == -1

    runner.unavailable = True  # the rule-based guess alone
    fid3 = give(db, jobs, text="The length of (1, 2, 2) is wrong, it should be 5")
    assert fb_item(db, fid3)["kind"] == "fact"


def test_agent_never_overrides_the_learners_kind(env):
    db, jobs, runner = env
    runner.responses["Feedback"] = {"kind": "me", "why": "general"}
    fid = give(db, jobs, text="more pictures here please", kind="lesson")
    assert fb_item(db, fid)["kind"] == "lesson" and not [r for r, _ in runner.calls if r == "Feedback"]


def test_edit_voids_old_signals_and_replays_and_delete_voids_them(env):
    db, jobs, _ = env
    fid = give(db, jobs, tags=["too-fast"])
    pb1 = state.playbook(db)
    assert pb1["adjust"]["pace"] == -1
    act(db, jobs, type="editFeedback", id=fid, tags=["too-slow"])
    pb2 = state.playbook(db)
    assert pb2["adjust"]["pace"] == 1 and pb2["version"] > pb1["version"]
    assert fb_item(db, fid)["tags"] == ["Too slow"] and fb_item(db, fid)["updatedAt"]

    act(db, jobs, type="editFeedback", id=fid, kind="lesson")  # not about me after all: playbook back to neutral
    pb3 = state.playbook(db)
    assert pb3["adjust"]["pace"] == 0 and pb3["version"] > pb2["version"]
    assert fb_item(db, fid)["kindSource"] == "learner"

    act(db, jobs, type="editFeedback", id=fid, kind="me")
    assert state.playbook(db)["adjust"]["pace"] == 1
    v = state.playbook(db)["version"]
    act(db, jobs, type="deleteFeedback", id=fid)
    pb4 = state.playbook(db)
    assert pb4["adjust"]["pace"] == 0 and pb4["version"] > v  # the version never goes down: stale stays correct
    assert all(f["id"] != fid for f in state.snapshot(db)["feedback"])


# ---------------------------------------------------------------- apply

def test_apply_writes_next_version_with_reasons_and_marks_items_applied(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, sectionId="s-idea", text="too abstract for me here", kind="lesson")
    b = give(db, jobs, tags=["too-fast"], kind="me")
    runner.responses["Feedback"] = apply_reply()
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a, b])
    call = [c for r, c in runner.calls if r == "Feedback"][-1]
    assert "<feedback>" in call.prompt and f"#{a}" in call.prompt and "fact guard" in call.prompt
    v = lesson.view(db, CID)
    assert v["head"] == 2 and v["rendition"]["shaped"] and not v["rendition"]["stale"]
    assert next(s for s in v["sections"] if s["id"] == "s-idea")["body"].startswith("A vector is a list")
    two = versions.get(db, CID, 2)
    assert two["source"] == "apply" and two["feedback_ids"] == [a, b] and two["changes"][0]["how"]
    assert fb_item(db, a)["status"] == {"state": "applied", "version": 2, "changedSinceApplied": False, "note": None}
    # an applied item edited later is marked as changed since it was applied
    act(db, jobs, type="editFeedback", id=a, text="too abstract, use code")
    assert fb_item(db, a)["status"]["changedSinceApplied"]


def test_fact_guard_keeps_revisions_to_prose(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, text="make the length section simpler", kind="lesson")
    leak = "Easy: $\\sqrt{1^2 + 2^2 + 2^2} = \\sqrt{9} = 3$. So the answer is 3."
    runner.responses["Feedback"] = lambda call: {
        "items": [{"id": a, "kind": "lesson", "why": ""}],
        "sections": [{"id": "s-length", "body": leak},                                   # reveals a hidden key
                     {"id": "s-misc", "body": "Also: $$\\lVert u + v \\rVert^2 = \\lVert u \\rVert^2 + \\lVert v \\rVert^2$$"},  # new claim
                     {"id": "s-nope", "body": "made-up section"}],                       # not a section
        "changes": [{"section_id": s, "feedback_ids": [a], "why": "x", "how": "y", "technique": "z"}
                    for s in ("s-length", "s-misc", "s-nope")],
        "summary": "bad"}
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    assert lesson.view(db, CID)["head"] == 1  # nothing passed the guard: no new version
    job = state.jobs(db)[0]
    reasons = " | ".join(job["progress"])
    assert "hidden answer key" in reasons and "formula" in reasons and "not a section" in reasons
    assert fb_item(db, a)["status"]["state"] == "pending"


def test_fact_guard_unit():
    card = {"formal": "Length: $$\\lVert v \\rVert = \\sqrt{v_1^2 + v_2^2}$$", "sections": [
        {"id": "s1", "check": {"explanation": "Because the coordinates add independently of each other."}},
        {"id": "s2", "explain": {"rubric": ["Moving along one axis does not change the other one"]}}]}
    base = {"s1": "Old one.", "s2": "Old two."}
    ok, bad = versions.fact_guard(card, base, [
        {"id": "s1", "body": "New: $$\\lVert v \\rVert = \\sqrt{v_1^2 + v_2^2}$$ with a picture."},
        {"id": "s2", "body": "Note: moving along one axis does NOT change the other one."}])
    assert list(ok) == ["s1"] and bad[0]["sectionId"] == "s2"
    # a numeric worked example in the card's notation is fine; a new symbolic identity is not
    ok, bad = versions.fact_guard(card, base, [
        {"id": "s1", "body": "Try it: $$\\lVert v \\rVert = \\sqrt{3^2 + 4^2} = 5$$"},
        {"id": "s2", "body": "And: $$\\lVert v \\rVert = v_1 + v_2$$"}])
    assert list(ok) == ["s1"] and "formula" in bad[0]["reason"]


def test_fact_claims_go_to_the_card_check_not_the_lesson(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    runner.responses["Card refresh"] = {"changed": False, "summary": "checked", "changes": []}
    a = give(db, jobs, text="the norm of (1,2,2) is wrong, it should be 5", kind="fact")
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    roles = [r for r, _ in runner.calls]
    assert "Card refresh" in roles and "Feedback" not in roles
    assert "it should be 5" in [c for r, c in runner.calls if r == "Card refresh"][0].prompt
    assert fb_item(db, a)["status"]["state"] == "routed" and lesson.view(db, CID)["head"] == 1

    # the agent spots a fact claim the rules missed: it is routed too, and the rest is applied
    b = give(db, jobs, text="the second example uses the wrong vector", kind="lesson")
    c = give(db, jobs, text="more pictures", kind="lesson")
    runner.responses["Feedback"] = apply_reply(ids=[c], items=[{"id": b, "kind": "fact", "why": "claims an error"},
                                                               {"id": c, "kind": "lesson", "why": ""}])
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[b, c])
    assert fb_item(db, c)["status"]["state"] == "applied"
    assert fb_item(db, b)["kind"] == "lesson"  # the learner chose "lesson": the agent may not override it
    assert fb_item(db, b)["status"]["state"] == "pending"


def test_offline_apply_switches_to_an_already_written_angle(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, sectionId="s-ops", text="arrows lose me here", kind="lesson", angle="geometric")
    runner.unavailable = True
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    v = lesson.view(db, CID)
    assert v["head"] == 2 and next(s for s in v["sections"] if s["id"] == "s-ops")["angle"] != "geometric"
    assert "offline" in versions.get(db, CID, 2)["changes"][0]["how"]
    assert fb_item(db, a)["status"]["state"] == "applied"


# ---------------------------------------------------------------- revert

def test_revert_moves_the_head_loses_nothing_and_teaches_the_playbook(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, sectionId="s-idea", text="too abstract here", kind="lesson")
    runner.responses["Feedback"] = apply_reply(technique="Cooking analogy")
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    pb = state.playbook(db)["version"]
    act(db, jobs, type="revertLesson", conceptId=CID, version=1)
    v = lesson.view(db, CID)
    assert v["head"] == 1 and [x["version"] for x in v["versions"]] == [2, 1]
    assert next(s for s in v["sections"] if s["id"] == "s-idea")["body"] == versions.get(db, CID, 1)["sections"]["s-idea"]
    assert fb_item(db, a)["status"]["state"] == "reverted" and fb_item(db, a)["status"]["version"] == 2
    tech = next(e for e in state.playbook(db)["entries"] if e["dimension"] == "technique")
    assert tech["value"] == "cooking analogy" and tech["score"] < 0.5
    assert state.playbook(db)["version"] == pb  # a weak signal: nothing is re-rendered because of it
    # later applies are told what did not work
    b = give(db, jobs, text="still too abstract", kind="lesson")
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[b])
    assert "cooking analogy" in [c for r, c in runner.calls if r == "Feedback"][-1].prompt
    # and forward again: nothing was lost
    act(db, jobs, type="revertLesson", conceptId=CID, version=2)
    assert lesson.view(db, CID)["head"] == 2 and fb_item(db, a)["status"]["state"] == "applied"


def test_shaped_lesson_is_not_rewritten_on_open_and_old_card_versions_cannot_be_restored(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, text="more pictures", kind="lesson")
    runner.responses["Feedback"] = apply_reply()
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    act(db, jobs, type="adjust", key="rigor", value=2)  # playbook changes
    v = lesson.open_lesson(db, jobs, CID)
    assert not v["refreshed"] and v["head"] == 2 and v["rendition"]["stale"] and v["rendition"]["shaped"]

    card = state.latest_card(db, CID)
    body = {k: x for k, x in card.items() if k not in ("conceptId", "version", "factCheck", "checkedAt")}
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
         (CID, card["version"] + 1, dumps(body), "passed", card["checkedAt"]))
    try:
        act(db, jobs, type="revertLesson", conceptId=CID, version=1)
        raise AssertionError("restored a version of an older card")
    except actions.ActionError as e:
        assert "card" in str(e)


# ---------------------------------------------------------------- diff

def test_word_diff():
    d = versions.word_diff("Vectors are arrows in space.", "Vectors are lists of numbers in space.")
    assert d[0] == ["eq", "Vectors are "] and ["del", "arrows"] in d and ["ins", "lists of numbers"] in d
    assert "".join(t for op, t in d if op != "ins") == "Vectors are arrows in space."
    assert "".join(t for op, t in d if op != "del") == "Vectors are lists of numbers in space."


def test_diff_between_versions_is_annotated_with_reasons_and_feedback(env):
    db, jobs, runner = env
    lesson.open_lesson(db, jobs, CID)
    a = give(db, jobs, sectionId="s-idea", text="too abstract", kind="lesson")
    runner.responses["Feedback"] = apply_reply()
    act(db, jobs, type="applyFeedback", conceptId=CID, ids=[a])
    client = TestClient(create_app(db=db, jobs=jobs))
    d = client.get(f"/api/lesson/{CID}/diff", params={"a": 1, "b": 2}).json()
    idea = next(s for s in d["sections"] if s["id"] == "s-idea")
    assert idea["status"] == "changed" and idea["inserted"] > 0 and idea["deleted"] > 0
    assert idea["changes"][0]["feedbackIds"] == [a] and idea["changes"][0]["why"] and not idea["changes"][0]["undone"]
    assert all(s["status"] == "same" for s in d["sections"] if s["id"] != "s-idea")
    assert d["feedback"][0]["id"] == a and d["feedback"][0]["text"] == "too abstract"
    back = client.get(f"/api/lesson/{CID}/diff", params={"a": 2, "b": 1}).json()
    assert next(s for s in back["sections"] if s["id"] == "s-idea")["changes"][0]["undone"]
    assert client.get(f"/api/lesson/{CID}/diff", params={"a": 1, "b": 9}).status_code == 404
    assert loads(db.one("SELECT feedback_ids FROM lesson_versions WHERE version=2")["feedback_ids"]) == [a]
