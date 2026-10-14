"""Renditions: this learner's version of a lesson, built from a card + the playbook.

Rules (docs/SPEC.md §2.3):
- Opening a not-yet-studied lesson re-renders it if the playbook or card changed since.
- A studied lesson is never rewritten silently; the UI offers "Refresh for current me".
- Feedback while reading changes only the targeted section (a pin), never the whole page.
"""

from __future__ import annotations

from . import engine, progress, state, viz
from .db import DB, dumps
from .jobs import Jobs

DONE = ("learned", "mastered", "rusty")


def _studied(db: DB, cid: str, r: dict | None) -> bool:
    if r and r["studied"]:
        return True
    gid = state.active_goal(db)
    _, states = state.concept_states(db, gid)
    return cid in states and states[cid].state in DONE


def ensure_rendition(db: DB, cid: str) -> dict | None:
    card = state.latest_card(db, cid)
    if not card or not card.get("sections"):
        return None
    r = state.rendition_row(db, cid)
    if not r:
        pb = state.playbook(db)
        angles = engine.choose_angles(card["sections"], pb, {})
        db.x("INSERT INTO renditions VALUES(?,?,?,?,?,?,0)",
             (cid, card["version"], pb["version"], engine.style_key(pb["adjust"]), dumps(angles), "{}"))
        r = state.rendition_row(db, cid)
    return r


def refresh(db: DB, jobs: Jobs, cid: str) -> None:
    card, pb, r = state.latest_card(db, cid), state.playbook(db), state.rendition_row(db, cid)
    if not card or not r:
        return
    angles = engine.choose_angles(card["sections"], pb, r["pinned"])
    db.x("UPDATE renditions SET card_version=?, playbook_version=?, style=?, section_angles=? WHERE concept_id=?",
         (card["version"], pb["version"], engine.style_key(pb["adjust"]), dumps(angles), cid))
    ensure_prose(db, jobs, cid)


def open_lesson(db: DB, jobs: Jobs, cid: str) -> dict:
    r = ensure_rendition(db, cid)
    refreshed = False
    if r and state.is_stale(r, state.latest_card(db, cid), state.playbook(db)) and not _studied(db, cid, r):
        refresh(db, jobs, cid)
        refreshed = True
    elif r:
        ensure_prose(db, jobs, cid)
    db.x("UPDATE concepts SET started=1 WHERE id=?", (cid,))
    progress.research_ahead(db, jobs)
    return {**view(db, cid), "refreshed": refreshed}


def ensure_prose(db: DB, jobs: Jobs, cid: str) -> None:
    """Queue one render job for every section whose exact prose isn't cached yet."""
    r = state.rendition_row(db, cid)
    if not r:
        return
    missing = [{"id": sid, "angle": a} for sid, a in r["section_angles"].items()
               if not db.one("SELECT 1 FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                             (cid, r["card_version"], sid, a, r["style"]))]
    if missing and not jobs.active("render", concept_id=cid, style=r["style"]):
        jobs.enqueue("render", "Render lesson", {"concept_id": cid, "card_version": r["card_version"],
                                                 "style": r["style"], "sections": missing})


def view(db: DB, cid: str) -> dict:
    """Lesson as the page shows it. Missing prose falls back to the same angle in another style
    (marked approximate) while a render job runs."""
    card = state.latest_card(db, cid)
    r = state.rendition_row(db, cid)
    pb = state.playbook(db)
    rendering = any(j["status"] in ("queued", "running") and j["input"].get("concept_id") == cid and j["kind"] == "render"
                    for j in state.jobs(db))
    failed = next((j["error"] for j in state.jobs(db) if j["kind"] == "render" and j["status"] == "failed"
                   and j["input"].get("concept_id") == cid), None)
    sections = []
    for s in (card or {}).get("sections", []):
        angle = (r or {}).get("section_angles", {}).get(s["id"]) or (s.get("angles") or ["geometric"])[0]
        exact = r and db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                             (cid, r["card_version"], s["id"], angle, r["style"]))
        approx = None if exact else db.one(
            "SELECT body FROM prose WHERE concept_id=? AND section_id=? AND angle=? ORDER BY card_version DESC, created_at DESC LIMIT 1",
            (cid, s["id"], angle))
        sections.append({
            "id": s["id"], "heading": s["heading"], "angle": angle, "angles": s.get("angles") or [angle],
            "body": (exact or approx or {}).get("body"), "approximate": bool(approx and not exact),
            "pending": not exact and rendering,
            "check": state.strip_check(s["check"]) if s.get("check") else None, "code": s.get("code"),
            "explain": state.strip_explain(s["explain"]) if s.get("explain") else None,
            "viz": viz.validate(s.get("viz")),  # re-validated on every read: only safe widget specs reach the page
        })
    return {
        "conceptId": cid, "card": state.public_card(card) if card else None, "sections": sections,
        "rendering": rendering, "renderError": failed if not rendering else None,
        "rendition": r and {"cardVersion": r["card_version"], "playbookVersion": r["playbook_version"],
                            "studied": _studied(db, cid, r), "stale": state.is_stale(r, card, pb)},
    }
