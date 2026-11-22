"""Book study: "teach me this book" (SPEC §28, §31). Version 2: a book is chapters, a chapter is lessons.

A book you read can be read again: every lesson stays open, whatever you already know.

1. **Start**: the book gets a hidden goal (``goals.kind = 'bookstudy'``) so the lesson machinery works unchanged: one
   track for the book, one module per chapter (``book_chapters.module_id``), one concept per lesson.
2. **Map** (job ``book_map``, one call per chapter, from the chapter's page text): a short chapter summary and the
   chapter's lessons, cut **by topic** (one book section can become several lessons, small ones can join). A lesson has
   a title, what it covers, its pages, its key ideas, the lessons it builds on (also in earlier chapters) and
   ``same_as`` when it is an idea already in the graph (another book, a goal). A lesson is one concept and one node of
   the knowledge map; prerequisites become concept prerequisites or links.
3. **Write** a lesson on first open (``research_module`` for a book goal runs ``write_cards``): the cards of the
   chapter's lessons are written from the chapter's pages only (no web), one section per stretch of the book, each with
   a close summary of what the book says (``section.book``) and its pages, plus checks, an explain-back and graphs. The
   normal lesson writer then writes "what it means" for this learner (playbook, guidelines, feedback), and the lesson
   is saved (prose cache and lesson versions). Research-ahead writes the next chapter in the background.
4. **Homework**: recall practice over a chapter's lessons.

Version 1 (parts taught as study sessions) is kept for books mapped before (``books.version = 1``).
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING

from . import graph, mcq, practice, viz
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

CHUNK_PAGES = 12          # a book without an outline is cut into chapters of this many pages
CHAPTER_CHARS = 80_000    # page text sent per chapter, at most
PAGE_CHARS = 3_000        # one page's text, at most
LESSON_MINUTES = 15
GRAPH_LIST_MAX = 400      # up to this many older graph ideas, the mapper sees all their titles; above, a word search
KNOWN = ("learned", "mastered", "rusty")
_SKIP = re.compile(r"^(table of )?contents$|^index$|^acknowledg|^copyright|^about the author|^also by|^dedication"
                   r"|^title page$|^cover$|^bibliography$|^references$", re.I)
# Back matter that is looked up, not studied: kept as a chapter (its pages count) but not cut into lessons.
_REFERENCE = re.compile(r"glossary|recommended reading|further reading|reading list|bibliography|^references$|^index$"
                        r"|^notes$|^endnotes$|^answers to|^solutions to|^list of (figures|tables)", re.I)
_PAGES = re.compile(r"(\d+)\s*(?:[-–]\s*(\d+))?")

MAP_SCHEMA = {"type": "object", "required": ["summary", "lessons"], "properties": {
    "summary": {"type": "string"},
    "lessons": {"type": "array", "items": {"type": "object",
        "required": ["key", "title", "covers", "pages", "ideas", "prereq_keys"], "properties": {
            "key": {"type": "string"}, "title": {"type": "string"}, "covers": {"type": "string"}, "pages": {"type": "string"},
            "ideas": {"type": "array", "items": {"type": "string"}},
            "prereq_keys": {"type": "array", "items": {"type": "string"}},
            "same_as": {"type": "string"}}}}}}

_ANGLES = {"enum": ["geometric", "algebraic", "computational"]}
CARDS_SCHEMA = {"type": "object", "required": ["cards"], "properties": {"cards": {"type": "array", "items": {
    "type": "object", "required": ["id", "card"], "properties": {
        "id": {"type": "string"},
        "card": {"type": "object", "required": ["bloom", "core", "formal", "why", "examples", "misconceptions", "sections"],
                 "properties": {
                     "bloom": {"type": "string"}, "core": {"type": "string"}, "formal": {"type": "string"}, "why": {"type": "string"},
                     "examples": {"type": "array", "items": {"type": "object", "required": ["label", "domain"], "properties": {
                         "label": {"type": "string"}, "domain": {"type": "string"}}}},
                     "misconceptions": {"type": "array", "items": {"type": "string"}},
                     "sections": {"type": "array", "minItems": 1, "items": {"type": "object",
                         "required": ["id", "heading", "purpose", "angles", "book"], "properties": {
                             "id": {"type": "string"}, "heading": {"type": "string"}, "purpose": {"type": "string"},
                             "angles": {"type": "array", "minItems": 1, "items": _ANGLES},
                             "book": {"type": "object", "required": ["summary", "pages"], "properties": {
                                 "summary": {"type": "string"}, "pages": {"type": "string"}}},
                             "check": mcq.SCHEMA,
                             "explain": {"type": "object", "required": ["prompt", "rubric"], "properties": {
                                 "prompt": {"type": "string"}, "work": {"type": "boolean"},
                                 "rubric": {"type": "array", "minItems": 1, "items": {"type": "string"}}}},
                             "viz": viz.SCHEMA}}}}}}}}}}


class BookError(Exception):
    pass


# ---------------------------------------------------------------- chapters from the outline

def parts_from_outline(outline: list[dict], n_pages: int) -> list[dict]:
    """The book's sections: [{chapter, chapter_title, title, page_from, page_to}] in reading order.

    The chapter level is the shallowest outline level with at least 3 entries (some PDFs put one root entry above the
    chapters). A chapter's sections (the next level) follow; pages before the first section go to the first one. Front
    matter (contents, index, …) is left out. Without a usable outline, the book is cut into fixed chunks."""
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
    bounds = sorted(o["page"] for o in outline if o.get("page") and o["level"] <= chapter_level)
    chapters = [o for o in top if o["level"] == chapter_level]
    out: list[dict] = []
    for ci, ch in enumerate(chapters):
        nxt = next((p for p in bounds if p > ch["page"]), n_pages + 1)
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


def chapters_from_outline(outline: list[dict], n_pages: int) -> list[dict]:
    """[{chapter, title, page_from, page_to, kind, sections: [{title, page_from, page_to}]}]. kind: chapter | reference
    (a glossary, a reading list, …: looked up, not cut into lessons)."""
    out: list[dict] = []
    for p in parts_from_outline(outline, n_pages):
        if not out or out[-1]["chapter"] != p["chapter"]:
            out.append({"chapter": p["chapter"], "title": p["chapter_title"], "page_from": p["page_from"],
                        "page_to": p["page_to"], "sections": [],
                        "kind": "reference" if _REFERENCE.search(_bare(p["chapter_title"])) else "chapter"})
        ch = out[-1]
        ch["page_to"] = max(ch["page_to"], p["page_to"])
        if p["title"] != p["chapter_title"]:
            ch["sections"].append({"title": p["title"], "page_from": p["page_from"], "page_to": p["page_to"]})
    return out


def _bare(title: str) -> str:
    """A chapter title without its number: "Appendix A: Inference Glossary" -> "Inference Glossary"."""
    return re.sub(r"^\s*(appendix|chapter|part)?\s*[\w.]{0,4}\s*[:.\-–]\s*", "", title.strip(), flags=re.I)


def _pages(text: str, lo: int, hi: int) -> tuple[int, int]:
    m = _PAGES.search(text or "")
    if not m:
        return lo, hi
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    a, b = max(lo, min(a, hi)), max(lo, min(max(a, b), hi))
    return a, b


# ---------------------------------------------------------------- reading

def get(db: DB, bid: str) -> dict | None:
    return db.one("SELECT * FROM books WHERE id=?", (bid,))


def _book_of_goal(db: DB, gid: str) -> dict | None:
    return db.one("SELECT * FROM books WHERE goal_id=?", (gid,))


def listing(db: DB) -> list[dict]:
    """Book studies, newest first, with their lessons: how many, how many known and how many strong (the shelf's rings)."""
    st = graph.states(db)
    counts: dict[str, dict] = {}
    for r in db.q("SELECT book_id, node_id FROM book_nodes"):
        c = counts.setdefault(r["book_id"], {"ideas": 0, "known": 0, "strong": 0})
        s = st.get(r["node_id"])
        c["ideas"] += 1
        c["known"] += int(bool(s) and s.state in KNOWN)
        c["strong"] += int(bool(s) and s.state == "mastered")
    out = []
    for b in db.q("SELECT b.*, s.author FROM books b LEFT JOIN sources s ON s.id = b.source_id ORDER BY b.updated_at DESC"):
        n = db.one("SELECT COUNT(*) AS n FROM book_chapters WHERE book_id=?", (b["id"],))["n"] or b["chapters"]
        done = sum(1 for ch in _chapter_rows(db, b["id"]) if ch["lessons"] and all(x["state"] in KNOWN for x in ch["lessons"]))
        out.append({"id": b["id"], "sourceId": b["source_id"], "title": b["title"], "author": b["author"] or "",
                    "status": b["status"], "chapters": b["chapters"], "chaptersDone": b["chapters_done"],
                    "parts": n, "partsDone": done, "goalId": b["goal_id"],
                    **counts.get(b["id"], {"ideas": 0, "known": 0, "strong": 0}), "updatedAt": b["updated_at"]})
    return out


def _chapter_rows(db: DB, bid: str, st: dict | None = None) -> list[dict]:
    st = st if st is not None else graph.states(db)
    nodes = graph.node_of(db)
    others: dict[str, list[str]] = {}
    for r in db.q("SELECT node_id, book_id FROM book_nodes WHERE book_id != ?", (bid,)):
        others.setdefault(r["node_id"], []).append(r["book_id"])
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM books")}
    written = {r["concept_id"] for r in db.q("SELECT DISTINCT concept_id FROM cards")}
    rendered = {r["concept_id"] for r in db.q("SELECT DISTINCT concept_id FROM prose")}
    started = {r["id"] for r in db.q("SELECT id FROM concepts WHERE started=1")}
    out = []
    for ch in db.q("SELECT * FROM book_chapters WHERE book_id=? ORDER BY chapter", (bid,)):
        lessons = []
        for p in db.q("SELECT * FROM book_parts WHERE book_id=? AND chapter=? AND concept_id IS NOT NULL ORDER BY ord",
                      (bid, ch["chapter"])):
            cid = p["concept_id"]
            nid = nodes.get(cid, cid)
            s = st.get(nid) or st.get(cid)
            lessons.append({"id": p["id"], "conceptId": cid, "nodeId": nid, "title": p["title"], "covers": p["summary"],
                            "pages": [p["page_from"], p["page_to"]], "ideas": loads(p["ideas"], []),
                            "state": s.state if s else "pending", "mastery": s.mastery if s else 0.0,
                            "written": cid in rendered, "carded": cid in written, "started": cid in started,
                            "alsoIn": [{"id": o, "title": titles.get(o, o)} for o in others.get(nid, [])]})
        out.append({"chapter": ch["chapter"], "title": ch["title"], "summary": ch["summary"], "pages": [ch["page_from"], ch["page_to"]],
                    "moduleId": ch["module_id"], "mapped": bool(ch["mapped"]), "kind": ch["kind"], "lessons": lessons})
    return out


def view(db: DB, bid: str) -> dict | None:
    b = get(db, bid)
    if not b:
        return None
    chapters = _chapter_rows(db, bid)
    running = db.one("SELECT status, error, progress FROM jobs WHERE kind='book_map' AND input LIKE ? ORDER BY id DESC LIMIT 1",
                     (f'%"{bid}"%',))
    research = {r["id"]: r["research"] for r in db.q("SELECT id, research FROM modules")}
    for ch in chapters:
        ch["writing"] = research.get(ch["moduleId"]) == "researching"
    order = [x for ch in chapters for x in ch["lessons"]]
    nxt = (next((x for x in order if x["started"] and x["state"] not in KNOWN), None)
           or next((x for x in order if x["state"] not in KNOWN), None))
    return {"id": b["id"], "sourceId": b["source_id"], "title": b["title"], "status": b["status"], "goalId": b["goal_id"],
            "version": b["version"], "chapters": chapters, "chapterCount": b["chapters"], "chaptersDone": b["chapters_done"],
            "next": nxt["conceptId"] if nxt else None,
            "error": running["error"] if running and running["status"] == "failed" else None,
            "progress": (loads(running["progress"], []) or [""])[-1] if running and running["status"] in ("queued", "running") else "",
            "busy": bool(running and running["status"] in ("queued", "running"))}


def lesson_book(db: DB, cid: str) -> dict | None:
    """For a lesson page: the book, chapter and pages of a book lesson, and its neighbours in reading order."""
    p = db.one("SELECT * FROM book_parts WHERE concept_id=?", (cid,))
    if not p:
        return None
    b = get(db, p["book_id"])
    order = [r["concept_id"] for r in db.q("SELECT concept_id FROM book_parts WHERE book_id=? AND concept_id IS NOT NULL ORDER BY ord",
                                            (p["book_id"],))]
    i = order.index(cid)
    title = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts WHERE id IN (%s)" % ",".join("?" * len(order)), order)}
    near = lambda j: {"id": order[j], "title": title.get(order[j], "")} if 0 <= j < len(order) else None  # noqa: E731
    return {"bookId": b["id"], "bookTitle": b["title"], "sourceId": b["source_id"], "chapter": p["chapter"],
            "chapterTitle": p["chapter_title"], "pages": [p["page_from"], p["page_to"]], "covers": p["summary"],
            "prev": near(i - 1), "next": near(i + 1), "index": i + 1, "count": len(order)}


# ---------------------------------------------------------------- learner actions

def start(db: DB, jobs: Jobs, source_id: str) -> str:
    """Make the book's hidden goal and chapters, then map it. Starting a book that exists opens it (and retries a failed map)."""
    src = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not src:
        raise BookError("unknown source")
    if src["status"] != "ready":
        raise BookError("this PDF has no readable text yet")
    old = db.one("SELECT * FROM books WHERE source_id=?", (source_id,))
    if old and old["version"] == 1:  # a book mapped as parts: map it again as chapters of lessons (sessions and ideas stay)
        delete(db, old["id"])
        old = None
    if old:
        retry(db, jobs, old["id"])
        return old["id"]
    chapters = chapters_from_outline(loads(src["outline"], []), src["pages"])
    if not chapters:
        raise BookError("the book has no pages to study")
    tag = secrets.token_hex(4)
    bid, gid = f"b-{tag}", f"g-book-{tag}"
    ts = now()
    with db.tx():
        db.conn.execute("""INSERT INTO goals(id, title, why, done, hours, profile, created_at, kind)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (gid, src["title"], f"Study the book {src['title']}", "", 5, "", ts, "bookstudy"))
        db.conn.execute("INSERT INTO tracks(id, goal_id, ord, title, summary) VALUES(?,?,?,?,?)",
                        (f"{gid}-t", gid, 0, src["title"], src["author"] or ""))
        for ch in chapters:
            mid = f"{gid}-c{ch['chapter']}"
            db.conn.execute("""INSERT INTO modules(id, track_id, ord, title, research, planned, summary, seq)
                               VALUES(?,?,?,?,?,?,?,?)""", (mid, f"{gid}-t", ch["chapter"], ch["title"][:200], "outline", 0, "", ch["chapter"]))
            db.conn.execute("""INSERT INTO book_chapters(book_id, chapter, title, page_from, page_to, sections, module_id, kind)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (bid, ch["chapter"], ch["title"][:200], ch["page_from"], ch["page_to"], dumps(ch["sections"]), mid,
                             ch["kind"]))
        db.conn.execute("""INSERT INTO books(id, source_id, title, status, chapters_done, chapters, created_at, updated_at, goal_id, version)
                           VALUES(?,?,?,?,?,?,?,?,?,2)""", (bid, source_id, src["title"], "mapping", 0, len(chapters), ts, ts, gid))
    jobs.enqueue("book_map", f"Map the book: {src['title'][:60]}", {"book_id": bid})
    return bid


def retry(db: DB, jobs: Jobs, bid: str) -> None:
    b = get(db, bid)
    if b and b["status"] != "ready" and not jobs.active("book_map", book_id=bid):
        db.x("UPDATE books SET status='mapping', updated_at=? WHERE id=?", (now(), bid))
        jobs.enqueue("book_map", f"Map the book: {b['title'][:60]}", {"book_id": bid})


def remap_chapter(db: DB, jobs: Jobs, bid: str, chapter: int, as_lessons: bool = False) -> None:
    """Cut one chapter into lessons again: its lessons and their written text go, the map job maps it anew. What the
    learner did stays: answers, notes and feedback are kept by lesson id, and a new lesson with the same key gets them
    back. ``as_lessons``: a reference chapter (glossary, reading list) is cut into lessons after all."""
    b = get(db, bid)
    ch = db.one("SELECT * FROM book_chapters WHERE book_id=? AND chapter=?", (bid, chapter))
    if not b or not ch:
        raise BookError("unknown chapter")
    if jobs.active("book_map", book_id=bid) or jobs.active("research_module", module_id=ch["module_id"]):
        raise BookError("this book is being mapped or written right now; try again when it is done")
    cids = [r["concept_id"] for r in db.q("SELECT concept_id FROM book_parts WHERE book_id=? AND chapter=? AND concept_id IS NOT NULL",
                                          (bid, chapter))]
    made = [r["node_id"] for r in db.q("""SELECT bn.node_id FROM book_nodes bn JOIN book_parts p ON p.id = bn.part_id
                                         WHERE bn.book_id=? AND p.chapter=? AND bn.created=1""", (bid, chapter))]
    with db.tx():
        for cid in cids:
            for t in ("cards", "prose", "renditions", "lesson_versions", "lesson_heads", "lesson_plans", "card_proposals",
                      "concept_nodes"):
                db.conn.execute(f"DELETE FROM {t} WHERE concept_id=?", (cid,))
            db.conn.execute("DELETE FROM concepts WHERE id=?", (cid,))
        db.conn.execute("""DELETE FROM book_nodes WHERE book_id=? AND part_id IN
                           (SELECT id FROM book_parts WHERE book_id=? AND chapter=?)""", (bid, bid, chapter))
        db.conn.execute("DELETE FROM book_parts WHERE book_id=? AND chapter=?", (bid, chapter))
        db.conn.execute("UPDATE book_chapters SET mapped=0, summary='', kind=? WHERE book_id=? AND chapter=?",
                        ("chapter" if as_lessons else ch["kind"], bid, chapter))
        db.conn.execute("UPDATE modules SET research='outline', planned=0, summary='' WHERE id=?", (ch["module_id"],))
        db.conn.execute("UPDATE books SET status='mapping', updated_at=? WHERE id=?", (now(), bid))
        _drop_unused(db, made)
    graph.prune(db)
    jobs.enqueue("book_map", f"Map again: {ch['title'][:60]}", {"book_id": bid})


def homework(db: DB, jobs: Jobs, bid: str, chapter: int) -> str:
    """Recall practice over a chapter's lessons."""
    ids = [r["node_id"] for r in db.q("""SELECT bn.node_id FROM book_nodes bn JOIN book_parts p ON p.id = bn.part_id
                                         WHERE bn.book_id=? AND p.chapter=? ORDER BY p.ord""", (bid, chapter))]
    if not ids:
        raise BookError("this chapter has no lessons to practise yet")
    return practice.start(db, jobs, ids)


def on_session_done(db: DB, sid: str) -> None:
    """Version 1 books: a part's study session is done."""
    db.x("UPDATE book_parts SET status='done' WHERE session_id=?", (sid,))


def delete(db: DB, bid: str) -> None:
    """Remove the book study and its hidden goal (lessons, cards, notes). Graph ideas other goals or books use stay."""
    b = get(db, bid)
    if not b:
        return
    from .seed import delete_goal
    if b["goal_id"]:
        delete_goal(db, b["goal_id"])
    made = [r["node_id"] for r in db.q("SELECT node_id FROM book_nodes WHERE book_id=? AND created=1", (bid,))]
    with db.tx():
        for t in ("book_nodes", "book_parts", "book_chapters"):
            db.conn.execute(f"DELETE FROM {t} WHERE book_id=?", (bid,))
        db.conn.execute("DELETE FROM books WHERE id=?", (bid,))
        _drop_unused(db, made)
    graph.prune(db)


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


def _graph_context(db: DB, title: str, text: str, mine: set[str]) -> str:
    """Older graph ideas the mapper may reuse (same_as) or build on: all their titles while the graph is small (a word
    search misses synonyms such as "matmul" and "matrix multiplication"), else the best word-search matches."""
    others = [r for r in db.q("SELECT id, title, statement FROM nodes ORDER BY title") if r["id"] not in mine]
    if len(others) <= GRAPH_LIST_MAX:
        return "\n".join(f'- {r["id"]}: {r["title"]}' for r in others) or "(the graph is empty)"
    found: dict[str, dict] = {}
    for q in (title, f"{title} {text[:3000]}"):
        for c in graph.candidates(db, q, k=30):
            if c["id"] not in mine:
                found.setdefault(c["id"], c)
    return graph.candidates_text(list(found.values())[:60])


def run_map(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    b = get(db, d["book_id"])
    if not b:
        return {"skipped": True}
    chapters = db.q("SELECT * FROM book_chapters WHERE book_id=? ORDER BY chapter", (b["id"],))
    try:
        for ch in chapters:
            if ch["mapped"]:
                continue
            if ch["kind"] == "reference":  # looked up, not studied: no lessons, no model call
                db.x("UPDATE book_chapters SET mapped=1 WHERE book_id=? AND chapter=?", (b["id"], ch["chapter"]))
            else:
                jobs.progress(jid, f"chapter {ch['chapter']} of {len(chapters)}: {ch['title'][:80]}")
                _map_chapter(db, jobs, jid, b, ch, prompt, Call)
            done = db.one("SELECT COUNT(*) AS n FROM book_chapters WHERE book_id=? AND mapped=1", (b["id"],))["n"]
            db.x("UPDATE books SET chapters_done=?, updated_at=? WHERE id=?", (done, now(), b["id"]))
    except Exception:
        db.x("UPDATE books SET status='failed', updated_at=? WHERE id=?", (now(), b["id"]))
        raise
    db.x("UPDATE books SET status='ready', updated_at=? WHERE id=?", (now(), b["id"]))
    n = db.one("SELECT COUNT(*) AS n FROM book_parts WHERE book_id=? AND concept_id IS NOT NULL", (b["id"],))["n"]
    jobs.progress(jid, f"mapped {len(chapters)} chapter(s), {n} lessons")
    return {"chapters": len(chapters), "lessons": n}


def _map_chapter(db: DB, jobs: Jobs, jid: int, b: dict, ch: dict, prompt, Call) -> None:
    from .jobs import slug
    graph.sync(db)
    secs = loads(ch["sections"], [])
    sections = "\n".join(f'- {s["title"]} (pp. {s["page_from"]}-{s["page_to"]})' for s in secs) or "(no sections in the outline)"
    text = _chapter_text(db, b["source_id"], ch["page_from"], ch["page_to"])
    earlier = db.q("""SELECT p.concept_id, p.title FROM book_parts p WHERE p.book_id=? AND p.chapter < ? AND p.concept_id IS NOT NULL
                      ORDER BY p.ord""", (b["id"], ch["chapter"]))
    earlier_text = "\n".join(f'- {r["concept_id"]}: {r["title"]}' for r in earlier) or "(none: this is the first chapter)"
    mine = {r["node_id"] for r in db.q("SELECT node_id FROM book_nodes WHERE book_id=?", (b["id"],))} \
        | {r["concept_id"] for r in db.q("SELECT concept_id FROM book_parts WHERE book_id=? AND concept_id IS NOT NULL", (b["id"],))}
    older = _graph_context(db, ch["title"], text, mine)
    out = jobs.call(jid, "Book map", Call(
        prompt=prompt("book_map", book=b["title"], chapter=ch["title"], pages=f'{ch["page_from"]}-{ch["page_to"]}',
                      sections=sections, earlier=earlier_text, graph=older, text=text or "(no text on these pages)"),
        schema=MAP_SCHEMA, model="opus", timeout=900))
    existing = {r["id"] for r in db.q("SELECT id FROM nodes")}
    in_book = {r["concept_id"] for r in earlier}
    base = db.one("SELECT COALESCE(MAX(ord), -1) AS o FROM book_parts WHERE book_id=?", (b["id"],))["o"] + 1
    ts = now()
    key_cid: dict[str, str] = {}
    rows = []
    for n, les in enumerate(out.get("lessons") or []):
        title = " ".join((les.get("title") or "").split())[:200]
        if not title:
            continue
        cid = f'{ch["module_id"]}-{slug(les.get("key") or title, 30)}'
        while cid in key_cid.values():
            cid += "-2"
        key_cid[les.get("key") or title] = cid
        rows.append((n, les, title, cid))
    with db.tx():
        for n, les, title, cid in rows:
            prereqs = []
            for pk in les.get("prereq_keys") or []:
                if pk in key_cid and key_cid[pk] != cid:
                    prereqs.append(key_cid[pk])
                elif pk in in_book:
                    prereqs.append(pk)
            a, z = _pages(les.get("pages") or "", ch["page_from"], ch["page_to"])
            db.conn.execute("INSERT OR REPLACE INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                            (cid, ch["module_id"], n, title, (les.get("covers") or "")[:400], LESSON_MINUTES, dumps(prereqs), 0.1))
            same = les.get("same_as")
            node, created = cid, 1
            if same in existing and same not in mine:
                db.conn.execute("INSERT OR REPLACE INTO concept_nodes(concept_id, node_id) VALUES(?,?)", (cid, same))
                node, created = same, 0
            cur = db.conn.execute("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to, summary,
                                     concept_id, ideas) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                  (b["id"], base + n, ch["chapter"], ch["title"], title, a, z, (les.get("covers") or "")[:400], cid,
                                   dumps([" ".join(i.split())[:160] for i in (les.get("ideas") or [])][:8])))
            db.conn.execute("""INSERT OR IGNORE INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                               VALUES(?,?,?,?,?,?,?)""", (b["id"], node, cur.lastrowid, cid, f"{a}-{z}" if z != a else str(a), created, n))
            for pk in les.get("prereq_keys") or []:  # an older graph idea it builds on: a link between nodes
                if pk in existing and pk not in mine and pk not in key_cid and pk not in in_book:
                    db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (pk, node, "", "book"))
        db.conn.execute("UPDATE book_chapters SET summary=?, mapped=1, kind=? WHERE book_id=? AND chapter=?",
                        ((out.get("summary") or "")[:1200], "chapter" if rows else "reference", b["id"], ch["chapter"]))
        db.conn.execute("UPDATE modules SET summary=?, planned=? WHERE id=?", ((out.get("summary") or "")[:600], len(rows), ch["module_id"]))
    graph.sync(db)


# ---------------------------------------------------------------- writing the lessons of a chapter (research for a book goal)

def is_book_goal(db: DB, gid: str) -> bool:
    g = db.one("SELECT kind FROM goals WHERE id=?", (gid,))
    return bool(g and g["kind"] == "bookstudy")


def write_cards(jobs: Jobs, jid: int, d: dict) -> dict:
    """The cards of one chapter's lessons, from the chapter's pages only (no web). Called by ``research_module`` for a
    book goal. Each section follows a stretch of the book and carries a close summary of what the book says there."""
    from . import lesson, writer
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    ch = db.one("SELECT * FROM book_chapters WHERE module_id=?", (d["module_id"],))
    b = get(db, ch["book_id"]) if ch else None
    if not ch or not b:
        raise BookError("this chapter belongs to no book")
    db.x("UPDATE modules SET research='researching' WHERE id=?", (ch["module_id"],))
    lessons = db.q("""SELECT p.*, c.objective FROM book_parts p JOIN concepts c ON c.id = p.concept_id
                      WHERE p.book_id=? AND p.chapter=? ORDER BY p.ord""", (b["id"], ch["chapter"]))
    have = {r["concept_id"] for r in db.q("SELECT DISTINCT concept_id FROM cards")}
    have |= {r["id"] for r in db.q("SELECT id FROM formula_lessons")}  # formula lessons are written by their own job
    todo = [x for x in lessons if x["concept_id"] not in have]
    if not todo:
        db.x("UPDATE modules SET research='ready' WHERE id=?", (ch["module_id"],))
        return {"cards": 0}
    jobs.progress(jid, f"writing {len(todo)} lesson(s) of “{ch['title'][:60]}” from pp. {ch['page_from']}-{ch['page_to']}")
    listing_text = "\n".join(
        f'- id {x["concept_id"]}: {x["title"]} (pp. {x["page_from"]}-{x["page_to"]}). Covers: {x["summary"]}. '
        f'Key ideas: {"; ".join(loads(x["ideas"], [])) or "-"}' for x in todo)
    others = "\n".join(f'- {x["title"]}' for x in lessons if x["concept_id"] not in {t["concept_id"] for t in todo}) or "(none)"
    out = jobs.call(jid, "Research", Call(
        prompt=prompt("book_cards", book=b["title"], chapter=ch["title"], summary=ch["summary"] or "(none)",
                      lessons=listing_text, others=others, source=b["source_id"],
                      text=_chapter_text(db, b["source_id"], ch["page_from"], ch["page_to"]) or "(no text)"),
        schema=CARDS_SCHEMA, model="opus", timeout=1800))
    by_id = {x["concept_id"]: x for x in todo}
    written = []
    ts = now()
    for c in out.get("cards") or []:
        x = by_id.get(c.get("id"))
        if not x or not c.get("card", {}).get("sections"):
            continue
        card = c["card"]
        for s in card["sections"]:
            if s.get("viz"):
                spec, notes = writer.check_viz(jobs, jid, {**card, "objective": x["objective"]}, s, s["viz"])
                if spec:
                    s["viz"] = spec
                else:
                    s.pop("viz", None)
                if notes:
                    s["vizNotes"] = notes
        written.append((x, card))
    with db.tx():
        for x, card in written:
            for s in card["sections"]:
                if "viz" in s:
                    s["viz"] = viz.validate(s["viz"])
                    if not s["viz"]:
                        del s["viz"]
                if s.get("check"):
                    s["check"] = {**mcq.shuffle(s["check"]), "id": f'q-{s["id"]}'}
                if s.get("explain"):
                    s["explain"]["id"] = f'e-{s["id"]}'
            pages = {p for s in card["sections"] for p in [s.get("book", {}).get("pages", "")] if p}
            body = {**card, "objective": x["objective"], "angles": card.get("angles") or [],
                    "sources": [{"title": f'{b["title"]}, pp. {x["page_from"]}-{x["page_to"]}',
                                 "url": f'source:{b["source_id"]}#page={x["page_from"]}', "kind": "book",
                                 "why": "The book this lesson follows" + (f' (pages {", ".join(sorted(pages))})' if pages else "")}]}
            db.conn.execute("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
                            (x["concept_id"], 1, dumps(body), "pending", ts))
        db.conn.execute("UPDATE modules SET research='ready' WHERE id=?", (ch["module_id"],))
    jobs.progress(jid, f"wrote {len(written)} lesson card(s) from the book")
    if written:
        jobs.enqueue("fact_check", f"Fact-check {ch['title'][:60]}", {"concept_ids": [x["concept_id"] for x, _ in written]})
    if d.get("open"):  # the lesson the learner opened: write its text now
        lesson.ensure_rendition(db, d["open"])
        lesson.ensure_prose(db, jobs, d["open"])
    return {"cards": len(written)}


def ensure_written(db: DB, jobs: Jobs, cid: str) -> bool:
    """On first open of a book lesson without a card: write the chapter's cards (then the lesson). True when queued.
    Any open of a book lesson marks its book as used now (Today continues the newest book)."""
    db.x("UPDATE books SET updated_at=? WHERE id=(SELECT book_id FROM book_parts WHERE concept_id=?)", (now(), cid))
    row = db.one("""SELECT m.id, m.research, t.goal_id FROM concepts c JOIN modules m ON m.id = c.module_id
                    JOIN tracks t ON t.id = m.track_id WHERE c.id=?""", (cid,))
    if not row or not is_book_goal(db, row["goal_id"]) or db.one("SELECT 1 FROM cards WHERE concept_id=?", (cid,)) \
            or db.one("SELECT 1 FROM formula_lessons WHERE id=?", (cid,)):
        return False
    if not jobs.active("research_module", module_id=row["id"]):
        db.x("UPDATE modules SET research='researching' WHERE id=?", (row["id"],))
        jobs.enqueue("research_module", "Write the lessons of this chapter", {"module_id": row["id"], "open": cid})
    return True


def open_lesson(db: DB, jobs: Jobs, cid: str) -> None:
    """Make the lesson's goal the active goal (the lesson page reads the active goal); for a book lesson, its hidden book
    goal, and the book is marked as used now. Works for any lesson, so a goal lesson opens while a book goal is active."""
    p = db.one("SELECT book_id FROM book_parts WHERE concept_id=?", (cid,))
    b = get(db, p["book_id"]) if p else None
    if not b or not b["goal_id"]:  # a goal's lesson: make its goal active (a book goal may be active now)
        g = db.one("""SELECT t.goal_id FROM concepts c JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id
                      WHERE c.id=?""", (cid,))
        if not g:
            raise BookError("unknown lesson")
        db.set_meta("active_goal", g["goal_id"])
        return
    db.set_meta("active_goal", b["goal_id"])
    db.set_meta("last_book", b["id"])
    db.x("UPDATE books SET updated_at=? WHERE id=?", (now(), b["id"]))
