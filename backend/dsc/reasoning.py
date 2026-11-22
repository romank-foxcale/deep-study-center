"""The tutor reads your reasoning (SPEC §32).

When you answer a lesson check and say how you think (typed or dictated), a job reads that thinking against the
question, the key and the lesson. It marks each part of your thinking as right, partly right or wrong, with a short
reason; names the wrong assumption behind a wrong answer; follows that assumption ("if it worked your way, then …")
until it breaks; and then derives how it really works from there. A right answer with gaps gets the gaps corrected.
Every review is saved with the answer, so the history shows how your understanding changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

MIN_CHARS = 20  # shorter thinking ("not sure") has nothing to read

SCHEMA = {"type": "object", "required": ["verdict", "summary", "parts", "assumption", "follow", "truth", "takeaway"], "properties": {
    "verdict": {"enum": ["right", "right_with_gaps", "wrong", "unclear"]},
    "summary": {"type": "string"},
    "parts": {"type": "array", "items": {"type": "object", "required": ["quote", "mark", "note"], "properties": {
        "quote": {"type": "string"}, "mark": {"enum": ["right", "partly", "wrong"]}, "note": {"type": "string"}}}},
    "assumption": {"type": "string"},
    "follow": {"type": "array", "items": {"type": "string"}},
    "truth": {"type": "string"},
    "takeaway": {"type": "string"}}}


def queue(db: DB, jobs: Jobs, cid: str, item: dict, evidence_id: int, thinking: str) -> int | None:
    """After an answer with thinking: save a pending review and queue the job. Returns the review id."""
    if len((thinking or "").strip()) < MIN_CHARS or item.get("kind") != "check":
        return None
    rid = db.x("INSERT INTO reasoning_reviews(ts, evidence_id, concept_id, item_id, status, body) VALUES(?,?,?,?,?,?)",
               (now(), evidence_id, cid, item["id"], "pending", "{}"))
    jobs.enqueue("reasoning_review", "Read your reasoning", {"review_id": rid, "concept_id": cid})
    return rid


def _check(db: DB, cid: str, item_id: str) -> tuple[dict | None, dict | None]:
    from . import state
    from .writer import effective_sections
    card = state.latest_card(db, cid) or {}
    for s in effective_sections(db, cid, card) + card.get("sections", []):
        if (s.get("check") or {}).get("id") == item_id:
            return card, s
    return card, None


def clean(out: dict, thinking: str) -> dict:
    """The review as the page shows it: quotes that are really in the thinking (sorted by where they stand), the rest kept."""
    thinking = thinking or ""
    parts = []
    for p in out.get("parts") or []:  # keep only quotes that are really in the thinking (the page marks them in place)
        q = (p.get("quote") or "").strip().strip('"“”')
        if q and q.lower() in thinking.lower():
            parts.append({"quote": q, "mark": p.get("mark") if p.get("mark") in ("right", "partly", "wrong") else "partly",
                          "note": (p.get("note") or "").strip()})
    parts.sort(key=lambda p: thinking.lower().find(p["quote"].lower()))  # numbered in the order they stand in the thinking
    return {"verdict": out.get("verdict") or "unclear", "summary": out.get("summary") or "", "parts": parts,
            "assumption": out.get("assumption") or "", "follow": [x for x in out.get("follow") or [] if x.strip()][:5],
            "truth": out.get("truth") or "", "takeaway": out.get("takeaway") or ""}


def queue_session(db: DB, jobs: Jobs, sid: str, row_id: int, idea_key: str, thinking: str) -> int | None:
    """A study-session answer (a prediction or a check) with thinking: the tutor reads it too (SPEC §35)."""
    if len((thinking or "").strip()) < MIN_CHARS:
        return None
    rid = db.x("""INSERT INTO reasoning_reviews(ts, evidence_id, concept_id, item_id, status, body, session_item_id)
                  VALUES(?,?,?,?,?,?,?)""", (now(), 0, sid, idea_key, "pending", "{}", row_id))
    jobs.enqueue("reasoning_review", "Read your reasoning", {"review_id": rid, "session_id": sid})
    return rid


def _session_inputs(db: DB, r: dict) -> dict | None:
    row = db.one("SELECT * FROM session_items WHERE id=?", (r["session_item_id"],))
    s = db.one("SELECT * FROM sessions WHERE id=?", (r["concept_id"],))
    if not row or not s:
        return None
    item = loads(row["item"], {})
    idea = next((i for i in loads(s["ideas"], []) if i.get("key") == row["idea_key"]), {})
    said = [loads(x["item"], {}).get("body", "") for x in db.q(
        "SELECT item FROM session_items WHERE session_id=? AND idea_key=? AND phase='explain' AND id < ? ORDER BY id",
        (row["session_id"], row["idea_key"], row["id"]))]
    phase = "a prediction before the explanation (they had not been taught this step yet)" if row["phase"] == "predict" \
        else "a check after the explanation"
    return {"lesson": s["title"], "core": idea.get("statement", ""), "why": "",
            "section": f'{idea.get("title", "")} ({phase})' + (f"\nWhat the tutor explained: {said[-1][:1500]}" if said else ""),
            "c": item, "choice": row["choice"], "correct": row["correct"], "confidence": row["confidence"], "thinking": row["thinking"]}


def _lesson_inputs(db: DB, r: dict) -> dict | None:
    ev = db.one("SELECT * FROM evidence WHERE id=?", (r["evidence_id"],))
    if not ev:
        return None
    card, sec = _check(db, r["concept_id"], r["item_id"])
    if not sec:
        return None
    book = (sec.get("book") or {}).get("summary", "")
    return {"lesson": (db.one("SELECT title FROM concepts WHERE id=?", (r["concept_id"],)) or {}).get("title", ""),
            "core": card.get("core", ""), "why": card.get("why", ""),
            "section": f'{sec.get("heading", "")}: {sec.get("purpose", "")}' + (f"\nWhat the book says: {book}" if book else ""),
            "c": sec["check"], "choice": ev["choice"], "correct": ev["correct"], "confidence": ev["confidence"],
            "thinking": ev["thinking"]}


def run(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    r = db.one("SELECT * FROM reasoning_reviews WHERE id=?", (d["review_id"],))
    if not r:
        return {"skipped": True}
    x = _session_inputs(db, r) if r.get("session_item_id") else _lesson_inputs(db, r)
    if not x:
        db.x("UPDATE reasoning_reviews SET status='failed', body=? WHERE id=?", (dumps({"error": "the question is gone"}), r["id"]))
        return {"skipped": True}
    c = x["c"]
    letters = "ABCDE"
    options = "\n".join(f"{letters[i]}) {o}" for i, o in enumerate(c["options"]))
    chose = letters[x["choice"]] if x["choice"] is not None and 0 <= x["choice"] < len(c["options"]) else "-"
    conf = "not given" if x["confidence"] is None else f'{round(x["confidence"] * 100)} %'
    out = jobs.call(jid, "Reasoning review", Call(
        prompt=prompt("reason_review", lesson=x["lesson"], core=x["core"], why=x["why"], section=x["section"],
                      question=c["prompt"], options=options, key=letters[c["answer"]], explanation=c.get("explanation", ""),
                      chose=chose, correct="right" if x["correct"] else "wrong", confidence=conf, thinking=x["thinking"]),
        schema=SCHEMA, model="sonnet", timeout=240))
    body = clean(out, x["thinking"])
    db.x("UPDATE reasoning_reviews SET status='done', body=? WHERE id=?", (dumps(body), r["id"]))
    return {"verdict": body["verdict"], "parts": len(body["parts"])}


def fallback(jobs: Jobs, jid: int, d: dict) -> None:
    jobs.db.x("UPDATE reasoning_reviews SET status='failed' WHERE id=? AND status='pending'", (d["review_id"],))


def _shown(r: dict) -> dict:
    return {"id": r["id"], "status": r["status"], **({} if r["status"] != "done" else loads(r["body"], {}))}


def by_evidence(db: DB, evidence_ids: list[int]) -> dict[int, dict]:
    """The newest review per answer, for the page."""
    if not evidence_ids:
        return {}
    out: dict[int, dict] = {}
    for r in db.q(f"""SELECT * FROM reasoning_reviews WHERE session_item_id IS NULL
                      AND evidence_id IN ({','.join('?' * len(evidence_ids))}) ORDER BY id""", evidence_ids):
        out[r["evidence_id"]] = _shown(r)
    return out


def by_session_items(db: DB, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    return {r["session_item_id"]: _shown(r) for r in db.q(
        f"SELECT * FROM reasoning_reviews WHERE session_item_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids)}


def grading_review(g: dict) -> dict | None:
    """An explain-back the grader read (SPEC §35), in the same shape as a review."""
    body = loads(g.get("review"), None) if g.get("review") else None
    if not body:
        return None
    verdict = {1.0: "right", 0.5: "right_with_gaps", 0.0: "wrong"}.get(float(g["score"]) if g.get("score") is not None else -1, "unclear")
    return {"id": g["id"], "status": "done", "verdict": verdict, "summary": "", **body}


def history(db: DB, cid: str | None = None, limit: int = 50) -> list[dict]:
    """Your reasoning over time: each answer with thinking (lesson checks, study sessions, explain-backs), how sure you
    were, and what the tutor found. Newest first."""
    out: list[dict] = []
    where, args = ("AND rr.concept_id=?", (cid,)) if cid else ("", ())
    for r in db.q(f"""SELECT rr.*, e.thinking, e.confidence, e.correct, e.ts AS answered, c.title FROM reasoning_reviews rr
                      JOIN evidence e ON e.id = rr.evidence_id LEFT JOIN concepts c ON c.id = rr.concept_id
                      WHERE rr.session_item_id IS NULL {where} ORDER BY rr.id DESC LIMIT ?""", args + (limit,)):
        out.append({"id": r["id"], "kind": "check", "conceptId": r["concept_id"], "title": r["title"] or r["concept_id"],
                    "link": f'/lesson/{r["concept_id"]}', "itemId": r["item_id"], "at": r["answered"], "correct": bool(r["correct"]),
                    "confidence": r["confidence"], "thinking": r["thinking"], **_shown(r)})
    if not cid:
        for r in db.q("""SELECT rr.*, si.thinking, si.confidence, si.correct, si.answered_at AS answered, s.title FROM reasoning_reviews rr
                         JOIN session_items si ON si.id = rr.session_item_id JOIN sessions s ON s.id = rr.concept_id
                         ORDER BY rr.id DESC LIMIT ?""", (limit,)):
            out.append({"id": r["id"], "kind": "session", "conceptId": r["concept_id"], "title": r["title"], "link": f'/study/{r["concept_id"]}',
                        "itemId": r["item_id"], "at": r["answered"], "correct": bool(r["correct"]), "confidence": r["confidence"],
                        "thinking": r["thinking"], **_shown(r)})
    gw, ga = ("AND g.concept_id=?", (cid,)) if cid else ("", ())
    for g in db.q(f"""SELECT g.*, c.title FROM gradings g LEFT JOIN concepts c ON c.id = g.concept_id
                      WHERE g.review IS NOT NULL {gw} ORDER BY g.id DESC LIMIT ?""", ga + (limit,)):
        out.append({"kind": "explain", "conceptId": g["concept_id"], "title": g["title"] or g["concept_id"], "link": f'/lesson/{g["concept_id"]}',
                    "itemId": g["item_id"], "at": g["ts"], "correct": (g["score"] or 0) >= 1, "confidence": g["confidence"],
                    "thinking": g["answer"], **grading_review(g), "id": 10_000_000 + g["id"]})
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return out[:limit]
