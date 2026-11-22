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


def run(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    r = db.one("SELECT * FROM reasoning_reviews WHERE id=?", (d["review_id"],))
    ev = db.one("SELECT * FROM evidence WHERE id=?", (r["evidence_id"],)) if r else None
    if not r or not ev:
        return {"skipped": True}
    card, sec = _check(db, r["concept_id"], r["item_id"])
    if not sec:
        db.x("UPDATE reasoning_reviews SET status='failed', body=? WHERE id=?", (dumps({"error": "the question is gone"}), r["id"]))
        return {"skipped": True}
    c = sec["check"]
    title = (db.one("SELECT title FROM concepts WHERE id=?", (r["concept_id"],)) or {}).get("title", "")
    letters = "ABCDE"
    options = "\n".join(f"{letters[i]}) {o}" for i, o in enumerate(c["options"]))
    chose = letters[ev["choice"]] if ev["choice"] is not None and 0 <= ev["choice"] < len(c["options"]) else "-"
    conf = "not given" if ev["confidence"] is None else f'{round(ev["confidence"] * 100)} %'
    book = (sec.get("book") or {}).get("summary", "")
    out = jobs.call(jid, "Reasoning review", Call(
        prompt=prompt("reason_review", lesson=title, core=card.get("core", ""), why=card.get("why", ""),
                      section=f'{sec.get("heading", "")}: {sec.get("purpose", "")}' + (f"\nWhat the book says: {book}" if book else ""),
                      question=c["prompt"], options=options, key=letters[c["answer"]], explanation=c.get("explanation", ""),
                      chose=chose, correct="right" if ev["correct"] else "wrong", confidence=conf, thinking=ev["thinking"]),
        schema=SCHEMA, model="sonnet", timeout=240))
    thinking = ev["thinking"] or ""
    parts = []
    for p in out.get("parts") or []:  # keep only quotes that are really in the thinking (the page marks them in place)
        q = (p.get("quote") or "").strip().strip('"“”')
        if q and q.lower() in thinking.lower():
            parts.append({"quote": q, "mark": p.get("mark") if p.get("mark") in ("right", "partly", "wrong") else "partly",
                          "note": (p.get("note") or "").strip()})
    parts.sort(key=lambda p: thinking.lower().find(p["quote"].lower()))  # numbered in the order they stand in the thinking
    body = {"verdict": out.get("verdict") or "unclear", "summary": out.get("summary") or "", "parts": parts,
            "assumption": out.get("assumption") or "", "follow": [x for x in out.get("follow") or [] if x.strip()][:5],
            "truth": out.get("truth") or "", "takeaway": out.get("takeaway") or ""}
    db.x("UPDATE reasoning_reviews SET status='done', body=? WHERE id=?", (dumps(body), r["id"]))
    return {"verdict": body["verdict"], "parts": len(parts)}


def fallback(jobs: Jobs, jid: int, d: dict) -> None:
    jobs.db.x("UPDATE reasoning_reviews SET status='failed' WHERE id=? AND status='pending'", (d["review_id"],))


def by_evidence(db: DB, evidence_ids: list[int]) -> dict[int, dict]:
    """The newest review per answer, for the page."""
    if not evidence_ids:
        return {}
    out: dict[int, dict] = {}
    for r in db.q(f"SELECT * FROM reasoning_reviews WHERE evidence_id IN ({','.join('?' * len(evidence_ids))}) ORDER BY id",
                  evidence_ids):
        out[r["evidence_id"]] = {"id": r["id"], "status": r["status"], **({} if r["status"] != "done" else loads(r["body"], {}))}
    return out


def history(db: DB, cid: str | None = None, limit: int = 50) -> list[dict]:
    """Your reasoning over time: each answer with thinking, how sure you were, and what the tutor found."""
    where, args = ("WHERE rr.concept_id=?", (cid,)) if cid else ("", ())
    rows = db.q(f"""SELECT rr.*, e.thinking, e.confidence, e.correct, e.ts AS answered, c.title FROM reasoning_reviews rr
                    JOIN evidence e ON e.id = rr.evidence_id LEFT JOIN concepts c ON c.id = rr.concept_id
                    {where} ORDER BY rr.id DESC LIMIT ?""", args + (limit,))
    return [{"id": r["id"], "conceptId": r["concept_id"], "title": r["title"] or r["concept_id"], "itemId": r["item_id"],
             "at": r["answered"], "correct": bool(r["correct"]), "confidence": r["confidence"], "thinking": r["thinking"],
             "status": r["status"], **({} if r["status"] != "done" else loads(r["body"], {}))} for r in rows]
