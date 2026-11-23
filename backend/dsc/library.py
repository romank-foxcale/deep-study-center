"""Full-text search, and the reuse of shared cards in goal research (cards shared before 0.5)."""

from __future__ import annotations

import re

from . import state
from .db import DB, loads

# ---------------------------------------------------------------- shared card library


def key_for(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def index_text(db: DB) -> str:
    rows = db.q("SELECT key, title, objective FROM library ORDER BY title")
    return "\n".join(f'- {r["key"]}: {r["title"]} - {r["objective"]}' for r in rows) or "(empty)"


def take(db: DB, key: str) -> dict | None:
    """A library card body for reuse; counts the use."""
    row = db.one("SELECT * FROM library WHERE key=?", (key,))
    if not row:
        return None
    db.x("UPDATE library SET uses = uses + 1 WHERE key=?", (key,))
    return loads(row["body"])


# ---------------------------------------------------------------- search


def search(db: DB, query: str, limit: int = 30) -> list[dict]:
    """Full-text search over notes, lesson prose and source cards of the active goal.

    The index is rebuilt per query: a learner's workspace is small, and this keeps it trivially
    consistent with the append-only tables.
    """
    terms = re.findall(r"[\w']+", query.lower())[:8]
    if not terms:
        return []
    gid = state.active_goal(db)
    concepts = {c["id"]: c for c in state.concepts_raw(db, gid)} if gid else {}
    if not concepts:
        return []
    ids = list(concepts)
    marks = ",".join("?" * len(ids))
    with db.lock:
        con = db.conn
        con.execute("DROP TABLE IF EXISTS temp.search_idx")
        con.execute("CREATE VIRTUAL TABLE temp.search_idx USING fts5(kind UNINDEXED, ref UNINDEXED, concept UNINDEXED, title, body)")
        rows = []
        for n in db.q(f"SELECT * FROM notes WHERE concept_id IN ({marks})", ids):
            rows.append(("note", str(n["id"]), n["concept_id"], concepts[n["concept_id"]]["title"],
                         f'{n["quote"] or ""} {n["text"]}'))
        for p in db.q(f"""SELECT p.concept_id, p.section_id, p.body FROM prose p JOIN renditions r ON r.concept_id = p.concept_id
                          WHERE p.concept_id IN ({marks}) AND p.style = r.style AND p.card_version = r.card_version""", ids):
            rows.append(("lesson", p["section_id"], p["concept_id"], concepts[p["concept_id"]]["title"], p["body"]))
        for cid in ids:
            card = state.latest_card(db, cid)
            if card:
                text = " ".join(str(card.get(k, "")) for k in ("objective", "core", "formal", "why"))
                text += " " + " ".join(card.get("misconceptions", []))
                rows.append(("card", cid, cid, concepts[cid]["title"], text))
        con.executemany("INSERT INTO temp.search_idx VALUES(?,?,?,?,?)", rows)
        match = " ".join(f'"{t}"*' for t in terms)
        hits = con.execute("""SELECT kind, ref, concept, title, snippet(search_idx, 4, '[[', ']]', ' … ', 14) AS snip
                              FROM temp.search_idx WHERE search_idx MATCH ? ORDER BY bm25(search_idx) LIMIT ?""",
                           (match, limit)).fetchall()
        con.execute("DROP TABLE temp.search_idx")
    return [{"kind": h["kind"], "ref": h["ref"], "conceptId": h["concept"], "title": h["title"], "snippet": h["snip"]}
            for h in hits]


# ---------------------------------------------------------------- Anki export


