"""Remedial lessons (SPEC §12): when the learner is stuck on a lesson, offer an extra lesson ("Vectors (b)")
aimed at exactly what went wrong. The learner adds it with one click; it is researched and fact-checked like
any card, and inserted right after the lesson (after earlier extra lessons of the same lesson).

Stuck = not learned yet, and a weighted count of struggle signals reaches ``STUCK_AT``: wrong answers,
failed explain-backs, questions to the tutor, and "I got lost" feedback. Questions alone never count as stuck.
"""

from __future__ import annotations

import re
import string

from . import state
from .db import DB, dumps, loads

STUCK_AT = 4.0
REOFFER_AFTER = 3.0  # after "Not now", offer again only when the score has grown this much
CONFUSED = "I got lost / missing background"
_SUFFIX = re.compile(r"^(?P<root>.+)-r(?P<letter>[b-z])$")


def root_of(cid: str) -> str:
    m = _SUFFIX.match(cid)
    return m.group("root") if m else cid


def extra_lessons(db: DB, cid: str) -> list[dict]:
    root = root_of(cid)
    return db.q("SELECT id, title, objective FROM concepts WHERE id LIKE ? ORDER BY id", (f"{root}-r_",))


SURE = 0.75  # a wrong answer given at least this sure is a likely misconception


def signals(db: DB, cid: str) -> dict:
    wrong = db.q("""SELECT e.item_id, e.choice, e.confidence, e.thinking FROM evidence e WHERE e.concept_id=? AND e.kind='practice'
                    AND e.voided=0 AND COALESCE(e.score, e.correct) < 0.5""", (cid,))
    sure = [w for w in wrong if w["confidence"] is not None and w["confidence"] >= SURE]
    explain_fail = db.q("SELECT * FROM gradings WHERE concept_id=? AND status='graded' AND score < 0.5", (cid,))
    questions = db.q("SELECT text FROM chats WHERE concept_id=? AND role='me' ORDER BY id", (cid,))
    fb = db.q("SELECT * FROM feedback WHERE concept_id=? AND deleted=0 ORDER BY id", (cid,))
    confused = [f for f in fb if CONFUSED in loads(f["tags"], [])]
    score = len(wrong) + len(sure) + 1.5 * len(explain_fail) + 0.5 * len(questions) + 2 * len(confused)  # sure + wrong counts 2
    return {"wrong": wrong, "sureWrong": sure, "explainFail": explain_fail, "questions": questions, "feedback": fb,
            "confused": confused, "score": score, "struggle": len(wrong) + len(explain_fail) + len(confused)}


def offer(db: DB, cid: str) -> dict | None:
    """The offer the lesson page shows, or None."""
    gid = state.active_goal(db)
    if not gid or not state.latest_card(db, cid):
        return None
    _, states = state.concept_states(db, gid)
    if cid not in states or states[cid].state == "learned":
        return None
    if any(states.get(x["id"]) and states[x["id"]].state != "learned" for x in extra_lessons(db, cid)
           if x["id"] != cid):
        return None  # an extra lesson for this is still open: do that one first
    s = signals(db, cid)
    seen = float(db.meta(f"remedial_seen:{cid}", "0") or 0)
    if s["score"] < max(STUCK_AT, seen + REOFFER_AFTER if seen else STUCK_AT) or not s["struggle"]:
        return None
    reasons = []
    if s["wrong"]:
        reasons.append(f'{len(s["wrong"])} wrong answer{"s" if len(s["wrong"]) > 1 else ""}')
    if s["sureWrong"]:
        n = len(s["sureWrong"])
        reasons.append(f'{n} of them given while sure: a likely misconception' if n == 1 else
                       f'{n} of them given while sure: likely misconceptions')
    if s["explainFail"]:
        reasons.append(f'{len(s["explainFail"])} explain-back{"s" if len(s["explainFail"]) > 1 else ""} not passed')
    if s["questions"]:
        reasons.append(f'{len(s["questions"])} question{"s" if len(s["questions"]) > 1 else ""} to the tutor')
    if s["confused"]:
        reasons.append('you said you got lost')
    letter = next_letter(db, cid)
    title = db.one("SELECT title FROM concepts WHERE id=?", (root_of(cid),))["title"]
    return {"reasons": reasons, "score": s["score"], "id": f"{root_of(cid)}-r{letter}", "title": f"{title} ({letter})"}


def next_letter(db: DB, cid: str) -> str:
    used = {x["id"][-1] for x in extra_lessons(db, cid)}
    return next(c for c in string.ascii_lowercase[1:] if c not in used)


def dismiss(db: DB, cid: str) -> None:
    db.set_meta(f"remedial_seen:{cid}", str(signals(db, cid)["score"]))


def brief(db: DB, cid: str) -> str:
    """What went wrong, for the research agent (learner data: goes inside <learner> tags in the prompt)."""
    s = signals(db, cid)
    from .writer import effective_sections
    card = state.latest_card(db, cid) or {}
    checks = {sec["check"]["id"]: sec["check"] for sec in card.get("sections", []) + effective_sections(db, cid, card)
              if sec.get("check")}
    lines = []
    for w in s["wrong"][-6:]:
        c = checks.get(w["item_id"])
        sure = w["confidence"] is not None and w["confidence"] >= SURE
        tail = (f' while sure ({round(w["confidence"] * 100)} %): likely a misconception' if sure else "") + \
            (f'. Their thinking: "{w["thinking"][:300]}"' if w["thinking"] else "")
        if c and w["choice"] is not None and 0 <= w["choice"] < len(c["options"]):
            lines.append(f'- Wrong answer to "{c["prompt"]}": chose "{c["options"][w["choice"]]}" '
                         f'(right: "{c["options"][c["answer"]]}"){tail}')
        else:
            lines.append(f'- Failed exercise or check {w["item_id"]}{tail}')
    for g in s["explainFail"][-3:]:
        lines.append(f'- Explain-back not passed; missing: {", ".join(loads(g["missing"], [])) or "(not given)"}')
    for q in s["questions"][-8:]:
        lines.append(f'- Asked the tutor: "{q["text"][:300]}"')
    for f in s["feedback"][-6:]:
        tags = ", ".join(loads(f["tags"], []))
        ref = loads(f["ref"], None) if f.get("ref") else None
        about = f' about "{ref["quote"][:200]}"' if ref and ref.get("quote") else ""
        lines.append(f'- Feedback{about}: {tags}{": " if tags and f["text"] else ""}{f["text"][:300]}')
    return "\n".join(lines) or "- (no details)"


def add(db: DB, jobs, cid: str) -> str:
    """Insert the extra lesson after the lesson (and its earlier extra lessons) and research its card."""
    root = root_of(cid)
    base = db.one("SELECT * FROM concepts WHERE id=?", (root,))
    if not base:
        raise ValueError("no such lesson")
    letter = next_letter(db, cid)
    new_id, title = f"{root}-r{letter}", f'{base["title"]} ({letter})'
    last = max([base] + [db.one("SELECT * FROM concepts WHERE id=?", (x["id"],)) for x in extra_lessons(db, cid)],
               key=lambda r: r["ord"])
    detail = (f'An extra ("remedial") lesson for a learner who got stuck on "{base["title"]}" ({base["objective"]}). '
              "Write one concept card that targets exactly these difficulties: fill the missing background, untangle the "
              "misconception behind the wrong answers, and use a different angle and smaller steps than the original lesson. "
              f"What went wrong (learner data):\n<learner>\n{brief(db, cid)}\n</learner>")
    pos = last["ord"] + 1
    with db.tx():
        db.conn.execute("UPDATE concepts SET ord = ord + 1 WHERE module_id=? AND ord >= ?", (base["module_id"], pos))
        db.conn.execute("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                        (new_id, base["module_id"], pos, title, f'Extra lesson: what got in the way in "{base["title"]}"',
                         15, dumps([]), 0.2))
    db.set_meta(f"remedial_seen:{cid}", str(signals(db, cid)["score"]))
    prev = db.one("SELECT research FROM modules WHERE id=?", (base["module_id"],))["research"]
    jobs.enqueue("research_module", f"Write extra lesson {title}",
                 {"module_id": base["module_id"], "prev_research": prev,
                  "concept": {"id": new_id, "title": title, "detail": detail}})
    return new_id
