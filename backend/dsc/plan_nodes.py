"""The steps of a planned lesson as ideas on the knowledge map (SPEC §46).

A step lesson (§43) teaches one plan node per step: foundations and reasoning steps are small ideas of their own, so
each becomes a node of the map (id ``pn-<lesson>-<key>``, kind "step", origin "plan"), placed next to its lesson in the
lesson's book and chapter. A step the plan links to an idea already on the map (``linksTo``) is that idea: no copy is
made, and its check counts on that idea. The plan's edges become links: a held node's map idea -> the step that builds on it, step ->
step, and the last steps -> the lesson's own idea (the plan's goal). Formula nodes are not ideas of their own: the
formula is already in the Formulas country, so an edge through one is joined across it.

- **State.** A step's check and explain-back count as evidence on the step's idea as well as on the lesson
  (``item_nodes``), and practice can target a step's idea directly. One check alone does not make an idea learned,
  so a step whose own evidence is not wrong takes its lesson's state when the lesson is learned.
- **Kept in step.** ``sync`` (from ``graph.sync``) maps each step lesson's newest card once per card version; a new
  card (re-plan and approve, or "Write it now without a plan") replaces or removes the lesson's step ideas.
"""

from __future__ import annotations

from .db import DB, loads, now

PREFIX = "pn-"
MAPPED = ("foundation", "step")


def node_id(cid: str, key: str) -> str:
    return f"{PREFIX}{cid}-{key}"


def sync(db: DB, conn_tx) -> None:
    """Map every step lesson whose newest card is not mapped yet; remove the steps of lessons that are not step
    lessons any more. ``conn_tx`` is graph._writing (a transaction that also works inside one already open)."""
    newest = {r["concept_id"]: r for r in db.q(
        """SELECT c.concept_id, c.version, instr(c.body, '"steps": true') > 0 AS steps FROM cards c
           JOIN (SELECT concept_id, MAX(version) AS v FROM cards GROUP BY concept_id) m
           ON m.concept_id = c.concept_id AND m.v = c.version""")}
    mapped = {r["concept_id"]: r["card_version"] for r in db.q("SELECT concept_id, card_version FROM plan_maps")}
    todo = [cid for cid, r in newest.items() if r["steps"] and mapped.get(cid) != r["version"]]
    gone = [cid for cid in mapped if cid not in newest or not newest[cid]["steps"]]
    if not todo and not gone:
        return
    with conn_tx(db):
        for cid in gone:
            _clear(db, cid)
            db.conn.execute("DELETE FROM plan_maps WHERE concept_id=?", (cid,))
        for cid in todo:
            _map(db, cid, newest[cid]["version"])
        _orphans(db)


def _orphans(db: DB) -> None:
    """Step ideas that no lesson owns any more (a lesson deleted, or a re-plan that left a step out)."""
    for (nid,) in db.conn.execute("""SELECT id FROM nodes WHERE origin='plan'
                                     AND id NOT IN (SELECT node_id FROM plan_nodes WHERE own=1)""").fetchall():
        db.conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
        db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (nid,))
        db.conn.execute("DELETE FROM links WHERE src=? OR dst=?", (nid, nid))


def _clear(db: DB, cid: str) -> None:
    ids = [r[0] for r in db.conn.execute("SELECT node_id FROM plan_nodes WHERE concept_id=? AND own=1", (cid,)).fetchall()]
    for nid in ids:
        db.conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
        db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (nid,))
        db.conn.execute("DELETE FROM links WHERE (src=? OR dst=?) AND origin='plan'", (nid, nid))
    db.conn.execute("DELETE FROM links WHERE origin='plan' AND why=?", (cid,))
    db.conn.execute("DELETE FROM plan_nodes WHERE concept_id=?", (cid,))


def _map(db: DB, cid: str, version: int) -> None:
    _clear(db, cid)
    body = loads(db.conn.execute("SELECT body FROM cards WHERE concept_id=? AND version=?", (cid, version)).fetchone()[0], {})
    plan_row = db.conn.execute("SELECT nodes, edges FROM lesson_graphs WHERE concept_id=? AND version=?",
                               (cid, body.get("planVersion") or 0)).fetchone()
    db.conn.execute("INSERT OR REPLACE INTO plan_maps(concept_id, card_version) VALUES(?,?)", (cid, version))
    lesson = db.conn.execute("SELECT node_id FROM concept_nodes WHERE concept_id=?", (cid,)).fetchone()
    lesson_node = lesson[0] if lesson else cid
    plan_nodes = loads(plan_row[0], []) if plan_row else []
    edges = loads(plan_row[1], []) if plan_row else []
    ts = now()
    known = {r[0] for r in db.conn.execute("SELECT id FROM nodes").fetchall()}
    linked = {n["key"]: n.get("linksTo") for n in plan_nodes if n.get("linksTo") in known and n["linksTo"] != lesson_node}
    target: dict[str, str] = {}  # plan key -> map node (absent: joined across, or nothing on the map)
    for i, s in enumerate(body.get("sections", [])):
        key = s.get("node")
        if not key or s.get("kind") not in MAPPED:
            continue
        if key in linked:  # an idea already on the map: the step is that idea
            db.conn.execute("INSERT INTO plan_nodes(concept_id, node_key, node_id, section_id, ord, own) VALUES(?,?,?,?,?,0)",
                            (cid, key, linked[key], s["id"], i))
            target[key] = linked[key]
            continue
        nid = node_id(cid, key)
        title, says = (s.get("heading") or key).strip(), (s.get("purpose") or "").strip()
        db.conn.execute("INSERT OR REPLACE INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                        (nid, title, says, "step", ts, "plan"))
        db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (nid, f"{title} {says}"))
        db.conn.execute("INSERT INTO plan_nodes(concept_id, node_key, node_id, section_id, ord) VALUES(?,?,?,?,?)",
                        (cid, key, nid, s["id"], i))
        target[key] = nid
    for n in plan_nodes:
        if n.get("kind") == "goal":
            target[n["key"]] = lesson_node
        elif n.get("kind") == "held" and n.get("linksTo") in known:
            target[n["key"]] = n["linksTo"]
    own = {v for k, v in target.items() if v.startswith(PREFIX)}
    joined = {n["key"] for n in plan_nodes if n.get("kind") not in ("goal", "held") and n["key"] not in target}
    for src, dst in _join(edges, joined):
        a, b = target.get(src), target.get(dst)
        if a and b and a != b and (a in own or b in own):
            db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (a, b, cid, "plan"))


def _join(edges: list, joined: set[str]) -> list[tuple[str, str]]:
    """The edges with every node in ``joined`` taken out: a -> j -> b becomes a -> b."""
    out = {(a, b) for a, b in (tuple(e[:2]) for e in edges if len(e) >= 2) if a not in joined and b not in joined}
    into: dict[str, set[str]] = {}
    outof: dict[str, set[str]] = {}
    for a, b in (tuple(e[:2]) for e in edges if len(e) >= 2):
        outof.setdefault(a, set()).add(b)
        into.setdefault(b, set()).add(a)

    def ends(start: str, step: dict[str, set[str]]) -> set[str]:
        seen, todo, found = set(), [start], set()
        while todo:
            x = todo.pop()
            for y in step.get(x, ()):
                if y in seen:
                    continue
                seen.add(y)
                if y in joined:
                    todo.append(y)
                else:
                    found.add(y)
        return found
    for j in joined:
        for a in ends(j, into):
            for b in ends(j, outof):
                if a != b:
                    out.add((a, b))
    return sorted(out)


def prune(db: DB) -> None:
    """Remove the step ideas of deleted lessons (inside graph.prune's transaction)."""
    for (cid,) in db.conn.execute("SELECT DISTINCT concept_id FROM plan_nodes WHERE concept_id NOT IN (SELECT id FROM concepts)").fetchall():
        _clear(db, cid)
    db.conn.execute("DELETE FROM plan_maps WHERE concept_id NOT IN (SELECT id FROM concepts)")
    _orphans(db)


def rows(db: DB) -> dict[str, dict]:
    """node id -> {conceptId, key, sectionId, ord} for every step idea made for a lesson (not the linked ones)."""
    return {r["node_id"]: {"conceptId": r["concept_id"], "key": r["node_key"], "sectionId": r["section_id"], "ord": r["ord"]}
            for r in db.q("SELECT * FROM plan_nodes WHERE own=1")}


def item_nodes(db: DB) -> dict[tuple[str, str], str]:
    """(lesson, item id) -> step idea, for the check and explain-back of every mapped step."""
    pn = db.q("SELECT node_id, concept_id, section_id FROM plan_nodes")
    if not pn:
        return {}
    by_section = {(r["concept_id"], r["section_id"]): r["node_id"] for r in pn}
    out = {}
    for cid in {r["concept_id"] for r in pn}:
        row = db.one("SELECT body FROM cards WHERE concept_id=? ORDER BY version DESC LIMIT 1", (cid,))
        for s in loads(row["body"], {}).get("sections", []) if row else []:
            nid = by_section.get((cid, s["id"]))
            if not nid:
                continue
            for part in ("check", "explain"):
                if (s.get(part) or {}).get("id"):
                    out[(cid, s[part]["id"])] = nid
    return out
