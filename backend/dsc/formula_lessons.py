"""Formula lessons (SPEC §34): a lesson about one formula, made from the formula's hover card.

A formula you meet for the first time has a gray frame and offers "Make a lesson about this formula". The lesson goes
right after the lesson you are reading (in the same chapter of a book) and is one idea in your graph. It is written
from the formula, the lesson it came from (and the book's pages), and the ideas you already know: what each part
means (the explorable formula widget with colored parts, sliders and "what if"), where it comes from, how to use it,
and its forms. When you learn it, the formula's frame turns green wherever this form appears.

Lessons write the same formula in different ways (other letters, other notation, rearranged). Such a form has an
orange frame: "Add this form" adds it to the formula lesson, which is written again to compare the forms: how they
map, why each is written that way, and when each is handy. You can mark the form you prefer; the formula lesson then
uses it as its main form.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING

from . import formulas, graph, mcq, viz
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs


class FormulaError(Exception):
    pass


def _card_schema() -> dict:
    from .bookstudy import CARDS_SCHEMA
    card = copy.deepcopy(CARDS_SCHEMA["properties"]["cards"]["items"]["properties"]["card"])
    sec = card["properties"]["sections"]["items"]
    sec["required"] = [r for r in sec["required"] if r != "book"]
    sec["properties"].pop("book", None)
    return {"type": "object", "required": ["card"], "properties": {"card": card}}


def _note(db: DB, cid: str, k: str) -> dict:
    row = db.one("SELECT * FROM formula_notes WHERE concept_id=? AND key=?", (cid, k))
    if not row:
        raise FormulaError("this formula has no note yet")
    return row


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:24] or "formula"


def make(db: DB, jobs: Jobs, cid: str, k: str) -> str:
    """Make a lesson about the formula ``k`` of lesson ``cid``: insert it after that lesson and write it."""
    note = _note(db, cid, k)
    status, info = formulas.status(db, cid, k, note["kind"], note["formula_id"], graph.states(db))
    if info:
        raise FormulaError(f'this formula already has a lesson: “{info["title"]}”')
    body = loads(note["body"], {})
    name = body.get("name") or "This formula"
    base = db.one("SELECT * FROM concepts WHERE id=?", (cid,))
    if not base:
        raise FormulaError("unknown lesson")
    new_id = f"{cid}-fx-{_slug(name)}"
    while db.one("SELECT 1 FROM concepts WHERE id=?", (new_id,)):
        new_id += "-2"
    after = max([base["ord"]] + [r["ord"] for r in db.q("""SELECT c.ord FROM concepts c JOIN formula_lessons f ON f.id = c.id
                                                            WHERE f.source_concept=?""", (cid,))])
    ts = now()
    part = db.one("SELECT * FROM book_parts WHERE concept_id=?", (cid,))
    with db.tx():
        db.conn.execute("UPDATE concepts SET ord = ord + 1 WHERE module_id=? AND ord > ?", (base["module_id"], after))
        db.conn.execute("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                        (new_id, base["module_id"], after + 1, name[:200],
                         f"Read, use and explain the formula: {body.get('meaning', '')}"[:400], 15, dumps([]), 0.1))
        db.conn.execute("INSERT INTO formula_lessons(id, name, source_concept, preferred, created_at) VALUES(?,?,?,?,?)",
                        (new_id, name[:200], cid, None, ts))
        db.conn.execute("INSERT INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES(?,?,?,?,?)",
                        (new_id, k, note["tex"], cid, ts))
        db.conn.execute("UPDATE formula_notes SET formula_id=?, matched_at=? WHERE concept_id=? AND key=?", (new_id, ts, cid, k))
        if part:  # a book lesson: the formula lesson is listed in the same chapter, right after it
            db.conn.execute("UPDATE book_parts SET ord = ord + 1 WHERE book_id=? AND ord > ?", (part["book_id"], part["ord"]))
            cur = db.conn.execute("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to, summary,
                                     concept_id, ideas) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                  (part["book_id"], part["ord"] + 1, part["chapter"], part["chapter_title"], name[:200],
                                   part["page_from"], part["page_to"], (body.get("meaning") or "")[:400], new_id,
                                   dumps([s["meaning"] for s in body.get("symbols", [])][:4])))
            db.conn.execute("""INSERT OR IGNORE INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                               VALUES(?,?,?,?,?,1,?)""", (part["book_id"], new_id, cur.lastrowid, new_id, "", 0))
    graph.sync(db)
    src_node = graph.node_of(db).get(cid, cid)
    db.x("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (new_id, src_node, "the lesson uses this formula", "formula"))
    queue(db, jobs, new_id, "Write the formula lesson")
    return new_id


def add_form(db: DB, jobs: Jobs, cid: str, k: str, fid: str) -> None:
    """Add the form ``k`` of lesson ``cid`` to formula lesson ``fid``; the formula lesson is written again with it."""
    note = _note(db, cid, k)
    if not db.one("SELECT 1 FROM formula_lessons WHERE id=?", (fid,)):
        raise FormulaError("unknown formula lesson")
    ts = now()
    with db.tx():
        db.conn.execute("INSERT OR IGNORE INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES(?,?,?,?,?)",
                        (fid, k, note["tex"], cid, ts))
        db.conn.execute("UPDATE formula_notes SET formula_id=?, matched_at=? WHERE concept_id=? AND key=?", (fid, ts, cid, k))
    queue(db, jobs, fid, "Add a form to the formula lesson")


def prefer(db: DB, jobs: Jobs, fid: str, k: str) -> None:
    """Mark the form the learner prefers; the formula lesson is written again with it as its main form."""
    if not db.one("SELECT 1 FROM formula_forms WHERE formula_id=? AND key=?", (fid, k)):
        raise FormulaError("unknown form")
    db.x("UPDATE formula_lessons SET preferred=? WHERE id=?", (k, fid))
    queue(db, jobs, fid, "Use your preferred form")


def queue(db: DB, jobs: Jobs, fid: str, label: str) -> None:
    if not jobs.active("formula_lesson", concept_id=fid):
        jobs.enqueue("formula_lesson", label, {"concept_id": fid})


def is_formula_lesson(db: DB, cid: str) -> bool:
    return bool(db.one("SELECT 1 FROM formula_lessons WHERE id=?", (cid,)))


def info(db: DB, cid: str) -> dict | None:
    """For the formula lesson's page: its forms (where each comes from) and the preferred one."""
    f = db.one("SELECT * FROM formula_lessons WHERE id=?", (cid,))
    if not f:
        return None
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    forms = [{"key": r["key"], "tex": r["tex"], "from": {"id": r["concept_id"], "title": titles.get(r["concept_id"], r["concept_id"])}}
             for r in db.q("SELECT * FROM formula_forms WHERE formula_id=? ORDER BY added_at", (cid,))]
    return {"forms": forms, "preferred": f["preferred"] or (forms[0]["key"] if forms else None),
            "source": {"id": f["source_concept"], "title": titles.get(f["source_concept"], "")}}


def _context(db: DB, cid: str, tex: str) -> str:
    """The text around the formula in the lesson it came from (and the book's pages for a book lesson)."""
    k = formulas.key(tex)
    out = ""
    for r in db.q("SELECT body FROM prose WHERE concept_id=? ORDER BY created_at DESC", (cid,)):
        flat = r["body"]
        i = flat.find(tex)
        if i < 0:
            continue
        out = flat[max(0, i - 900): i + len(tex) + 900]
        break
    part = db.one("SELECT p.*, b.source_id FROM book_parts p JOIN books b ON b.id = p.book_id WHERE p.concept_id=?", (cid,))
    if part:
        from .bookstudy import _chapter_text
        pages = _chapter_text(db, part["source_id"], part["page_from"], part["page_to"])
        out += f"\n\nThe book's pages for that lesson (pp. {part['page_from']}-{part['page_to']}):\n{pages[:12000]}"
    return out or f"(the formula {k} appears in the lesson)"


def run(jobs: Jobs, jid: int, d: dict) -> dict:
    """Write (or write again) the card of a formula lesson, then the lesson itself."""
    from . import lesson, writer
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    fid = d["concept_id"]
    f = db.one("SELECT * FROM formula_lessons WHERE id=?", (fid,))
    if not f:
        return {"skipped": True}
    forms = db.q("SELECT * FROM formula_forms WHERE formula_id=? ORDER BY added_at", (fid,))
    pref = f["preferred"] or forms[0]["key"]
    main = next(x for x in forms if x["key"] == pref)
    note = db.one("SELECT body FROM formula_notes WHERE concept_id=? AND key=?", (main["concept_id"], main["key"]))
    nb = loads((note or {}).get("body"), {})
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    forms_text = "\n".join(f'- ${x["tex"]}$ (from the lesson “{titles.get(x["concept_id"], x["concept_id"])}”)'
                           + (" — the learner's preferred form" if x["key"] == pref and f["preferred"] else "") for x in forms)
    st = graph.states(db)
    near = formulas._ideas(db, f["source_concept"], f'{f["name"]} {nb.get("meaning", "")}')
    known = "\n".join(f'- {t} ({st[i].state if i in st else "new"})' for i, t in near.items() if i != fid) or "(none)"
    symbols = "\n".join(f'- ${s["tex"]}$: {s["meaning"]}' for s in nb.get("symbols", [])) or "(none)"
    jobs.progress(jid, f"writing the lesson about “{f['name'][:60]}” ({len(forms)} form(s))")
    out = jobs.call(jid, "Research", Call(
        prompt=prompt("formula_lesson", title=f["name"], main=main["tex"], forms=forms_text, meaning=nb.get("meaning", ""),
                      symbols=symbols, known=known, context=_context(db, main["concept_id"], main["tex"])),
        schema=_card_schema(), model="opus", timeout=1200))
    card = out.get("card") or {}
    if not card.get("sections"):
        raise FormulaError("the writer returned no sections")
    concept = db.one("SELECT objective FROM concepts WHERE id=?", (fid,))
    for s in card["sections"]:
        if s.get("viz"):
            spec, notes_ = writer.check_viz(jobs, jid, {**card, "objective": concept["objective"]}, s, s["viz"])
            if spec:
                s["viz"] = spec
            else:
                s.pop("viz", None)
            if notes_:
                s["vizNotes"] = notes_
    for s in card["sections"]:
        if "viz" in s:
            s["viz"] = viz.validate(s["viz"])
            if not s["viz"]:
                del s["viz"]
        if s.get("check"):
            s["check"] = {**mcq.shuffle(s["check"]), "id": f'q-{s["id"]}'}
        if s.get("explain"):
            s["explain"]["id"] = f'e-{s["id"]}'
    version = (db.one("SELECT MAX(version) AS v FROM cards WHERE concept_id=?", (fid,))["v"] or 0) + 1
    body = {**card, "objective": concept["objective"], "angles": card.get("angles") or [],
            "sources": [{"title": f'Formula from “{titles.get(x["concept_id"], "")}”', "url": "", "kind": "article",
                         "why": "Where this form appears"} for x in forms][:3]}
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
         (fid, version, dumps(body), "pending", now()))
    jobs.enqueue("fact_check", f"Fact-check {f['name'][:60]}", {"concept_ids": [fid]})
    if version == 1:
        lesson.ensure_rendition(db, fid)
        lesson.ensure_prose(db, jobs, fid)
    else:  # a new form or a new preferred form: the whole lesson is written again
        lesson.refresh(db, jobs, fid, by_learner=True)
    return {"version": version, "forms": len(forms)}
