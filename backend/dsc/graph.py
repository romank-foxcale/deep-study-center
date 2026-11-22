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
    lessons_of: dict[str, list[dict]] = {}
    for r in db.q("""SELECT c.id, c.title, t.goal_id FROM concepts c JOIN modules m ON m.id = c.module_id
                     JOIN tracks t ON t.id = m.track_id JOIN goals g ON g.id = t.goal_id WHERE g.kind != 'bookstudy'
                     ORDER BY t.goal_id, m.seq, t.ord, m.ord, c.ord"""):
        nid = nodes.get(r["id"], r["id"])
        goals_of.setdefault(nid, set()).add(r["goal_id"])
        lessons_of.setdefault(nid, []).append({"id": r["id"], "title": r["title"], "goalId": r["goal_id"]})
    concepts_of: dict[str, list[str]] = {}
    for cid, nid in nodes.items():
        concepts_of.setdefault(nid, []).append(cid)
    sessions_of: dict[str, list[str]] = {}
    for r in db.q("SELECT session_id, node_id FROM session_nodes"):
        sessions_of.setdefault(r["node_id"], []).append(r["session_id"])
    books_of: dict[str, list[str]] = {}
    for r in db.q("SELECT book_id, node_id FROM book_nodes"):
        books_of.setdefault(r["node_id"], []).append(r["book_id"])
    out = []
    for n in db.q("SELECT * FROM nodes ORDER BY created_at, id"):
        s = st.get(n["id"])
        out.append({"id": n["id"], "title": n["title"], "statement": n["statement"], "kind": n["kind"],
                    "state": s.state if s else "pending", "mastery": s.mastery if s else 0.0,
                    "goals": sorted(goals_of.get(n["id"], ())), "concepts": sorted(concepts_of.get(n["id"], [])),
                    "sessions": sorted(sessions_of.get(n["id"], [])), "lessons": lessons_of.get(n["id"], []),
                    "books": sorted(books_of.get(n["id"], []))})
    goals = [{"id": g["id"], "title": g["title"]} for g in db.q("SELECT id, title FROM goals WHERE kind != 'bookstudy' ORDER BY created_at")]
    sessions = [{"id": r["id"], "title": r["title"]} for r in db.q("SELECT id, title FROM sessions ORDER BY created_at")]
    books = [{"id": r["id"], "title": r["title"]} for r in db.q("SELECT id, title FROM books ORDER BY created_at")]
    clusters, place = _clusters(db, out)
    for n in out:
        n.update(place.get(n["id"], {"cluster": "loose", "also": [], "chapter": 0, "chapterTitle": "", "order": 0.0}))
    return {"nodes": out, "links": links(db), "goals": goals, "sessions": sessions, "books": books, "clusters": clusters}


def _clusters(db: DB, nodes: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Group the map into clusters for the map views (SPEC §29): each idea belongs to one cluster (the book that made
    it, else its first book, else its first goal, else its first study session, else "loose") and lists the other
    books and goals it also appears in. ``chapter`` and ``order`` (0..1) give its place inside the cluster."""
    place: dict[str, dict] = {}
    seq: dict[str, list[tuple]] = {}
    book_rows = db.q("""SELECT bn.node_id, bn.book_id, bn.created, bn.ord, p.ord AS pord, p.chapter, p.chapter_title
                        FROM book_nodes bn JOIN book_parts p ON p.id = bn.part_id ORDER BY bn.created DESC""")
    in_books: dict[str, list[dict]] = {}
    for r in book_rows:
        in_books.setdefault(r["node_id"], []).append(r)
    goal_rows = db.q("""SELECT cn.node_id, t.goal_id, t.ord AS tord, t.title AS ttitle, m.seq, m.ord AS mord, c.ord AS cord
                        FROM concept_nodes cn JOIN concepts c ON c.id = cn.concept_id JOIN modules m ON m.id = c.module_id
                        JOIN tracks t ON t.id = m.track_id JOIN goals g ON g.id = t.goal_id WHERE g.kind != 'bookstudy'""")
    in_goals: dict[str, list[dict]] = {}
    for r in goal_rows:
        in_goals.setdefault(r["node_id"], []).append(r)
    for n in nodes:
        nid = n["id"]
        bs, gs = in_books.get(nid, []), in_goals.get(nid, [])
        if bs:
            b = bs[0]
            key, chapter, title, rank = f"book:{b['book_id']}", b["chapter"], b["chapter_title"], (b["pord"], b["ord"])
        elif gs:
            g = gs[0]
            key, chapter, title, rank = f"goal:{g['goal_id']}", g["tord"] + 1, g["ttitle"], (g["seq"], g["mord"], g["cord"])
        elif n["sessions"]:
            key, chapter, title, rank = f"session:{n['sessions'][0]}", 1, "", (0,)
        else:
            key, chapter, title, rank = "loose", 1, "", (0,)
        also = sorted(({f"book:{x['book_id']}" for x in bs} | {f"goal:{x['goal_id']}" for x in gs}) - {key})
        place[nid] = {"cluster": key, "also": also, "chapter": chapter, "chapterTitle": title}
        seq.setdefault(key, []).append((chapter, rank, n["created"] if "created" in n else "", nid))
    for key, items in seq.items():
        items.sort(key=lambda t: (t[0], t[1], t[3]))
        for i, t in enumerate(items):
            place[t[3]]["order"] = round(i / max(1, len(items) - 1), 4)
    titles = {f"book:{r['id']}": ("book", r["title"]) for r in db.q("SELECT id, title FROM books")}
    titles.update({f"goal:{r['id']}": ("goal", r["title"]) for r in db.q("SELECT id, title FROM goals")})
    titles.update({f"session:{r['id']}": ("session", r["title"]) for r in db.q("SELECT id, title FROM sessions")})
    titles["loose"] = ("loose", "Other ideas")
    clusters = [{"id": k, "kind": titles.get(k, ("loose", k))[0], "title": titles.get(k, ("loose", k))[1], "size": len(v)}
                for k, v in sorted(seq.items(), key=lambda kv: -len(kv[1]))]
    return clusters, place


def node_detail(db: DB, nid: str) -> dict | None:
    """One idea for a hover card (SPEC §28): its state, where the learner met it (books with pages, sessions, goal
    lessons), and the ideas it builds on and leads to."""
    n = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not n:
        return None
    st = states(db)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}

    def brief(i: str) -> dict:
        s = st.get(i)
        return {"id": i, "title": titles.get(i, i), "state": s.state if s else "pending"}
    ls = links(db)
    s = st.get(nid)
    books = [{"id": r["book_id"], "title": r["title"], "part": r["part"], "pages": r["pages"], "conceptId": r["concept_id"]}
             for r in db.q("""SELECT bn.book_id, b.title, p.title AS part, bn.pages, p.concept_id FROM book_nodes bn
                              JOIN books b ON b.id = bn.book_id JOIN book_parts p ON p.id = bn.part_id
                              WHERE bn.node_id=?""", (nid,))]
    sessions = [{"id": r["id"], "title": r["title"], "status": r["status"]}
                for r in db.q("""SELECT s.id, s.title, s.status FROM session_nodes sn JOIN sessions s ON s.id = sn.session_id
                                 WHERE sn.node_id=? ORDER BY s.created_at""", (nid,))]
    lessons = [{"id": r["id"], "title": r["title"], "goalId": r["goal_id"]}
               for r in db.q("""SELECT c.id, c.title, t.goal_id FROM concept_nodes cn JOIN concepts c ON c.id = cn.concept_id
                                JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id
                                JOIN goals g ON g.id = t.goal_id WHERE cn.node_id=? AND g.kind != 'bookstudy'""", (nid,))]
    return {"id": nid, "title": n["title"], "statement": n["statement"], "kind": n["kind"],
            "state": s.state if s else "pending", "mastery": s.mastery if s else 0.0,
            "buildsOn": [brief(lk["src"]) for lk in ls if lk["dst"] == nid],
            "leadsTo": [brief(lk["dst"]) for lk in ls if lk["src"] == nid],
            "books": books, "sessions": sessions, "lessons": lessons}
