"""Step lessons (SPEC §43): an approved lesson plan is taught one step at a time, each step written just ahead of the
learner. Phase 2 of the lessons rework.

On approval, the lesson gets a card with one section per plan node that is not held, in the plan's order (the card has
``steps: true``). A section's content is written by the ``lesson_step`` job only when the learner is near it: the step
they are on and the next one. A step is:

- ``predict``: an optional question before the step, about what it will show (answered with ``predictStep``; not graded
  evidence: guessing is the point);
- the text (prose, as for any lesson), at most about 80 words, in the form the plan chose, with a widget for an
  interactive step;
- ``check``: a question after the step (answered like any check: evidence on the map, the tutor reads the thinking);
- ``repair``: a short re-explanation of the wrong idea, shown only after a wrong check;
- the goal step also has an explain-back.

A step is done when its check (or, for the goal, its explain-back) has an answer; the next step then opens. "Explain
differently" writes one step again, with the learner's note.
"""

from __future__ import annotations

from . import mcq, state, viz
from .db import DB, dumps, loads, now

ANGLE_OF = {"example": "computational", "interactive": "geometric", "figure": "geometric", "derivation": "algebraic",
            "text": "algebraic"}
AHEAD = 1  # steps written past the one the learner is on

_MCQ = {"type": "object", "required": ["prompt", "options", "answer", "explanation"], "properties": {
    "prompt": {"type": "string"}, "options": {"type": "array", "minItems": 3, "maxItems": 4, "items": {"type": "string"}},
    "answer": {"type": "integer"}, "explanation": {"type": "string"}}}
SCHEMA = {"type": "object", "required": ["body", "check", "repair"], "properties": {
    "predict": _MCQ,
    "body": {"type": "string"},
    "viz": viz.SCHEMA,
    "check": _MCQ,
    "repair": {"type": "string"},
    "explain": {"type": "object", "required": ["prompt", "rubric"], "properties": {
        "prompt": {"type": "string"}, "work": {"type": "boolean"},
        "rubric": {"type": "array", "minItems": 1, "items": {"type": "string"}}}}}}


class StepError(Exception):
    pass


def is_steps(card: dict | None) -> bool:
    return bool(card and card.get("steps"))


# ---------------------------------------------------------------- the card

def start(db: DB, jobs, cid: str, plan: dict) -> None:
    """Turn an approved plan into a step lesson: a card with one empty section per node that is not held, then write
    the first steps."""
    from . import lesson, lesson_graph
    book = db.one("""SELECT p.*, b.title AS book, b.source_id FROM book_parts p JOIN books b ON b.id = p.book_id
                     WHERE p.concept_id=?""", (cid,))
    obj = (db.one("SELECT objective FROM concepts WHERE id=?", (cid,)) or {}).get("objective", "")
    sections = []
    for n in lesson_graph._ordered(plan):
        if n["kind"] == "held":
            continue
        sec = {"id": f's-{n["key"]}', "heading": n["title"], "purpose": n["says"], "node": n["key"], "kind": n["kind"],
               "form": n["form"], "whyForm": n.get("whyForm", ""), "angles": [ANGLE_OF.get(n["form"], "algebraic")],
               "book": {"summary": "", "pages": n.get("pages") or ""}}
        sections.append(sec)
    if not sections:
        raise StepError("the plan has nothing to teach")
    held = [n["title"] for n in plan["nodes"] if n["kind"] == "held"]
    body = {"steps": True, "planVersion": plan["version"], "objective": obj, "core": plan["goal"], "formal": "",
            "why": plan["approach"], "bloom": "understand", "examples": [], "misconceptions": [], "angles": [],
            "held": held, "sections": sections,
            "sources": [{"title": f'{book["book"]}, pp. {book["page_from"]}-{book["page_to"]}',
                         "url": f'source:{book["source_id"]}#page={book["page_from"]}', "kind": "book",
                         "why": "The book this lesson follows"}] if book else []}
    row = db.one("SELECT MAX(version) AS v FROM cards WHERE concept_id=?", (cid,))
    version = (row["v"] or 0) + 1
    with db.tx():
        db.conn.execute("DELETE FROM renditions WHERE concept_id=?", (cid,))  # the new card gets a new rendition
        db.conn.execute("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
                        (cid, version, dumps(body), "skipped", now()))
    if book:
        db.x("UPDATE modules SET research='ready' WHERE id=(SELECT module_id FROM concepts WHERE id=?)", (cid,))
    lesson.ensure_rendition(db, cid)
    ensure(db, jobs, cid)


def _card(db: DB, cid: str) -> dict:
    card = state.latest_card(db, cid)
    if not is_steps(card):
        raise StepError("this lesson is not a step lesson")
    return card


def _save_section(db: DB, cid: str, version: int, sid: str, fields: dict) -> None:
    """Change one section of the card in place (a step lesson's card is filled in step by step)."""
    with db.tx():
        row = db.conn.execute("SELECT body FROM cards WHERE concept_id=? AND version=?", (cid, version)).fetchone()
        body = loads(row[0], {})
        for s in body["sections"]:
            if s["id"] == sid:
                for k, v in fields.items():
                    if v is None:
                        s.pop(k, None)
                    else:
                        s[k] = v
        db.conn.execute("UPDATE cards SET body=? WHERE concept_id=? AND version=?", (dumps(body), cid, version))


# ---------------------------------------------------------------- progress

def done_ids(db: DB, cid: str, card: dict) -> set[str]:
    """Sections whose check (or explain-back) has an answer."""
    answered = {r["item_id"] for r in db.q("SELECT DISTINCT item_id FROM evidence WHERE concept_id=? AND voided=0 AND kind='practice'",
                                           (cid,))}
    graded = {r["item_id"] for r in db.q("SELECT DISTINCT item_id FROM gradings WHERE concept_id=?", (cid,))}
    out = set()
    for s in card["sections"]:
        if (s.get("check") and s["check"]["id"] in answered) or (s.get("explain") and s["explain"]["id"] in graded):
            out.add(s["id"])
    return out


def current(db: DB, cid: str, card: dict) -> int:
    """The index of the step the learner is on: the first one not done (len(sections) when all are done)."""
    done = done_ids(db, cid, card)
    return next((i for i, s in enumerate(card["sections"]) if s["id"] not in done), len(card["sections"]))


def _written(db: DB, cid: str, card: dict, sid: str) -> bool:
    return bool(db.one("SELECT 1 FROM prose WHERE concept_id=? AND card_version=? AND section_id=?", (cid, card["version"], sid)))


def ensure(db: DB, jobs, cid: str) -> None:
    """Write the step the learner is on and the next one, when they are not written or being written."""
    card = state.latest_card(db, cid)
    if not is_steps(card):
        return
    at = current(db, cid, card)
    for s in card["sections"][at: at + 1 + AHEAD]:
        if not _written(db, cid, card, s["id"]) and not jobs.active("lesson_step", concept_id=cid, section_id=s["id"]):
            jobs.enqueue("lesson_step", f"Write the step “{s['heading'][:50]}”", {"concept_id": cid, "section_id": s["id"]})


def view(db: DB, cid: str, card: dict) -> dict:
    """What the lesson page needs on top of the sections: where the learner is, the plan's steps, the predictions."""
    at = current(db, cid, card)
    done = done_ids(db, cid, card)
    writing = set()
    for j in db.q("SELECT input FROM jobs WHERE kind='lesson_step' AND status IN ('queued','running')"):
        data = loads(j["input"], {})
        if data.get("concept_id") == cid:
            writing.add(data.get("section_id"))
    preds = {}
    for r in db.q("SELECT * FROM step_predictions WHERE concept_id=? ORDER BY id", (cid,)):
        preds[r["section_id"]] = {"choice": r["choice"], "correct": bool(r["correct"]), "thinking": r["thinking"]}
    secs = {s["id"]: s for s in card["sections"]}
    for sid, p in preds.items():  # the key is shown once the learner has predicted
        pr = secs.get(sid, {}).get("predict")
        if pr:
            p.update({"answer": pr["answer"], "explanation": pr.get("explanation", "")})
    return {"current": at, "total": len(card["sections"]), "held": card.get("held", []), "planVersion": card.get("planVersion"),
            "nodes": [{"id": s["id"], "title": s["heading"], "kind": s.get("kind", "step"), "form": s.get("form", "text"),
                       "done": s["id"] in done, "written": _written(db, cid, card, s["id"]), "writing": s["id"] in writing}
                      for s in card["sections"]],
            "predictions": preds}


# ---------------------------------------------------------------- learner actions

def predict(db: DB, cid: str, sid: str, choice: int, thinking: str = "") -> None:
    card = _card(db, cid)
    sec = next((s for s in card["sections"] if s["id"] == sid), None)
    if not sec or not sec.get("predict"):
        raise StepError("this step has no prediction")
    if not isinstance(choice, int) or not 0 <= choice < len(sec["predict"]["options"]):
        raise StepError("pick one of the options")
    db.x("DELETE FROM step_predictions WHERE concept_id=? AND section_id=?", (cid, sid))
    db.x("INSERT INTO step_predictions(concept_id, section_id, choice, correct, thinking, at) VALUES(?,?,?,?,?,?)",
         (cid, sid, choice, int(choice == sec["predict"]["answer"]), (thinking or "")[:2000], now()))


def rewrite(db: DB, jobs, cid: str, sid: str, note: str = "") -> None:
    """"Explain differently": write this step again with the learner's note (its answers stay)."""
    card = _card(db, cid)
    if not any(s["id"] == sid for s in card["sections"]):
        raise StepError("no such step")
    if jobs.active("lesson_step", concept_id=cid, section_id=sid):
        raise StepError("this step is being written")
    db.x("DELETE FROM prose WHERE concept_id=? AND card_version=? AND section_id=?", (cid, card["version"], sid))
    jobs.enqueue("lesson_step", "Write a step again", {"concept_id": cid, "section_id": sid,
                                                        "note": (note or "").strip()[:600] or "Explain it another way."})


# ---------------------------------------------------------------- the job

def run(jobs, jid: int, d: dict) -> dict:
    from .bookstudy import _chapter_text
    from .jobs import prompt
    from .providers import Call
    from . import lesson_graph, writer
    db = jobs.db
    cid, sid = d["concept_id"], d["section_id"]
    card = _card(db, cid)
    idx = next((i for i, s in enumerate(card["sections"]) if s["id"] == sid), None)
    if idx is None:
        raise StepError("no such step")
    sec = card["sections"][idx]
    r = state.rendition_row(db, cid)
    if not r or r["card_version"] != card["version"]:
        from . import lesson
        r = lesson.ensure_rendition(db, cid)
    x = db.one("""SELECT p.*, b.title AS book, b.source_id FROM book_parts p JOIN books b ON b.id = p.book_id WHERE p.concept_id=?""",
               (cid,))
    plan = lesson_graph.approved(db, cid)
    jobs.progress(jid, f"writing step {idx + 1} of {len(card['sections'])}: {sec['heading'][:60]}")
    text = _chapter_text(db, x["source_id"], x["page_from"], x["page_to"]) if x else ""
    out = jobs.call(jid, "Renditions", Call(
        prompt=prompt("lesson_step", book=x["book"] if x else "", lesson=(x or {}).get("title", sec["heading"]),
                      plan=lesson_graph.as_text(plan) if plan else card.get("why", ""),
                      step=f'{idx + 1} of {len(card["sections"])}: [{sec.get("kind", "step")}] {sec["heading"]}. {sec["purpose"]}',
                      form=f'{sec.get("form", "text")}' + (f' ({sec["whyForm"]})' if sec.get("whyForm") else ""),
                      goal="yes" if sec.get("kind") == "goal" else "no",
                      done=_done_text(db, cid, card, idx), note=d.get("note") or "(none)", text=text or "(no text)"),
        schema=SCHEMA, model="sonnet", timeout=600))
    body = str(out.get("body") or "").strip()
    if not body:
        raise StepError("the step came back empty")
    fields: dict = {"repair": str(out.get("repair") or "").strip() or None}
    chk = out.get("check") or {}
    fields["check"] = {**mcq.shuffle(chk), "id": f"q-{sid}"} if _mcq_ok(chk) else None
    pr = out.get("predict")
    fields["predict"] = {**mcq.shuffle(pr), "id": f"p-{sid}"} if isinstance(pr, dict) and _mcq_ok(pr) else None
    ex = out.get("explain")
    fields["explain"] = ({"prompt": ex["prompt"], "rubric": ex["rubric"][:4], "work": bool(ex.get("work")), "id": f"e-{sid}"}
                         if sec.get("kind") == "goal" and isinstance(ex, dict) and ex.get("prompt") and ex.get("rubric") else None)
    raw = out.get("viz")
    if isinstance(raw, dict):
        spec, notes = writer.check_viz(jobs, jid, {**card, "objective": card.get("objective", "")}, sec, raw)
        spec = viz.validate(spec) if spec else None
        fields["viz"], fields["vizNotes"] = spec, (notes or None) if spec else None
    else:
        fields["viz"] = fields["vizNotes"] = None
    _save_section(db, cid, card["version"], sid, fields)
    angle = (r or {}).get("section_angles", {}).get(sid) or sec["angles"][0]
    style = (r or {}).get("style") or "default"
    db.x("""INSERT OR REPLACE INTO prose(concept_id, card_version, section_id, angle, style, body, source, created_at)
            VALUES(?,?,?,?,?,?,?,?)""", (cid, card["version"], sid, angle, style, body, "step", now()))
    jobs.progress(jid, "step written" + (", with a widget" if fields.get("viz") else ""))
    return {"section": sid}


def _mcq_ok(q: dict) -> bool:
    opts = q.get("options") or []
    return bool(q.get("prompt")) and 3 <= len(opts) <= 4 and isinstance(q.get("answer"), int) and 0 <= q["answer"] < len(opts)


def _done_text(db: DB, cid: str, card: dict, idx: int) -> str:
    """The steps before this one: what each said, and how the learner did on its prediction and check."""
    if idx == 0:
        return "(none: this is the first step)"
    ev = {r["item_id"]: r for r in db.q("""SELECT item_id, correct, thinking FROM evidence WHERE concept_id=? AND voided=0
                                          AND kind='practice' ORDER BY id""", (cid,))}
    preds = {r["section_id"]: r for r in db.q("SELECT * FROM step_predictions WHERE concept_id=?", (cid,))}
    out = []
    for s in card["sections"][:idx]:
        p = db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? ORDER BY created_at DESC LIMIT 1",
                   (cid, card["version"], s["id"]))
        line = f'- {s["heading"]}: {((p or {}).get("body") or s["purpose"])[:500]}'
        pr = preds.get(s["id"])
        if pr:
            line += f' | Prediction: {"right" if pr["correct"] else "wrong"}' + (f' ("{pr["thinking"][:200]}")' if pr["thinking"] else "")
        e = ev.get((s.get("check") or {}).get("id", ""))
        if e:
            line += f' | Check: {"right" if e["correct"] else "WRONG (the repair was shown)"}' + \
                    (f' ("{(e["thinking"] or "")[:200]}")' if e["thinking"] else "")
        out.append(line)
    return "\n".join(out)
