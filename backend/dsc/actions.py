"""Write side: every UI action. Each one appends to the logs (or edits user-owned records like
notes and settings); the UI then re-reads the snapshot."""

from __future__ import annotations

import re

from . import bookstudy, dictation, engine, guidelines, lesson, practice, probe, progress, reasoning, remedial, session, sources, state, versions, writer
from . import feedback as fb
from .db import DB, dumps, loads, now
from .jobs import Jobs
from .seed import delete_goal as _delete_goal, seed_demo


class ActionError(ValueError):
    pass


TAG_LABELS = fb.TAG_LABELS


def _signal(db: DB, kind: str, dimension: str, value: str, delta: float = 0, evidence: float = 0,
            note: str = "", bumps: bool = True) -> None:
    fb._signal(db, kind, dimension, value, delta, evidence, note, bumps)


def _entry(pb: dict, dimension: str, value: str) -> dict | None:
    return next((e for e in pb["entries"] if e["dimension"] == dimension and e["value"] == value), None)


def _card_item(db: DB, cid: str, item_id: str) -> dict | None:
    """An item of the lesson: from the card, or a quiz question made for this learner (``writer``). An item of the
    card that the learner's lesson replaced can still be answered (e.g. in reviews)."""
    card = state.latest_card(db, cid) or {}
    for s in writer.effective_sections(db, cid, card) + card.get("sections", []):
        for kind in ("check", "code", "explain"):
            if s.get(kind, {}).get("id") == item_id:
                return {"kind": kind, **s[kind]}
    return None


# ---------------------------------------------------------------- answers

def _steps_on(db: DB, jobs: Jobs, cid: str) -> None:
    """After an answer in a step lesson (SPEC §43): write the next steps."""
    from . import lesson_steps
    if lesson_steps.is_steps(state.latest_card(db, cid)):
        lesson_steps.ensure(db, jobs, cid)


def answer(db: DB, jobs: Jobs, a: dict) -> None:
    cid, item_id = a["conceptId"], a["checkId"]
    item = _card_item(db, cid, item_id)
    if not item:
        raise ActionError(f"unknown item {item_id}")
    if item["kind"] == "explain":
        raise ActionError("explain-back answers go through the 'explain' action")
    # Checks are graded here against the hidden key; code exercises run in the browser (Pyodide).
    correct = (a.get("choice") == item["answer"]) if item["kind"] == "check" else bool(a.get("correct"))
    thinking, conf = progress.reasoning(a)
    # A right answer you marked as a guess is half evidence: it moves P(learned) but does not count as known.
    score = 0.5 if progress.guessed(correct, conf, len(item.get("options") or []) or 4) else (1.0 if correct else 0.0)
    finished = progress.record_evidence(db, cid, item_id, score, choice=a.get("choice"), angle=a.get("angle"),
                                        thinking=thinking, confidence=conf, correct=correct)
    eid = db.one("SELECT MAX(id) AS id FROM evidence WHERE concept_id=? AND item_id=?", (cid, item_id))["id"]
    reasoning.queue(db, jobs, cid, {**item, "id": item_id}, eid, thinking)  # the tutor reads how you thought (SPEC §32)
    if finished:
        progress.on_finished(db, jobs, cid)
    _steps_on(db, jobs, cid)
    progress.research_ahead(db, jobs)


def _formula(fn):
    def run(db: DB, jobs: Jobs, a: dict) -> None:
        from .formula_lessons import FormulaError
        try:
            fn(db, jobs, a)
        except FormulaError as e:
            raise ActionError(str(e)) from e
    return run


@_formula
def make_formula_lesson(db: DB, jobs: Jobs, a: dict) -> None:
    from . import formula_lessons
    formula_lessons.make(db, jobs, str(a["conceptId"]), str(a["key"]))


@_formula
def add_formula_form(db: DB, jobs: Jobs, a: dict) -> None:
    from . import formula_lessons
    formula_lessons.add_form(db, jobs, str(a["conceptId"]), str(a["key"]), str(a["formulaId"]))


@_formula
def learn_blocks_first(db: DB, jobs: Jobs, a: dict) -> None:
    from . import formula_lessons
    formula_lessons.learn_first(db, jobs, str(a["formulaId"]))


@_formula
def prefer_formula_form(db: DB, jobs: Jobs, a: dict) -> None:
    from . import formula_lessons
    formula_lessons.prefer(db, jobs, str(a["formulaId"]), str(a["key"]))


def review_reasoning(db: DB, jobs: Jobs, a: dict) -> None:
    """Let the tutor read the thinking of an earlier answer (one given before reviews existed, or one whose review failed)."""
    cid, item_id = a["conceptId"], a["itemId"]
    item = _card_item(db, cid, item_id)
    ev = db.one("""SELECT * FROM evidence WHERE concept_id=? AND item_id=? AND voided=0 AND kind='practice'
                   ORDER BY id DESC LIMIT 1""", (cid, item_id))
    if not item or not ev:
        raise ActionError("no answer to read")
    if not reasoning.queue(db, jobs, cid, {**item, "id": item_id}, ev["id"], ev["thinking"] or ""):
        raise ActionError("this answer has no thinking to read")


def explain(db: DB, jobs: Jobs, a: dict) -> None:
    """Explain-back: the learner's own words, graded against a rubric by an independent grader job."""
    cid, item_id, text = a["conceptId"], a["itemId"], (a.get("answer") or "").strip()
    item = _card_item(db, cid, item_id)
    if not item or item["kind"] != "explain":
        raise ActionError(f"unknown explain-back item {item_id}")
    drawing = _save_drawing(a.get("drawing"))
    if len(text) < 15 and not (drawing and len(text) >= 1):
        raise ActionError("write a few sentences in your own words first" if not drawing else "add a line about your drawing")
    _, conf = progress.reasoning(a)
    gid = db.x("INSERT INTO gradings(ts, concept_id, item_id, answer, status, confidence, drawing) VALUES(?,?,?,?,?,?,?)",
               (now(), cid, item_id, text[:4000], "pending", conf, drawing))
    jobs.enqueue("grade", "Grade explanation", {"grading_id": gid, "concept_id": cid, "angle": a.get("angle")})
    _steps_on(db, jobs, cid)


def _save_drawing(data: object) -> str | None:
    """A drawing board image (a PNG data URL) saved under workspace/drawings; returns the file name."""
    if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
        return None
    import base64
    import secrets
    from .db import workspace
    raw = base64.b64decode(data.split(",", 1)[1], validate=True)
    if len(raw) > 4_000_000 or not raw.startswith(b"\x89PNG"):
        raise ActionError("the drawing is too big or not a PNG")
    folder = workspace() / "drawings"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}.png"
    (folder / name).write_bytes(raw)
    return name


# ---------------------------------------------------------------- feedback

def feedback(db: DB, jobs: Jobs, a: dict) -> None:
    """New feedback. Its kind (lesson | me | fact) is the learner's choice, or a first guess an agent refines.
    Only "me" feedback adds playbook signals; any kind can then be applied to the lesson (SPEC §11)."""
    cid, sid, angle = a["conceptId"], a.get("sectionId"), a.get("angle")
    tags, text = a.get("tags", []), (a.get("text") or "").strip()
    worked = [" ".join(str(w).split())[:60] for w in (a.get("worked") or []) if str(w).strip()][:6] if "loved-it" in tags else []
    if worked:  # "This worked really well" + what exactly worked
        text = (text + "\n" if text else "") + "What worked: " + ", ".join(w[0].lower() + w[1:] for w in worked) + "."
    if not tags and not text:
        raise ActionError("pick a tag or write something")
    ref = _clean_ref(a.get("ref"))
    if ref and not sid:
        sid = ref.get("sectionId")
    chosen = a.get("kind") in fb.KINDS
    kind = a["kind"] if chosen else fb.propose_kind(tags, text)
    pb0 = state.playbook(db)
    signal_ids, effects = fb.add_signals(db, tags, text, angle, kind)
    done_note = None
    if "confused" in tags:
        jobs.enqueue("roadmap_review", "Review roadmap after feedback", {"concept_id": cid, "tags": [TAG_LABELS[t] for t in tags], "text": text})
        effects.append("Roadmap: reviewing whether something is missing; a proposed change will appear on the roadmap")

    # A framing that missed here is replaced here at once, whatever the global ranking says.
    r = state.rendition_row(db, cid)
    if "framing-off" in tags and sid and angle and r:
        avail = a.get("available") or []
        ranking = engine.angle_ranking(state.playbook(db))
        nxt = next((x for x in ranking if x != angle and x in avail), None)
        if nxt:
            _pin(db, cid, sid, nxt)
            lesson.ensure_prose(db, jobs, cid)
            done_note = f"This section switched to the {nxt} angle right away"
            effects.insert(0, f"This section now uses the {nxt} angle. Other lessons switch too if the pattern repeats.")

    pb1 = state.playbook(db)
    if pb1["version"] != pb0["version"]:
        n = sum(1 for x in db.q("SELECT playbook_version FROM renditions") if x["playbook_version"] < pb1["version"])
        effects.append(f"Playbook v{pb1['version']}: {n} lesson{'s' if n != 1 else ''} will be re-rendered for you "
                       "(past ones offer a refresh)")
    if worked and kind == "me":
        effects.append(_keep_doing(db, cid, worked))
    effects.append(fb.kind_effect(kind))
    fid = db.x("""INSERT INTO feedback(ts, concept_id, section_id, tags, text, effects, kind, kind_source, signal_ids, angle, done_note, ref)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (now(), cid, sid, dumps([TAG_LABELS.get(t, t) for t in tags]), text, dumps(effects), kind,
                "learner" if chosen else "auto", dumps(signal_ids), angle, done_note, dumps(ref) if ref else None))
    if text and not chosen and not a.get("apply"):
        jobs.enqueue("classify_feedback", "Sort feedback", {"feedback_id": fid, "concept_id": cid})
    if a.get("apply"):  # "Add and apply": write the next lesson version from this item alone
        try:
            apply_feedback(db, jobs, {"conceptId": cid, "ids": [fid]})
        except ActionError as e:
            raise ActionError(f"Feedback added, but not applied: {e}. Apply it later from the Feedback log.") from e


def _keep_doing(db: DB, cid: str, worked: list[str]) -> str:
    """Praise meant for all future lessons becomes a lesson guideline at once (the learner's own line, so the
    guideline job keeps it)."""
    title = db.one("SELECT title FROM concepts WHERE id=?", (cid,))["title"]
    parts = ", ".join(w[0].lower() + w[1:] for w in worked)
    line = f"Keep {parts} like in the lesson “{title}”: they worked well for me."
    cur = guidelines.current(db) or {"items": []}
    items = [{"text": it["text"], "why": it.get("why", ""), "feedbackIds": it.get("feedbackIds", []), "byLearner": it.get("byLearner")}
             for it in cur["items"]]
    if len(items) >= guidelines.MAX_ITEMS:
        return "Lesson guidelines are full (10 points): the next guideline update takes this praise into account"
    v = guidelines.save(db, items + [{"text": line, "why": "You marked it as worked really well.", "byLearner": True}], "feedback",
                        f"Added from your feedback on {title}.")
    return f'Lesson guidelines v{v}: added "{line}"'


def _clean_ref(ref: object) -> dict | None:
    """The part of the lesson a piece of feedback is about: selected text, a formula (LaTeX) or a graph."""
    if not isinstance(ref, dict) or ref.get("kind") not in ("text", "formula", "viz"):
        return None
    quote = " ".join(str(ref.get("quote") or "").split())[:600]
    if ref["kind"] != "viz" and not quote:
        return None
    sid = ref.get("sectionId")
    return {"kind": ref["kind"], "quote": quote, "sectionId": sid if isinstance(sid, str) else None}


def edit_feedback(db: DB, jobs: Jobs, a: dict) -> None:
    """Change an item's tags, text or kind: its old signals are voided and new ones added (the playbook replays)."""
    kind = a.get("kind")
    if kind is not None and kind not in fb.KINDS:
        raise ActionError("kind must be lesson, me or fact")
    try:
        fb.resignal(db, int(a["id"]), tags=a.get("tags"), text=a.get("text"), kind=kind,
                    kind_source="learner" if kind else None)
    except ValueError as e:
        raise ActionError(str(e)) from e


def delete_feedback(db: DB, jobs: Jobs, a: dict) -> None:
    """Remove an item: its signals are voided (the playbook replays). Lesson versions that applied it stay."""
    try:
        fb.delete(db, int(a["id"]))
    except ValueError as e:
        raise ActionError(str(e)) from e


def apply_feedback(db: DB, jobs: Jobs, a: dict) -> None:
    """Apply selected feedback to one lesson: one agent job writes the next lesson version.
    Fact claims never touch the prose: they go to the card check (refresh proposal + fact-check)."""
    cid = a["conceptId"]
    ids = sorted({int(i) for i in a.get("ids") or []})
    if not ids:
        raise ActionError("select at least one piece of feedback")
    rows = db.q(f"SELECT * FROM feedback WHERE deleted=0 AND concept_id=? AND id IN ({','.join('?' * len(ids))})", [cid, *ids])
    if len(rows) != len(ids):
        raise ActionError("every selected item must be feedback on this lesson")
    if jobs.active("apply_feedback", concept_id=cid):
        raise ActionError("feedback is already being applied to this lesson; wait for it to finish")
    facts = [r for r in rows if r["kind"] == "fact"]
    prose = [r["id"] for r in rows if r["kind"] != "fact"]
    h = None
    if prose:
        lesson.ensure_rendition(db, cid)
        versions.sync(db, cid)
        h = versions.head(db, cid)
        if not versions.head_matches(h, state.rendition_row(db, cid)):
            raise ActionError("this lesson is still being written; apply when it is ready")
    if facts:
        route_facts(db, jobs, cid, facts)
    if prose:
        title = db.one("SELECT title FROM concepts WHERE id=?", (cid,))["title"]
        jobs.enqueue("apply_feedback", f"Apply feedback to {title}",
                     {"concept_id": cid, "feedback_ids": prose, "base_version": h["version"]})


def route_facts(db: DB, jobs: Jobs, cid: str, rows: list[dict]) -> None:
    """A learner's report that the material is wrong goes to the card check, never into their lesson."""
    claims = [r["text"] or ", ".join(loads(r["tags"], [])) for r in rows]
    db.x(f"UPDATE feedback SET routed_at=? WHERE id IN ({','.join('?' * len(rows))})", [now(), *[r["id"] for r in rows]])
    if not jobs.active("refresh_card", concept_id=cid):
        title = db.one("SELECT title FROM concepts WHERE id=?", (cid,))["title"]
        jobs.enqueue("refresh_card", f"Check {title} (your report)", {"concept_id": cid, "claims": claims})


def revert_lesson(db: DB, jobs: Jobs, a: dict) -> None:
    """Show another version of a lesson. Leaving applied feedback behind is a learning signal."""
    try:
        versions.restore(db, a["conceptId"], int(a["version"]))
    except ValueError as e:
        raise ActionError(str(e)) from e


def _pin(db: DB, cid: str, sid: str, angle: str) -> None:
    r = state.rendition_row(db, cid)
    db.x("UPDATE renditions SET section_angles=?, pinned=? WHERE concept_id=?",
         (dumps({**r["section_angles"], sid: angle}), dumps({**r["pinned"], sid: angle}), cid))


def explain_differently(db: DB, jobs: Jobs, a: dict) -> None:
    cid, sid = a["conceptId"], a["sectionId"]
    r = state.rendition_row(db, cid)
    card = state.latest_card(db, cid)
    from . import lesson_steps
    if lesson_steps.is_steps(card):  # a step lesson: write the step again, another way (SPEC §43)
        return rewrite_step(db, jobs, {**a, "note": a.get("note") or "Explain it another way: a different example or picture."})
    sec = next((s for s in card["sections"] if s["id"] == sid), None) if card else None
    if not r or not sec:
        raise ActionError("no such section")
    avail = sec.get("angles") or list(engine.ANGLES)
    order = [x for x in engine.angle_ranking(state.playbook(db)) if x in avail]
    cur = r["section_angles"].get(sid, order[0])
    nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
    _signal(db, "explain", "angle", cur, -0.04, 0.3, bumps=False)
    _pin(db, cid, sid, nxt)
    lesson.ensure_prose(db, jobs, cid)
    db.x("INSERT INTO feedback(ts, concept_id, section_id, tags, text, effects, kind, angle, done_note) VALUES(?,?,?,?,?,?,?,?,?)",
         (now(), cid, sid, dumps(["Explain it differently"]), "",
          dumps([f"Section switched: {cur} → {nxt}", f"Weak signal recorded: \"{cur}\" didn't land here"]),
          "lesson", cur, f"Section switched to the {nxt} angle right away"))


def refresh(db: DB, jobs: Jobs, a: dict) -> None:
    lesson.refresh(db, jobs, a["conceptId"], by_learner=True)


def mark_studied(db: DB, jobs: Jobs, a: dict) -> None:
    r = state.rendition_row(db, a["conceptId"])
    db.x("UPDATE renditions SET studied=1 WHERE concept_id=?", (a["conceptId"],))
    if r and not r["studied"]:
        progress.on_finished(db, jobs, a["conceptId"])


def add_remedial(db: DB, jobs: Jobs, a: dict) -> None:
    """Add the offered extra lesson ("Vectors (b)") after this one; it is researched and fact-checked."""
    if not remedial.offer(db, a["conceptId"]):
        raise ActionError("no extra lesson is offered for this lesson now")
    try:
        remedial.add(db, jobs, a["conceptId"])
    except ValueError as e:
        raise ActionError(str(e)) from e


def dismiss_remedial(db: DB, jobs: Jobs, a: dict) -> None:
    remedial.dismiss(db, a["conceptId"])


def edit_guidelines(db: DB, jobs: Jobs, a: dict) -> None:
    """The learner's own version of the lesson guidelines: every line they keep or write stays."""
    items = [{"text": t, "byLearner": True} for t in (a.get("lines") or []) if isinstance(t, str) and t.strip()]
    from .guidelines import MAX_ITEMS
    if len(items) > MAX_ITEMS:
        raise ActionError(f"at most {MAX_ITEMS} guidelines")
    guidelines.save(db, items, "learner", "Edited by you")


def distill_guidelines(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("distill_guidelines"):
        jobs.enqueue("distill_guidelines", "Learn from your feedback", {"concept_id": None, "next": None})


# ---------------------------------------------------------------- notes & chat

def add_note(db: DB, jobs: Jobs, a: dict) -> None:
    if not (a.get("text") or "").strip():
        raise ActionError("empty note")
    db.x("INSERT INTO notes(ts, concept_id, quote, text) VALUES(?,?,?,?)", (now(), a["conceptId"], a.get("quote"), a["text"]))


def delete_note(db: DB, jobs: Jobs, a: dict) -> None:
    db.x("DELETE FROM notes WHERE id=?", (a["id"],))


def chat(db: DB, jobs: Jobs, a: dict) -> None:
    text = (a.get("text") or "").strip()
    if not text:
        raise ActionError("empty message")
    db.x("INSERT INTO chats(ts, concept_id, role, text) VALUES(?,?,?,?)", (now(), a["conceptId"], "me", text))
    jobs.enqueue("tutor", "Tutor reply", {"concept_id": a["conceptId"], "section": a.get("sectionHeading")})


# ---------------------------------------------------------------- roadmap

def decide_diff(db: DB, jobs: Jobs, a: dict) -> None:
    d = db.one("SELECT * FROM diffs WHERE id=?", (a["id"],))
    if not d or d["status"] != "pending":
        raise ActionError("no pending change with that id")
    db.x("UPDATE diffs SET status=? WHERE id=?", ("approved" if a["approve"] else "rejected", d["id"]))
    if not a["approve"]:
        return
    from .db import loads
    for ch in loads(d["changes"]):
        if ch["op"] == "insert" and ch.get("anchor"):
            _insert_concept(db, jobs, ch)
        elif ch["op"] == "compress" and ch.get("module"):
            db.x("UPDATE modules SET known=1 WHERE id=?", (ch["module"],))
    progress.research_ahead(db, jobs)


def _insert_concept(db: DB, jobs: Jobs, ch: dict) -> None:
    """Insert the proposed concept next to its anchor and research its card in the background."""
    anchor = db.one("SELECT * FROM concepts WHERE id=?", (ch["anchor"],))
    if not anchor:
        return
    after = "(after" in ch["title"]
    title = re.sub(r"\s*\((before|after) [^)]*\)\s*$", "", ch["title"]).strip()
    cid = f'{anchor["module_id"]}-ins-{re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30]}'
    if db.one("SELECT 1 FROM concepts WHERE id=?", (cid,)):
        return
    pos = anchor["ord"] + (1 if after else 0)
    with db.tx():
        db.conn.execute("UPDATE concepts SET ord = ord + 1 WHERE module_id=? AND ord >= ?", (anchor["module_id"], pos))
        db.conn.execute("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                        (cid, anchor["module_id"], pos, title, ch["detail"], 10, dumps([]), 0.3))
    prev = db.one("SELECT research FROM modules WHERE id=?", (anchor["module_id"],))["research"]
    jobs.enqueue("research_module", f"Research {title}",
                 {"module_id": anchor["module_id"], "prev_research": prev,
                  "concept": {"id": cid, "title": title, "detail": ch["detail"]}})


def research_module(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("research_module", module_id=a["moduleId"]):
        db.x("UPDATE modules SET research='researching' WHERE id=?", (a["moduleId"],))
        m = db.one("SELECT title FROM modules WHERE id=?", (a["moduleId"],))
        jobs.enqueue("research_module", f"Research {m['title']}", {"module_id": a["moduleId"]})


def create_goal(db: DB, jobs: Jobs, a: dict) -> None:
    answers = [{"q": str(x.get("q", "")), "a": str(x.get("a", ""))} for x in (a.get("answers") or [])]
    layout = "list" if a.get("layout") == "list" else "ohtani"
    if not answers or not answers[0]["a"].strip():
        raise ActionError("the goal is required")
    known = {r["id"] for r in db.q("SELECT id FROM sources")}
    ids = [s for s in (a.get("sourceIds") or []) if s in known]
    jobs.enqueue("outline", "Build Ohtani table" if layout == "ohtani" else "Build roadmap",
                 {"answers": answers, "layout": layout, "source_ids": ids})


# ---------------------------------------------------------------- the learner's own sources (PDF)

def link_source(db: DB, jobs: Jobs, a: dict) -> None:
    gid = a.get("goalId") or state.active_goal(db)
    if not gid or not db.one("SELECT 1 FROM sources WHERE id=?", (a["sourceId"],)):
        raise ActionError("unknown source or goal")
    sources.link(db, gid, a["sourceId"], bool(a.get("on", True)))


def edit_source(db: DB, jobs: Jobs, a: dict) -> None:
    row = db.one("SELECT * FROM sources WHERE id=?", (a["id"],))
    if not row:
        raise ActionError("unknown source")
    title = " ".join(str(a.get("title") or row["title"]).split())[:200] or row["title"]
    kind = a.get("kind") if a.get("kind") in sources.KINDS else row["kind"]
    db.x("UPDATE sources SET title=?, kind=? WHERE id=?", (title, kind, a["id"]))


def reread_source(db: DB, jobs: Jobs, a: dict) -> None:
    """Read a source again (after a failed read)."""
    row = db.one("SELECT * FROM sources WHERE id=?", (a["id"],))
    if row and row["url"] and not sources.file_path(a["id"]).exists():  # a link: read its page or captions again (SPEC §47)
        if not jobs.active("read_link", source_id=a["id"]):
            db.x("UPDATE sources SET status='reading' WHERE id=?", (a["id"],))
            jobs.enqueue("read_link", "Read a link", {"source_id": a["id"]})
        return
    if not row or not sources.file_path(a["id"]).exists():
        raise ActionError("unknown source")
    db.x("UPDATE sources SET status='reading' WHERE id=?", (a["id"],))
    jobs.enqueue("ingest_source", f"Read {row['filename'] or row['title']}", {"source_id": a["id"]})


def delete_source(db: DB, jobs: Jobs, a: dict) -> None:
    if not db.one("SELECT 1 FROM sources WHERE id=?", (a["id"],)):
        raise ActionError("unknown source")
    sources.delete(db, a["id"])


def set_goal(db: DB, jobs: Jobs, a: dict) -> None:
    if not db.one("SELECT 1 FROM goals WHERE id=?", (a["id"],)):
        raise ActionError("unknown goal")
    db.set_meta("active_goal", a["id"])


# ---------------------------------------------------------------- study sessions ("teach me X")

def _session(fn):
    def run(db: DB, jobs: Jobs, a: dict) -> None:
        try:
            fn(db, jobs, a)
        except ValueError as e:
            raise ActionError(str(e)) from e
    return run


@_session
def start_session(db: DB, jobs: Jobs, a: dict) -> None:
    sid = session.start(db, jobs, str(a.get("topic") or ""), list(a.get("sourceIds") or []))
    db.set_meta("last_session", sid)


@_session
def session_learn_again(db: DB, jobs: Jobs, a: dict) -> None:
    session.learn_all_again(db, a["sessionId"])


@_session
def session_answer(db: DB, jobs: Jobs, a: dict) -> None:
    thinking, conf = progress.reasoning(a)
    session.answer(db, jobs, a["sessionId"], int(a["itemId"]), a.get("choice"), thinking, conf)


@_session
def session_known(db: DB, jobs: Jobs, a: dict) -> None:
    session.set_known(db, a["sessionId"], a["ideaKey"], bool(a.get("known", True)))


@_session
def session_teach(db: DB, jobs: Jobs, a: dict) -> None:
    session.start_teaching(db, jobs, a["sessionId"])


@_session
def session_assess_now(db: DB, jobs: Jobs, a: dict) -> None:
    session.assess_now(db, jobs, a["sessionId"])


@_session
def session_retry(db: DB, jobs: Jobs, a: dict) -> None:
    session.retry(db, jobs, a["sessionId"])


@_session
def delete_session(db: DB, jobs: Jobs, a: dict) -> None:
    session.delete(db, a["sessionId"])


# ---------------------------------------------------------------- book study (SPEC §28)

def _book(fn):
    def run(db: DB, jobs: Jobs, a: dict) -> None:
        try:
            fn(db, jobs, a)
        except (bookstudy.BookError, ValueError) as e:
            raise ActionError(str(e)) from e
    return run


@_book
def study_book(db: DB, jobs: Jobs, a: dict) -> None:
    sid = str(a["sourceId"])
    src = db.one("SELECT url, status, pages FROM sources WHERE id=?", (sid,))
    if src and src["url"] and not (src["status"] == "ready" and src["pages"]):  # a link not read yet: read it, then teach it
        if src["status"] == "no_text":
            raise ActionError("No text was found on this link, so there is nothing to teach from.")
        if not jobs.active("read_link", source_id=sid, teach=True):
            db.x("UPDATE sources SET status='reading' WHERE id=?", (sid,))
            jobs.enqueue("read_link", "Read a link and teach it", {"source_id": sid, "teach": True})
        return
    db.set_meta("last_book", bookstudy.start(db, jobs, sid))


def _plan(fn):
    """Lesson plan actions (SPEC §42): a PlanError is a 400 for the learner."""
    def wrapped(db: DB, jobs: Jobs, a: dict) -> None:
        from . import lesson_graph
        try:
            fn(db, jobs, a)
        except lesson_graph.PlanError as e:
            raise ActionError(str(e)) from e
    return wrapped


def _step(fn):
    """Step lesson actions (SPEC §43): a StepError is a 400 for the learner."""
    def wrapped(db: DB, jobs: Jobs, a: dict) -> None:
        from . import lesson_steps
        try:
            fn(db, jobs, a)
        except lesson_steps.StepError as e:
            raise ActionError(str(e)) from e
    return wrapped


@_step
def predict_step(db: DB, jobs: Jobs, a: dict) -> None:
    from . import lesson_steps
    thinking, _ = progress.reasoning(a)
    lesson_steps.predict(db, str(a.get("conceptId") or ""), str(a.get("sectionId") or ""), a.get("choice"), thinking)


@_step
def demo_result(db: DB, jobs: Jobs, a: dict) -> None:
    """The page ran a generated demo hidden and operated it (SPEC §45): it passed, or these errors came up."""
    from . import demos
    try:
        demos.result(db, jobs, str(a.get("conceptId") or ""), str(a.get("sectionId") or ""), int(a.get("version") or 0),
                     bool(a.get("ok")), [str(e) for e in a.get("errors") or []])
    except demos.DemoError as e:
        raise ActionError(str(e)) from e


@_step
def rewrite_step(db: DB, jobs: Jobs, a: dict) -> None:
    from . import lesson_steps
    lesson_steps.rewrite(db, jobs, str(a.get("conceptId") or ""), str(a.get("sectionId") or ""), str(a.get("note") or ""))


@_plan
def plan_lesson(db: DB, jobs: Jobs, a: dict) -> None:
    """Make the next version of a lesson's plan (the first one, or a re-plan with the learner's notes)."""
    from . import lesson_graph
    lesson_graph.start(db, jobs, str(a.get("conceptId") or ""))


@_plan
def lesson_plan_note(db: DB, jobs: Jobs, a: dict) -> None:
    from . import lesson_graph
    lesson_graph.note(db, jobs, str(a.get("conceptId") or ""), str(a.get("kind") or ""), str(a.get("text") or ""),
                      str(a.get("node") or ""))


@_plan
def approve_lesson_plan(db: DB, jobs: Jobs, a: dict) -> None:
    from . import lesson_graph
    lesson_graph.approve(db, jobs, str(a.get("conceptId") or ""))


@_book
def book_retry(db: DB, jobs: Jobs, a: dict) -> None:
    bookstudy.retry(db, jobs, str(a["bookId"]))


@_book
def book_open_lesson(db: DB, jobs: Jobs, a: dict) -> None:
    """Open a book lesson: its book's hidden goal becomes the active goal, so the lesson page works as for any lesson."""
    bookstudy.open_lesson(db, jobs, str(a["conceptId"]))


@_book
def book_remap_chapter(db: DB, jobs: Jobs, a: dict) -> None:
    bookstudy.remap_chapter(db, jobs, str(a["bookId"]), int(a["chapter"]), bool(a.get("asLessons")))


def open_formula(db: DB, jobs: Jobs, a: dict) -> None:
    """The derivation graph: find what this formula is built from, one level down (SPEC §40)."""
    node = str(a.get("node") or "")
    if not node or not (node.startswith("block:") or db.one("SELECT 1 FROM formula_lessons WHERE id=?", (node,))):
        raise ActionError("unknown formula")
    if not jobs.active("formula_open", node=node):
        jobs.enqueue("formula_open", "Find what a formula is built from", {"node": node})


def make_formula_flow(db: DB, jobs: Jobs, a: dict) -> None:
    """Build (or build again) the formula flow of a formula page (SPEC §52)."""
    from . import formula_flow
    cid = str(a.get("conceptId") or "")
    if not db.one("SELECT 1 FROM formula_lessons WHERE id=? AND COALESCE(kind, 'formula')='formula'", (cid,)):
        raise ActionError("only a formula page has a formula flow")
    formula_flow.request(db, jobs, cid)


def make_formula_page(db: DB, jobs: Jobs, a: dict) -> None:
    from . import formula_lessons
    try:
        formula_lessons.make_page(db, jobs, str(a.get("node") or ""))
    except formula_lessons.FormulaError as e:
        raise ActionError(str(e)) from e


@_book
def book_replan(db: DB, jobs: Jobs, a: dict) -> None:
    bookstudy.replan(db, jobs, str(a["bookId"]))


@_book
def book_homework(db: DB, jobs: Jobs, a: dict) -> None:
    db.set_meta("last_practice", bookstudy.homework(db, jobs, str(a["bookId"]), int(a["chapter"])))


@_book
def delete_book(db: DB, jobs: Jobs, a: dict) -> None:
    bookstudy.delete(db, str(a["bookId"]))


MAP_VIEWS = ("hex", "tree")  # SPEC §50: the hex map of ideas; the country views were removed


def _goal(fn):
    """Goals on the map (SPEC §53): a GoalError is a 400 for the learner."""
    def wrapped(db: DB, jobs: Jobs, a: dict) -> None:
        from . import map_goals
        try:
            fn(db, jobs, a)
        except map_goals.GoalError as e:
            raise ActionError(str(e)) from e
    return wrapped


@_goal
def add_map_goal(db: DB, jobs: Jobs, a: dict) -> None:
    from . import map_goals
    db.set_meta("last_map_goal", map_goals.add(db, jobs, str(a.get("title") or "")))


@_goal
def rename_map_goal(db: DB, jobs: Jobs, a: dict) -> None:
    from . import map_goals
    map_goals.rename(db, jobs, str(a["goalId"]), str(a.get("title") or ""))


@_goal
def remove_map_goal(db: DB, jobs: Jobs, a: dict) -> None:
    from . import map_goals
    map_goals.remove(db, str(a["goalId"]))


@_goal
def add_goal_block(db: DB, jobs: Jobs, a: dict) -> None:
    from . import map_goals
    db.set_meta("last_gap_idea", map_goals.add_block(db, str(a["goalId"]), int(a["blockId"])))


def _gap(fn):
    """Gap actions (SPEC §51): a GapError is a 400 for the learner."""
    def wrapped(db: DB, jobs: Jobs, a: dict) -> None:
        from . import gaps
        try:
            fn(db, jobs, a)
        except gaps.GapError as e:
            raise ActionError(str(e)) from e
    return wrapped


@_gap
def find_gaps(db: DB, jobs: Jobs, a: dict) -> None:
    from . import gaps
    gaps.find(db, jobs, str(a.get("gapId") or ""))  # with a gap: "find more" for it


@_gap
def accept_gap(db: DB, jobs: Jobs, a: dict) -> None:
    from . import gaps
    db.set_meta("last_gap_idea", gaps.accept(db, str(a["gapId"]), int(a.get("index") or 0)))


@_gap
def dismiss_gap(db: DB, jobs: Jobs, a: dict) -> None:
    from . import gaps
    gaps.dismiss(db, str(a["gapId"]))


def set_map_view(db: DB, jobs: Jobs, a: dict) -> None:
    """The learner's choice of knowledge-map view (SPEC §29), kept in the workspace."""
    if a.get("view") not in MAP_VIEWS:
        raise ActionError(f"unknown map view {a.get('view')!r}")
    db.set_meta("map_view", a["view"])


# ---------------------------------------------------------------- local dictation (SPEC §27)

def _dictation(fn):
    def wrapped(db: DB, jobs: Jobs, a: dict) -> None:
        try:
            fn(db, jobs, a)
        except dictation.DictationError as e:
            raise ActionError(str(e)) from e
    return wrapped


@_dictation
def set_dictation(db: DB, jobs: Jobs, a: dict) -> None:
    dictation.set_settings(db, a.get("mode"), a.get("model"))


@_dictation
def download_dictation_model(db: DB, jobs: Jobs, a: dict) -> None:
    dictation.start_download(db, jobs, a["model"])


@_dictation
def remove_dictation_model(db: DB, jobs: Jobs, a: dict) -> None:
    dictation.remove(a["model"])


# ---------------------------------------------------------------- recall practice

@_session
def start_practice(db: DB, jobs: Jobs, a: dict) -> None:
    pid = practice.start(db, jobs, list(a.get("nodeIds") or []), str(a.get("own") or ""), a.get("source"),
                         focus=a.get("focus") if isinstance(a.get("focus"), dict) else None,
                         formulas=[str(k) for k in a.get("formulas") or []], count=a.get("count"),
                         surface=str(a.get("surface") or "mixed"), title=str(a.get("title") or ""))
    db.set_meta("last_practice", pid)


@_session
def practice_submit(db: DB, jobs: Jobs, a: dict) -> None:
    practice.submit(db, jobs, int(a["itemId"]), str(a.get("text") or ""), bool(a.get("hint")))


@_session
def practice_give_up(db: DB, jobs: Jobs, a: dict) -> None:
    practice.give_up(db, jobs, int(a["itemId"]))


@_session
def practice_retry(db: DB, jobs: Jobs, a: dict) -> None:
    practice.retry(db, jobs, a["practiceId"])


def practice_next(db: DB, jobs: Jobs, a: dict) -> None:
    """"Next problem" (SPEC §44): show the problem written while the learner read the last one."""
    try:
        practice.advance(db, str(a.get("practiceId") or ""))
    except ValueError as e:
        raise ActionError(str(e)) from e


@_session
def practice_stop(db: DB, jobs: Jobs, a: dict) -> None:
    practice.stop(db, a["practiceId"])


# ---------------------------------------------------------------- the probe (where you stand)

def start_probe(db: DB, jobs: Jobs, a: dict) -> None:
    probe.start(db, jobs, state.active_goal(db))


def probe_answer(db: DB, jobs: Jobs, a: dict) -> None:
    """One probe answer; choice None means "I don't know" (never counted as a guess)."""
    thinking, conf = progress.reasoning(a)
    try:
        probe.answer(db, jobs, state.active_goal(db), int(a["itemId"]), a.get("choice"), thinking, conf)
    except ValueError as e:
        raise ActionError(str(e)) from e


def probe_assess_now(db: DB, jobs: Jobs, a: dict) -> None:
    probe.assess_now(db, jobs, state.active_goal(db))


def apply_probe(db: DB, jobs: Jobs, a: dict) -> None:
    """Use the assessment: known steps become a roadmap proposal; the edge goes into the goal profile."""
    probe.apply(db, state.active_goal(db))


def reset_probe(db: DB, jobs: Jobs, a: dict) -> None:
    """Retake: clear this goal's probe (steps already marked known stay known) and start again."""
    gid = state.active_goal(db)
    probe.reset(db, gid)
    db.set_meta(f"probe_dismissed:{gid}", "0")
    probe.start(db, jobs, gid)


def dismiss_probe(db: DB, jobs: Jobs, a: dict) -> None:
    db.set_meta(f"probe_dismissed:{state.active_goal(db)}", "1")


# ---------------------------------------------------------------- reflection

def reflect(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("reflect"):
        jobs.enqueue("reflect", "Weekly reflection", {})


def decide_proposal(db: DB, jobs: Jobs, a: dict) -> None:
    """Accept or reject one reflection proposal; accepting writes it to the playbook as a signal."""
    from .db import loads
    r = db.one("SELECT * FROM reflections WHERE id=?", (a["reflectionId"],))
    proposals = loads(r["proposals"], []) if r else []
    i = a["index"]
    if not r or not 0 <= i < len(proposals) or proposals[i]["status"] != "pending":
        raise ActionError("no pending proposal there")
    p = proposals[i]
    if a["accept"]:
        if p["dimension"] in engine.ADJUST_KEYS:
            _signal(db, "adjust", p["dimension"], p["dimension"], max(-1, min(1, int(p.get("delta") or 0))))
        else:
            _signal(db, "stated", p["dimension"], p["value"], 0, 0.5, note=f'From reflection: {p["why"]}')
            _signal(db, "correction", p["dimension"], p["value"], note=p["verdict"])
    proposals[i] = {**p, "status": "accepted" if a["accept"] else "rejected"}
    db.x("UPDATE reflections SET proposals=? WHERE id=?", (dumps(proposals), r["id"]))


# ---------------------------------------------------------------- playbook & settings

def correct_entry(db: DB, jobs: Jobs, a: dict) -> None:
    dimension, _, value = a["id"].partition(":")
    if a["verdict"] == "remove":
        _signal(db, "remove", dimension, value)
    elif a["verdict"] in ("works", "avoid", "trying"):
        _signal(db, "correction", dimension, value, note=a["verdict"])
    else:
        raise ActionError("bad verdict")


def adjust(db: DB, jobs: Jobs, a: dict) -> None:
    if a["key"] not in engine.ADJUST_KEYS:
        raise ActionError("bad key")
    _signal(db, "adjust_set", a["key"], a["key"], int(engine.clamp(int(a["value"]), -3, 3)))


def route(db: DB, jobs: Jobs, a: dict) -> None:
    from .providers import MODELS
    if a["provider"] not in MODELS or a["model"] not in MODELS[a["provider"]]:
        raise ActionError("unknown provider or model")
    db.x("UPDATE routes SET provider=?, model=? WHERE role=?", (a["provider"], a["model"], a["role"]))


def use_recommended_routes(db: DB, jobs: Jobs, a: dict) -> None:
    """Set every job to its recommended provider and model (Settings). A recommended provider that is not installed
    keeps the job on Claude (for the fact-check: Opus)."""
    from .providers import RECOMMENDED, status
    detected = {p["id"] for p in status() if p["detected"]}
    for role, (prov, model, _why) in RECOMMENDED.items():
        if prov not in detected and prov != "claude":
            prov, model = "claude", "opus"
        db.x("UPDATE routes SET provider=?, model=? WHERE role=?", (prov, model, role))


def set_api_key(db: DB, jobs: Jobs, a: dict) -> None:
    """Check the key with the Models API (no tokens used), then keep it in the OS keychain (SPEC §25)."""
    from . import apikey
    key = str(a.get("key") or "").strip()
    try:
        import anthropic
        anthropic.Anthropic(api_key=key, timeout=20.0, max_retries=1).models.list(limit=1)
    except anthropic.AuthenticationError as e:
        raise ActionError("the API rejected this key") from e
    except anthropic.APIConnectionError as e:
        raise ActionError("cannot reach the Anthropic API to check the key; try again when you are online") from e
    except anthropic.APIStatusError as e:
        raise ActionError(f"the API could not check the key ({e.status_code})") from e
    try:
        apikey.set_key(key)
    except ValueError as e:
        raise ActionError(str(e)) from e
    except Exception as e:  # noqa: BLE001 - no keychain on this system
        raise ActionError(f"cannot store the key in the system keychain: {e}"[:300]) from e


def clear_api_key(db: DB, jobs: Jobs, a: dict) -> None:
    from . import apikey
    apikey.clear()


def use_api_for_all(db: DB, jobs: Jobs, a: dict) -> None:
    """Every job on the Claude API with the recommended model (a Codex job goes to Opus)."""
    from . import apikey
    from .providers import RECOMMENDED
    if not apikey.get():
        raise ActionError("add an Anthropic API key first")
    for role, (prov, model, _why) in RECOMMENDED.items():
        db.x("UPDATE routes SET provider='anthropic', model=? WHERE role=?", (model if prov == "claude" else "opus", role))


def set_setting(db: DB, jobs: Jobs, a: dict) -> None:
    if a["key"] == "lessonWriting":  # "steps": planner, graphs and questions, text, review; "single": one call for the text
        if a["value"] not in ("steps", "single"):
            raise ActionError("lesson writing must be steps or single")
        db.set_meta("lesson_writing", a["value"])
        return
    if a["key"] == "writingStyle":  # "ste": Simplified Technical English (about 80 %); "plain": no style rule
        if a["value"] not in ("ste", "plain"):
            raise ActionError("writing style must be ste or plain")
        db.set_meta("writing_style", a["value"])
        from .jobs import STYLE
        STYLE["writing"] = a["value"]
        return
    keys = {"autoResearch": "auto_research", "autoRefresh": "auto_refresh"}
    if a["key"] not in keys:
        raise ActionError("unknown setting")
    db.set_meta(keys[a["key"]], "1" if a["value"] else "0")
    progress.research_ahead(db, jobs)


def setup_runner(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("runner_setup"):
        jobs.enqueue("runner_setup", "Set up local Python (numpy, torch)", {})


def refresh_card(db: DB, jobs: Jobs, a: dict) -> None:
    if not state.latest_card(db, a["conceptId"]):
        raise ActionError("no card to refresh")
    if not jobs.active("refresh_card", concept_id=a["conceptId"]):
        title = db.one("SELECT title FROM concepts WHERE id=?", (a["conceptId"],))["title"]
        jobs.enqueue("refresh_card", f"Check {title} for updates", {"concept_id": a["conceptId"]})


def decide_card_proposal(db: DB, jobs: Jobs, a: dict) -> None:
    """Approve: the proposal becomes the card's next version (fact-checked again; lessons re-render).
    Reject: nothing changes."""
    from .db import loads
    p = db.one("SELECT * FROM card_proposals WHERE id=?", (a["id"],))
    if not p or p["status"] != "pending":
        raise ActionError("no pending proposal with that id")
    if not a["approve"]:
        db.x("UPDATE card_proposals SET status='rejected' WHERE id=?", (p["id"],))
        return
    current = state.latest_card(db, p["concept_id"])
    if current and current["version"] != p["base_version"]:
        db.x("UPDATE card_proposals SET status='superseded' WHERE id=?", (p["id"],))
        raise ActionError("the card changed since this was proposed; ask for a fresh check")
    ver = (current["version"] if current else 0) + 1
    body = loads(p["body"])
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
         (p["concept_id"], ver, dumps(body), "pending", now()))
    db.x("UPDATE card_proposals SET status='approved' WHERE id=?", (p["id"],))
    db.x("UPDATE concepts SET objective=? WHERE id=?", (body.get("objective") or current["objective"], p["concept_id"]))
    jobs.enqueue("fact_check", "Fact-check updated card", {"concept_ids": [p["concept_id"]]})


def set_plan_settings(db: DB, jobs: Jobs, a: dict) -> None:
    if "weeklyHours" in a:
        h = float(a["weeklyHours"])
        if not 0.5 <= h <= 80:
            raise ActionError("weekly hours must be between 0.5 and 80")
        db.set_meta("plan_weekly_hours", str(h))
    if "studyDays" in a:
        days = sorted({int(d) for d in a["studyDays"] if 0 <= int(d) <= 6})
        if not days:
            raise ActionError("pick at least one study day")
        db.set_meta("plan_study_days", ",".join(map(str, days)))
    if "startTime" in a:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", a["startTime"]):
            raise ActionError("start time must look like 19:00")
        db.set_meta("plan_start_time", a["startTime"])
    if "hours" in a and "goalId" in a:
        h = float(a["hours"])
        if not 0.5 <= h <= 80:
            raise ActionError("hours must be between 0.5 and 80")
        db.x("UPDATE goals SET hours=? WHERE id=?", (h, a["goalId"]))


def undo_answer(db: DB, jobs: Jobs, a: dict) -> None:
    """Undo the latest answer to an item (mis-click, or a grade you disagree with): void its evidence,
    so the item can be answered again. Mastery is recomputed from what remains."""
    cid, item_id = a["conceptId"], a["itemId"]
    row = db.one("""SELECT id FROM evidence WHERE concept_id=? AND item_id=? AND kind='practice' AND voided=0
                    ORDER BY id DESC LIMIT 1""", (cid, item_id))
    if not row:
        raise ActionError("nothing to undo")
    db.x("UPDATE evidence SET voided=1 WHERE id=?", (row["id"],))
    db.x("UPDATE gradings SET status='voided' WHERE id = (SELECT MAX(id) FROM gradings WHERE concept_id=? AND item_id=?)", (cid, item_id))


def load_demo(db: DB, jobs: Jobs, a: dict) -> None:
    if db.one("SELECT 1 FROM goals LIMIT 1"):
        raise ActionError("the demo can only be loaded into an empty workspace")
    seed_demo(db)


def delete_goal(db: DB, jobs: Jobs, a: dict) -> None:
    if not db.one("SELECT 1 FROM goals WHERE id=?", (a["id"],)):
        raise ActionError("unknown goal")
    from . import backup
    backup.backup_now(db)  # always keep a copy before deleting
    _delete_goal(db, a["id"])


def backup_now(db: DB, jobs: Jobs, a: dict) -> None:
    from . import backup
    backup.backup_now(db)


def set_runner_mode(db: DB, jobs: Jobs, a: dict) -> None:
    from . import runner
    if a["mode"] not in ("local", "docker"):
        raise ActionError("mode must be local or docker")
    if a["mode"] == "docker" and not runner.docker_available():
        raise ActionError("Docker isn't available: install Docker Desktop and start it first")
    db.set_meta("runner_mode", a["mode"])


def setup_runner_docker(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("runner_docker_setup"):
        jobs.enqueue("runner_docker_setup", "Build the exercise container", {})


def reset(db: DB, jobs: Jobs, a: dict) -> None:
    seed_demo(db)


ACTIONS = {
    "answer": answer, "explain": explain,
    "startProbe": start_probe, "probeAnswer": probe_answer, "probeAssessNow": probe_assess_now, "applyProbe": apply_probe,
    "resetProbe": reset_probe, "dismissProbe": dismiss_probe,
    "sessionLearnAgain": session_learn_again,
    "startSession": start_session, "sessionAnswer": session_answer, "sessionKnown": session_known, "sessionTeach": session_teach,
    "sessionAssessNow": session_assess_now, "sessionRetry": session_retry, "deleteSession": delete_session,
    "startPractice": start_practice, "practiceSubmit": practice_submit, "practiceGiveUp": practice_give_up,
    "practiceRetry": practice_retry, "practiceStop": practice_stop, "practiceNext": practice_next,
    "reflect": reflect, "decideProposal": decide_proposal, "setSetting": set_setting,
    "setupRunner": setup_runner,
    "refreshCard": refresh_card, "decideCardProposal": decide_card_proposal, "setPlanSettings": set_plan_settings,
    "undoAnswer": undo_answer, "loadDemo": load_demo, "deleteGoal": delete_goal, "backupNow": backup_now,
    "setRunnerMode": set_runner_mode, "setupRunnerDocker": setup_runner_docker, "feedback": feedback, "explainDifferently": explain_differently,
    "editFeedback": edit_feedback, "deleteFeedback": delete_feedback, "applyFeedback": apply_feedback,
    "revertLesson": revert_lesson, "addRemedial": add_remedial, "dismissRemedial": dismiss_remedial,
    "editGuidelines": edit_guidelines, "distillGuidelines": distill_guidelines, "refresh": refresh, "markStudied": mark_studied, "addNote": add_note, "deleteNote": delete_note,
    "chat": chat, "decideDiff": decide_diff, "researchModule": research_module, "createGoal": create_goal,
    "setGoal": set_goal, "correctEntry": correct_entry, "adjust": adjust, "route": route, "useRecommendedRoutes": use_recommended_routes,
    "setApiKey": set_api_key, "clearApiKey": clear_api_key, "useApiForAll": use_api_for_all,
    "linkSource": link_source, "editSource": edit_source, "deleteSource": delete_source, "rereadSource": reread_source, "reset": reset,
    "studyBook": study_book, "bookRetry": book_retry, "bookOpenLesson": book_open_lesson, "reviewReasoning": review_reasoning,
    "makeFormulaLesson": make_formula_lesson, "addFormulaForm": add_formula_form, "preferFormulaForm": prefer_formula_form,
    "learnBlocksFirst": learn_blocks_first, "bookRemapChapter": book_remap_chapter, "bookReplan": book_replan,
    "openFormula": open_formula, "makeFormulaPage": make_formula_page, "makeFormulaFlow": make_formula_flow, "bookHomework": book_homework,
    "deleteBook": delete_book, "setMapView": set_map_view,
    "findGaps": find_gaps, "acceptGap": accept_gap, "dismissGap": dismiss_gap,
    "addMapGoal": add_map_goal, "renameMapGoal": rename_map_goal, "removeMapGoal": remove_map_goal, "addGoalBlock": add_goal_block,
    "planLesson": plan_lesson, "predictStep": predict_step, "rewriteStep": rewrite_step, "demoResult": demo_result, "lessonPlanNote": lesson_plan_note, "approveLessonPlan": approve_lesson_plan,
    "setDictation": set_dictation, "downloadDictationModel": download_dictation_model,
    "removeDictationModel": remove_dictation_model,
}


def dispatch(db: DB, jobs: Jobs, a: dict) -> None:
    fn = ACTIONS.get(a.get("type", ""))
    if not fn:
        raise ActionError(f"unknown action {a.get('type')!r}")
    fn(db, jobs, a)
