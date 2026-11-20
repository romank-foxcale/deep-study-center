"""The probe (SPEC §20): rounds of quick questions picked from earlier answers, then an assessment."""

import json

import pytest

from dsc import actions, probe, state


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def q(module_id, n=0):
    return {"module_id": module_id, "prompt": f"Q{n} on {module_id}?", "options": ["right", "wrong", "other"], "answer": 0,
            "explanation": "because"}


ASSESSMENT = {"summary": "You know linear algebra; calculus is new.", "edge": "Solid on vectors; the chain rule is the edge.",
              "modules": [{"module_id": "m-la", "level": "known", "note": "all right and sure"},
                          {"module_id": "m-calc", "level": "partial", "note": "guessed the chain rule"},
                          {"module_id": "m-nope", "level": "known", "note": "unknown id is dropped"}],
              "misconceptions": ["thinks the derivative of a product is the product of derivatives"]}


def fake_probe(call):
    """Round 1: two questions; round 2: one question; then the assessment (or at once when told to end)."""
    if "Must you end now? yes" in call.prompt:
        return {"done": True, "questions": [], "assessment": ASSESSMENT}
    if "this is the first round" in call.prompt:
        return {"done": False, "questions": [q("m-la", 1), q("m-calc", 2), q("m-merge-unknown", 3)]}
    if "round 2" not in call.prompt:
        return {"done": False, "questions": [q("m-calc", 4)]}
    return {"done": True, "questions": [], "assessment": ASSESSMENT}


def test_probe_rounds_use_thinking_and_end_with_an_assessment(env):
    db, jobs, runner = env
    runner.responses["Placement"] = fake_probe
    s = act(db, jobs, type="startProbe")
    p = s["probe"]
    assert p["status"] == "asking" and p["rounds"] == 1
    assert "answer" not in json.dumps(p["question"]) and "explanation" not in json.dumps(p["question"])
    first = p["question"]
    s = act(db, jobs, type="probeAnswer", itemId=first["id"], choice=0, confidence=0.9, thinking="vectors add tip to tail")
    assert s["probe"]["answered"][0]["correct"] and s["probe"]["answered"][0]["explanation"] == "because"
    s = act(db, jobs, type="probeAnswer", itemId=s["probe"]["question"]["id"], choice=None, thinking="no idea about the chain rule")
    # the unknown module id was dropped, so round 1 is complete and round 2 was asked for with the answers
    p = s["probe"]
    assert p["rounds"] == 2 and p["asked"] == 2
    call = [c for r, c in runner.calls if r == "Placement"][-1]
    assert "vectors add tip to tail" in call.prompt and "did not know" in call.prompt and "confidence 90%" in call.prompt
    s = act(db, jobs, type="probeAnswer", itemId=p["question"]["id"], choice=1)
    a = s["probe"]["assessment"]
    assert s["probe"]["status"] == "done" and [m["moduleId"] for m in a["modules"]] == ["m-la", "m-calc"]
    assert a["modules"][0]["title"] == "Linear algebra" and not a["applied"]

    s = act(db, jobs, type="applyProbe")
    assert s["probe"]["assessment"]["applied"]
    diff = next(d for d in s["diffs"] if d["status"] == "pending" and d["reason"].startswith("Probe"))
    assert [c["module"] for c in diff["changes"]] == ["m-la"]
    assert "the chain rule is the edge" in s["goal"]["profile"] and "product of derivatives" in s["goal"]["profile"]
    act(db, jobs, type="applyProbe")  # applying twice adds nothing
    assert db.one("SELECT COUNT(*) AS n FROM diffs WHERE reason LIKE 'Probe%'")["n"] == 1
    s = act(db, jobs, type="decideDiff", id=diff["id"], approve=True)
    assert next(m for m in s["modules"] if m["id"] == "m-la")["known"]


def test_assess_now_and_retake(env):
    db, jobs, runner = env
    runner.responses["Placement"] = fake_probe
    s = act(db, jobs, type="startProbe")
    s = act(db, jobs, type="probeAnswer", itemId=s["probe"]["question"]["id"], choice=0)
    s = act(db, jobs, type="probeAssessNow")
    assert s["probe"]["status"] == "done" and s["probe"]["asked"] == 1  # the unanswered question was dropped
    s = act(db, jobs, type="resetProbe")
    assert s["probe"]["assessment"] is None and s["probe"]["rounds"] == 1 and s["probe"]["asked"] == 0


def test_a_reply_without_questions_fails_the_job_instead_of_ending_the_probe(env):
    db, jobs, runner = env
    runner.responses["Placement"] = {"done": False, "questions": [q("m-unknown")]}
    s = act(db, jobs, type="startProbe")
    assert s["probe"]["status"] == "idle" and s["probe"]["assessment"] is None
    assert "no usable questions" in s["probe"]["error"]


def test_dismiss_and_errors(env):
    db, jobs, runner = env
    s = act(db, jobs, type="dismissProbe")
    assert s["probe"]["dismissed"]
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "probeAnswer", "itemId": 999, "choice": 0})
    assert probe.MAX_QUESTIONS >= probe.ROUND
