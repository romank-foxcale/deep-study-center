"""Gaps on the map (SPEC §51): open space where an idea is missing between two cells.

A gap sits on an arrow "A -> B" of the map (hold A before B) when B needs one to three ideas that are on no cell: the
step is too big without them. An agent finds gaps (job ``find_gaps``, prompt ``gap_find.md``): after a book is mapped,
and when the learner asks ("Find gaps"). Code checks every gap: both ends are ideas of the map, no proposed idea is
already on the map (same title), and no gap repeats an open one on the same arrow.

The map shows a gap as empty hexes between its two cells, one per missing idea. The learner can:
- **add** one idea to the map (``accept``): it becomes a cell (not explored yet) between A and B, linked A -> new -> B;
  the gap shrinks, and closes when nothing is left;
- **find more** (``more``): the agent looks at that arrow again; the gap grows (at most 3 ideas);
- say it is **not missing** (``dismiss``): the gap closes and is not proposed again for that arrow.
"""

from __future__ import annotations

import re
import secrets

from . import graph
from .db import DB, dumps, loads, now

MAX_IDEAS = 3
LIMIT = 6          # gaps per search
ARROWS_MAX = 160   # arrows the agent sees, at most
IDEAS_MAX = 450    # ideas the agent sees, at most

SCHEMA = {"type": "object", "required": ["gaps"], "properties": {"gaps": {"type": "array", "items": {
    "type": "object", "required": ["between", "ideas"], "properties": {
        "between": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "ideas": {"type": "array", "minItems": 1, "maxItems": MAX_IDEAS, "items": {
            "type": "object", "required": ["title", "says"], "properties": {"title": {"type": "string"}, "says": {"type": "string"}}}}}}}}}


class GapError(Exception):
    pass


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


# ---------------------------------------------------------------- reading

def open_gaps(db: DB) -> list[dict]:
    """The open gaps whose two ends are still on the map, with their ideas still to add."""
    known = {r["id"] for r in db.q("SELECT id FROM nodes")}
    out = []
    for r in db.q("SELECT * FROM gaps WHERE status='open' ORDER BY created_at, id"):
        ideas = [i for i in loads(r["ideas"], []) if i.get("status", "open") == "open"]
        if ideas and r["a"] in known and r["b"] in known:
            out.append({"id": r["id"], "between": [r["a"], r["b"]], "ideas": [{"title": i["title"], "says": i["says"]} for i in ideas],
                        "busy": bool(r["busy"])})
    return out


# ---------------------------------------------------------------- finding gaps

def find(db: DB, jobs, focus: str = "") -> int | None:
    """Queue a search for gaps (``focus``: a gap id to look at again, "find more")."""
    if jobs.active("find_gaps", focus=focus or ""):
        return None
    if focus:
        db.x("UPDATE gaps SET busy=1 WHERE id=?", (focus,))
    return jobs.enqueue("find_gaps", "Find more for a gap" if focus else "Find gaps in your map", {"focus": focus or ""})


def run(jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    focus = db.one("SELECT * FROM gaps WHERE id=?", (d.get("focus"),)) if d.get("focus") else None
    try:
        st = graph.states(db)
        nodes = {r["id"]: r for r in db.q("SELECT id, title, statement, origin FROM nodes")}
        links = graph.links(db)
        started = {nid for nid, s in st.items() if s.state in ("learning", "learned")}
        if focus:
            arrows = [(focus["a"], focus["b"])]
        else:
            near = {x for lk in links if lk["src"] in started or lk["dst"] in started for x in (lk["src"], lk["dst"])}
            arrows = [(lk["src"], lk["dst"]) for lk in links if lk["src"] in near and lk["dst"] in near]
            arrows.sort(key=lambda a: -((a[0] in started) + (a[1] in started)))
            arrows = arrows[:ARROWS_MAX]
        if not arrows:
            return {"gaps": 0, "why": "no arrows near what you study yet"}
        label = lambda i: f'{i}: {nodes[i]["title"]}'  # noqa: E731
        ideas = "\n".join(f'- {label(i)} — {(nodes[i]["statement"] or "")[:160]} ({st[i].state if i in st else "pending"})'
                          for i in list(nodes)[:IDEAS_MAX])
        arrows_text = "\n".join(f"- {label(a)} -> {label(b)}" for a, b in arrows if a in nodes and b in nodes)
        focus_text = ""
        if focus:
            have = [i["title"] for i in loads(focus["ideas"], []) if i.get("status", "open") == "open"]
            focus_text = (f"Look only at the arrow {label(focus['a'])} -> {label(focus['b'])}. These missing ideas are already proposed "
                          f"there: {', '.join(have) or '(none)'}. Add only ideas that are still missing; return the one gap with the new ideas.")
        jobs.progress(jid, f"reading {len(arrows)} arrow(s) of your map")
        out = jobs.call(jid, "Research", Call(
            prompt=prompt("gap_find", ideas=ideas, arrows=arrows_text, focus=focus_text, limit=1 if focus else LIMIT),
            schema=SCHEMA, model="sonnet", timeout=600))
        return {"gaps": save(db, out.get("gaps") or [], focus)}
    finally:
        if focus:
            db.x("UPDATE gaps SET busy=0 WHERE id=?", (focus["id"],))


def save(db: DB, found: list[dict], focus: dict | None = None) -> int:
    """Keep the gaps that pass the checks; with ``focus``, add new ideas to that gap only. Returns how many changed."""
    nodes = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    titles = {_norm(t) for t in nodes.values()}
    dismissed = {(r["a"], r["b"]) for r in db.q("SELECT a, b FROM gaps WHERE status='dismissed'")}
    opened = {(r["a"], r["b"]): r for r in db.q("SELECT * FROM gaps WHERE status='open'")}
    changed = 0
    for g in found[:LIMIT]:
        a, b = (list(g.get("between") or []) + ["", ""])[:2]
        if a not in nodes or b not in nodes or a == b or (a, b) in dismissed:
            continue
        if focus and (a, b) != (focus["a"], focus["b"]):
            continue
        row = opened.get((a, b))
        have = loads(row["ideas"], []) if row else []
        seen = titles | {_norm(i["title"]) for i in have}
        new = []
        for i in g.get("ideas") or []:
            t, says = " ".join(str(i.get("title") or "").split())[:80], " ".join(str(i.get("says") or "").split())[:400]
            if t and _norm(t) not in seen:
                seen.add(_norm(t))
                new.append({"title": t, "says": says, "status": "open"})
        room = MAX_IDEAS - sum(1 for i in have if i.get("status", "open") == "open")
        new = new[:max(0, room)]
        if not new:
            continue
        if row:
            db.x("UPDATE gaps SET ideas=?, updated_at=? WHERE id=?", (dumps(have + new), now(), row["id"]))
        else:
            gid = f"gap-{secrets.token_hex(4)}"
            db.x("INSERT INTO gaps(id, a, b, status, ideas, created_at, updated_at, busy) VALUES(?,?,?,?,?,?,?,0)",
                 (gid, a, b, "open", dumps(new), now(), now()))
            opened[(a, b)] = db.one("SELECT * FROM gaps WHERE id=?", (gid,))
        changed += 1
    return changed


# ---------------------------------------------------------------- the learner's choices

def _gap(db: DB, gid: str) -> dict:
    row = db.one("SELECT * FROM gaps WHERE id=? AND status='open'", (gid,))
    if not row:
        raise GapError("this gap is closed")
    return row


def accept(db: DB, gid: str, index: int) -> str:
    """Add one missing idea to the map: a new cell between the gap's two ideas. Returns the new idea's id."""
    row = _gap(db, gid)
    ideas = loads(row["ideas"], [])
    open_ = [i for i in ideas if i.get("status", "open") == "open"]
    if not 0 <= index < len(open_):
        raise GapError("no such idea in this gap")
    idea = open_[index]
    nid = f"n-gap-{secrets.token_hex(4)}"
    ts = now()
    with db.tx():
        db.conn.execute("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                        (nid, idea["title"], idea["says"], "concept", ts, "gap"))
        db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (nid, f'{idea["title"]} {idea["says"]}'))
        db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (row["a"], nid, gid, "gap"))
        db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (nid, row["b"], gid, "gap"))
        idea["status"], idea["nodeId"] = "added", nid
        left = [i for i in ideas if i.get("status", "open") == "open"]
        # what is still missing now sits between the new idea and B
        db.conn.execute("UPDATE gaps SET ideas=?, status=?, updated_at=? WHERE id=?",
                        (dumps(ideas), "open" if left else "filled", ts, gid))
        if left:
            db.conn.execute("UPDATE gaps SET a=? WHERE id=?", (nid, gid))
    return nid


def dismiss(db: DB, gid: str) -> None:
    _gap(db, gid)
    db.x("UPDATE gaps SET status='dismissed', updated_at=? WHERE id=?", (now(), gid))
