"""The Today page (SPEC §30): where to pick up, what to recall, and this week in numbers. Read-only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import bookstudy, graph, practice, session
from .db import DB

KNOWN = ("learned", "mastered", "rusty")


def _week_start() -> datetime:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _continue(db: DB) -> dict | None:
    """The newest study session that is not finished, else the next part of the newest book study."""
    for s in db.q("SELECT id FROM sessions WHERE status NOT IN ('done') ORDER BY updated_at DESC LIMIT 5"):
        v = session.view(db, s["id"])
        if not v:
            continue
        plan = v["plan"]
        nxt = plan[v["current"]] if v["status"] == "teaching" and v["current"] < len(plan) else None
        idea = next((i for i in v["ideas"] if i["key"] == nxt), None)
        return {"kind": "session", "sessionId": v["id"], "title": v["title"], "status": v["status"], "book": v.get("book"),
                "next": idea["title"] if idea else None, "nextStatement": idea["statement"] if idea else None,
                "done": min(v["current"], len(plan)) if v["status"] == "teaching" else 0, "total": len(plan) or len(v["ideas"])}
    for b in db.q("SELECT id FROM books WHERE status='ready' ORDER BY updated_at DESC LIMIT 3"):
        v = bookstudy.view(db, b["id"])
        part = next((p for p in v["parts"] if p["id"] == v["next"]), None) if v else None
        if part:
            return {"kind": "part", "bookId": v["id"], "bookTitle": v["title"], "partId": part["id"], "title": part["title"],
                    "pages": part["pages"], "summary": part["summary"], "total": len(part["ideas"]), "done": 0}
    return None


def view(db: DB) -> dict:
    st = graph.states(db)
    week = _week_start()
    learned_week = sum(1 for s in st.values() if s.state in KNOWN and (_parse(s.learned_at) or datetime.min.replace(tzinfo=timezone.utc)) >= week)
    answers_week = db.one("SELECT COUNT(*) AS n FROM evidence WHERE ts >= ? AND voided = 0", (week.isoformat(),))["n"]
    sessions_week = db.one("SELECT COUNT(*) AS n FROM sessions WHERE status='done' AND updated_at >= ?", (week.isoformat(),))["n"]
    due = practice.due(db)
    recent = [{"id": r["id"], "title": r["title"], "status": r["status"], "updatedAt": r["updated_at"]}
              for r in db.q("SELECT id, title, status, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 4")]
    return {
        "continue": _continue(db),
        "due": {"count": sum(1 for d in due if d["reason"] == "due"), "items": due[:6]},
        "week": {"learned": learned_week, "strong": sum(1 for s in st.values() if s.state == "mastered"),
                 "answers": answers_week, "sessions": sessions_week},
        "recent": recent,
    }
