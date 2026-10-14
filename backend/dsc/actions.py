"""Write side: every UI action. Each one appends to the logs (or edits user-owned records like
notes and settings); the UI then re-reads the snapshot."""

from __future__ import annotations

import re

from . import engine, lesson, state
from .db import DB, dumps, now
from .jobs import Jobs
from .seed import seed_demo


class ActionError(ValueError):
    pass


TAG_LABELS = {
    "framing-off": "The framing didn't work for me",
    "confused": "I got lost / missing background",
    "too-abstract": "Too abstract",
    "too-fast": "Too fast",
    "too-slow": "Too slow",
    "too-long": "Too long",
    "more-rigor": "I want more rigor",
    "loved-it": "This worked really well",
}


def _signal(db: DB, kind: str, dimension: str, value: str, delta: float = 0, evidence: float = 0,
            note: str = "", bumps: bool = True) -> None:
    db.x("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,?,?,?)",
         (now(), kind, dimension, value, delta, evidence, note, 1 if bumps else 0))


def _entry(pb: dict, dimension: str, value: str) -> dict | None:
    return next((e for e in pb["entries"] if e["dimension"] == dimension and e["value"] == value), None)


def _card_item(db: DB, cid: str, item_id: str) -> dict | None:
    card = state.latest_card(db, cid) or {}
    for s in card.get("sections", []):
        for kind in ("check", "code"):
            if s.get(kind, {}).get("id") == item_id:
                return {"kind": kind, **s[kind]}
    return None


# ---------------------------------------------------------------- answers & reviews

def answer(db: DB, jobs: Jobs, a: dict) -> None:
    cid, item_id = a["conceptId"], a["checkId"]
    item = _card_item(db, cid, item_id)
    if not item:
        raise ActionError(f"unknown item {item_id}")
    # Checks are graded here against the hidden key; code exercises run in the browser (Pyodide).
    correct = (a.get("choice") == item["answer"]) if item["kind"] == "check" else bool(a.get("correct"))
    gid = state.active_goal(db)
    _, before = state.concept_states(db, gid)
    db.x("INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, angle) VALUES(?,?,?,?,?,?,?)",
         (now(), cid, item_id, "practice", a.get("choice"), int(correct), a.get("angle")))
    db.x("UPDATE concepts SET started=1 WHERE id=?", (cid,))
    if a.get("angle"):  # outcome signal: weak evidence about the angle used; doesn't re-render anything
        _signal(db, "outcome", "angle", a["angle"], 0.03 if correct else -0.03, 0.3, bumps=False)
    _, after = state.concept_states(db, gid)
    if after[cid].learned_at and not before[cid].learned_at:
        card, due = engine.first_review(after[cid].learned_at)
        db.x("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?)", (cid, card, due, after[cid].learned_at))


def review(db: DB, jobs: Jobs, a: dict) -> None:
    cid, item_id = a["conceptId"], a["checkId"]
    item = _card_item(db, cid, item_id)
    row = db.one("SELECT * FROM reviews WHERE concept_id=?", (cid,))
    if not item or item["kind"] != "check" or not row:
        raise ActionError("nothing to review")
    correct = a.get("choice") == item["answer"]
    ts = now()
    db.x("INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct) VALUES(?,?,?,?,?,?)",
         (ts, cid, item_id, "review", a.get("choice"), int(correct)))
    card, due = engine.review(row["card"], correct, ts)
    db.x("UPDATE reviews SET card=?, due=? WHERE concept_id=?", (card, due, cid))


# ---------------------------------------------------------------- feedback

def feedback(db: DB, jobs: Jobs, a: dict) -> None:
    cid, sid, angle = a["conceptId"], a.get("sectionId"), a.get("angle")
    tags, text = a.get("tags", []), (a.get("text") or "").strip()
    pb0 = state.playbook(db)
    effects: list[str] = []

    def nudge(value: str, delta: float, why: str) -> None:
        e = _entry(pb0, "angle", value) or {"score": 0.5}
        _signal(db, "reaction", "angle", value, delta, 1.0, note=text or why)
        effects.append(f'Playbook: "{value}" {"less" if delta < 0 else "more"} trusted '
                       f'({e["score"]:.2f} → {engine.clamp(e["score"] + delta, 0.02, 0.98):.2f}) {why}')

    def knob(key: str, step: int, what: str) -> None:
        _signal(db, "adjust", key, key, step)
        effects.append(f"{key.capitalize()} {'+' if step > 0 else ''}{step}: {what}")

    for t in tags:
        if t == "framing-off" and angle:
            nudge(angle, -0.14, "because the framing missed")
        elif t == "loved-it" and angle:
            nudge(angle, +0.10, "because it landed")
        elif t == "too-abstract":
            nudge("computational", +0.08, "(more concrete, code-first)")
        elif t == "too-fast":
            knob("pace", -1, "smaller steps, more worked examples")
        elif t == "too-slow":
            knob("pace", +1, "fewer worked examples, skip what you show you know")
        elif t == "too-long":
            knob("depth", -1, 'shorter lessons, details moved to "go deeper"')
        elif t == "more-rigor":
            knob("rigor", +1, "formal statements and proofs earlier")
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
            effects.insert(0, f"This section now uses the {nxt} angle. Other lessons switch too if the pattern repeats.")

    pb1 = state.playbook(db)
    if pb1["version"] != pb0["version"]:
        n = sum(1 for x in db.q("SELECT playbook_version FROM renditions") if x["playbook_version"] < pb1["version"])
        effects.append(f"Playbook v{pb1['version']}: {n} lesson{'s' if n != 1 else ''} will be re-rendered for you "
                       "(past ones offer a refresh)")
    if text:
        effects.append("Your comment is logged and goes into the weekly reflection")
    db.x("INSERT INTO feedback(ts, concept_id, section_id, tags, text, effects) VALUES(?,?,?,?,?,?)",
         (now(), cid, sid, dumps([TAG_LABELS.get(t, t) for t in tags]), text, dumps(effects or ["Logged"])))


def _pin(db: DB, cid: str, sid: str, angle: str) -> None:
    r = state.rendition_row(db, cid)
    db.x("UPDATE renditions SET section_angles=?, pinned=? WHERE concept_id=?",
         (dumps({**r["section_angles"], sid: angle}), dumps({**r["pinned"], sid: angle}), cid))


def explain_differently(db: DB, jobs: Jobs, a: dict) -> None:
    cid, sid = a["conceptId"], a["sectionId"]
    r = state.rendition_row(db, cid)
    card = state.latest_card(db, cid)
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
    db.x("INSERT INTO feedback(ts, concept_id, section_id, tags, text, effects) VALUES(?,?,?,?,?,?)",
         (now(), cid, sid, dumps(["Explain it differently"]), "",
          dumps([f"Section switched: {cur} → {nxt}", f"Weak signal recorded: \"{cur}\" didn't land here"])))


def refresh(db: DB, jobs: Jobs, a: dict) -> None:
    lesson.refresh(db, jobs, a["conceptId"])


def mark_studied(db: DB, jobs: Jobs, a: dict) -> None:
    db.x("UPDATE renditions SET studied=1 WHERE concept_id=?", (a["conceptId"],))


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
    jobs.enqueue("research_module", f"Research {title}",
                 {"module_id": anchor["module_id"], "concept": {"id": cid, "title": title, "detail": ch["detail"]}})


def research_module(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("research_module", module_id=a["moduleId"]):
        db.x("UPDATE modules SET research='researching' WHERE id=?", (a["moduleId"],))
        m = db.one("SELECT title FROM modules WHERE id=?", (a["moduleId"],))
        jobs.enqueue("research_module", f"Research {m['title']}", {"module_id": a["moduleId"]})


def create_goal(db: DB, jobs: Jobs, a: dict) -> None:
    answers = a.get("answers") or []
    if not answers or not answers[0].get("a", "").strip():
        raise ActionError("the goal is required")
    jobs.enqueue("outline", "Build roadmap", {"answers": answers})


def set_goal(db: DB, jobs: Jobs, a: dict) -> None:
    if not db.one("SELECT 1 FROM goals WHERE id=?", (a["id"],)):
        raise ActionError("unknown goal")
    db.set_meta("active_goal", a["id"])


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


def reset(db: DB, jobs: Jobs, a: dict) -> None:
    seed_demo(db)


ACTIONS = {
    "answer": answer, "review": review, "feedback": feedback, "explainDifferently": explain_differently,
    "refresh": refresh, "markStudied": mark_studied, "addNote": add_note, "deleteNote": delete_note,
    "chat": chat, "decideDiff": decide_diff, "researchModule": research_module, "createGoal": create_goal,
    "setGoal": set_goal, "correctEntry": correct_entry, "adjust": adjust, "route": route, "reset": reset,
}


def dispatch(db: DB, jobs: Jobs, a: dict) -> None:
    fn = ACTIONS.get(a.get("type", ""))
    if not fn:
        raise ActionError(f"unknown action {a.get('type')!r}")
    fn(db, jobs, a)
