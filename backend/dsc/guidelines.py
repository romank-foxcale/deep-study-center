"""Lesson guidelines (SPEC §12): the main points and patterns of the learner's feedback, distilled into a short
list that every new lesson and every applied revision follows.

The playbook stores scores per dimension (angles, pace, depth, rigor). Guidelines keep what scores cannot:
"start with a tiny numeric example", "name the shape before the formula". They are versioned (one row per
version), written by the ``distill_guidelines`` job after each finished lesson, and editable by the learner.
Lines the learner wrote or kept are never dropped by the job.
"""

from __future__ import annotations

from .db import DB, dumps, loads, now

MAX_ITEMS = 10


def current(db: DB) -> dict | None:
    row = db.one("SELECT * FROM guidelines ORDER BY id DESC LIMIT 1")
    if not row:
        return None
    n = db.one("SELECT COUNT(*) AS n FROM guidelines")["n"]
    return {"version": n, "ts": row["ts"], "source": row["source"], "summary": row["summary"],
            "items": loads(row["items"], [])}


def save(db: DB, items: list[dict], source: str, summary: str = "") -> int:
    """Store a new version. items: [{text, why, feedbackIds, byLearner}]."""
    clean = []
    for it in items[:MAX_ITEMS]:
        text = " ".join((it.get("text") or "").split())[:240]
        if text:
            clean.append({"text": text, "why": (it.get("why") or "")[:240], "feedbackIds": [int(i) for i in it.get("feedbackIds") or []],
                          "byLearner": bool(it.get("byLearner"))})
    db.x("INSERT INTO guidelines(ts, items, source, summary) VALUES(?,?,?,?)", (now(), dumps(clean), source, summary[:400]))
    return db.one("SELECT COUNT(*) AS n FROM guidelines")["n"]


def text(db: DB) -> str:
    g = current(db)
    if not g or not g["items"]:
        return "(none yet)"
    return "\n".join(f'- {it["text"]}' for it in g["items"])
