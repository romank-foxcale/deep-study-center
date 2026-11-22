"""The tutor reads your reasoning in explain-backs and study sessions too (SPEC §35)."""

from dsc import actions, reasoning, session, state
from dsc.db import dumps, now
from dsc.mock import _NoJobs

ANSWER = ("Two vectors that are not parallel point in different directions, so I can scale each one and add them. "
          "Parallel ones also reach everything because I can make them as long as I want.")


def test_the_grader_marks_the_explain_back_and_follows_the_assumption(env):
    db, jobs, runner = env
    runner.responses["Grading"] = {
        "score": 0.5, "feedback": "The first part is right; the parallel case is not.", "missing": ["parallel vectors stay on one line"],
        "followup": "", "parts": [
            {"quote": "so I can scale each one and add them", "mark": "right", "note": "Yes: two directions give two knobs."},
            {"quote": "Parallel ones also reach everything", "mark": "wrong", "note": "They share one direction."},
            {"quote": "words that are not there", "mark": "right", "note": "dropped"}],
        "assumption": "You assume that length alone can reach any point.",
        "follow": ["If length were enough, one arrow could reach (0, 1) from (1, 0).", "But scaling (1, 0) never leaves the x-axis."],
        "truth": "Scaling keeps the direction, so parallel vectors stay on one line.", "takeaway": "Two directions, two knobs."}
    actions.dispatch(db, jobs, {"type": "explain", "conceptId": "c-lincomb", "itemId": "e-reach", "answer": ANSWER})
    g = state.gradings(db, ["c-lincomb"])["c-lincomb:e-reach"]
    r = g["review"]
    assert g["score"] == 0.5 and r["verdict"] == "right_with_gaps" and r["status"] == "done"
    assert [p["quote"] for p in r["parts"]] == ["so I can scale each one and add them", "Parallel ones also reach everything"]
    assert r["assumption"].startswith("You assume") and len(r["follow"]) == 2 and r["truth"]
    prompt = [c for role, c in runner.calls if role == "Grading"][0].prompt
    assert "follow it until it breaks" in prompt
    h = reasoning.history(db)
    assert h[0]["kind"] == "explain" and h[0]["thinking"] == ANSWER and h[0]["link"] == "/lesson/c-lincomb"


def test_a_session_prediction_with_thinking_is_read(env):
    db, jobs, runner = env
    sid = session.start_from_ideas(db, _NoJobs(), "vectors", "Vectors", [
        {"key": "i1", "title": "Adding vectors", "statement": "Add matching parts.", "node": "c-vectors", "prereqs": [], "fromGraph": False}], [])
    db.x("UPDATE sessions SET status='teaching', plan=? WHERE id=?", (dumps(["i1"]), sid))
    item = {"prompt": "What is (1, 2) + (3, 4)?", "options": ["(4, 6)", "(3, 8)", "(2, 2)"], "answer": 0, "explanation": "Add parts."}
    row = db.x("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
               (sid, "i1", "predict", 0, 0, dumps(item), now()))
    seen = []

    def reply(call):
        seen.append(call.prompt)
        return {"verdict": "wrong", "summary": "You multiplied.", "parts": [
            {"quote": "I multiply the second parts", "mark": "wrong", "note": "Vectors add part by part."}],
            "assumption": "You assume vectors multiply part by part.", "follow": ["Then (1,2)+(0,0) would be (0,0).", "But adding zero changes nothing."],
            "truth": "Add matching parts.", "takeaway": "Add part by part."}
    runner.responses["Reasoning review"] = reply
    session.answer(db, jobs, sid, row, 1, "I add the first parts and I multiply the second parts, so 3 and 8", 0.6)
    assert "a prediction before the explanation" in seen[0] and "They chose: B (wrong)" in seen[0]
    q = next(i for i in session.view(db, sid)["items"] if i["id"] == row)
    assert q["review"]["status"] == "done" and q["review"]["parts"][0]["mark"] == "wrong"
    h = reasoning.history(db)
    assert any(x["kind"] == "session" and x["link"] == f"/study/{sid}" for x in h)
    short = db.x("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                 (sid, "i1", "check", 0, 1, dumps(item), now()))
    session.answer(db, jobs, sid, short, 0, "sure", 0.9)
    assert next(i for i in session.view(db, sid)["items"] if i["id"] == short)["review"] is None  # too short to read
