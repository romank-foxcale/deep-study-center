"""Shared write helpers used by both actions and jobs: recording evidence, and keeping research one
module ahead of the learner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import engine, state
from .db import DB, now

if TYPE_CHECKING:
    from .jobs import Jobs


def record_evidence(db: DB, cid: str, item_id: str, score: float, *, choice: int | None = None,
                    angle: str | None = None) -> None:
    """Append graded practice evidence; schedule the first review when the concept becomes learned."""
    gid = state.active_goal(db)
    _, before = state.concept_states(db, gid)
    db.x("INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, angle, score) VALUES(?,?,?,?,?,?,?,?)",
         (now(), cid, item_id, "practice", choice, int(score >= engine.PASS_SCORE), angle, score))
    db.x("UPDATE concepts SET started=1 WHERE id=?", (cid,))
    if angle:  # outcome signal: weak evidence about the angle used; never re-renders anything by itself
        delta = 0.03 if score >= engine.PASS_SCORE else (-0.03 if score < 0.5 else 0.0)
        if delta:
            db.x("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,?,?,0)",
                 (now(), "outcome", "angle", angle, delta, 0.3, ""))
    _, after = state.concept_states(db, gid)
    if cid in after and after[cid].learned_at and not before[cid].learned_at:
        card, due = engine.first_review(after[cid].learned_at)
        db.x("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?)", (cid, card, due, after[cid].learned_at))


def research_ahead(db: DB, jobs: Jobs) -> str | None:
    """Keep deep research about one module ahead of the learner (Settings → auto research).

    The current module is the first one (in roadmap order, skipping modules placement marked as
    known) that still has unlearned concepts or no research. The module after it is researched too.
    Returns the module id queued, if any.
    """
    if db.meta("auto_research", "1") != "1" or jobs.active("research_module") or jobs.active("outline"):
        return None
    gid = state.active_goal(db)
    if not gid:
        return None
    modules = db.q("""SELECT m.* FROM modules m JOIN tracks t ON t.id = m.track_id
                      WHERE t.goal_id = ? AND m.known = 0 ORDER BY t.ord, m.ord""", (gid,))
    if not modules:
        return None
    concepts, states = state.concept_states(db, gid)
    done = {"learned", "mastered"}
    unfinished = {c["module_id"] for c in concepts if states[c["id"]].state not in done}
    current = next((i for i, m in enumerate(modules) if m["research"] != "ready" or m["id"] in unfinished), None)
    if current is None:
        return None
    for m in modules[current:current + 2]:
        if m["research"] == "outline":
            db.x("UPDATE modules SET research='researching' WHERE id=?", (m["id"],))
            jobs.enqueue("research_module", f"Research {m['title']} (ahead of you)", {"module_id": m["id"]})
            return m["id"]
    return None
