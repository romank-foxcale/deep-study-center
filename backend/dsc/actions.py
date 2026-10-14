"""Write side: every UI action. Each one appends to the logs (or edits user-owned records like
notes and settings); the UI then re-reads the snapshot."""

from __future__ import annotations

import re

from . import engine, lesson, library, progress, state
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
        for kind in ("check", "code", "explain"):
            if s.get(kind, {}).get("id") == item_id:
                return {"kind": kind, **s[kind]}
    return None


# ---------------------------------------------------------------- answers & reviews

def answer(db: DB, jobs: Jobs, a: dict) -> None:
    cid, item_id = a["conceptId"], a["checkId"]
    item = _card_item(db, cid, item_id)
    if not item:
        raise ActionError(f"unknown item {item_id}")
    if item["kind"] == "explain":
        raise ActionError("explain-back answers go through the 'explain' action")
    # Checks are graded here against the hidden key; code exercises run in the browser (Pyodide).
    correct = (a.get("choice") == item["answer"]) if item["kind"] == "check" else bool(a.get("correct"))
    progress.record_evidence(db, cid, item_id, 1.0 if correct else 0.0, choice=a.get("choice"), angle=a.get("angle"))
    progress.research_ahead(db, jobs)


def explain(db: DB, jobs: Jobs, a: dict) -> None:
    """Explain-back: the learner's own words, graded against a rubric by an independent grader job."""
    cid, item_id, text = a["conceptId"], a["itemId"], (a.get("answer") or "").strip()
    item = _card_item(db, cid, item_id)
    if not item or item["kind"] != "explain":
        raise ActionError(f"unknown explain-back item {item_id}")
    if len(text) < 15:
        raise ActionError("write a few sentences in your own words first")
    gid = db.x("INSERT INTO gradings(ts, concept_id, item_id, answer, status) VALUES(?,?,?,?,?)",
               (now(), cid, item_id, text[:4000], "pending"))
    jobs.enqueue("grade", "Grade explanation", {"grading_id": gid, "concept_id": cid, "angle": a.get("angle")})


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


# ---------------------------------------------------------------- placement diagnostic

def start_placement(db: DB, jobs: Jobs, a: dict) -> None:
    gid = state.active_goal(db)
    if not db.one("SELECT 1 FROM placement_items WHERE goal_id=?", (gid,)) and not jobs.active("placement_bank", goal_id=gid):
        jobs.enqueue("placement_bank", "Write placement quiz", {"goal_id": gid})


def placement_answer(db: DB, jobs: Jobs, a: dict) -> None:
    """One placement answer; choice None means "I don't know" (counted as a gap, never a guess)."""
    gid = state.active_goal(db)
    row = db.one("SELECT item FROM placement_items WHERE goal_id=? AND module_id=?", (gid, a["moduleId"]))
    if not row:
        raise ActionError("no placement question for that module")
    from .db import loads
    item = loads(row["item"])
    choice = a.get("choice")
    correct = choice is not None and choice == item["answer"]
    db.x("INSERT INTO placement_answers(ts, goal_id, module_id, choice, correct) VALUES(?,?,?,?,?)",
         (now(), gid, a["moduleId"], choice, int(correct)))


def finish_placement(db: DB, jobs: Jobs, a: dict) -> None:
    """Turn placement results into a roadmap proposal: compress modules the learner already knows."""
    gid = state.active_goal(db)
    p = state.placement(db, gid)
    known = [m for m, st in p["status"].items() if st == "known"]
    if known:
        titles = {m["id"]: m["title"] for m in db.q(
            f"SELECT id, title FROM modules WHERE id IN ({','.join('?' * len(known))})", known)}
        changes = [{"op": "compress", "title": titles[m], "module": m,
                    "detail": "Placement showed you know this: marked as known; open it any time to review."} for m in known]
        db.x("INSERT INTO diffs(ts, goal_id, reason, changes, status) VALUES(?,?,?,?,'pending')",
             (now(), gid, f"Placement: you already know {len(known)} module{'s' if len(known) != 1 else ''}.", dumps(changes)))
    db.set_meta(f"placement_done:{gid}", "1")


def reset_placement(db: DB, jobs: Jobs, a: dict) -> None:
    """Retake: clear this goal's placement answers (modules already marked known stay known)."""
    gid = state.active_goal(db)
    db.x("DELETE FROM placement_answers WHERE goal_id=?", (gid,))
    db.set_meta(f"placement_done:{gid}", "0")
    start_placement(db, jobs, a)


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


def set_setting(db: DB, jobs: Jobs, a: dict) -> None:
    if a["key"] != "autoResearch":
        raise ActionError("unknown setting")
    db.set_meta("auto_research", "1" if a["value"] else "0")
    progress.research_ahead(db, jobs)


def promote_card(db: DB, jobs: Jobs, a: dict) -> None:
    try:
        library.promote(db, a["conceptId"])
    except ValueError as e:
        raise ActionError(str(e)) from e


def setup_runner(db: DB, jobs: Jobs, a: dict) -> None:
    if not jobs.active("runner_setup"):
        jobs.enqueue("runner_setup", "Set up local Python (numpy, torch)", {})


def reset(db: DB, jobs: Jobs, a: dict) -> None:
    seed_demo(db)


ACTIONS = {
    "answer": answer, "explain": explain, "review": review,
    "startPlacement": start_placement, "placementAnswer": placement_answer, "finishPlacement": finish_placement, "resetPlacement": reset_placement,
    "reflect": reflect, "decideProposal": decide_proposal, "setSetting": set_setting,
    "promoteCard": promote_card, "setupRunner": setup_runner, "feedback": feedback, "explainDifferently": explain_differently,
    "refresh": refresh, "markStudied": mark_studied, "addNote": add_note, "deleteNote": delete_note,
    "chat": chat, "decideDiff": decide_diff, "researchModule": research_module, "createGoal": create_goal,
    "setGoal": set_goal, "correctEntry": correct_entry, "adjust": adjust, "route": route, "reset": reset,
}


def dispatch(db: DB, jobs: Jobs, a: dict) -> None:
    fn = ACTIONS.get(a.get("type", ""))
    if not fn:
        raise ActionError(f"unknown action {a.get('type')!r}")
    fn(db, jobs, a)
