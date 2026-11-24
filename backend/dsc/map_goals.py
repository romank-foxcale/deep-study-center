"""Goals on the map (SPEC §53): a goal is a place at the edge of the learner's land, in its own direction.

The learner writes a goal in one line ("a top-level AI/ML engineer, like Karpathy"). The goal agent (job
``goal_research``, prompt ``goal_research.md``) writes its **direction** (one or two sentences), its **building
blocks** (ideas it needs: some are already cells of the map, the others are missing), and a **score** 0..1 for each
idea of the map: how much it moves the learner toward this goal. When new cells join the map (a book, a link,
"Teach me", a gap), the agent scores them for every goal (job ``goal_score``); a missing block the new cell is
becomes "on the map". An idea with no score yet counts as 0.1 (a side road).

The map places every cell along each goal's direction by its score: a building block goes toward the goal's star, a
side road away from it (``HexMap.layoutCells``). Several goals each have their own edge and color (the chosen mock
"C · Several goals"). The old roadmap goals (``goals``) are a different, older thing and are not touched.
"""

from __future__ import annotations

import re
import secrets

from .db import DB, dumps, loads, now

COLORS = ["#f5c451", "#c792ea", "#5fd0b0", "#ff8a65", "#7fd3ff", "#f07fa8"]
ANGLES = [-40, 150, 60, 240, -120, 15]   # the edge of each new goal, degrees (0 = right, -90 = up)
DEFAULT = 0.1                            # the score of an idea not scored yet
IDEAS_MAX = 450
MAX_BLOCKS = 12

RESEARCH_SCHEMA = {"type": "object", "required": ["direction", "blocks", "scores"], "properties": {
    "direction": {"type": "string"},
    "blocks": {"type": "array", "items": {"type": "object", "required": ["title", "says"], "properties": {
        "title": {"type": "string"}, "says": {"type": "string"}, "same_as": {"type": "string"}}}},
    "scores": {"type": "array", "items": {"type": "object", "required": ["id", "score"], "properties": {
        "id": {"type": "string"}, "score": {"type": "number"}}}}}}
SCORE_SCHEMA = {"type": "object", "required": ["scores"], "properties": {
    "scores": {"type": "array", "items": {"type": "object", "required": ["id", "score"], "properties": {
        "id": {"type": "string"}, "score": {"type": "number"}, "block": {"type": "string"}}}}}}


class GoalError(Exception):
    pass


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


# ---------------------------------------------------------------- reading

def view(db: DB) -> list[dict]:
    """The goals for the map: direction, color, edge, their open blocks, whether the agent is busy, and the scores."""
    out = []
    for g in db.q("SELECT * FROM map_goals WHERE status='active' ORDER BY created_at"):
        blocks = [{"id": b["id"], "title": b["title"], "says": b["says"]}
                  for b in db.q("SELECT * FROM goal_blocks WHERE goal_id=? AND status='open' ORDER BY id", (g["id"],))]
        scores = {r["node_id"]: round(r["score"], 3) for r in db.q("SELECT node_id, score FROM goal_scores WHERE goal_id=?", (g["id"],))}
        out.append({"id": g["id"], "title": g["title"], "direction": g["direction"], "color": g["color"], "angle": g["angle"],
                    "researched": bool(g["researched_at"]), "busy": bool(g["busy"]), "error": g["error"] or None,
                    "blocks": blocks, "scores": scores})
    return out


# ---------------------------------------------------------------- the learner's actions

def add(db: DB, jobs, title: str) -> str:
    title = " ".join((title or "").split())[:200]
    if len(title) < 4:
        raise GoalError("write the goal in a few words")
    n = db.one("SELECT COUNT(*) AS n FROM map_goals")["n"]
    gid = f"mg-{secrets.token_hex(4)}"
    db.x("""INSERT INTO map_goals(id, title, direction, color, angle, status, created_at, researched_at, busy, error)
            VALUES(?,?,?,?,?,?,?,?,?,?)""", (gid, title, "", COLORS[n % len(COLORS)], ANGLES[n % len(ANGLES)], "active", now(), None, 1, ""))
    jobs.enqueue("goal_research", f"Research the goal “{title[:60]}”", {"goal_id": gid})
    return gid


def rename(db: DB, jobs, gid: str, title: str) -> None:
    _goal(db, gid)
    title = " ".join((title or "").split())[:200]
    if len(title) < 4:
        raise GoalError("write the goal in a few words")
    db.x("UPDATE map_goals SET title=?, busy=1 WHERE id=?", (title, gid))
    jobs.enqueue("goal_research", f"Research the goal “{title[:60]}” again", {"goal_id": gid})


def remove(db: DB, gid: str) -> None:
    _goal(db, gid)
    db.x("UPDATE map_goals SET status='removed' WHERE id=?", (gid,))


def add_block(db: DB, gid: str, bid: int) -> str:
    """A missing building block joins the map as a cell (not explored yet). Returns the new idea's id."""
    _goal(db, gid)
    b = db.one("SELECT * FROM goal_blocks WHERE id=? AND goal_id=? AND status='open'", (bid, gid))
    if not b:
        raise GoalError("this block is already on your map")
    nid = f"n-goal-{secrets.token_hex(4)}"
    with db.tx():
        db.conn.execute("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                        (nid, b["title"], b["says"], "concept", now(), "goal"))
        db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (nid, f'{b["title"]} {b["says"]}'))
        db.conn.execute("UPDATE goal_blocks SET status='on_map', node_id=? WHERE id=?", (nid, bid))
        db.conn.execute("INSERT OR REPLACE INTO goal_scores(goal_id, node_id, score, at) VALUES(?,?,?,?)", (gid, nid, 1.0, now()))
    return nid


def _goal(db: DB, gid: str) -> dict:
    g = db.one("SELECT * FROM map_goals WHERE id=? AND status='active'", (gid,))
    if not g:
        raise GoalError("no such goal")
    return g


# ---------------------------------------------------------------- the goal agent

def _ideas_text(db: DB, ids: list[str] | None = None) -> str:
    from . import graph
    graph.sync(db)  # every lesson has its idea on the map
    rows = db.q("SELECT id, title, statement FROM nodes ORDER BY created_at, id")
    if ids is not None:
        keep = set(ids)
        rows = [r for r in rows if r["id"] in keep]
    return "\n".join(f'- {r["id"]}: {r["title"]} — {(r["statement"] or "")[:140]}' for r in rows[:IDEAS_MAX]) or "(the map is empty)"


def _save_scores(db: DB, gid: str, scores: list[dict], known: set[str]) -> int:
    n = 0
    with db.tx():
        for s in scores:
            nid = str(s.get("id") or "")
            if nid not in known:
                continue
            try:
                v = max(0.0, min(1.0, float(s.get("score"))))
            except (TypeError, ValueError):
                continue
            db.conn.execute("INSERT OR REPLACE INTO goal_scores(goal_id, node_id, score, at) VALUES(?,?,?,?)", (gid, nid, v, now()))
            n += 1
    return n


def research(jobs, jid: int, d: dict) -> dict:
    """Direction, building blocks and the scores of every idea for one goal."""
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    gid = d["goal_id"]
    g = _goal(db, gid)
    try:
        jobs.progress(jid, f"researching “{g['title'][:60]}”: its direction and building blocks")
        out = jobs.call(jid, "Research", Call(prompt=prompt("goal_research", goal=g["title"], ideas=_ideas_text(db)),
                                               schema=RESEARCH_SCHEMA, model="opus", timeout=900))
        known = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
        by_title = {_norm(t): i for i, t in known.items()}
        with db.tx():
            db.conn.execute("DELETE FROM goal_blocks WHERE goal_id=? AND status='open'", (gid,))
            db.conn.execute("DELETE FROM goal_scores WHERE goal_id=?", (gid,))
        n_scores = _save_scores(db, gid, out.get("scores") or [], set(known))
        blocks = 0
        for b in (out.get("blocks") or [])[:MAX_BLOCKS]:
            title, says = " ".join(str(b.get("title") or "").split())[:80], " ".join(str(b.get("says") or "").split())[:300]
            if not title:
                continue
            same = b.get("same_as") if b.get("same_as") in known else by_title.get(_norm(title))
            if same:  # already a cell: a building block on the map
                db.x("INSERT OR REPLACE INTO goal_scores(goal_id, node_id, score, at) VALUES(?,?,?,?)", (gid, same, 1.0, now()))
                db.x("INSERT INTO goal_blocks(goal_id, title, says, node_id, status, created_at) VALUES(?,?,?,?,?,?)",
                     (gid, title, says, same, "on_map", now()))
            else:
                db.x("INSERT INTO goal_blocks(goal_id, title, says, node_id, status, created_at) VALUES(?,?,?,?,?,?)",
                     (gid, title, says, None, "open", now()))
            blocks += 1
        db.x("UPDATE map_goals SET direction=?, researched_at=?, busy=0, error='' WHERE id=?",
             (" ".join(str(out.get("direction") or "").split())[:500], now(), gid))
        return {"scores": n_scores, "blocks": blocks}
    except Exception as e:  # noqa: BLE001 - the panel shows the error
        db.x("UPDATE map_goals SET busy=0, error=? WHERE id=?", (str(e)[:300], gid))
        raise


def unscored(db: DB) -> dict[str, list[str]]:
    """goal -> the ideas it has no score for yet (new cells since it was researched)."""
    from . import graph
    graph.sync(db)
    ids = [r["id"] for r in db.q("SELECT id FROM nodes")]
    out = {}
    for g in db.q("SELECT id FROM map_goals WHERE status='active' AND researched_at IS NOT NULL AND busy=0"):
        have = {r["node_id"] for r in db.q("SELECT node_id FROM goal_scores WHERE goal_id=?", (g["id"],))}
        missing = [i for i in ids if i not in have]
        if missing:
            out[g["id"]] = missing[:200]
    return out


def ensure_scores(db: DB, jobs) -> None:
    """Score new cells for every goal (called when the map is read; one job per goal at a time)."""
    for gid, ids in unscored(db).items():
        if not jobs.active("goal_score", goal_id=gid):
            jobs.enqueue("goal_score", "Place new cells for your goal", {"goal_id": gid, "ids": ids})


def score(jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    gid = d["goal_id"]
    g = _goal(db, gid)
    ids = [i for i in d.get("ids") or [] if db.one("SELECT 1 FROM nodes WHERE id=?", (i,))]
    if not ids:
        return {"scores": 0}
    blocks = db.q("SELECT id, title, says FROM goal_blocks WHERE goal_id=? AND status='open'", (gid,))
    out = jobs.call(jid, "Research", Call(prompt=prompt(
        "goal_score", goal=g["title"], direction=g["direction"] or "(none)", ideas=_ideas_text(db, ids),
        blocks="\n".join(f'- {b["id"]}: {b["title"]} — {b["says"]}' for b in blocks) or "(none)"),
        schema=SCORE_SCHEMA, model="sonnet", timeout=600))
    scores = out.get("scores") or []
    n = _save_scores(db, gid, scores, set(ids))
    with db.tx():
        for i in ids:  # an idea the agent left out is a side road: it is scored, so it is not asked about again
            db.conn.execute("INSERT OR IGNORE INTO goal_scores(goal_id, node_id, score, at) VALUES(?,?,?,?)", (gid, i, DEFAULT, now()))
        open_ids = {str(b["id"]) for b in blocks}
        for s in scores:  # a new cell is a missing block: the block is on the map now
            if str(s.get("block") or "") in open_ids and s.get("id") in ids:
                db.conn.execute("UPDATE goal_blocks SET status='on_map', node_id=? WHERE id=?", (s["id"], int(s["block"])))
                db.conn.execute("INSERT OR REPLACE INTO goal_scores(goal_id, node_id, score, at) VALUES(?,?,?,?)", (gid, s["id"], 1.0, now()))
    return {"scores": n}
