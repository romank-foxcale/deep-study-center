"""Thinking and confidence on every answer (SPEC §18): stored, used for scoring, and shown to the agents."""

from dsc import actions, state


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def test_thinking_and_confidence_are_stored_and_returned(env):
    db, jobs, _ = env
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=1,
            thinking="  I think   you add  the arrows tip to tail ", confidence=0.9)
    a = s["answers"]["c-vectors:q-ops"]
    assert a["thinking"] == "I think you add the arrows tip to tail" and a["confidence"] == 0.9 and a["correct"] is False
    log = state.reasoning_log(db)
    assert "wrong while sure" in log and "tip to tail" in log and "confidence 90%" in log


def test_a_right_guess_is_half_evidence_and_never_counts_as_known(env):
    db, jobs, _ = env
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=0, confidence=0.1)
    a = s["answers"]["c-vectors:q-ops"]
    assert a["correct"] is True and a["score"] == 0.5  # shown as right, scored as half
    assert "right, but a guess" in state.reasoning_log(db, "c-vectors")
    for item, choice in (("q-norm", 1), ("q-misc", 3)):
        act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice, confidence=0.9)
    # only 2 items are really known, so the lesson is not learned even with a good explain-back
    _, states = state.concept_states(db, "g-ai")
    assert len([1 for e in db.q("SELECT * FROM evidence WHERE concept_id='c-vectors' AND score >= 0.8")]) == 2
    assert states["c-vectors"].state == "learning"


def test_confidence_is_clamped_and_optional(env):
    db, jobs, _ = env
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=0, confidence="lots")
    assert s["answers"]["c-vectors:q-ops"]["confidence"] is None and s["answers"]["c-vectors:q-ops"]["score"] == 1.0
    s = act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-norm", choice=1, confidence=7)
    assert s["answers"]["c-vectors:q-norm"]["confidence"] == 1.0


def test_tutor_and_lesson_planner_see_the_thinking(env):
    db, jobs, runner = env
    act(db, jobs, type="answer", conceptId="c-vectors", checkId="q-ops", choice=1,
        thinking="maybe you multiply the lengths", confidence=0.8)
    runner.responses["Tutor chat"] = "Let's look at the arrows."
    act(db, jobs, type="chat", conceptId="c-vectors", text="why is it not the product?")
    tutor_prompt = next(c.prompt for role, c in runner.calls if role == "Tutor chat")
    assert "maybe you multiply the lengths" in tutor_prompt and "wrong while sure" in tutor_prompt


def test_review_guess_is_not_recall_and_explain_keeps_confidence(env):
    db, jobs, runner = env
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice)
    runner.responses["Grading"] = {"score": 1, "feedback": "Clear.", "missing": [], "followup": ""}
    act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", confidence=0.6,
        answer="Moving right doesn't change how far up you are, so each coordinate adds on its own.")
    assert db.one("SELECT confidence FROM gradings")["confidence"] == 0.6
    s = act(db, jobs, type="review", conceptId="c-vectors", checkId="q-norm", choice=1, confidence=0.2)
    assert {c["id"]: c["state"] for c in s["concepts"]}["c-vectors"] == "rusty"
