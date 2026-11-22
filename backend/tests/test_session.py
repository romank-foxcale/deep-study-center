"""Study sessions, "teach me X" (SPEC §22): sketch -> probe -> plan -> teach (predict, explain, check) -> extract."""

import json

import pytest

from dsc import actions, graph, session, state

from test_graph import learn_vectors


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def mcq(prompt, answer=0):
    return {"prompt": prompt, "options": ["right", "wrong", "other"], "answer": answer, "explanation": "because"}


SKETCH = {"title": "Dot products", "target_key": "cos", "ideas": [
    {"key": "vec", "title": "Vectors", "statement": "A vector is an arrow.", "prereq_keys": [], "same_as": "c-vectors"},
    {"key": "proj", "title": "Projection", "statement": "Projecting a onto b.", "prereq_keys": ["vec"]},
    {"key": "len", "title": "Length", "statement": "Length from the dot product.", "prereq_keys": ["vec"]},
    {"key": "cos", "title": "Cosine similarity", "statement": "The angle from the dot product.", "prereq_keys": ["proj", "len"]}]}


RESULT = {"start": "Start with the projection; the length is solid.", "ideas": [
    {"idea_key": "len", "level": "known", "reasons_from": "Pythagoras", "runs_out": "", "misconceptions": []},
    {"idea_key": "proj", "level": "unknown", "reasons_from": "", "runs_out": "the projection as a length",
     "misconceptions": ["thinks the projection is a number"]},
    {"idea_key": "cos", "level": "untested", "reasons_from": "", "runs_out": "", "misconceptions": []}]}


def probe_reply(call):
    if "Must you end now? yes" in call.prompt or "idea len" in call.prompt:
        return {"done": True, "result": RESULT}
    return {"done": False, "question": {"idea_key": "len", **mcq("Length of (3, 4)?")}}


def turn_reply(call):
    if "Your task: **predict**" in call.prompt:
        return {"predict": mcq("What do you expect?")}
    return {"body": "You were close: the **projection** is the shadow.", "check": mcq("Which is the shadow?")}


def extract_reply(call):
    extract_reply.prompt = call.prompt
    return {"summary": "You now understand cosine similarity.",
            "statements": [{"idea_key": "proj", "statement": "The projection of a on b is (a·b/|b|²) b."}],
            "links": [{"src": "proj", "dst": "c-dot", "why": "uses the dot product"}, {"src": "x", "dst": "cos", "why": "bad"}]}


def setup(runner):
    runner.responses["Study plan"] = lambda call: extract_reply(call) if "close a study session" in call.prompt else SKETCH
    runner.responses["Study tutor"] = lambda call: turn_reply(call) if "Your task:" in call.prompt else probe_reply(call)


def view(db):
    return session.view(db, db.meta("last_session"))


def answer_open(db, jobs, choice=0, **extra):
    v = view(db)
    q = next(i for i in v["items"] if i["phase"] != "explain" and not i["answered"])
    act(db, jobs, type="sessionAnswer", sessionId=v["id"], itemId=q["id"], choice=choice, **extra)
    return q


def test_full_session_from_topic_to_graph(env):
    db, jobs, runner = env
    learn_vectors(db, jobs, runner)  # "Vectors" is learned in the demo goal: the sketch maps to it and skips it
    setup(runner)
    s = act(db, jobs, type="startSession", topic="teach me cosine similarity")
    assert s["sessions"][0]["topic"] == "teach me cosine similarity"
    v = view(db)
    assert v["status"] == "probing"
    vec = next(i for i in v["ideas"] if i["key"] == "vec")
    assert vec["node"] == "c-vectors" and vec["level"] == "known" and vec["fromGraph"]
    sketch_prompt = next(c.prompt for r, c in runner.calls if r == "Study plan")
    assert "c-vectors: Vectors" in sketch_prompt and "[state: learned]" in sketch_prompt
    # new ideas became nodes at once, with the session's reasoning links
    proj = next(i for i in v["ideas"] if i["key"] == "proj")
    assert proj["node"].startswith("n-") and ("c-vectors", proj["node"]) in {(lk["src"], lk["dst"]) for lk in graph.links(db)}

    # probe: one question on "len" (answered right and sure) -> the result per idea -> planning
    q = answer_open(db, jobs, choice=0, confidence=0.9, thinking="3-4-5 triangle")
    assert q["phase"] == "probe"
    probe_prompt = [c.prompt for r, c in runner.calls if r == "Study tutor"][-1]
    assert "confidence 90% (chance: 33%)" in probe_prompt and "3-4-5 triangle" in probe_prompt
    v = view(db)
    assert v["status"] == "planning" and v["plan"] == ["proj", "cos"]  # vec known from the graph, len from the probe
    by = {i["key"]: i for i in v["ideas"]}
    assert by["proj"]["level"] == "unknown" and by["proj"]["probe"]["misconceptions"] == ["thinks the projection is a number"]
    assert by["cos"]["level"] is None and by["cos"]["probe"]["level"] == "untested"  # untested is not a finding
    assert v["probeStart"].startswith("Start with the projection")
    len_node = next(i for i in v["ideas"] if i["key"] == "len")["node"]
    assert db.one("SELECT score FROM evidence WHERE concept_id=?", (len_node,))["score"] == 1.0

    # the learner says they know "proj" after all, then changes their mind
    act(db, jobs, type="sessionKnown", sessionId=v["id"], ideaKey="proj", known=True)
    assert view(db)["plan"] == ["cos"]
    act(db, jobs, type="sessionKnown", sessionId=v["id"], ideaKey="proj", known=False)
    act(db, jobs, type="sessionTeach", sessionId=v["id"])

    # teach "proj": predict -> explain + check (wrong) -> repair + check (right) -> next idea
    assert answer_open(db, jobs, choice=1, thinking="I think it is the length")["phase"] == "predict"
    v = view(db)
    assert [i["phase"] for i in v["items"] if i["idea"] == "proj"] == ["predict", "explain", "check"]
    turn_prompt = [c.prompt for r, c in runner.calls if r == "Study tutor"][-1]
    assert "I think it is the length" in turn_prompt and "Your task: **explain**" in turn_prompt
    assert "misconceptions: thinks the projection is a number" in turn_prompt and "Start with the projection" in turn_prompt
    answer_open(db, jobs, choice=2)  # wrong check
    assert "Your task: **repair**" in [c.prompt for r, c in runner.calls if r == "Study tutor"][-1]
    answer_open(db, jobs, choice=0)  # right
    v = view(db)
    assert v["current"] == 1 and [i["phase"] for i in v["items"] if i["idea"] == "cos"] == ["predict"]
    proj_scores = [r["score"] for r in db.q("SELECT score FROM evidence WHERE concept_id=? ORDER BY id", (proj["node"],))]
    assert proj_scores == [0.0, 1.0]  # the two checks; the prediction is not evidence

    # teach "cos", then extract
    answer_open(db, jobs, choice=0)
    answer_open(db, jobs, choice=0, confidence=0.1)  # right but a guess: half evidence
    v = view(db)
    assert v["status"] == "done" and v["summary"].startswith("You now understand")
    node = db.one("SELECT * FROM nodes WHERE id=?", (proj["node"],))
    assert node["statement"].startswith("The projection") and node["origin"] == "session"
    pairs = {(lk["src"], lk["dst"]) for lk in graph.links(db)}
    assert (proj["node"], "c-dot") in pairs
    g = graph.view(db)
    pn = next(n for n in g["nodes"] if n["id"] == proj["node"])
    assert pn["state"] == "learning" and pn["sessions"] == [v["id"]] and pn["goals"] == []
    # the answers in the prompts never carried the hidden keys
    assert all('"answer"' not in json.dumps(i) or i["answered"] for i in v["items"] if i["phase"] != "explain")


def test_a_lesson_on_a_session_idea_sees_the_session_evidence(env):
    """Research may map a later lesson to an idea first learned in a session (same_as a session node)."""
    db, jobs, runner = env
    setup(runner)
    act(db, jobs, type="startSession", topic="cosine similarity")
    proj = next(i for i in view(db)["ideas"] if i["key"] == "proj")["node"]
    db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score)
            VALUES('2026-01-01T00:00:00+00:00', ?, 's-x-1', 'practice', 1, 1.0)""", (proj,))
    db.x("""INSERT INTO concepts(id, module_id, ord, title, objective, minutes, prereqs, p_init, started)
            VALUES('c-proj', 'm-la', 50, 'Projection', 'o', 10, '[]', 0.1, 0)""")
    graph.attach(db, "c-proj", proj)
    ev = [e for e in graph.evidence_for(db, ["c-proj"]) if e["item_id"] == "s-x-1"]
    assert ev and ev[0]["concept_id"] == "c-proj"
    assert state.concept_states(db, "g-ai")[1]["c-proj"].mastery > 0.1


def test_errors_retry_and_delete(env):
    db, jobs, runner = env
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "startSession", "topic": "x"})
    runner.responses["Study plan"] = {"title": "t", "target_key": "missing", "ideas": SKETCH["ideas"]}
    act(db, jobs, type="startSession", topic="cosine similarity")
    v = view(db)
    assert v["status"] == "sketching" and "no target" in v["error"]
    setup(runner)
    act(db, jobs, type="sessionRetry", sessionId=v["id"])
    v = view(db)
    assert v["status"] == "probing" and not v["error"]
    made = [i["node"] for i in v["ideas"] if not i["fromGraph"]]
    act(db, jobs, type="sessionAssessNow", sessionId=v["id"])  # no answers yet: plan at once, no result
    assert view(db)["status"] == "planning" and not view(db)["probeStart"]
    s = act(db, jobs, type="deleteSession", sessionId=v["id"])
    assert s["sessions"] == [] and not db.q(f"SELECT * FROM nodes WHERE id IN ({','.join('?' * len(made))})", made)
    assert db.one("SELECT 1 FROM nodes WHERE id='c-vectors'")  # graph ideas that were reused stay


def test_one_question_at_a_time_and_assess_now_writes_the_result(env):
    db, jobs, runner = env
    setup(runner)
    calls = []

    def reply(call):
        calls.append(call.prompt)
        if "Must you end now? yes" in call.prompt:
            return {"done": True, "result": RESULT}
        return {"done": False, "question": {"idea_key": "proj", **mcq(f"Q{len(calls)}?")}}
    runner.responses["Study tutor"] = reply
    act(db, jobs, type="startSession", topic="cosine similarity")
    for n in range(3):
        v = view(db)
        assert [i["round"] for i in v["items"] if not i["answered"]] == [n + 1]  # exactly one open question
        answer_open(db, jobs, choice=1, confidence=0.3, thinking=f"thought {n}")
    assert "thought 2" in calls[-1] and "(chance: 33%)" in calls[-1]
    act(db, jobs, type="sessionAssessNow", sessionId=view(db)["id"])
    v = view(db)
    assert v["status"] == "planning" and "Must you end now? yes" in calls[-1] and v["probeStart"]
    assert len([i for i in v["items"] if i["phase"] == "probe"]) == 3  # the open question was dropped
