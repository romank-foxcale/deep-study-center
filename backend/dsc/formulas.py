"""Formula notes (SPEC §33): hover a formula in a lesson to see what it is, what each symbol means, and where you met it.

A job reads the lesson's formulas (display formulas and the longer inline ones) once and writes a note for each: a name,
what it says in one or two sentences, its symbols, and the graph ideas it belongs to (this lesson, the lessons it builds
on, other books and goals). The notes are saved by the formula's TeX without spaces, so the page finds the note of the
formula under the mouse from KaTeX's own TeX annotation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

MAX = 25
_DISPLAY = re.compile(r"\$\$([\s\S]+?)\$\$")
_INLINE = re.compile(r"(?<![\\$])\$([^$\n]+?)\$(?!\$)")
_WORTH = re.compile(r"=|\\frac|\\sum|\\prod|\\int|\\log|\\exp|\\nabla|\\partial|\\leftarrow|\\mathbb\{E\}|\^|_\{")

SCHEMA = {"type": "object", "required": ["formulas"], "properties": {"formulas": {"type": "array", "items": {
    "type": "object", "required": ["n", "name", "meaning", "kind", "formula", "symbols", "ideas"], "properties": {
        "n": {"type": "integer"}, "name": {"type": "string"}, "meaning": {"type": "string"},
        "kind": {"enum": ["idea", "step"]}, "formula": {"type": "string"},
        "symbols": {"type": "array", "items": {"type": "object", "required": ["tex", "meaning"], "properties": {
            "tex": {"type": "string"}, "meaning": {"type": "string"}}}},
        "ideas": {"type": "array", "items": {"type": "string"}}}}}}}


def key(tex: str) -> str:
    """The formula's TeX without any white space (the page computes the same key from KaTeX's annotation)."""
    return re.sub(r"\s+", "", tex or "")[:600]


def extract(text: str) -> list[str]:
    """Display formulas, then inline formulas that say something (an equation, a sum, a fraction …), in order, unique."""
    out: list[str] = []
    for m in _DISPLAY.finditer(text or ""):
        out.append(m.group(1).strip())
    rest = _DISPLAY.sub(" ", text or "")
    for m in _INLINE.finditer(rest):
        t = m.group(1).strip()
        if len(key(t)) >= 6 and _WORTH.search(t) and re.search(r"[A-Za-z]", re.sub(r"\\[A-Za-z]+", "", t)):  # a symbol, not 2 \times 3 = 6
            out.append(t)
    seen, uniq = set(), []
    for t in out:
        if key(t) and key(t) not in seen:
            seen.add(key(t))
            uniq.append(t)
    return uniq[:MAX]


def _lesson_text(db: DB, cid: str) -> tuple[str, str]:
    """The text the page shows for this lesson (the newest prose per section) and the book summaries."""
    from . import state
    from .writer import effective_sections
    card = state.latest_card(db, cid) or {}
    parts, book = [], []
    for s in effective_sections(db, cid, card):
        row = db.one("SELECT body FROM prose WHERE concept_id=? AND section_id=? ORDER BY card_version DESC, created_at DESC LIMIT 1",
                     (cid, s["id"]))
        if row:
            parts.append(row["body"])
        if (s.get("book") or {}).get("summary"):
            book.append(s["book"]["summary"])
    return "\n\n".join(parts + book), card.get("formal") or ""


def missing(db: DB, cid: str) -> list[str]:
    text, formal = _lesson_text(db, cid)
    have = {r["key"] for r in db.q("SELECT key FROM formula_notes WHERE concept_id=?", (cid,))}
    return [t for t in extract(f"{text}\n\n{formal}") if key(t) not in have]


def stale(db: DB, cid: str) -> bool:
    """A formula lesson was made after this lesson's notes were matched: match them again (a form may now be known)."""
    if db.one("SELECT 1 FROM formula_notes WHERE concept_id=? AND matched_at IS NULL", (cid,)):
        return True  # notes written before kinds and matching existed
    last = db.one("SELECT MAX(created_at) AS t FROM formula_lessons")["t"]
    if not last:
        return False
    return bool(db.one("SELECT 1 FROM formula_notes WHERE concept_id=? AND kind='idea' AND COALESCE(matched_at, '') < ?",
                       (cid, last)))


def ensure(db: DB, jobs: Jobs, cid: str) -> bool:
    """Queue the notes for formulas of this lesson that have none yet, or a new match against the formula lessons.
    True when a job was queued."""
    if db.meta("formula_notes", "1") != "1" or jobs.active("formula_notes", concept_id=cid):
        return False
    if not missing(db, cid) and not stale(db, cid):
        return False
    jobs.enqueue("formula_notes", "Explain the formulas of this lesson", {"concept_id": cid})
    return True


def _ideas(db: DB, cid: str, text: str) -> dict[str, str]:
    """Graph ideas a formula may belong to: this lesson's idea, what it builds on and leads to, and word matches."""
    from . import graph
    own = graph.node_of(db).get(cid, cid)
    ls = graph.links(db)
    near = [own] + [lk["src"] for lk in ls if lk["dst"] == own] + [lk["dst"] for lk in ls if lk["src"] == own]
    found = [c["id"] for c in graph.candidates(db, text[:4000], k=25)]
    want = list(dict.fromkeys(near + found))[:45]
    if not want:
        return {}
    rows = db.q(f"SELECT id, title FROM nodes WHERE id IN ({','.join('?' * len(want))})", want)
    return {r["id"]: r["title"] for r in rows}


def run(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    cid = d["concept_id"]
    todo = missing(db, cid)
    if not todo:
        return _rematch(jobs, jid, cid) if stale(db, cid) else {"formulas": 0}
    text, _ = _lesson_text(db, cid)
    title = (db.one("SELECT title FROM concepts WHERE id=?", (cid,)) or {}).get("title", "")
    ideas = _ideas(db, cid, f"{title} {text}")
    jobs.progress(jid, f"explaining {len(todo)} formula(s)")
    out = jobs.call(jid, "Formula notes", Call(
        prompt=prompt("formula_notes", lesson=title, text=text[:12000],
                      formulas="\n".join(f"{n + 1}. {t}" for n, t in enumerate(todo)),
                      ideas="\n".join(f"- {i}: {t}" for i, t in ideas.items()) or "(none)", known=_known_text(db, cid)),
        schema=SCHEMA, model="sonnet", timeout=300))
    ts, saved = now(), 0
    with db.tx():
        for f in out.get("formulas") or []:
            n = f.get("n")
            if not isinstance(n, int) or not 1 <= n <= len(todo):
                continue
            body = {"name": (f.get("name") or "").strip()[:120], "meaning": (f.get("meaning") or "").strip()[:600],
                    "symbols": [{"tex": (s.get("tex") or "")[:60], "meaning": (s.get("meaning") or "")[:200]}
                                for s in (f.get("symbols") or [])[:10] if s.get("tex")],
                    "ideas": [i for i in dict.fromkeys(f.get("ideas") or []) if i in ideas][:4]}
            fid = _formula_id(db, f.get("formula"), cid)
            db.conn.execute("""INSERT OR REPLACE INTO formula_notes(concept_id, key, tex, body, created_at, kind, formula_id, matched_at)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (cid, key(todo[n - 1]), todo[n - 1], dumps(body), ts, "step" if f.get("kind") == "step" else "idea",
                             fid, ts))
            saved += 1
    if stale(db, cid):  # older notes of this lesson: match them against formula lessons made since
        _rematch(jobs, jid, cid)
    return {"formulas": saved}


def _formula_id(db: DB, fid: object, cid: str) -> str | None:
    """A formula lesson id the agent matched, if it exists and is not this lesson itself."""
    if not isinstance(fid, str) or not fid or fid == cid:
        return None
    return fid if db.one("SELECT 1 FROM formula_lessons WHERE id=?", (fid,)) else None


def _known_text(db: DB, cid: str) -> str:
    """The learner's formula lessons, with their forms, for matching (one line each)."""
    rows = db.q("SELECT id, name FROM formula_lessons WHERE id != ? ORDER BY created_at", (cid,))
    if not rows:
        return "(none yet)"
    lines = []
    for r in rows:
        forms = [f["tex"] for f in db.q("SELECT tex FROM formula_forms WHERE formula_id=? ORDER BY added_at", (r["id"],))]
        lines.append(f'- {r["id"]}: {r["name"]}. Forms: ' + " | ".join(f"${t}$" for t in forms[:4]))
    return "\n".join(lines)


MATCH_SCHEMA = {"type": "object", "required": ["matches"], "properties": {"matches": {"type": "array", "items": {
    "type": "object", "required": ["n", "kind", "formula"], "properties": {"n": {"type": "integer"}, "kind": {"enum": ["idea", "step"]},
                                                                        "formula": {"type": "string"}}}}}}


def _rematch(jobs: Jobs, jid: int, cid: str) -> dict:
    """Match this lesson's formula notes against the formula lessons made since they were written."""
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    rows = db.q("""SELECT key, tex, body FROM formula_notes WHERE concept_id=? AND (kind='idea' OR matched_at IS NULL)
                   ORDER BY created_at, rowid""", (cid,))
    ts = now()
    if not rows:
        return {"matched": 0}
    out = jobs.call(jid, "Formula notes", Call(
        prompt=prompt("formula_match", formulas="\n".join(f'{n + 1}. {loads(r["body"], {}).get("name", "")}: ${r["tex"]}$'
                                                           for n, r in enumerate(rows)), known=_known_text(db, cid)),
        schema=MATCH_SCHEMA, model="sonnet", timeout=180))
    found = {m.get("n"): _formula_id(db, m.get("formula"), cid) for m in out.get("matches") or []}
    kinds = {m.get("n"): m.get("kind") for m in out.get("matches") or [] if m.get("kind") in ("idea", "step")}
    with db.tx():
        for n, r in enumerate(rows):
            db.conn.execute("""UPDATE formula_notes SET formula_id=COALESCE(?, formula_id), kind=COALESCE(?, kind), matched_at=?
                               WHERE concept_id=? AND key=?""", (found.get(n + 1), kinds.get(n + 1), ts, cid, r["key"]))
    return {"matched": sum(1 for v in found.values() if v)}


KNOWN = ("learned",)


def status(db: DB, cid: str, k: str, kind: str, fid: str | None, st: dict) -> tuple[str, dict | None]:
    """green: you learned the formula lesson and this form is one of its forms; orange: a formula lesson exists but this
    form is new to it; gray: no formula lesson yet (or not learned yet); step: a step of a derivation (neutral)."""
    from . import graph
    exact = db.one("SELECT formula_id FROM formula_forms WHERE key=? ORDER BY added_at LIMIT 1", (k,))
    fid = (exact or {}).get("formula_id") or fid
    if kind == "step" and not fid:
        return "step", None
    if not fid:
        return "gray", None
    row = db.one("SELECT f.id, f.name, c.title FROM formula_lessons f LEFT JOIN concepts c ON c.id = f.id WHERE f.id=?", (fid,))
    if not row:
        return ("step" if kind == "step" else "gray"), None
    node = graph.node_of(db).get(fid, fid)
    s = st.get(node)
    state_ = s.state if s else "pending"
    same = bool(exact) or bool(db.one("SELECT 1 FROM formula_forms WHERE formula_id=? AND key=?", (fid, k)))
    missing = db.one("SELECT COUNT(*) AS n FROM formula_blocks WHERE formula_id=? AND ref IS NULL AND basic=0", (fid,))["n"]
    info = {"id": fid, "title": row["title"] or row["name"], "state": state_, "sameForm": same, "here": fid == cid, "missing": missing}
    if not same:
        return "orange", info
    return ("green" if state_ in KNOWN else "gray"), info


def notes(db: DB, cid: str) -> dict[str, dict]:
    """key -> note for the page, each idea with its title, state and where to open it (a lesson, a book or the map),
    and the frame color: green, orange, gray or step."""
    from . import graph
    rows = db.q("SELECT key, body, kind, formula_id FROM formula_notes WHERE concept_id=?", (cid,))
    if not rows:
        return {}
    st = graph.states(db)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    lesson_of: dict[str, str] = {}
    for r in db.q("SELECT concept_id, node_id FROM concept_nodes"):
        lesson_of.setdefault(r["node_id"], r["concept_id"])
    out = {}
    for r in rows:
        b = loads(r["body"], {})
        b["ideas"] = [{"id": i, "title": titles.get(i, i), "state": st[i].state if i in st else "pending",
                       "lesson": lesson_of.get(i), "here": lesson_of.get(i) == cid} for i in b.get("ideas", [])]
        b["kind"] = r["kind"] or "idea"
        b["status"], b["formula"] = status(db, cid, r["key"], b["kind"], r["formula_id"], st)
        out[r["key"]] = b
    return out
