"""Lesson versions (SPEC §11): immutable snapshots of one lesson's prose, a head pointer, revert, and diffs.

- A version stores the body of every section plus the fingerprint it was written for:
  (card version, style, angle per section). It never changes after it is written.
- The rendered lesson becomes v1. A re-render (new card, new style, other angle) or an applied piece of
  feedback adds the next version. ``parent`` is the version it was built from, so versions form a tree.
- The head is the version the page shows. Revert moves the head; nothing is lost.
- A section whose fingerprint still matches the head keeps the head's text, so an "explain differently"
  in one section does not throw away feedback applied to the others.
"""

from __future__ import annotations

import difflib
import re

from . import state
from .db import DB, dumps, loads, now

REVERT_DELTA, REVERT_EVIDENCE = -0.1, 0.5  # weak: three reverts of the same technique make it "avoid"


# ---------------------------------------------------------------- read

def _parse(row: dict | None) -> dict | None:
    if not row:
        return None
    return {**row, "angles": loads(row["angles"], {}), "sections": loads(row["sections"], {}),
            "feedback_ids": loads(row["feedback_ids"], []), "changes": loads(row["changes"], [])}


def get(db: DB, cid: str, version: int) -> dict | None:
    return _parse(db.one("SELECT * FROM lesson_versions WHERE concept_id=? AND version=?", (cid, version)))


def all_versions(db: DB, cid: str) -> list[dict]:
    return [_parse(r) for r in db.q("SELECT * FROM lesson_versions WHERE concept_id=? ORDER BY version", (cid,))]


def head(db: DB, cid: str) -> dict | None:
    h = db.one("SELECT * FROM lesson_heads WHERE concept_id=?", (cid,))
    if not h:
        return None
    v = get(db, cid, h["version"])
    return v and {**v, "chosen": bool(h["chosen"])}


def lineage(versions: dict[int, dict], v: int | None) -> list[int]:
    """v, its parent, its parent's parent, ... (newest first)."""
    out: list[int] = []
    while v is not None and v in versions and v not in out:
        out.append(v)
        v = versions[v]["parent"]
    return out


def section_from_head(h: dict | None, r: dict, sid: str) -> str | None:
    """The head's text for a section, if the head was written for the section's current fingerprint."""
    if h and h["card_version"] == r["card_version"] and h["style"] == r["style"] \
            and h["angles"].get(sid) == r["section_angles"].get(sid):
        return h["sections"].get(sid)
    return None


def head_matches(h: dict | None, r: dict | None) -> bool:
    return bool(h and r and h["card_version"] == r["card_version"] and h["style"] == r["style"]
                and h["angles"] == r["section_angles"])


# ---------------------------------------------------------------- write

def create(db: DB, cid: str, *, parent: int | None, card_version: int, playbook_version: int, style: str,
           angles: dict, sections: dict, source: str, summary: str = "", feedback_ids: list[int] | None = None,
           changes: list[dict] | None = None, chosen: bool | None = None) -> int:
    """Write the next version and make it the head."""
    with db.tx():
        n = db.conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM lesson_versions WHERE concept_id=?", (cid,)).fetchone()[0]
        db.conn.execute("""INSERT INTO lesson_versions(concept_id, version, ts, parent, card_version, playbook_version, style,
                           angles, sections, source, summary, feedback_ids, changes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (cid, n, now(), parent, card_version, playbook_version, style, dumps(angles), dumps(sections),
                         source, summary, dumps(feedback_ids or []), dumps(changes or [])))
        old = db.conn.execute("SELECT chosen FROM lesson_heads WHERE concept_id=?", (cid,)).fetchone()
        keep = bool(old and old[0]) if chosen is None else chosen
        db.conn.execute("INSERT OR REPLACE INTO lesson_heads(concept_id, version, chosen) VALUES(?,?,?)", (cid, n, int(keep)))
    return n


def sync(db: DB, cid: str) -> int | None:
    """Snapshot the rendered lesson as a new version when its prose is complete and differs from the head
    (first render, new card, new style, another angle). Returns the new version, if any."""
    r = state.rendition_row(db, cid)
    card = state.latest_card(db, cid)
    if not r or not card or not card.get("sections"):
        return None
    h = head(db, cid)
    if head_matches(h, r):
        return None
    bodies, changes = {}, []
    for s in card["sections"]:
        sid, angle = s["id"], r["section_angles"].get(s["id"])
        kept = section_from_head(h, r, sid)
        if kept is not None:
            bodies[sid] = kept
            continue
        row = db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                     (cid, r["card_version"], sid, angle, r["style"]))
        if not row:
            return None  # still being written
        bodies[sid] = row["body"]
        if h:
            changes.append({"sectionId": sid, "feedbackIds": [], "why": _render_why(h, r, sid), "how": f"Re-rendered ({angle} angle)",
                            "technique": ""})
    if not h:
        summary = f"First version, as rendered for you (card v{r['card_version']}, playbook v{r['playbook_version']})"
    else:
        summary = "Re-rendered: " + "; ".join(sorted({c["why"] for c in changes}))
    return create(db, cid, parent=h["version"] if h else None, card_version=r["card_version"],
                  playbook_version=r["playbook_version"], style=r["style"], angles=dict(r["section_angles"]),
                  sections=bodies, source="render", summary=summary, changes=changes)


def _render_why(h: dict, r: dict, sid: str) -> str:
    if h["card_version"] != r["card_version"]:
        return f"the source card changed (v{h['card_version']} → v{r['card_version']})"
    if h["style"] != r["style"]:
        return f"your style changed ({h['style']} → {r['style']})"
    return f"the angle changed ({h['angles'].get(sid)} → {r['section_angles'].get(sid)})"


def restore(db: DB, cid: str, version: int) -> dict:
    """Make ``version`` the head. Leaving applied feedback behind is recorded as a learning signal:
    the way that feedback was applied did not work for this learner."""
    h, target, card = head(db, cid), get(db, cid, version), state.latest_card(db, cid)
    if not target:
        raise ValueError("no such version")
    if not h or h["version"] == version:
        raise ValueError("that version is already shown")
    if card and target["card_version"] != card["version"]:
        raise ValueError(f"v{version} was written from card v{target['card_version']}, and the card has changed since "
                         f"(v{card['version']}). Only versions of the current card can be restored.")
    vs = {v["version"]: v for v in all_versions(db, cid)}
    keep = set(lineage(vs, version))
    left = [vs[v] for v in lineage(vs, h["version"]) if v not in keep and vs[v]["source"] == "apply"]
    with db.tx():
        db.conn.execute("UPDATE lesson_heads SET version=?, chosen=1 WHERE concept_id=?", (version, cid))
        db.conn.execute("UPDATE renditions SET card_version=?, style=?, section_angles=? WHERE concept_id=?",
                        (target["card_version"], target["style"], dumps(target["angles"]), cid))
    if not left:
        return {"reverted": []}
    fids = sorted({i for v in left for i in v["feedback_ids"]})
    changes = [c for v in left for c in v["changes"]]
    db.x("INSERT INTO lesson_reverts(ts, concept_id, from_version, to_version, feedback_ids, changes) VALUES(?,?,?,?,?,?)",
         (now(), cid, h["version"], version, dumps(fids), dumps(changes)))
    title = (db.one("SELECT title FROM concepts WHERE id=?", (cid,)) or {"title": cid})["title"]
    for tech in sorted({(c.get("technique") or "").strip().lower() for c in changes} - {""}):
        # Weak and non-bumping: it informs later writers and the reflection, but re-renders nothing.
        db.x("""INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps)
                VALUES(?, 'reaction', 'technique', ?, ?, ?, ?, 0)""",
             (now(), tech[:60], REVERT_DELTA, REVERT_EVIDENCE, f'Reverted in "{title}"'))
    return {"reverted": [v["version"] for v in left], "feedbackIds": fids}


def recent_reverts(db: DB, limit: int = 8) -> list[dict]:
    out = []
    for r in db.q("""SELECT r.*, c.title FROM lesson_reverts r LEFT JOIN concepts c ON c.id = r.concept_id
                     ORDER BY r.id DESC LIMIT ?""", (limit,)):
        out.append({**r, "feedback_ids": loads(r["feedback_ids"], []), "changes": loads(r["changes"], [])})
    return out


def reverts_text(db: DB) -> str:
    lines = []
    for r in recent_reverts(db):
        for c in r["changes"]:
            lines.append(f'- in "{r["title"] or r["concept_id"]}": {c.get("how", "")} (technique: {c.get("technique") or "n/a"})')
    return "\n".join(lines[:12]) or "(none)"


# ---------------------------------------------------------------- feedback status

def feedback_status(db: DB, rows: list[dict]) -> dict[int, dict]:
    """Per feedback id: pending | applied (in vN, on the shown version's line) | reverted (vN was left) |
    routed (sent to the card check) | done (handled at once, e.g. a section switched angle)."""
    out: dict[int, dict] = {}
    by_concept: dict[str, tuple[dict, list[int]]] = {}
    for f in rows:
        cid = f["concept_id"]
        if cid not in by_concept:
            vs = {v["version"]: v for v in all_versions(db, cid)}
            h = db.one("SELECT version FROM lesson_heads WHERE concept_id=?", (cid,))
            by_concept[cid] = (vs, lineage(vs, h["version"]) if h else [])
        vs, line = by_concept[cid]
        holding = [v for v in vs.values() if v["source"] == "apply" and f["id"] in v["feedback_ids"]]
        on_line = [v for v in holding if v["version"] in line]
        st: dict = {"state": "pending", "version": None, "changedSinceApplied": False, "note": None}
        if f.get("routed_at"):
            st.update(state="routed", note="Sent to the card check")
        elif on_line:
            v = max(on_line, key=lambda x: x["version"])
            st.update(state="applied", version=v["version"],
                      changedSinceApplied=bool(f.get("updated_at") and f["updated_at"] >= v["ts"]))
        elif holding:
            st.update(state="reverted", version=max(v["version"] for v in holding))
        elif f.get("done_note"):
            st.update(state="done", note=f["done_note"])
        out[f["id"]] = st
    return out


# ---------------------------------------------------------------- diff

_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


def word_diff(a: str, b: str) -> list[list[str]]:
    """Word-level diff of two texts: [[op, text], ...] with op in eq | del | ins (adjacent ops merged)."""
    ta, tb = _TOKEN.findall(a or ""), _TOKEN.findall(b or "")
    out: list[list[str]] = []

    def put(op: str, toks: list[str]) -> None:
        text = "".join(toks)
        if not text:
            return
        if out and out[-1][0] == op:
            out[-1][1] += text
        else:
            out.append([op, text])

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            put("eq", ta[i1:i2])
        else:
            put("del", ta[i1:i2])
            put("ins", tb[j1:j2])
    return out


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def diff(db: DB, cid: str, a: int, b: int) -> dict:
    """Compare two versions of a lesson, per section, with each change's reason and feedback ids."""
    vs = {v["version"]: v for v in all_versions(db, cid)}
    if a not in vs or b not in vs:
        raise ValueError("no such version")
    va, vb = vs[a], vs[b]
    la, lb = set(lineage(vs, a)), set(lineage(vs, b))
    forward = [vs[v] for v in sorted(lb - la)]   # changes made on the way to b
    undone = [vs[v] for v in sorted(la - lb)]    # changes in a that b does not have
    card = state.latest_card(db, cid) or {}
    heads = {s["id"]: s["heading"] for s in card.get("sections", [])}
    fb = {f["id"]: f for f in db.q("SELECT id, text, tags, kind, deleted FROM feedback WHERE concept_id=?", (cid,))}
    order = list(heads) + [s for s in list(va["sections"]) + list(vb["sections"]) if s not in heads]
    sections = []
    for sid in dict.fromkeys(order):
        ta, tb = va["sections"].get(sid), vb["sections"].get(sid)
        if ta is None and tb is None:
            continue
        tokens = word_diff(ta or "", tb or "")
        notes = [{**c, "version": v["version"], "undone": False} for v in forward for c in v["changes"] if c.get("sectionId") == sid]
        notes += [{**c, "version": v["version"], "undone": True} for v in undone for c in v["changes"] if c.get("sectionId") == sid]
        sections.append({
            "id": sid, "heading": heads.get(sid, sid),
            "status": "added" if ta is None else "removed" if tb is None else "same" if ta == tb else "changed",
            "angleA": va["angles"].get(sid), "angleB": vb["angles"].get(sid), "tokens": tokens,
            "inserted": sum(_words(t) for op, t in tokens if op == "ins"),
            "deleted": sum(_words(t) for op, t in tokens if op == "del"),
            "changes": notes})
    used = sorted({i for v in forward + undone for i in v["feedback_ids"]})
    return {"conceptId": cid, "a": summary(va), "b": summary(vb), "sections": sections,
            "feedback": [{"id": i, "text": fb[i]["text"], "tags": loads(fb[i]["tags"], []), "kind": fb[i]["kind"],
                          "deleted": bool(fb[i]["deleted"])} for i in used if i in fb]}


def summary(v: dict) -> dict:
    return {"version": v["version"], "ts": v["ts"], "parent": v["parent"], "source": v["source"], "summary": v["summary"],
            "cardVersion": v["card_version"], "playbookVersion": v["playbook_version"], "style": v["style"],
            "feedbackIds": v["feedback_ids"], "changes": len(v["changes"])}


# ---------------------------------------------------------------- fact guard

_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)
_ANY_MATH = re.compile(r"\$\$(.+?)\$\$|\$([^$\n]+?)\$", re.S)


def _symbols(math: str) -> set[str]:
    """Variable letters of a formula (LaTeX commands such as \\begin or \\lVert are layout, not variables)."""
    return set(re.findall(r"[A-Za-z]", re.sub(r"\\[A-Za-z]+", " ", math)))


def _new_claim(math: str, known: set[str], known_symbols: set[str]) -> bool:
    """A display formula that is not in the card or lesson is a new claim, unless it is a worked example:
    it has numbers and only uses symbols the fact-checked material already uses."""
    if _norm(math) in known:
        return False
    values = re.sub(r"[\^_](\{[^{}]*\}|\S)", " ", math)  # numbers in exponents or indices (x^2, v_1) are notation
    return not (re.search(r"\d", values) and _symbols(math) <= known_symbols)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def fact_guard(card: dict, base: dict[str, str], proposed: list[dict]) -> tuple[dict[str, str], list[dict]]:
    """Accept only prose revisions (SPEC §11). A revision is rejected when it targets something that is not a
    section of the lesson, reveals a hidden answer key or rubric, adds a display formula that is a new claim
    (not in the card or lesson, and not a numeric worked example in their notation), or grows far beyond the section. Checks, exercises and the card itself are never
    part of a revision: the job can only return section prose."""
    secs = {s["id"]: s for s in card.get("sections", [])}
    hidden = []
    for s in secs.values():
        if s.get("check"):
            hidden.append(s["check"].get("explanation", ""))
        if s.get("explain"):
            hidden += list(s["explain"].get("rubric", [])) + [s["explain"].get("exemplar", "")]
    hidden = [_norm(h) for h in hidden if len(_norm(h)) >= 25]
    material = " ".join([card.get(k) or "" for k in ("core", "formal", "why")] + list(base.values()))
    known_math = {_norm(m) for m in _DISPLAY_MATH.findall(material)}
    known_symbols = set().union(*[_symbols(a or b) for a, b in _ANY_MATH.findall(material)])
    accepted: dict[str, str] = {}
    rejected: list[dict] = []
    for p in proposed:
        sid, body = p.get("id"), (p.get("body") or "").strip()
        if sid not in secs or sid not in base:
            rejected.append({"sectionId": sid, "reason": "not a section of this lesson"})
        elif not body or body == base[sid].strip():
            continue
        elif len(body) > max(3 * len(base[sid]), 2500):
            rejected.append({"sectionId": sid, "reason": "far longer than the section it replaces"})
        elif any(h in _norm(body) for h in hidden):
            rejected.append({"sectionId": sid, "reason": "reveals a hidden answer key or grading rubric"})
        elif new := [m for m in _DISPLAY_MATH.findall(body) if _new_claim(m, known_math, known_symbols)]:
            rejected.append({"sectionId": sid, "reason": f"adds a formula that is not in the fact-checked card: $${new[0].strip()[:120]}$$"})
        else:
            accepted[sid] = body
    return accepted, rejected
