"""Renditions: this learner's version of a lesson, built from a card + the playbook.

Rules (docs/SPEC.md §2.3):
- Opening a not-yet-studied lesson re-renders it if the playbook or card changed since.
- A studied lesson is never rewritten silently; the UI offers "Refresh for current me".
- Feedback while reading changes only the targeted section (a pin), never the whole page.
- The page shows the head lesson version (see ``versions``). A lesson the learner shaped (applied feedback
  or restored a version) is treated like a studied one: never rewritten silently.
"""

from __future__ import annotations

from . import engine, progress, remedial, state, versions, viz, writer
from .db import DB, dumps
from .jobs import Jobs

DONE = ("learned",)


def _studied(db: DB, cid: str, r: dict | None) -> bool:
    if r and r["studied"]:
        return True
    gid = state.active_goal(db)
    _, states = state.concept_states(db, gid)
    return cid in states and states[cid].state in DONE


def _chosen(db: DB, cid: str) -> bool:
    h = db.one("SELECT chosen FROM lesson_heads WHERE concept_id=?", (cid,))
    return bool(h and h["chosen"])


def ensure_rendition(db: DB, cid: str) -> dict | None:
    card = state.latest_card(db, cid)
    if not card or not card.get("sections"):
        return None
    r = state.rendition_row(db, cid)
    if not r:
        pb = state.playbook(db)
        angles = engine.choose_angles(card["sections"], pb, {})
        db.x("INSERT OR IGNORE INTO renditions VALUES(?,?,?,?,?,?,0)",  # two opens at once: the first one wins
             (cid, card["version"], pb["version"], engine.style_key(pb["adjust"]), dumps(angles), "{}"))
        r = state.rendition_row(db, cid)
    return r


def refresh(db: DB, jobs: Jobs, cid: str, by_learner: bool = False) -> None:
    card, pb, r = state.latest_card(db, cid), state.playbook(db), state.rendition_row(db, cid)
    if not card or not r:
        return
    if by_learner:  # "Refresh for current me": the learner hands the lesson back to the playbook
        db.x("UPDATE lesson_heads SET chosen=0 WHERE concept_id=?", (cid,))
    angles = engine.choose_angles(card["sections"], pb, r["pinned"])
    db.x("UPDATE renditions SET card_version=?, playbook_version=?, style=?, section_angles=? WHERE concept_id=?",
         (card["version"], pb["version"], engine.style_key(pb["adjust"]), dumps(angles), cid))
    # "Refresh for current me" writes the whole lesson again (in steps, if Settings say so), not only the missing sections
    ensure_prose(db, jobs, cid, rewrite=by_learner)


def open_lesson(db: DB, jobs: Jobs, cid: str, plan: bool = True, book: str | None = None) -> dict:
    from . import bookstudy
    bookstudy.ensure_written(db, jobs, cid, plan=plan)  # a book lesson opened for the first time: plan it, or write it
    r = ensure_rendition(db, cid)
    refreshed = False
    if r and state.is_stale(r, state.latest_card(db, cid), state.playbook(db)) and not _studied(db, cid, r) \
            and not _chosen(db, cid):
        refresh(db, jobs, cid)
        refreshed = True
    elif r:
        ensure_prose(db, jobs, cid)
    db.x("UPDATE concepts SET started=1 WHERE id=?", (cid,))
    from . import formulas
    if not any(j["status"] in ("queued", "running") and j["kind"] == "render" and j["input"].get("concept_id") == cid
               for j in state.jobs(db)):
        formulas.ensure(db, jobs, cid)  # hover notes for formulas written before notes existed
    progress.research_ahead(db, jobs)
    return {**view(db, cid, book), "refreshed": refreshed}


def ensure_prose(db: DB, jobs: Jobs, cid: str, rewrite: bool = False) -> None:
    """Queue one render job for every section whose exact prose isn't cached yet (``rewrite``: every section).
    A step lesson (SPEC §43) is written one step at a time instead."""
    from . import lesson_steps
    if lesson_steps.is_steps(state.latest_card(db, cid)):
        lesson_steps.ensure(db, jobs, cid)
        return
    r = state.rendition_row(db, cid)
    if not r:
        return
    h = versions.head(db, cid)
    missing = [{"id": sid, "angle": a} for sid, a in r["section_angles"].items()
               if rewrite or (versions.section_from_head(h, r, sid) is None
               and not db.one("SELECT 1 FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                              (cid, r["card_version"], sid, a, r["style"])))]
    if missing and not jobs.active("render", concept_id=cid, style=r["style"]):
        # the whole lesson, written in steps (plan, graphs and questions, prose, review) unless Settings say one call
        full = len(missing) == len(r["section_angles"]) and db.meta("lesson_writing", "steps") == "steps"
        jobs.enqueue("render", "Write lesson" if full else "Render lesson",
                     {"concept_id": cid, "card_version": r["card_version"], "style": r["style"], "sections": missing, "full": full,
                      "rewrite": rewrite})


def _viz_notes(s: dict) -> list[str]:
    """What the app had to fix or remove in this section's graph: notes stored when it was written, and what a
    check of the stored graph finds now (for graphs written before the checks existed)."""
    notes = list(s.get("vizNotes") or [])
    if s.get("viz"):
        notes += [p for p in viz.inspect(s["viz"])[1] if p not in notes]
    # A value without a colored part still gets its own slider row on the page: a note for the agent, not the learner.
    return [n for n in notes if "has no colored part" not in n]


# The writing steps a lesson page shows while a lesson is written, keyed by the role each step calls.
_STEPS = [("Formula", "Plan the formula lesson"), ("Research", "Plan the chapter's lessons from the book"), ("Lesson planner", "Plan the lesson for you"),
          ("Lesson assets", "Make graphs and questions"), ("Renditions", "Write the text"), ("Lesson review", "Review and fix")]


def writing(db: DB, cid: str) -> dict | None:
    """While this lesson is being written: the steps, the step it is on and the newest progress line (for the page's
    progress bar). None when nothing is written for it now."""
    mod = (db.one("SELECT module_id FROM concepts WHERE id=?", (cid,)) or {}).get("module_id")
    active = [j for j in state.jobs(db) if j["status"] in ("queued", "running")
              and ((j["kind"] in ("render", "apply_feedback", "formula_lesson") and j["input"].get("concept_id") == cid)
                   or (j["kind"] == "research_module" and mod and j["input"].get("module_id") == mod))]
    if not active:
        return None
    research = any(j["kind"] == "research_module" for j in active)
    formula = any(j["kind"] == "formula_lesson" for j in active)
    single = db.meta("lesson_writing", "steps") != "steps" or any(j["kind"] == "apply_feedback" for j in active)
    roles = (["Formula"] if formula else []) + (["Research"] if research else []) + (["Renditions"] if single else ["Lesson planner", "Lesson assets", "Renditions",
                                                                                   "Lesson review"])
    lines = [m for j in sorted(active, key=lambda j: j["id"]) for m in j["progress"]]
    at = 0
    said = {"writing the text": "Renditions", "planning the lesson": "Lesson planner", "writing ": "Research"}
    for m in lines:  # "<role>: asking …", or a step's own line, marks the step the job reached
        for i, r in enumerate(roles):
            if m.startswith(f"{r}:") or any(m.startswith(k) and v == r for k, v in said.items()):
                at = max(at, i)
    label = dict(_STEPS)
    return {"steps": [label[r] for r in roles], "at": at, "message": lines[-1] if lines else "waiting to start",
            "queued": all(j["status"] == "queued" for j in active)}


def view(db: DB, cid: str, book: str | None = None) -> dict:
    """Lesson as the page shows it: the head version's text where it fits the rendition, else cached prose.
    Missing prose falls back to the same angle in another style (marked approximate) while a render job runs.
    Complete new prose is snapshotted as the next lesson version first."""
    versions.sync(db, cid)
    card = state.latest_card(db, cid)
    r = state.rendition_row(db, cid)
    h = versions.head(db, cid)
    pb = state.playbook(db)
    rendering = any(j["status"] in ("queued", "running") and j["input"].get("concept_id") == cid and j["kind"] == "render"
                    for j in state.jobs(db))
    failed = next((j["error"] for j in state.jobs(db) if j["kind"] == "render" and j["status"] == "failed"
                   and j["input"].get("concept_id") == cid), None)
    sections = []
    for s in writer.effective_sections(db, cid, card):
        angle = (r or {}).get("section_angles", {}).get(s["id"]) or (s.get("angles") or ["geometric"])[0]
        kept = versions.section_from_head(h, r, s["id"]) if r else None
        exact = {"body": kept} if kept is not None else r and db.one(
            "SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
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
            "vizMine": s["vizMine"], "checkMine": s["checkMine"],
            "vizNotes": _viz_notes(s),
            "book": s.get("book"),  # book lessons: a close summary of what the book says here, and its pages
            # step lessons (SPEC §43): the prediction before the step (its key only once predicted) and the repair
            "predict": state.strip_check(s["predict"]) if s.get("predict") else None, "repair": s.get("repair"),
            "kind": s.get("kind"), "form": s.get("form"),
            "demo": _demo(s.get("demo")),  # a generated demo (SPEC §45)
        })
    p = writer.current_plan(db, cid, card["version"]) if card else None
    from . import bookstudy, formula_lessons, formulas
    book = bookstudy.lesson_book(db, cid, book)
    mod = db.one("SELECT module_id FROM concepts WHERE id=?", (cid,)) if book else None
    writing_cards = bool(mod) and any(j["status"] in ("queued", "running") and j["kind"] == "research_module"
                                and j["input"].get("module_id") == mod["module_id"] for j in state.jobs(db))
    return {
        "book": book, "writingCards": writing_cards, "writing": writing(db, cid),
        "lessonPlan": _plan_brief(db, cid) if book else None,
        "steps": _steps(db, cid, card),
        "formulas": formulas.notes(db, cid),
        "formulaLesson": formula_lessons.info(db, cid),
        "blockVersions": bookstudy.versions_of(db, cid),
        "sources": _sources(db, cid),  # every source of this idea (SPEC §49)
        "formulasPending": any(j["status"] in ("queued", "running") and j["kind"] == "formula_notes"
                               and j["input"].get("concept_id") == cid for j in state.jobs(db)),
        "conceptId": cid, "card": state.public_card(card) if card else None, "sections": sections,
        "rendering": rendering, "renderError": failed if not rendering else None,
        "rendition": r and {"cardVersion": r["card_version"], "playbookVersion": r["playbook_version"],
                            "studied": _studied(db, cid, r), "stale": state.is_stale(r, card, pb),
                            "shaped": bool(h and h["chosen"])},
        "head": h["version"] if h else None,
        "plan": p and {"summary": p["plan"].get("summary", ""),
                       "briefs": {x["id"]: x["brief"] for x in p["plan"].get("sections", []) if x.get("brief")},
                       "review": p["review"] or None},
        "remedial": remedial.offer(db, cid),
        "extraLessons": [{"id": x["id"], "title": x["title"]} for x in remedial.extra_lessons(db, cid)],
        "versions": [versions.summary(v) for v in versions.all_versions(db, cid)][::-1],
        "applying": any(j["status"] in ("queued", "running") and j["kind"] == "apply_feedback"
                        and j["input"].get("concept_id") == cid for j in state.jobs(db)),
    }


def _plan_brief(db: DB, cid: str) -> dict | None:
    """The lesson's plan graph, in short (SPEC §42): its newest version and status."""
    from . import lesson_graph
    p = lesson_graph.latest(db, cid)
    return {"version": p["version"], "status": p["status"]} if p else None


def _steps(db: DB, cid: str, card: dict | None) -> dict | None:
    """A step lesson's progress (SPEC §43), or None for any other lesson."""
    from . import lesson_steps
    return lesson_steps.view(db, cid, card) if lesson_steps.is_steps(card) else None


def _demo(d: dict | None) -> dict | None:
    from . import demos
    return demos.public(d)


def _sources(db: DB, cid: str) -> list[dict]:
    from . import cells
    return [{k: x[k] for k in ("bookId", "sourceId", "title", "kind", "url", "chapter", "chapterTitle", "part", "pages")}
            for x in cells.sources(db, cid)]
