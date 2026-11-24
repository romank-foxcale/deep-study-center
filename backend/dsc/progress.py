"""Shared write helpers used by both actions and jobs: recording evidence, and keeping research one
module ahead of the learner."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from . import engine, mcq, state
from .db import DB, now

if TYPE_CHECKING:
    from .jobs import Jobs




def reasoning(a: dict) -> tuple[str, float | None]:
    """The learner's thinking and confidence sent with an answer (both optional)."""
    thinking = " ".join(str(a.get("thinking") or "").split())[:4000]
    c = a.get("confidence")
    try:
        conf = None if c is None else min(1.0, max(0.0, float(c)))
    except (TypeError, ValueError):
        conf = None
    return thinking, conf


def guessed(correct: bool, confidence: float | None, n_options: int = 4) -> bool:
    """A right answer the learner did not trust: confidence at or below chance (1/n) or at or below 30%."""
    return correct and confidence is not None and confidence <= mcq.guess_line(n_options) + 1e-9


def record_evidence(db: DB, cid: str, item_id: str, score: float, *, choice: int | None = None,
                    angle: str | None = None, thinking: str = "", confidence: float | None = None,
                    correct: bool | None = None) -> bool:
    """Append graded practice evidence.
    Returns True when this answer made the concept learned (the lesson is finished: see ``on_finished``)."""
    gid = state.active_goal(db)
    _, before = state.concept_states(db, gid)
    db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, angle, score, thinking, confidence)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
         (now(), cid, item_id, "practice", choice, int(score >= engine.PASS_SCORE if correct is None else correct), angle, score,
          thinking, confidence))
    db.x("UPDATE concepts SET started=1 WHERE id=?", (cid,))
    if angle:  # outcome signal: weak evidence about the angle used; never re-renders anything by itself
        delta = 0.03 if score >= engine.PASS_SCORE else (-0.03 if score < 0.5 else 0.0)
        if delta:
            db.x("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,?,?,0)",
                 (now(), "outcome", "angle", angle, delta, 0.3, ""))
    _, after = state.concept_states(db, gid)
    return bool(cid in after and after[cid].learned_at and not before[cid].learned_at)


def next_lesson(db: DB, cid: str) -> str | None:
    """The next lesson in roadmap order after ``cid`` that is not learned yet and has a lesson plan."""
    gid = state.active_goal(db)
    if not gid:
        return None
    concepts, states = state.concept_states(db, gid)
    ids = [c["id"] for c in concepts]
    if cid not in ids:
        return None
    for nxt in ids[ids.index(cid) + 1:]:
        card = state.latest_card(db, nxt)
        if card and card.get("sections") and states[nxt].state != "learned":
            return nxt
    return None


def on_finished(db: DB, jobs: Jobs, cid: str) -> None:
    """A lesson is finished ("I've read it" or the mastery gate): distill the feedback so far into lesson
    guidelines, then write the next lesson with them (SPEC §12). Without a model the next lesson is still written."""
    nxt = next_lesson(db, cid)
    if jobs.active("distill_guidelines"):
        if nxt:
            prewrite(db, jobs, nxt)
        return
    jobs.enqueue("distill_guidelines", "Learn from your feedback", {"concept_id": cid, "next": nxt})


def prewrite(db: DB, jobs: Jobs, cid: str) -> None:
    """Write a lesson ahead of time with the current playbook and guidelines (never rewrites a studied or
    shaped lesson)."""
    from . import lesson
    r = lesson.ensure_rendition(db, cid)
    if not r:
        return
    if state.is_stale(r, state.latest_card(db, cid), state.playbook(db)) and not lesson._studied(db, cid, r) \
            and not lesson._chosen(db, cid):
        lesson.refresh(db, jobs, cid)
    else:
        lesson.ensure_prose(db, jobs, cid)


_AHEAD = threading.RLock()  # several threads call research_ahead at once (actions, finished jobs, lesson opens)


def research_ahead(db: DB, jobs: Jobs) -> str | None:
    """See ``_research_ahead``; the check and the enqueue run as one step, so a module is never researched twice."""
    with _AHEAD:
        return _research_ahead(db, jobs)


def _research_ahead(db: DB, jobs: Jobs) -> str | None:
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
                      WHERE t.goal_id = ? AND m.known = 0 ORDER BY m.seq, t.ord, m.ord""", (gid,))
    if db.one("SELECT 1 FROM goals WHERE id=? AND kind='bookstudy'", (gid,)):
        modules = [m for m in modules if m["planned"] > 0]  # a book: only chapters the map has cut into lessons
    if not modules:
        return None
    concepts, states = state.concept_states(db, gid)
    done = {"learned"}
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
