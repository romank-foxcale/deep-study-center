"""The tutor reads the learner's reasoning on an answer (SPEC §32)."""

import pytest

from dsc import actions, jobs as jobs_mod, reasoning, state

CID, CHECK = "c-lincomb", "q-reach"  # demo check: a(1,0) + b(1,1) = (3,2), right answer a=1, b=2 (option 0)
THINKING = ("I think b only changes the first part so a must be 3 and b must be 2 because the second part "
            "comes from both of them together")


def reply(call):
    reply.prompts.append(call.prompt)
    return {"verdict": "wrong", "summary": "You mixed up which part b changes.", "parts": [
        {"quote": "b only changes the first part", "mark": "wrong", "note": "b is in both parts; only b gives the second part."},
        {"quote": "a must be 3", "mark": "wrong", "note": "a + b = 3, so a = 1."},
        {"quote": "a sentence that is not in the thinking", "mark": "right", "note": "dropped"}],
        "assumption": "You assume b changes only the first part.",
        "follow": ["If b changed only the first part, the second part would come from a alone.", "But a(1,0) has 0 as its second part."],
        "truth": "Only b gives the second part, so b = 2; then a + 2 = 3 gives a = 1.", "takeaway": "Read each part separately."}


@pytest.fixture
def tutor(env):
    db, jobs, runner = env
    reply.prompts = []
    runner.responses["Reasoning review"] = reply
    return db, jobs, runner


def test_the_tutor_reads_the_thinking_and_marks_its_parts(tutor):
    db, jobs, runner = tutor
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": CID, "checkId": CHECK, "choice": 1, "thinking": THINKING,
                                "confidence": 0.8})
    p = reply.prompts[0]
    assert THINKING in p and "They chose: B (wrong)" in p and "Right answer: A" in p and "80 %" in p
    a = state.answers(db, [CID])[f"{CID}:{CHECK}"]
    r = a["review"]
    assert r["status"] == "done" and r["verdict"] == "wrong" and r["assumption"].startswith("You assume")
    assert [x["quote"] for x in r["parts"]] == ["b only changes the first part", "a must be 3"]  # invented quotes dropped
    assert len(r["follow"]) == 2 and r["truth"] and r["takeaway"]
    h = reasoning.history(db)
    assert h[0]["thinking"] == THINKING and h[0]["verdict"] == "wrong" and h[0]["confidence"] == 0.8


def test_no_review_without_real_thinking_and_a_failed_review_says_so(tutor):
    db, jobs, runner = tutor
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": CID, "checkId": CHECK, "choice": 0, "thinking": "not sure"})
    assert state.answers(db, [CID])[f"{CID}:{CHECK}"]["review"] is None and not reply.prompts
    runner.responses["Reasoning review"] = lambda call: (_ for _ in ()).throw(RuntimeError("model down"))
    actions.dispatch(db, jobs, {"type": "undoAnswer", "conceptId": CID, "itemId": CHECK})
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": CID, "checkId": CHECK, "choice": 0, "thinking": THINKING})
    assert state.answers(db, [CID])[f"{CID}:{CHECK}"]["review"]["status"] == "failed"


def test_the_writing_style_is_simplified_technical_english_by_default(tutor):
    db, jobs, runner = tutor
    assert state.settings(db)["writingStyle"] == "ste" and "Simplified Technical English" in jobs_mod.prompt("render")
    actions.dispatch(db, jobs, {"type": "setSetting", "key": "writingStyle", "value": "plain"})
    assert "Simplified Technical English" not in jobs_mod.prompt("render")
    actions.dispatch(db, jobs, {"type": "setSetting", "key": "writingStyle", "value": "ste"})
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setSetting", "key": "writingStyle", "value": "fancy"})


def test_an_earlier_answer_can_be_read_later(tutor):
    db, jobs, runner = tutor
    runner.responses.pop("Reasoning review")  # no tutor at answer time: the review fails
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": CID, "checkId": CHECK, "choice": 1, "thinking": THINKING})
    assert state.answers(db, [CID])[f"{CID}:{CHECK}"]["review"]["status"] == "failed"
    runner.responses["Reasoning review"] = reply
    actions.dispatch(db, jobs, {"type": "reviewReasoning", "conceptId": CID, "itemId": CHECK})
    assert state.answers(db, [CID])[f"{CID}:{CHECK}"]["review"]["status"] == "done"
