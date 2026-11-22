"""The probe: find the edge of what the learner knows for a goal (SPEC §20). It replaces the placement quiz.

An agent asks quick multiple-choice questions, one at a time (SPEC §26). It sees the roadmap, what the learner learned
in other goals, and every earlier answer with the learner's thinking and confidence. It brackets the edge of each area
(it starts high; a well-reasoned right answer allows a big jump, a miss moves toward the basics) and drills in only
where the answer would change what gets taught. Options are shuffled when stored. When the edge is clear (or at the limit) it writes an assessment: per step known / partial /
unknown, the edge in words, and the misconceptions it saw. "Use this" turns known steps into a roadmap proposal and
adds the edge and misconceptions to the goal profile, so research and every lesson see them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import mcq, state
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

ROUND = 1           # one question at a time, each chosen from the answers so far (SPEC §26)
MAX_QUESTIONS = 15
MAX_ROUNDS = MAX_QUESTIONS
LEVELS = ("known", "partial", "unknown")

SCHEMA = {"type": "object", "required": ["done", "questions"], "properties": {
    "done": {"type": "boolean"},
    "questions": {"type": "array", "maxItems": ROUND, "items": {"type": "object",
        "required": ["module_id", *mcq.SCHEMA["required"]],
        "properties": {"module_id": {"type": "string"}, **mcq.SCHEMA["properties"]}}},
    "assessment": {"type": "object", "required": ["summary", "edge", "modules", "misconceptions"], "properties": {
        "summary": {"type": "string"}, "edge": {"type": "string"},
        "modules": {"type": "array", "items": {"type": "object", "required": ["module_id", "level", "note"], "properties": {
            "module_id": {"type": "string"}, "level": {"enum": list(LEVELS)}, "note": {"type": "string"}}}},
        "misconceptions": {"type": "array", "items": {"type": "string"}}}}}}


def _steps(db: DB, gid: str) -> list[dict]:
    """The goal's steps in roadmap order, without merge steps (they only join what other steps teach)."""
    return db.q("""SELECT m.id, m.title, m.summary, t.title AS area FROM modules m JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id=? AND m.requires='[]' ORDER BY t.ord, m.ord""", (gid,))


def _items(db: DB, gid: str) -> list[dict]:
    return db.q("SELECT * FROM probe_items WHERE goal_id=? ORDER BY round, ord", (gid,))


def _result(db: DB, gid: str) -> dict | None:
    return db.one("SELECT * FROM probe_results WHERE goal_id=?", (gid,))


def start(db: DB, jobs: Jobs, gid: str) -> None:
    if _items(db, gid) or _result(db, gid) or jobs.active("probe_round", goal_id=gid):
        return
    jobs.enqueue("probe_round", "Find where you stand", {"goal_id": gid})


def answer(db: DB, jobs: Jobs, gid: str, item_id: int, choice: int | None, thinking: str, confidence: float | None) -> None:
    """One answer; choice None is "I don't know". When the round is complete, the next round (or the assessment) is asked for."""
    row = db.one("SELECT * FROM probe_items WHERE id=? AND goal_id=?", (item_id, gid))
    if not row:
        raise ValueError("unknown question")
    if row["answered"]:
        return
    item = loads(row["item"])
    correct = choice is not None and choice == item["answer"]
    db.x("""UPDATE probe_items SET choice=?, answered=1, correct=?, thinking=?, confidence=?, answered_at=? WHERE id=?""",
         (choice, int(correct), thinking, confidence, now(), item_id))
    if not db.one("SELECT 1 FROM probe_items WHERE goal_id=? AND answered=0", (gid,)) and not jobs.active("probe_round", goal_id=gid):
        jobs.enqueue("probe_round", "Find where you stand", {"goal_id": gid})


def assess_now(db: DB, jobs: Jobs, gid: str) -> None:
    """Stop asking: drop unanswered questions and ask for the assessment from the answers so far."""
    db.x("DELETE FROM probe_items WHERE goal_id=? AND answered=0", (gid,))
    if not jobs.active("probe_round", goal_id=gid) and not _result(db, gid):
        jobs.enqueue("probe_round", "Assess where you stand", {"goal_id": gid, "assess": True})


def reset(db: DB, gid: str) -> None:
    db.x("DELETE FROM probe_items WHERE goal_id=?", (gid,))
    db.x("DELETE FROM probe_results WHERE goal_id=?", (gid,))


def answers_text(db: DB, gid: str) -> str:
    titles = {m["id"]: m["title"] for m in db.q("SELECT id, title FROM modules")}
    lines = []
    for r in _items(db, gid):
        if not r["answered"]:
            continue
        it = loads(r["item"])
        chose = "I don't know" if r["choice"] is None else it["options"][r["choice"]]
        line = (f'- question {r["round"]}, step {r["module_id"]} ({titles.get(r["module_id"], "?")}): {it["prompt"]} '
                f'| chose: {chose} ({"right" if r["correct"] else "wrong" if r["choice"] is not None else "did not know"})')
        if r["confidence"] is not None:
            line += f' | confidence {round(r["confidence"] * 100)}% (chance: {round(mcq.chance(len(it["options"])) * 100)}%)'
        if r["thinking"]:
            line += f' | thinking: "{r["thinking"][:600]}"'
        lines.append(line)
    return "\n".join(lines) or "(none yet: this is the first question)"


def known_elsewhere(db: DB, gid: str) -> str:
    """What the learner learned in other goals (concepts with a review = learned)."""
    rows = db.q("""SELECT c.title, t.goal_id FROM reviews r JOIN concepts c ON c.id = r.concept_id
                   JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id WHERE t.goal_id != ?""", (gid,))
    known = db.q("""SELECT m.title FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id != ? AND m.known=1""", (gid,))
    out = [f"- learned: {r['title']}" for r in rows[:80]] + [f"- known step: {r['title']}" for r in known[:40]]
    return "\n".join(out) or "(nothing yet)"


def run_round(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    gid = d["goal_id"]
    g = db.one("SELECT * FROM goals WHERE id=?", (gid,))
    steps = _steps(db, gid)
    items = _items(db, gid)
    rounds = max((r["round"] for r in items), default=0)
    asked = sum(1 for r in items if r["answered"])
    must_end = bool(d.get("assess")) or rounds >= MAX_ROUNDS or asked >= MAX_QUESTIONS
    out = jobs.call(jid, "Placement", Call(
        prompt=prompt("probe", goal=g["title"], profile=g["profile"],
                      steps="\n".join(f'{m["id"]} | {m["area"]} | {m["title"]} - {m["summary"] or ""}' for m in steps),
                      elsewhere=known_elsewhere(db, gid), answers=answers_text(db, gid), asked=asked, rounds=rounds,
                      max_questions=MAX_QUESTIONS, round_size=ROUND,
                      must_end="yes: write the assessment now, no more questions" if must_end else "no"),
        schema=SCHEMA, model="sonnet", timeout=300))
    ids = {m["id"] for m in steps}
    questions = [q for q in out.get("questions") or [] if q["module_id"] in ids and 0 <= q["answer"] < len(q["options"])]
    if not (out.get("done") or must_end or questions):
        raise ValueError("the probe returned no usable questions")
    if out.get("done") or must_end:
        a = out.get("assessment") or {}
        mods = [{"moduleId": m["module_id"], "level": m["level"], "note": m["note"][:300]}
                for m in a.get("modules", []) if m["module_id"] in ids and m["level"] in LEVELS]
        assessment = {"summary": (a.get("summary") or "")[:1500], "edge": (a.get("edge") or "")[:1500], "modules": mods,
                      "misconceptions": [x[:300] for x in a.get("misconceptions", [])][:12]}
        db.x("INSERT OR REPLACE INTO probe_results(goal_id, ts, assessment, applied) VALUES(?,?,?,0)", (gid, now(), dumps(assessment)))
        jobs.progress(jid, f"assessment ready after {asked} question(s)")
        return {"assessed": True, "asked": asked}
    with db.tx():
        for i, q in enumerate(questions[:ROUND]):
            item = mcq.shuffle({"prompt": q["prompt"], "options": q["options"], "answer": q["answer"], "explanation": q["explanation"]})
            db.conn.execute("INSERT INTO probe_items(goal_id, round, ord, module_id, item) VALUES(?,?,?,?,?)",
                            (gid, rounds + 1, i, q["module_id"], dumps(item)))
    jobs.progress(jid, f"question {rounds + 1}")
    return {"round": rounds + 1}


def apply(db: DB, gid: str) -> None:
    """Use the assessment: known steps become a roadmap proposal; the edge and misconceptions go into the profile."""
    res = _result(db, gid)
    if not res or res["applied"]:
        return
    a = loads(res["assessment"])
    known = [m["moduleId"] for m in a["modules"] if m["level"] == "known"]
    titles = {m["id"]: m["title"] for m in db.q("SELECT id, title FROM modules")}
    notes = {m["moduleId"]: m["note"] for m in a["modules"]}
    if known:
        changes = [{"op": "compress", "title": titles.get(m, m), "module": m,
                    "detail": f"The probe showed you know this ({notes.get(m) or 'all answers right and sure'}); marked as known."}
                   for m in known]
        db.x("INSERT INTO diffs(ts, goal_id, reason, changes, status) VALUES(?,?,?,?,'pending')",
             (now(), gid, f"Probe: you already know {len(known)} step{'s' if len(known) != 1 else ''}.", dumps(changes)))
    g = db.one("SELECT profile FROM goals WHERE id=?", (gid,))
    add = f"Where they stand (probe, {now()[:10]}): {a['edge']}"
    if a["misconceptions"]:
        add += " Misconceptions seen: " + "; ".join(a["misconceptions"])
    db.x("UPDATE goals SET profile=? WHERE id=?", (((g["profile"] or "").rstrip() + "\n" + add).strip(), gid))
    db.x("UPDATE probe_results SET applied=1 WHERE goal_id=?", (gid,))


def view(db: DB, gid: str, running: bool) -> dict:
    """The probe as the page shows it: the current question (without its key), the answered ones, the assessment."""
    items = _items(db, gid)
    res = _result(db, gid)
    titles = {m["id"]: m["title"] for m in db.q("SELECT id, title FROM modules")}
    answered = []
    for r in items:
        if r["answered"]:
            it = loads(r["item"])
            answered.append({"id": r["id"], "round": r["round"], "module": titles.get(r["module_id"], ""), "prompt": it["prompt"],
                             "options": it["options"], "choice": r["choice"], "correct": bool(r["correct"]), "answer": it["answer"],
                             "explanation": it["explanation"], "thinking": r["thinking"], "confidence": r["confidence"]})
    nxt = next((r for r in items if not r["answered"]), None)
    question = None
    if nxt:
        it = loads(nxt["item"])
        question = {"id": nxt["id"], "round": nxt["round"], "module": titles.get(nxt["module_id"], ""),
                    "prompt": it["prompt"], "options": it["options"]}
    assessment = None
    if res:
        a = loads(res["assessment"])
        assessment = {**a, "applied": bool(res["applied"]),
                      "modules": [{**m, "title": titles.get(m["moduleId"], m["moduleId"])} for m in a["modules"]]}
    status = "done" if res else ("thinking" if running else ("asking" if question else ("idle" if not items else "thinking")))
    return {"status": status, "question": question, "answered": answered, "asked": len(answered),
            "rounds": max((r["round"] for r in items), default=0), "maxQuestions": MAX_QUESTIONS, "assessment": assessment}
