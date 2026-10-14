"""Shared card library, full-text search, and Anki export."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import state
from .db import DB, dumps, loads, now, workspace

# ---------------------------------------------------------------- shared card library


def key_for(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def promote(db: DB, concept_id: str) -> str:
    """Copy a fact-checked card into the shared library (newer versions replace older ones)."""
    card = state.latest_card(db, concept_id)
    c = db.one("SELECT * FROM concepts WHERE id=?", (concept_id,))
    if not card or not c:
        raise ValueError("no card to promote")
    if card["factCheck"] != "passed":
        raise ValueError("only fact-checked cards can go into the shared library")
    key = key_for(c["title"])
    body = {k: v for k, v in card.items() if k not in ("conceptId", "version", "factCheck", "checkedAt")}
    existing = db.one("SELECT version, uses FROM library WHERE key=?", (key,))
    db.x("INSERT OR REPLACE INTO library VALUES(?,?,?,?,?,?,?,?,?)",
         (key, c["title"], c["objective"], dumps(body), (existing["version"] + 1) if existing else 1,
          concept_id, state.active_goal(db) or "", now(), existing["uses"] if existing else 0))
    return key


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


def listing(db: DB) -> list[dict]:
    return [{"key": r["key"], "title": r["title"], "objective": r["objective"], "version": r["version"],
             "sourceConcept": r["source_concept"], "promotedAt": r["promoted_at"], "uses": r["uses"]}
            for r in db.q("SELECT * FROM library ORDER BY title")]


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


def _anki_math(text: str) -> str:
    """Markdown/KaTeX math to Anki's MathJax delimiters."""
    text = re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", text, flags=re.S)
    return re.sub(r"\$(.+?)\$", r"\\(\1\\)", text)


def _esc(text: str) -> str:
    return _anki_math(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")).replace("\n", "<br>")


def export_anki(db: DB) -> Path:
    """Deck of the learned/mastered concepts' checks and explain-back prompts for the active goal."""
    import genanki

    gid = state.active_goal(db)
    goal = db.one("SELECT title FROM goals WHERE id=?", (gid,))
    concepts, states = state.concept_states(db, gid)
    stable = lambda s: int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)  # noqa: E731 - stable ids per goal
    model = genanki.Model(stable("dsc-model-v1"), "Deep Study Center", fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Concept"}],
                          templates=[{"name": "Card", "qfmt": "<div class=c>{{Concept}}</div>{{Front}}",
                                      "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
                          css=".card{font-family:system-ui;font-size:18px;text-align:left}.c{color:#888;font-size:13px}")
    deck = genanki.Deck(stable(f"dsc-deck-{gid}"), f"Deep Study Center::{goal['title']}")
    n = 0
    for c in concepts:
        if states[c["id"]].state not in ("learned", "mastered", "rusty"):
            continue
        card = state.latest_card(db, c["id"]) or {}
        for s in card.get("sections", []):
            if s.get("check"):
                ch = s["check"]
                front = _esc(ch["prompt"]) + "<ol type=A>" + "".join(f"<li>{_esc(o)}</li>" for o in ch["options"]) + "</ol>"
                back = f"<b>{chr(65 + ch['answer'])}</b>: {_esc(ch['options'][ch['answer']])}<br><br>{_esc(ch['explanation'])}"
                deck.add_note(genanki.Note(model=model, fields=[front, back, _esc(c["title"])], guid=genanki.guid_for(c["id"], ch["id"])))
                n += 1
            if s.get("explain"):
                ex = s["explain"]
                back = "A good answer covers:<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in ex["rubric"]) + "</ul>"
                deck.add_note(genanki.Note(model=model, fields=[_esc(ex["prompt"]), back, _esc(c["title"])], guid=genanki.guid_for(c["id"], ex["id"])))
                n += 1
    out = workspace() / "exports" / f"{key_for(goal['title'])}.apkg"
    out.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(out))
    db.set_meta("last_anki_export", f"{now()}|{n}")
    return out
