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


def _insert(db: DB, anchor: str, place: str, name: str, objective: str, summary: str, ideas: list[str]) -> str:
    """Inside a transaction: a new concept right after (``place`` "after") or right before ("before") the lesson
    ``anchor`` in its module, and in its book chapter when the anchor is a book lesson. Returns the new id."""
    base = db.conn.execute("SELECT * FROM concepts WHERE id=?", (anchor,)).fetchone()
    if not base:
        raise FormulaError("unknown lesson")
    root = re.sub(r"-fx-.*$", "", anchor)
    new_id = f"{root}-fx-{_slug(name)}"
    while db.conn.execute("SELECT 1 FROM concepts WHERE id=?", (new_id,)).fetchone():
        new_id += "-2"
    if place == "after":  # after the lesson and its earlier formula lessons
        rows = db.conn.execute("""SELECT c.ord FROM concepts c JOIN formula_lessons f ON f.id = c.id
                                  WHERE f.source_concept=?""", (anchor,)).fetchall()
        pos = max([base["ord"]] + [r[0] for r in rows]) + 1
    else:
        pos = base["ord"]
    db.conn.execute("UPDATE concepts SET ord = ord + 1 WHERE module_id=? AND ord >= ?", (base["module_id"], pos))
    db.conn.execute("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                    (new_id, base["module_id"], pos, name[:200], objective[:400], 10, dumps([]), 0.1))
    part = db.conn.execute("SELECT * FROM book_parts WHERE concept_id=?", (anchor,)).fetchone()
    if part:  # a book lesson: listed in the same chapter, next to it
        ppos = part["ord"] + 1 if place == "after" else part["ord"]
        db.conn.execute("UPDATE book_parts SET ord = ord + 1 WHERE book_id=? AND ord >= ?", (part["book_id"], ppos))
        cur = db.conn.execute("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to, summary,
                                 concept_id, ideas) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (part["book_id"], ppos, part["chapter"], part["chapter_title"], name[:200], part["page_from"],
                               part["page_to"], summary[:400], new_id, dumps(ideas[:4])))
        db.conn.execute("""INSERT OR IGNORE INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                           VALUES(?,?,?,?,?,1,?)""", (part["book_id"], new_id, cur.lastrowid, new_id, "", 0))
    return new_id


def make(db: DB, jobs: Jobs, cid: str, k: str) -> str:
    """Make a lesson about the formula ``k`` of lesson ``cid``: insert it after that lesson and write it."""
    note = _note(db, cid, k)
    status, info_ = formulas.status(db, cid, k, note["kind"], note["formula_id"], graph.states(db))
    if info_:
        raise FormulaError(f'this formula already has a lesson: “{info_["title"]}”')
    body = loads(note["body"], {})
    name = body.get("name") or "This formula"
    ts = now()
    with db.tx():
        new_id = _insert(db, cid, "after", name, f"Read, use and explain the formula: {body.get('meaning', '')}",
                         body.get("meaning") or "", [s["meaning"] for s in body.get("symbols", [])])
        db.conn.execute("INSERT INTO formula_lessons(id, name, source_concept, preferred, created_at, meaning) VALUES(?,?,?,?,?,?)",
                        (new_id, name[:200], cid, None, ts, body.get("meaning") or ""))
        db.conn.execute("INSERT INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES(?,?,?,?,?)",
                        (new_id, k, note["tex"], cid, ts))
        db.conn.execute("UPDATE formula_notes SET formula_id=?, matched_at=? WHERE concept_id=? AND key=?", (new_id, ts, cid, k))
    graph.sync(db)
    src_node = graph.node_of(db).get(cid, cid)
    db.x("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (new_id, src_node, "the lesson uses this formula", "formula"))
    queue(db, jobs, new_id, "Write the formula lesson")
    return new_id


# ---------------------------------------------------------------- the formula tree (SPEC §37)

KNOWN = ("learned",)
BLOCKS_SCHEMA = {"type": "object", "required": ["blocks"], "properties": {"blocks": {"type": "array", "maxItems": 6, "items": {
    "type": "object", "required": ["name", "kind", "tex", "meaning", "ref", "basic"], "properties": {
        "name": {"type": "string"}, "kind": {"enum": ["notation", "formula", "idea"]}, "tex": {"type": "string"},
        "meaning": {"type": "string"}, "ref": {"type": "string"}, "basic": {"type": "boolean"}}}}}}


def _resolve(db: DB, ref: object, fid: str) -> tuple[str | None, str | None]:
    """A block's reference: ("lesson", id) for a formula lesson, ("idea", id) for a graph idea, else (None, None)."""
    if not isinstance(ref, str) or not ref or ref == fid:
        return None, None
    if db.one("SELECT 1 FROM formula_lessons WHERE id=?", (ref,)):
        return "lesson", ref
    if db.one("SELECT 1 FROM nodes WHERE id=?", (ref,)):
        return "idea", ref
    return None, None


def _find_blocks(jobs: Jobs, jid: int, name: str, tex: str, meaning: str, near_concept: str | None, exclude: str) -> list[dict]:
    """Ask the model what a formula is directly built from (one level down)."""
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    st = graph.states(db)
    near = formulas._ideas(db, near_concept, f"{name} {meaning}") if near_concept else {}
    ideas = "\n".join(f'- {i}: {t} ({st[i].state if i in st else "new"})' for i, t in near.items() if i != exclude) or "(none)"
    jobs.progress(jid, f"finding what “{name[:60]}” is built from")
    out = jobs.call(jid, "Formula notes", Call(
        prompt=prompt("formula_blocks", title=name, main=tex or name, meaning=meaning,
                      known=formulas._known_text(db, exclude), ideas=ideas),
        schema=BLOCKS_SCHEMA, model="sonnet", timeout=300))
    return (out.get("blocks") or [])[:6]


def decompose(jobs: Jobs, jid: int, fid: str) -> int:
    """Find the building blocks of a formula: the notations it uses and the simpler formulas and ideas it is built
    from, each matched to a formula lesson or graph idea the learner has, or marked basic. Saved once per formula."""
    db = jobs.db
    f = db.one("SELECT * FROM formula_lessons WHERE id=?", (fid,))
    main = _main_form(db, f)
    found = _find_blocks(jobs, jid, f["name"], main["tex"], f["meaning"] or "", f["source_concept"], fid)
    out = {"blocks": found}
    ts = now()
    with db.tx():
        db.conn.execute("DELETE FROM formula_blocks WHERE formula_id=?", (fid,))
        for n, bl in enumerate((out.get("blocks") or [])[:6]):
            kind, ref = _resolve(db, bl.get("ref"), fid)
            db.conn.execute("""INSERT INTO formula_blocks(formula_id, ord, name, kind, tex, meaning, ref_kind, ref, basic, created_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (fid, n, (bl.get("name") or "")[:120], bl.get("kind") if bl.get("kind") in ("notation", "formula", "idea")
                             else "formula", (bl.get("tex") or "")[:300], (bl.get("meaning") or "")[:400], kind, ref,
                             int(bool(bl.get("basic")) and not ref and bl.get("kind") != "notation"), ts))  # a notation is never basic
        db.conn.execute("UPDATE formula_lessons SET blocks_at=? WHERE id=?", (ts, fid))
    return len(out.get("blocks") or [])


def open_node(jobs: Jobs, jid: int, node: str) -> int:
    """The derivation graph (SPEC §40): find what a node is built from, one level down. A formula lesson gets its
    blocks (``decompose``); a formula with no lesson ("block:<name>") gets its parts in ``formula_parts``."""
    db = jobs.db
    if db.one("SELECT 1 FROM formula_lessons WHERE id=?", (node,)):
        return decompose(jobs, jid, node)
    if not node.startswith("block:"):
        raise FormulaError("only a formula or a notation can be opened")
    want = node[len("block:"):]
    row = next((r for r in db.q("SELECT name, kind, tex, meaning, formula_id AS near FROM formula_blocks")
                + db.q("SELECT name, kind, tex, meaning, NULL AS near FROM formula_parts") if _norm(r["name"]) == want), None)
    if not row:
        raise FormulaError("unknown formula")
    near = row["near"] and db.one("SELECT source_concept FROM formula_lessons WHERE id=?", (row["near"],))
    found = _find_blocks(jobs, jid, row["name"], row["tex"], row["meaning"], near["source_concept"] if near else None, "")
    ts = now()
    with db.tx():
        db.conn.execute("DELETE FROM formula_parts WHERE node=?", (node,))
        for n, bl in enumerate(found):
            kind = bl.get("kind") if bl.get("kind") in ("notation", "formula", "idea") else "formula"
            db.conn.execute("""INSERT INTO formula_parts(node, ord, name, kind, tex, meaning, basic, created_at)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (node, n, (bl.get("name") or "")[:120], kind, (bl.get("tex") or "")[:300], (bl.get("meaning") or "")[:400],
                             int(bool(bl.get("basic")) and kind != "notation"), ts))
        db.conn.execute("INSERT OR REPLACE INTO formula_opened(node, at) VALUES(?,?)", (node, ts))
    return len(found)


def make_page(db: DB, jobs: Jobs, node: str) -> str:
    """A formula page for a node of the derivation graph that has none (SPEC §40). It is placed before the nearest
    formula lesson above it in the graph, and written."""
    t = tree(db)
    by = {n["id"]: n for n in t["nodes"]}
    n = by.get(node)
    if not n or n["lesson"] or n["kind"] == "idea":
        raise FormulaError("this node already has a page, or is not a formula")
    up, seen, anchor = [node], set(), None
    while up and not anchor:  # breadth first up the graph to a formula lesson
        cur = up.pop(0)
        for lk in t["links"]:
            if lk["src"] == cur and lk["dst"] not in seen:
                seen.add(lk["dst"])
                if by[lk["dst"]]["formula"]:
                    anchor = lk["dst"]
                    break
                up.append(lk["dst"])
    if not anchor:
        raise FormulaError("no formula lesson above this one")
    kind = "notation" if n["kind"] == "notation" else "formula"
    obj = (f"Read the notation {n['name']}: what it means and how to use it" if kind == "notation"
           else f"Read, use and explain: {n['meaning']}")
    ts = now()
    with db.tx():
        new_id = _insert(db, anchor, "before", n["name"], obj, n["meaning"], [])
        db.conn.execute("""INSERT INTO formula_lessons(id, name, source_concept, preferred, created_at, meaning, kind)
                           VALUES(?,?,?,?,?,?,?)""", (new_id, n["name"][:200], anchor, None, ts, n["meaning"], kind))
        if n["tex"]:
            db.conn.execute("INSERT OR IGNORE INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES(?,?,?,?,?)",
                            (new_id, formulas.key(n["tex"]), n["tex"], anchor, ts))
        # what the node was found to be built from becomes the page's blocks
        for p in db.conn.execute("SELECT * FROM formula_parts WHERE node=? ORDER BY ord", (node,)).fetchall():
            db.conn.execute("""INSERT INTO formula_blocks(formula_id, ord, name, kind, tex, meaning, ref_kind, ref, basic, created_at)
                               VALUES(?,?,?,?,?,?,NULL,NULL,?,?)""", (new_id, p["ord"], p["name"], p["kind"], p["tex"], p["meaning"], p["basic"], ts))
        if db.conn.execute("SELECT 1 FROM formula_parts WHERE node=?", (node,)).fetchone():
            db.conn.execute("UPDATE formula_lessons SET blocks_at=? WHERE id=?", (ts, new_id))
    graph.sync(db)
    db.x("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (new_id, anchor, "a building block", "formula"))
    queue(db, jobs, new_id, "Write a formula page")
    return new_id


def _basic(b: dict) -> bool:
    """Basic school arithmetic needs no lesson. A notation is never basic (rows from before this rule may say so)."""
    return bool(b["basic"]) and b["kind"] != "notation"


def blocks(db: DB, fid: str, st: dict | None = None) -> list[dict]:
    """The blocks of a formula with what the learner knows: known (a learned lesson or idea, or basic), new, or
    writing (its lesson is being written)."""
    st = st if st is not None else graph.states(db)
    nodes = graph.node_of(db)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    out = []
    for b in db.q("SELECT * FROM formula_blocks WHERE formula_id=? ORDER BY ord", (fid,)):
        state, link = "new", None
        if _basic(b):
            state = "known"
        elif b["ref"]:
            node = nodes.get(b["ref"], b["ref"])
            s = st.get(node)
            state = "known" if s and s.state in KNOWN else "new"
            lesson_id = b["ref"] if b["ref_kind"] == "lesson" else next((c for c, n in nodes.items() if n == b["ref"]), None)
            link = {"id": lesson_id, "title": titles.get(node, b["name"]), "kind": b["ref_kind"]}
        out.append({"id": b["id"], "name": b["name"], "kind": b["kind"], "tex": b["tex"], "meaning": b["meaning"],
                    "basic": _basic(b), "state": state, "link": link})
    return out


def learn_first(db: DB, jobs: Jobs, fid: str) -> list[str]:
    """Make a short lesson for every new block of formula ``fid`` (placed right before it) and write them."""
    if not db.one("SELECT 1 FROM formula_lessons WHERE id=?", (fid,)):
        raise FormulaError("unknown formula lesson")
    todo = [b for b in db.q("SELECT * FROM formula_blocks WHERE formula_id=? ORDER BY ord", (fid,)) if not b["ref"] and not _basic(b)]
    if not todo:
        raise FormulaError("every building block already has a lesson or is known")
    made, ts = [], now()
    with db.tx():
        for b in todo:
            kind = "notation" if b["kind"] == "notation" else "formula"
            obj = (f"Read the notation {b['name']}: what it means and how to use it" if kind == "notation"
                   else f"Read, use and explain: {b['meaning']}")
            new_id = _insert(db, fid, "before", b["name"], obj, b["meaning"], [])
            db.conn.execute("""INSERT INTO formula_lessons(id, name, source_concept, preferred, created_at, meaning, kind)
                               VALUES(?,?,?,?,?,?,?)""", (new_id, b["name"][:200], fid, None, ts, b["meaning"], kind))
            if b["tex"]:
                db.conn.execute("INSERT OR IGNORE INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES(?,?,?,?,?)",
                                (new_id, formulas.key(b["tex"]), b["tex"], fid, ts))
            db.conn.execute("UPDATE formula_blocks SET ref_kind='lesson', ref=? WHERE id=?", (new_id, b["id"]))
            made.append(new_id)
    graph.sync(db)
    for new_id in made:  # the block comes before the formula that is built from it
        db.x("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (new_id, fid, "a building block", "formula"))
        queue(db, jobs, new_id, "Write a building-block lesson")
    return made


def used_in(db: DB, fid: str) -> list[dict]:
    """The formulas built from this one, and the lessons where its forms appear."""
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    out = [{"id": r["formula_id"], "title": titles.get(r["formula_id"], ""), "kind": "formula"}
           for r in db.q("SELECT DISTINCT formula_id FROM formula_blocks WHERE ref=?", (fid,))]
    out += [{"id": r["concept_id"], "title": titles.get(r["concept_id"], ""), "kind": "lesson"}
            for r in db.q("SELECT DISTINCT concept_id FROM formula_forms WHERE formula_id=?", (fid,))
            if r["concept_id"] not in {x["id"] for x in out}]
    return [x for x in out if x["title"]]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def tree(db: DB) -> dict:
    """The whole formula tree (SPEC §38): every formula lesson and every building block, as one graph.

    A node is a formula lesson, a graph idea that is a block, or a block with no lesson yet (``new``; the same name
    under two formulas is one node). A link goes from a block to the formula built from it, so basics are at the bottom.
    ``state``: known (learned, or basic), learning, writing (its lesson is being written), new."""
    st = graph.states(db)
    nodes_of = graph.node_of(db)
    lesson_of = {}  # graph node id -> one lesson id (to open an idea)
    for c, n in nodes_of.items():
        lesson_of.setdefault(n, c)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    concept_titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    busy = {loads(j["input"]).get("concept_id") for j in db.q(
        "SELECT input FROM jobs WHERE kind='formula_lesson' AND status IN ('queued','running')")}

    def state_of(node_id: str | None) -> str:
        s = st.get(node_id) if node_id else None
        if not s:
            return "new"
        return "known" if s.state in KNOWN else "learning" if s.state in ("learning",) else "new"

    out: dict[str, dict] = {}
    for f in db.q("SELECT * FROM formula_lessons ORDER BY created_at, rowid"):
        main = _main_form(db, dict(f))
        state = state_of(nodes_of.get(f["id"]))
        if f["id"] in busy and state != "known":
            state = "writing"
        out[f["id"]] = {"id": f["id"], "name": f["name"], "kind": f["kind"] or "formula", "tex": main["tex"] if main["key"] else "",
                        "meaning": f["meaning"] or "", "state": state, "lesson": f["id"], "basic": False,
                        "formula": True, "blocksReady": bool(f["blocks_at"]),
                        "source": {"id": f["source_concept"], "title": concept_titles.get(f["source_concept"], "")}, "covers": []}
    by_name = {_norm(n["name"]): i for i, n in out.items()}  # a block named like a formula lesson is that lesson
    links: set[tuple[str, str]] = set()
    for b in db.q("SELECT * FROM formula_blocks ORDER BY formula_id, ord"):
        if b["formula_id"] not in out or _norm(b["name"]) == _norm(out[b["formula_id"]]["name"]):
            continue  # a block that is the formula itself (the model can list it) is not a block
        if b["ref_kind"] == "lesson" and b["ref"] in out:
            nid = b["ref"]
        elif not b["ref"] and _norm(b["name"]) in by_name:
            nid = by_name[_norm(b["name"])]
        elif b["ref_kind"] == "idea" and b["ref"]:
            nid = f"idea:{b['ref']}"
            if nid not in out:
                out[nid] = {"id": nid, "name": titles.get(b["ref"], b["name"]), "kind": "idea", "tex": b["tex"],
                            "meaning": b["meaning"], "state": state_of(b["ref"]), "lesson": lesson_of.get(b["ref"]),
                            "basic": False, "formula": False, "blocksReady": True, "source": None, "covers": []}
            if b["name"] not in out[nid]["covers"] and _norm(b["name"]) != _norm(out[nid]["name"]):
                out[nid]["covers"].append(b["name"])
        else:
            nid = f"block:{_norm(b['name'])}"
            if nid not in out:
                out[nid] = {"id": nid, "name": b["name"], "kind": b["kind"], "tex": b["tex"], "meaning": b["meaning"],
                            "state": "known" if _basic(b) else "new", "lesson": None, "basic": _basic(b),
                            "formula": False, "blocksReady": True, "source": None, "covers": []}
        if nid != b["formula_id"]:
            links.add((nid, b["formula_id"]))
    # deeper levels of the derivation graph (SPEC §40): parts found for formulas that have no lesson
    parts = db.q("SELECT * FROM formula_parts ORDER BY created_at, node, ord")
    for _ in range(12):  # each pass adds one more level
        added = False
        for p in parts:
            if p["node"] not in out or _norm(p["name"]) == p["node"][len("block:"):]:
                continue
            key = _norm(p["name"])
            nid = by_name.get(key) or f"block:{key}"
            if nid not in out:
                out[nid] = {"id": nid, "name": p["name"], "kind": p["kind"], "tex": p["tex"], "meaning": p["meaning"],
                            "state": "known" if p["basic"] else "new", "lesson": None, "basic": bool(p["basic"]),
                            "formula": False, "blocksReady": True, "source": None, "covers": []}
                added = True
            if nid != p["node"] and (nid, p["node"]) not in links:
                links.add((nid, p["node"]))
                added = True
        if not added:
            break
    opened = {r["node"] for r in db.q("SELECT node FROM formula_opened")}
    opening = {loads(j["input"]).get("node") for j in db.q(
        "SELECT input FROM jobs WHERE kind='formula_open' AND status IN ('queued','running')")}
    has_parts = {d for _, d in links}
    for n in out.values():
        n["opening"] = n["id"] in opening
        n["openable"] = (n["kind"] != "idea" and not n["basic"] and n["id"] not in has_parts
                         and not (n["formula"] and n["blocksReady"]) and n["id"] not in opened)
    return {"nodes": list(out.values()), "links": [{"src": s, "dst": d} for s, d in sorted(links)]}


def _main_form(db: DB, f: dict) -> dict:
    forms = db.q("SELECT * FROM formula_forms WHERE formula_id=? ORDER BY added_at", (f["id"],))
    pref = f["preferred"] or (forms[0]["key"] if forms else None)
    return next((x for x in forms if x["key"] == pref), {"tex": f["name"], "key": "", "concept_id": f["source_concept"]})


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


def preferred_text(db: DB) -> str:
    """Guideline lines for the formulas whose form the learner chose (SPEC §36): every writer uses that form, and shows
    the source's form once, mapped to it, when the source writes it another way. Empty when there are none."""
    lines = []
    for f in db.q("SELECT * FROM formula_lessons WHERE preferred IS NOT NULL ORDER BY created_at"):
        forms = db.q("SELECT key, tex FROM formula_forms WHERE formula_id=? ORDER BY added_at", (f["id"],))
        pref = next((x for x in forms if x["key"] == f["preferred"]), None)
        if not pref or len(forms) < 2:
            continue
        others = "; ".join(f'${x["tex"]}$' for x in forms if x["key"] != pref["key"])
        lines.append(f'- Formula form the learner prefers: write “{f["name"]}” as ${pref["tex"]}$ (not {others}). When the '
                     "source writes it another way, show the source's form once, map it to this form symbol by symbol, "
                     "then use this form.")
    return "\n".join(lines)


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
    bl = blocks(db, cid)
    return {"forms": forms, "preferred": f["preferred"] or (forms[0]["key"] if forms else None), "chosen": bool(f["preferred"]),
            "source": {"id": f["source_concept"], "title": titles.get(f["source_concept"], "")},
            "kind": f["kind"] or "formula", "blocks": bl, "blocksReady": bool(f["blocks_at"]),
            "missing": sum(1 for b in bl if b["state"] == "new" and not b["link"]), "usedIn": used_in(db, cid),
            "flow": _flow(db, cid)}


def _flow(db: DB, cid: str) -> dict | None:
    from . import formula_flow
    return formula_flow.get(db, cid)


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
    if not f["blocks_at"]:
        decompose(jobs, jid, fid)
    forms = db.q("SELECT * FROM formula_forms WHERE formula_id=? ORDER BY added_at", (fid,))
    pref = f["preferred"] or (forms[0]["key"] if forms else None)
    main = _main_form(db, f)
    note = db.one("SELECT body FROM formula_notes WHERE concept_id=? AND key=?", (main["concept_id"], main["key"]))
    nb = loads((note or {}).get("body"), {}) or {"meaning": f["meaning"] or ""}
    bl = blocks(db, fid)
    blocks_text = "\n".join(f'- {b["name"]} ({b["kind"]}){": $" + b["tex"] + "$" if b["tex"] else ""}: {b["meaning"]} — the learner '
                             + ("knows it" if b["state"] == "known" else "does not know it yet"
                                + (f' (its lesson: “{b["link"]["title"]}”)' if b["link"] else ""))
                             for b in bl) or "(none: it is basic)"
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    forms_text = "\n".join(f'- ${x["tex"]}$ (from the lesson “{titles.get(x["concept_id"], x["concept_id"])}”)'
                           + (" — the learner's preferred form" if x["key"] == pref and f["preferred"] else "") for x in forms)
    st = graph.states(db)
    near = formulas._ideas(db, f["source_concept"], f'{f["name"]} {nb.get("meaning", "")}')
    known = "\n".join(f'- {t} ({st[i].state if i in st else "new"})' for i, t in near.items() if i != fid) or "(none)"
    symbols = "\n".join(f'- ${s["tex"]}$: {s["meaning"]}' for s in nb.get("symbols", [])) or "(none)"
    jobs.progress(jid, f"writing the lesson about “{f['name'][:60]}” ({len(forms)} form(s))")
    out = jobs.call(jid, "Research", Call(
        prompt=prompt("formula_lesson" if (f["kind"] or "formula") != "notation" else "notation_lesson", title=f["name"],
                      main=main["tex"], forms=forms_text, meaning=nb.get("meaning", ""), symbols=symbols, known=known,
                      blocks=blocks_text, context=_context(db, main["concept_id"], main["tex"])),
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
    if (f["kind"] or "formula") == "formula" and db.meta("auto_flow", "1") != "0":  # the page's formula flow (SPEC §52)
        from . import formula_flow
        formula_flow.request(db, jobs, fid)
    if version == 1:
        lesson.ensure_rendition(db, fid)
        lesson.ensure_prose(db, jobs, fid)
    else:  # a new form or a new preferred form: the whole lesson is written again
        lesson.refresh(db, jobs, fid, by_learner=True)
    return {"version": version, "forms": len(forms)}
