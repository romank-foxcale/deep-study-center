"""Book study: "teach me this book" (SPEC §28, TODO D1-D3). The main flow from 2026-11-22.

1. **Map** (job ``book_map``): the book's outline gives chapters and sections with pages. A section (or a chapter
   without sections) is a **part**, the size of one study session. An agent reads one chapter at a time (its pages'
   text) and writes the ideas of each part: title, statement, pages, kind, prerequisites, and ``same_as`` when the idea
   is already a node in the learner's graph. New ideas become nodes (origin "book"); prerequisites become links, also
   to earlier chapters and to older nodes. So every book has its own graph, joined to the rest where ideas are shared.
   The job keeps ``chapters_done``: after a failure, a retry continues with the next chapter.
2. **Study** a part: a study session (SPEC §22) that starts with the part's ideas (no sketch step), plus the ideas from
   outside the part that they build on (the probe checks those; one the learner lacks is taught first). The teaching
   turns get the part's own pages. When the session is done, so is the part.
3. **Homework**: a recall practice (SPEC §24) over the part's ideas; each idea then has its own review schedule.

Big goals (Ohtani table, ``books.py`` book goals) are on hold beside this, not removed.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING

from . import graph, practice, session
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

CHUNK_PAGES = 12          # a book without an outline is cut into parts of this many pages
CHAPTER_CHARS = 80_000    # page text sent per chapter, at most
PAGE_CHARS = 3_000        # one page's text, at most
KINDS = ("concept", "formula", "method", "fact", "term")
PART_MAX = 10             # a part with more ideas is split into sessions of at most PART_SPLIT ideas
PART_SPLIT = 8
GRAPH_LIST_MAX = 400      # up to this many older graph ideas, the mapper sees all their titles; above, a word search
_SPLIT = re.compile(r" \((\d+)/(\d+)\)$")
_SKIP = re.compile(r"^(table of )?contents$|^index$|^acknowledg|^copyright|^about the author|^also by|^dedication"
                   r"|^title page$|^cover$|^bibliography$|^references$", re.I)

MAP_SCHEMA = {"type": "object", "required": ["parts"], "properties": {
    "parts": {"type": "array", "items": {"type": "object", "required": ["part", "summary", "ideas"], "properties": {
        "part": {"type": "integer"},
        "summary": {"type": "string"},
        "ideas": {"type": "array", "items": {"type": "object",
            "required": ["key", "title", "statement", "kind", "pages", "prereq_keys"], "properties": {
                "key": {"type": "string"}, "title": {"type": "string"}, "statement": {"type": "string"},
                "kind": {"enum": list(KINDS)}, "pages": {"type": "string"},
                "prereq_keys": {"type": "array", "items": {"type": "string"}},
                "same_as": {"type": "string"}}}}}}}}}


class BookError(Exception):
    pass


# ---------------------------------------------------------------- parts from the outline

def parts_from_outline(outline: list[dict], n_pages: int) -> list[dict]:
    """The study parts of a book: [{chapter, chapter_title, title, page_from, page_to}] in reading order.

    The chapter level is the shallowest outline level with at least 3 entries (some PDFs put one root entry above the
    chapters). A chapter's sections (the next level) are its parts; pages before the first section go to the first
    one. Front matter (contents, index, …) is left out. Without a usable outline, the book is cut into fixed chunks."""
    items = [o for o in outline if o.get("page") and not _SKIP.search(o["title"].strip())]
    levels = sorted({o["level"] for o in items})
    chapter_level = next((lv for lv in levels if sum(1 for o in items if o["level"] == lv) >= 3), None)
    if chapter_level is None:
        return [{"chapter": n + 1, "chapter_title": f"Pages {a}-{min(a + CHUNK_PAGES - 1, n_pages)}",
                 "title": f"Pages {a}-{min(a + CHUNK_PAGES - 1, n_pages)}", "page_from": a,
                 "page_to": min(a + CHUNK_PAGES - 1, n_pages)}
                for n, a in enumerate(range(1, n_pages + 1, CHUNK_PAGES))]
    top = [o for o in items if o["level"] <= chapter_level]
    top.sort(key=lambda o: o["page"])
    chapters = [o for o in top if o["level"] == chapter_level]
    out: list[dict] = []
    for ci, ch in enumerate(chapters):
        at = next(i for i, o in enumerate(top) if o is ch)
        nxt = next((o["page"] for o in top[at + 1:] if o["page"] > ch["page"]), n_pages + 1)
        end = max(ch["page"], nxt - 1)
        secs = sorted([o for o in items if o["level"] == chapter_level + 1 and ch["page"] <= o["page"] <= end],
                      key=lambda o: o["page"])
        if not secs:
            out.append({"chapter": ci + 1, "chapter_title": ch["title"], "title": ch["title"],
                        "page_from": ch["page"], "page_to": end})
            continue
        for si, sec in enumerate(secs):
            start = ch["page"] if si == 0 else sec["page"]
            stop = (secs[si + 1]["page"] - 1) if si + 1 < len(secs) else end
            out.append({"chapter": ci + 1, "chapter_title": ch["title"], "title": sec["title"],
                        "page_from": start, "page_to": max(sec["page"], stop)})
    return out


# ---------------------------------------------------------------- reading

def get(db: DB, bid: str) -> dict | None:
    return db.one("SELECT * FROM books WHERE id=?", (bid,))


def parts(db: DB, bid: str) -> list[dict]:
    return db.q("SELECT * FROM book_parts WHERE book_id=? ORDER BY ord", (bid,))


def _chapters(db: DB, bid: str) -> list[list[dict]]:
    by: dict[int, list[dict]] = {}
    for p in parts(db, bid):
        by.setdefault(p["chapter"], []).append(p)
    return [by[k] for k in sorted(by)]


def listing(db: DB) -> list[dict]:
    """Book studies, newest first, with their ideas: how many, how many known and how many strong (the shelf's rings)."""
    st = graph.states(db)
    counts: dict[str, dict] = {}
    for r in db.q("SELECT book_id, node_id FROM book_nodes"):
        c = counts.setdefault(r["book_id"], {"ideas": 0, "known": 0, "strong": 0})
        s = st.get(r["node_id"])
        c["ideas"] += 1
        c["known"] += int(bool(s) and s.state in ("learned", "mastered", "rusty"))
        c["strong"] += int(bool(s) and s.state == "mastered")
    out = []
    for b in db.q("SELECT b.*, s.author FROM books b LEFT JOIN sources s ON s.id = b.source_id ORDER BY b.updated_at DESC"):
        ps = parts(db, b["id"])
        out.append({"id": b["id"], "sourceId": b["source_id"], "title": b["title"], "author": b["author"] or "",
                    "status": b["status"], "chapters": b["chapters"], "chaptersDone": b["chapters_done"],
                    "parts": len(ps), "partsDone": sum(1 for p in ps if p["status"] == "done"),
                    **counts.get(b["id"], {"ideas": 0, "known": 0, "strong": 0}), "updatedAt": b["updated_at"]})
    return out


def view(db: DB, bid: str) -> dict | None:
    b = get(db, bid)
    if not b:
        return None
    st = graph.states(db)
    nodes_by_part: dict[int, list[dict]] = {}
    for r in db.q("""SELECT bn.*, n.title, n.statement, n.kind FROM book_nodes bn JOIN nodes n ON n.id = bn.node_id
                     WHERE bn.book_id=? ORDER BY bn.part_id, bn.ord""", (bid,)):
        s = st.get(r["node_id"])
        others = [x["book_id"] for x in db.q("SELECT book_id FROM book_nodes WHERE node_id=? AND book_id!=?", (r["node_id"], bid))]
        nodes_by_part.setdefault(r["part_id"], []).append(
            {"id": r["node_id"], "title": r["title"], "statement": r["statement"], "kind": r["kind"], "pages": r["pages"],
             "state": s.state if s else "pending", "fromGraph": not r["created"], "otherBooks": others})
    running = db.one("SELECT status, error, progress FROM jobs WHERE kind='book_map' AND input LIKE ? ORDER BY id DESC LIMIT 1",
                     (f'%"{bid}"%',))
    ps = []
    for p in parts(db, bid):
        ps.append({"id": p["id"], "ord": p["ord"], "chapter": p["chapter"], "chapterTitle": p["chapter_title"],
                   "title": p["title"], "pages": [p["page_from"], p["page_to"]], "summary": p["summary"],
                   "status": p["status"], "sessionId": p["session_id"], "practiceId": p["practice_id"],
                   "ideas": nodes_by_part.get(p["id"], [])})
    # the part you are in the middle of comes first, else the first part not done
    nxt = (next((p["id"] for p in ps if p["status"] == "studying" and p["ideas"]), None)
           or next((p["id"] for p in ps if p["status"] != "done" and p["ideas"]), None))
    return {"id": b["id"], "sourceId": b["source_id"], "title": b["title"], "status": b["status"],
            "chapters": b["chapters"], "chaptersDone": b["chapters_done"], "parts": ps, "next": nxt,
            "error": running["error"] if running and running["status"] == "failed" else None,
            "progress": (loads(running["progress"], []) or [""])[-1] if running and running["status"] in ("queued", "running") else "",
            "busy": bool(running and running["status"] in ("queued", "running"))}


# ---------------------------------------------------------------- learner actions

def start(db: DB, jobs: Jobs, source_id: str) -> str:
    """Make the book's parts and map it. Starting a book that exists opens it (and retries a failed map)."""
    src = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not src:
        raise BookError("unknown source")
    if src["status"] != "ready":
        raise BookError("this PDF has no readable text yet")
    old = db.one("SELECT * FROM books WHERE source_id=?", (source_id,))
    if old:
        if old["status"] in ("failed", "mapping") and not jobs.active("book_map", book_id=old["id"]):
            db.x("UPDATE books SET status='mapping', updated_at=? WHERE id=?", (now(), old["id"]))
            jobs.enqueue("book_map", f"Map the book: {old['title'][:60]}", {"book_id": old["id"]})
        return old["id"]
    ps = parts_from_outline(loads(src["outline"], []), src["pages"])
    if not ps:
        raise BookError("the book has no pages to study")
    bid = f"b-{secrets.token_hex(4)}"
    ts = now()
    with db.tx():
        db.conn.execute("""INSERT INTO books(id, source_id, title, status, chapters_done, chapters, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (bid, source_id, src["title"], "mapping", 0, len({p["chapter"] for p in ps}), ts, ts))
        for n, p in enumerate(ps):
            db.conn.execute("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to)
                               VALUES(?,?,?,?,?,?,?)""",
                            (bid, n, p["chapter"], p["chapter_title"][:200], p["title"][:200], p["page_from"], p["page_to"]))
    jobs.enqueue("book_map", f"Map the book: {src['title'][:60]}", {"book_id": bid})
    return bid


def retry(db: DB, jobs: Jobs, bid: str) -> None:
    b = get(db, bid)
    if b and b["status"] != "ready" and not jobs.active("book_map", book_id=bid):
        db.x("UPDATE books SET status='mapping', updated_at=? WHERE id=?", (now(), bid))
        jobs.enqueue("book_map", f"Map the book: {b['title'][:60]}", {"book_id": bid})


def _part(db: DB, part_id: int) -> dict:
    p = db.one("SELECT * FROM book_parts WHERE id=?", (part_id,))
    if not p:
        raise BookError("unknown part")
    return p


def study(db: DB, jobs: Jobs, part_id: int) -> str:
    """Start (or reopen) the study session of one part."""
    p = _part(db, part_id)
    if p["session_id"] and session.get(db, p["session_id"]):
        return p["session_id"]
    b = get(db, p["book_id"])
    own = db.q("""SELECT bn.node_id, bn.key, bn.pages, n.title, n.statement FROM book_nodes bn JOIN nodes n ON n.id = bn.node_id
                  WHERE bn.part_id=? ORDER BY bn.ord""", (part_id,))
    if not own:
        raise BookError("this part has no ideas to study")
    own_ids = {r["node_id"] for r in own}
    into: dict[str, set[str]] = {}
    for lk in graph.links(db):
        if lk["dst"] in own_ids:
            into.setdefault(lk["dst"], set()).add(lk["src"])
    outside = sorted({s for srcs in into.values() for s in srcs} - own_ids)
    titles = {r["id"]: r for r in db.q(f"SELECT id, title, statement FROM nodes WHERE id IN ({','.join('?' * len(outside))})",
                                       outside)} if outside else {}
    key_of = {r["node_id"]: f"i{n + 1}" for n, r in enumerate(own)}
    key_of.update({nid: f"p{n + 1}" for n, nid in enumerate(n for n in outside if n in titles)})
    ideas = [{"key": key_of[nid], "title": titles[nid]["title"], "statement": titles[nid]["statement"], "node": nid,
              "prereqs": [], "fromGraph": True, "outside": True} for nid in outside if nid in titles]
    for r in own:
        ideas.append({"key": key_of[r["node_id"]], "title": r["title"], "statement": r["statement"], "node": r["node_id"],
                      "prereqs": sorted(key_of[s] for s in into.get(r["node_id"], ()) if s in key_of and s != r["node_id"]),
                      "pages": r["pages"], "fromGraph": False})
    topic = f'{p["title"]} ({b["title"]}, pp. {p["page_from"]}-{p["page_to"]})'
    sid = session.start_from_ideas(db, jobs, topic, p["title"], ideas, [b["source_id"]], book_part=part_id)
    db.x("UPDATE book_parts SET session_id=?, status='studying' WHERE id=?", (sid, part_id))
    db.x("UPDATE books SET updated_at=? WHERE id=?", (now(), b["id"]))
    return sid


def on_session_done(db: DB, sid: str) -> None:
    db.x("UPDATE book_parts SET status='done' WHERE session_id=?", (sid,))


def homework(db: DB, jobs: Jobs, part_id: int) -> str:
    """Recall practice over the part's ideas (and reopen it when it already exists and is not finished)."""
    p = _part(db, part_id)
    if p["practice_id"]:
        row = db.one("SELECT status FROM practices WHERE id=?", (p["practice_id"],))
        if row and row["status"] == "active":
            return p["practice_id"]
    ids = [r["node_id"] for r in db.q("SELECT node_id FROM book_nodes WHERE part_id=? ORDER BY ord", (part_id,))]
    if not ids:
        raise BookError("this part has no ideas to practise")
    pid = practice.start(db, jobs, ids)
    db.x("UPDATE book_parts SET practice_id=? WHERE id=?", (pid, part_id))
    return pid


def delete(db: DB, bid: str) -> None:
    """Remove the book study. Ideas it made stay when the learner has evidence on them or another session or book uses
    them; the others go."""
    if not get(db, bid):
        return
    made = [r["node_id"] for r in db.q("SELECT node_id FROM book_nodes WHERE book_id=? AND created=1", (bid,))]
    with db.tx():
        db.conn.execute("DELETE FROM book_nodes WHERE book_id=?", (bid,))
        db.conn.execute("DELETE FROM book_parts WHERE book_id=?", (bid,))
        db.conn.execute("DELETE FROM books WHERE id=?", (bid,))
        _drop_unused(db, made)


def _drop_unused(db: DB, nids: list[str]) -> None:
    """Inside a transaction: delete book-made ideas that no book, goal, session or evidence uses any more."""
    for nid in nids:
        used = (db.conn.execute("SELECT 1 FROM book_nodes WHERE node_id=?", (nid,)).fetchone()
                or db.conn.execute("SELECT 1 FROM concept_nodes WHERE node_id=?", (nid,)).fetchone()
                or db.conn.execute("SELECT 1 FROM session_nodes WHERE node_id=?", (nid,)).fetchone()
                or db.conn.execute("SELECT 1 FROM evidence WHERE concept_id=?", (nid,)).fetchone())
        if not used:
            db.conn.execute("DELETE FROM nodes WHERE id=? AND origin='book'", (nid,))
            db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (nid,))
            db.conn.execute("DELETE FROM links WHERE src=? OR dst=?", (nid, nid))


# ---------------------------------------------------------------- the map job

def _chapter_text(db: DB, source_id: str, page_from: int, page_to: int) -> str:
    n = max(1, page_to - page_from + 1)
    per = min(PAGE_CHARS, CHAPTER_CHARS // n)
    rows = db.q("SELECT page, text FROM source_pages WHERE source_id=? AND page BETWEEN ? AND ? ORDER BY page",
                (source_id, page_from, page_to))
    return "\n\n".join(f"[p. {r['page']}]\n{r['text'][:per]}" for r in rows if r["text"].strip())


def run_map(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    b = get(db, d["book_id"])
    if not b:
        return {"skipped": True}
    chapters = _chapters(db, b["id"])
    todo = d.get("only") or range(b["chapters_done"], len(chapters))  # "only": re-map chosen chapters (by index)
    try:
        for ci in todo:
            ch = chapters[ci]
            jobs.progress(jid, f"chapter {ci + 1} of {len(chapters)}: {ch[0]['chapter_title'][:80]}")
            _map_chapter(db, jobs, jid, b, ci, ch, prompt, Call)
            if not d.get("only"):
                db.x("UPDATE books SET chapters_done=?, updated_at=? WHERE id=?", (ci + 1, now(), b["id"]))
    except Exception:
        db.x("UPDATE books SET status='failed', updated_at=? WHERE id=?", (now(), b["id"]))
        raise
    db.x("UPDATE books SET status='ready', updated_at=? WHERE id=?", (now(), b["id"]))
    n = db.one("SELECT COUNT(*) AS n FROM book_nodes WHERE book_id=?", (b["id"],))["n"]
    jobs.progress(jid, f"mapped {len(chapters)} chapter(s), {n} ideas")
    return {"chapters": len(chapters), "ideas": n}


def _unsplit(db: DB, ch: list[dict]) -> list[dict]:
    """Before a chapter is mapped again: join the parts an earlier map split (no session yet) back into one."""
    keep = []
    first: dict[str, int] = {}
    for p in ch:
        m = _SPLIT.search(p["title"])
        base = _SPLIT.sub("", p["title"])
        if m and m.group(1) == "1":
            first[base] = p["id"]
        if m and m.group(1) != "1" and not p["session_id"] and base in first:
            db.x("UPDATE book_nodes SET part_id=? WHERE part_id=?", (first[base], p["id"]))  # cleaned up with the chapter
            db.x("DELETE FROM book_parts WHERE id=?", (p["id"],))
            continue
        if m:
            db.x("UPDATE book_parts SET title=? WHERE id=?", (_SPLIT.sub("", p["title"]), p["id"]))
            p = {**p, "title": _SPLIT.sub("", p["title"])}
        keep.append(p)
    return keep


def _subsections(db: DB, b: dict, p: dict) -> list[str]:
    """The outline titles one level below a part, to help the mapper place ideas."""
    src = db.one("SELECT outline FROM sources WHERE id=?", (b["source_id"],))
    items = [o for o in loads(src["outline"] if src else "[]", []) if o.get("page")]
    mine = next((o for o in items if o["title"] == p["title"]), None)
    if not mine:
        return []
    return [o["title"] for o in items
            if o["level"] == mine["level"] + 1 and p["page_from"] <= o["page"] <= p["page_to"]][:12]


def _graph_context(db: DB, ch: list[dict], text: str, mine: set[str]) -> str:
    """Older graph ideas the mapper may reuse (same_as) or build on: all their titles while the graph is small (a word
    search misses synonyms such as "matmul" and "matrix multiplication"), else the best word-search matches."""
    others = [r for r in db.q("SELECT id, title, statement FROM nodes ORDER BY title") if r["id"] not in mine]
    if len(others) <= GRAPH_LIST_MAX:
        return "\n".join(f'- {r["id"]}: {r["title"]}' for r in others) or "(the graph is empty)"
    found: dict[str, dict] = {}
    for q in [p["title"] for p in ch] + [f'{ch[0]["chapter_title"]} {text[:3000]}']:
        for c in graph.candidates(db, q, k=12):
            if c["id"] not in mine:
                found.setdefault(c["id"], c)
    return graph.candidates_text(list(found.values())[:60])


def _split_big_parts(db: DB, b: dict, ch: list[dict]) -> None:
    """A part with more than PART_MAX ideas becomes several parts of at most PART_SPLIT ideas, in the book's order
    (each one study session), with the same pages. Then the book's parts are numbered again."""
    for p in ch:
        rows = db.q("SELECT node_id FROM book_nodes WHERE part_id=? ORDER BY ord", (p["id"],))
        if len(rows) <= PART_MAX or p["session_id"]:
            continue
        groups = [rows[i:i + PART_SPLIT] for i in range(0, len(rows), PART_SPLIT)]
        if len(groups) > 1 and len(groups[-1]) < 3:  # no tiny last session
            groups[-2] += groups.pop()
        n = len(groups)
        summary = (db.one("SELECT summary FROM book_parts WHERE id=?", (p["id"],)) or {}).get("summary", "")
        db.x("UPDATE book_parts SET title=? WHERE id=?", (f'{p["title"]} (1/{n})', p["id"]))
        for gi, g in enumerate(groups[1:], start=2):
            new = db.x("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to, summary)
                          VALUES(?,?,?,?,?,?,?,?)""",
                       (b["id"], p["ord"], p["chapter"], p["chapter_title"], f'{p["title"]} ({gi}/{n})',
                        p["page_from"], p["page_to"], summary))
            for r in g:
                db.x("UPDATE book_nodes SET part_id=? WHERE part_id=? AND node_id=?", (new, p["id"], r["node_id"]))
    for n, r in enumerate(db.q("SELECT id FROM book_parts WHERE book_id=? ORDER BY ord, id", (b["id"],))):
        db.x("UPDATE book_parts SET ord=? WHERE id=?", (n, r["id"]))


def _map_chapter(db: DB, jobs: Jobs, jid: int, b: dict, ci: int, ch: list[dict], prompt, Call) -> None:
    graph.sync(db)  # every goal concept has its node before the mapper sees the graph
    ch = _unsplit(db, ch)
    lines = []
    for n, p in enumerate(ch):
        subs = _subsections(db, b, p)
        lines.append(f'{n}. {p["title"]} (pp. {p["page_from"]}-{p["page_to"]})' + (f' [{"; ".join(subs)}]' if subs else ""))
    sections = "\n".join(lines)
    text = _chapter_text(db, b["source_id"], ch[0]["page_from"], ch[-1]["page_to"])
    # The chapter's own earlier result (a re-map) does not count: it is replaced below.
    here = [p["id"] for p in ch]
    not_here = f"AND bn.part_id NOT IN ({','.join('?' * len(here))})"
    earlier = db.q(f"""SELECT bn.key, bn.node_id, n.title FROM book_nodes bn JOIN nodes n ON n.id = bn.node_id
                       WHERE bn.book_id=? {not_here} ORDER BY bn.part_id, bn.ord""", (b["id"], *here))
    earlier_text = "\n".join(f'- {r["key"]}: {r["title"]}' for r in earlier) or "(none: this is the first chapter)"
    mine = {r["node_id"] for r in earlier}
    # Every idea of this book (also this chapter's own earlier result) is never "older": earlier chapters are linked
    # by key, and this chapter's old result is replaced.
    book_all = {r["node_id"] for r in db.q("SELECT node_id FROM book_nodes WHERE book_id=?", (b["id"],))}
    older = _graph_context(db, ch, text, book_all)
    out = jobs.call(jid, "Book map", Call(
        prompt=prompt("book_map", book=b["title"], chapter=ch[0]["chapter_title"], sections=sections,
                      earlier=earlier_text, graph=older, text=text or "(no text on these pages)"),
        schema=MAP_SCHEMA, model="opus", timeout=900))
    key_node = {r["key"]: r["node_id"] for r in earlier}
    existing = {r["id"] for r in db.q("SELECT id FROM nodes")}
    prefix = f"c{ci + 1}-"
    ts = now()
    pending_links: list[tuple[str, list[str]]] = []
    with db.tx():
        old = [r[0] for r in db.conn.execute(
            "SELECT node_id FROM book_nodes WHERE book_id=? AND created=1 AND part_id IN (%s)" % ",".join("?" * len(ch)),
            (b["id"], *here)).fetchall()]
        db.conn.execute("DELETE FROM book_nodes WHERE book_id=? AND part_id IN (%s)" % ",".join("?" * len(ch)),
                        (b["id"], *here))  # a retried chapter starts clean
        _drop_unused(db, old)
        for entry in out.get("parts") or []:
            if not isinstance(entry.get("part"), int) or not 0 <= entry["part"] < len(ch):
                continue
            part = ch[entry["part"]]
            db.conn.execute("UPDATE book_parts SET summary=? WHERE id=?", ((entry.get("summary") or "")[:600], part["id"]))
            for n, idea in enumerate(entry.get("ideas") or []):
                title = " ".join((idea.get("title") or "").split())[:200]
                if not title:
                    continue
                key = idea["key"] if idea["key"].startswith(prefix) else prefix + idea["key"]
                if key in key_node:
                    continue  # a duplicate key: the first one wins
                same = idea.get("same_as")
                if same in existing and same not in book_all and same not in mine:
                    node, created = same, 0
                    if db.conn.execute("SELECT 1 FROM book_nodes WHERE book_id=? AND node_id=?", (b["id"], node)).fetchone():
                        key_node[key] = node  # this book already uses it in an earlier part
                        continue
                else:
                    node, created = f"n-{secrets.token_hex(5)}", 1
                    kind = idea.get("kind") if idea.get("kind") in KINDS else "concept"
                    db.conn.execute("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                                    (node, title, (idea.get("statement") or "")[:600], kind, ts, "book"))
                    db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)",
                                    (node, f'{title} {idea.get("statement") or ""}'))
                    mine.add(node)
                db.conn.execute("""INSERT OR IGNORE INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                                   VALUES(?,?,?,?,?,?,?)""",
                                (b["id"], node, part["id"], key, (idea.get("pages") or "")[:40], created, n))
                key_node[key] = node
                pending_links.append((node, idea.get("prereq_keys") or []))
        for node, prereqs in pending_links:
            for pk in prereqs:
                src = key_node.get(pk) or key_node.get(prefix + pk) or (pk if pk in existing and pk not in book_all else None)
                if src and src != node:
                    db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (src, node, "", "book"))
    _split_big_parts(db, b, ch)
