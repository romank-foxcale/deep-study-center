"""One knowledge graph of everything the learner knows (SPEC §21). Step 3 of the knowledge-graph rework.

A **node** is one idea. Every concept (a lesson inside a goal's module) points to one node through ``concept_nodes``;
several concepts in different goals can point to the same node, so an idea learned for one goal is known in every
goal. A **link** says "this idea is used to reason toward that idea" (basic -> advanced). Links come from the
concepts' prerequisites (mapped to their nodes) and from the ``links`` table (added by later steps, e.g. sessions).

The learner's state is computed **per node from all evidence of all its concepts**, with the same rules as a concept
(``engine.derive_concepts``). ``state.concept_states`` uses the node's evidence, so a concept in goal B shows what was
learned for the same node in goal A.

Every new concept gets its own node automatically (``sync``, called before any read), so the code that inserts
concepts does not need to know about nodes. Research can map a new concept to an existing node instead (``same_as``).
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from . import engine
from .db import DB, loads, now

_WORD = re.compile(r"[\w']+")
_STOP = {"the", "and", "for", "with", "from", "into", "that", "this", "what", "how", "why", "are", "its", "their", "your",
         "you", "of", "to", "in", "on", "a", "an", "is", "as", "by", "or", "at", "be", "it", "we", "using", "use", "via"}


@contextmanager
def _writing(db: DB):
    """A transaction that also works inside one this thread already has open (sync runs from read paths)."""
    with db.lock:  # RLock: waits for other threads' transactions, re-enters our own
        if db.conn.in_transaction:
            yield
            return
        db.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            db.conn.execute("ROLLBACK")
            raise
        db.conn.execute("COMMIT")


def sync(db: DB) -> int:
    """Give every concept without a node its own node (node id = concept id). Returns how many were added."""
    rows = db.q("""SELECT c.id, c.title, c.objective FROM concepts c LEFT JOIN concept_nodes n ON n.concept_id = c.id
                   WHERE n.concept_id IS NULL""")
    if not rows:
        return 0
    ts = now()
    with _writing(db):
        for r in rows:
            db.conn.execute("INSERT OR IGNORE INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                            (r["id"], r["title"], r["objective"], "concept", ts, "concept"))
            if db.conn.execute("SELECT changes()").fetchone()[0]:
                db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (r["id"], f'{r["title"]} {r["objective"]}'))
            db.conn.execute("INSERT OR IGNORE INTO concept_nodes(concept_id, node_id) VALUES(?,?)", (r["id"], r["id"]))
    return len(rows)


def node_of(db: DB) -> dict[str, str]:
    """concept id -> node id, for every concept."""
    sync(db)
    return {r["concept_id"]: r["node_id"] for r in db.q("SELECT concept_id, node_id FROM concept_nodes")}


def attach(db: DB, concept_id: str, node_id: str) -> None:
    """Point a concept at an existing node (research found the same idea). Call before ``sync`` sees the concept."""
    db.conn.execute("INSERT OR REPLACE INTO concept_nodes(concept_id, node_id) VALUES(?,?)", (concept_id, node_id))


def prune(db: DB) -> None:
    """Remove mappings of deleted concepts and concept nodes that no concept uses any more."""
    with _writing(db):
        db.conn.execute("DELETE FROM concept_nodes WHERE concept_id NOT IN (SELECT id FROM concepts)")
        gone = [r[0] for r in db.conn.execute("""SELECT id FROM nodes WHERE origin='concept'
                                                 AND id NOT IN (SELECT node_id FROM concept_nodes)""").fetchall()]
        for nid in gone:
            db.conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
            db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (nid,))
            db.conn.execute("DELETE FROM links WHERE src=? OR dst=?", (nid, nid))


def evidence_for(db: DB, concept_ids: list[str]) -> list[dict]:
    """The evidence of these concepts, plus the evidence of every other concept on the same nodes, given to the
    local concept. An explain-back passed on a sibling counts as this concept's explain-back."""
    if not concept_ids:
        return []
    nodes = node_of(db)
    local_by_node: dict[str, list[str]] = {}
    for cid in concept_ids:
        local_by_node.setdefault(nodes.get(cid, cid), []).append(cid)
    # sibling concepts on the same nodes, and evidence recorded on the node itself (study sessions)
    siblings = sorted({c for c, n in nodes.items() if n in local_by_node} | set(local_by_node))
    rows = db.q(f"SELECT * FROM evidence WHERE concept_id IN ({','.join('?' * len(siblings))}) ORDER BY id", siblings)
    explain = _explain_items(db, concept_ids)
    local = set(concept_ids)
    out = []
    for r in rows:
        if r["concept_id"] in local:
            out.append(r)
        for cid in local_by_node.get(nodes.get(r["concept_id"], r["concept_id"]), []):
            if cid == r["concept_id"]:
                continue
            e = dict(r, concept_id=cid)
            if str(r["item_id"]).startswith("e-") and explain.get(cid):
                e["item_id"] = explain[cid][0]
            out.append(e)
    out.sort(key=lambda e: e["id"])
    return out


def _explain_items(db: DB, concept_ids: list[str]) -> dict[str, list[str]]:
    out = {}
    for cid in concept_ids:
        row = db.one("SELECT body FROM cards WHERE concept_id=? ORDER BY version DESC LIMIT 1", (cid,))
        out[cid] = [s["explain"]["id"] for s in loads(row["body"], {}).get("sections", []) if s.get("explain")] if row else []
    return out


def candidates(db: DB, text: str, k: int = 15, exclude_module: str | None = None) -> list[dict]:
    """Existing nodes that may be the same idea as ``text`` (full-text search, best first)."""
    sync(db)
    terms = [t for t in dict.fromkeys(_WORD.findall(text.lower())) if len(t) > 2 and t not in _STOP][:16]
    if not terms:
        return []
    match = " OR ".join(f'"{t}"*' for t in terms)
    with db.lock:
        rows = db.conn.execute("""SELECT node_id FROM node_fts WHERE node_fts MATCH ? ORDER BY bm25(node_fts) LIMIT ?""",
                               (match, k * 2)).fetchall()
    skip = set()
    if exclude_module:
        skip = {r["node_id"] for r in db.q("""SELECT n.node_id FROM concept_nodes n JOIN concepts c ON c.id = n.concept_id
                                               WHERE c.module_id=?""", (exclude_module,))}
    out = []
    for (nid,) in rows:
        if nid in skip:
            continue
        n = db.one("SELECT id, title, statement FROM nodes WHERE id=?", (nid,))
        if n:
            out.append(n)
        if len(out) >= k:
            break
    return out


def candidates_text(nodes: list[dict]) -> str:
    return "\n".join(f'- {n["id"]}: {n["title"]} - {n["statement"][:200]}' for n in nodes) or "(none)"


def links(db: DB) -> list[dict]:
    """All links: from concept prerequisites (mapped to nodes) and from the links table. No self-links, no duplicates."""
    nodes = node_of(db)
    seen: dict[tuple[str, str], dict] = {}
    for c in db.q("SELECT id, prereqs FROM concepts"):
        dst = nodes.get(c["id"], c["id"])
        for p in loads(c["prereqs"], []):
            src = nodes.get(p)
            if src and src != dst:
                seen.setdefault((src, dst), {"src": src, "dst": dst, "origin": "prerequisite"})
    for r in db.q("SELECT src, dst, origin FROM links"):
        if r["src"] != r["dst"]:
            seen.setdefault((r["src"], r["dst"]), {"src": r["src"], "dst": r["dst"], "origin": r["origin"]})
    return list(seen.values())


def states(db: DB) -> dict[str, engine.ConceptState]:
    """The learner's state per node, from all evidence of all its concepts (any goal)."""
    nodes = node_of(db)
    concepts_of: dict[str, list[str]] = {}
    for cid, nid in nodes.items():
        concepts_of.setdefault(nid, []).append(cid)
    explain = _explain_items(db, list(nodes))
    prereqs: dict[str, set[str]] = {}
    for link in links(db):
        prereqs.setdefault(link["dst"], set()).add(link["src"])
    started = {r["id"] for r in db.q("SELECT id FROM concepts WHERE started=1")}
    all_nodes = [r["id"] for r in db.q("SELECT id FROM nodes")]  # also nodes without a concept (study sessions)
    pseudo = [{"id": nid, "p_init": 0.1, "prereqs": sorted(prereqs.get(nid, ())),
               "started": any(c in started for c in concepts_of.get(nid, [])),
               "explain_items": sorted({i for c in concepts_of.get(nid, []) for i in explain.get(c, [])})}
              for nid in all_nodes]
    known_nodes = set(all_nodes)
    ev = []
    for r in db.q("SELECT * FROM evidence ORDER BY id"):
        nid = nodes.get(r["concept_id"]) or (r["concept_id"] if r["concept_id"] in known_nodes else None)
        if nid:
            ev.append(dict(r, concept_id=nid))
    return engine.derive_concepts(pseudo, ev)


def view(db: DB) -> dict:
    """The whole graph for the map: nodes with the learner's state, the goals that use them, and the links."""
    nodes = node_of(db)
    st = states(db)
    goals_of: dict[str, set[str]] = {}
    for r in db.q("""SELECT c.id, t.goal_id FROM concepts c JOIN modules m ON m.id = c.module_id
                     JOIN tracks t ON t.id = m.track_id"""):
        goals_of.setdefault(nodes.get(r["id"], r["id"]), set()).add(r["goal_id"])
    concepts_of: dict[str, list[str]] = {}
    for cid, nid in nodes.items():
        concepts_of.setdefault(nid, []).append(cid)
    sessions_of: dict[str, list[str]] = {}
    for r in db.q("SELECT session_id, node_id FROM session_nodes"):
        sessions_of.setdefault(r["node_id"], []).append(r["session_id"])
    out = []
    for n in db.q("SELECT * FROM nodes ORDER BY created_at, id"):
        s = st.get(n["id"])
        out.append({"id": n["id"], "title": n["title"], "statement": n["statement"], "kind": n["kind"],
                    "state": s.state if s else "pending", "mastery": s.mastery if s else 0.0,
                    "goals": sorted(goals_of.get(n["id"], ())), "concepts": sorted(concepts_of.get(n["id"], [])),
                    "sessions": sorted(sessions_of.get(n["id"], []))})
    return {"nodes": out, "links": links(db)}
