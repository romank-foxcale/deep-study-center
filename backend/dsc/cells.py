"""One cell per idea (SPEC §49): an idea of the map is one cell with one lesson, whatever the number of sources.

Book mapping already joins a book's lesson to the same idea from another book (``same_as``): the two lessons point to
one node of the map. Before this, each book still had its own lesson of the idea ("a shared block"). Now:

- **Home.** Every cell has one home lesson (``home``): the lesson of the idea that is furthest along (a plan, then a
  written card, then answers), else the first one. Every other lesson of the same idea is an alias: the book pages and
  the map open the home lesson. The choice is kept (``cell_homes``), so the home does not jump about; it moves only
  when another lesson of the idea is further along.
- **Sources.** A cell's sources are the book parts of all its lessons (``sources``): which book, article or video, and
  which pages. The tutor writes the home lesson from all of them (``source_text``): it chooses the clearest source for
  each step. The learner's answers and notes change how the lesson is built, not what it is about.
- Nothing is deleted. A lesson written before this from a second book stays as an earlier version of the idea.
"""

from __future__ import annotations

from .db import DB, now

CHAPTER_CHARS = 80_000    # source text sent for one lesson, at most (all sources together)
PAGE_CHARS = 3_000        # one page's text, at most


def _node(db: DB, cid: str) -> str:
    row = db.one("SELECT node_id FROM concept_nodes WHERE concept_id=?", (cid,))
    return row["node_id"] if row else cid


def lessons_of(db: DB, node: str) -> list[str]:
    """The lessons (concepts) of one idea, oldest first."""
    return [r["concept_id"] for r in db.q("""SELECT cn.concept_id FROM concept_nodes cn JOIN concepts c ON c.id = cn.concept_id
                                             WHERE cn.node_id=? ORDER BY c.rowid""", (node,))]


def _score(db: DB, cid: str) -> int:
    """How far along a lesson is: a plan, a written card, answers, opened."""
    s = 0
    if db.one("SELECT 1 FROM lesson_graphs WHERE concept_id=?", (cid,)):
        s += 8
    if db.one("SELECT 1 FROM cards WHERE concept_id=?", (cid,)):
        s += 4
    s += min(3, db.one("SELECT COUNT(*) AS n FROM evidence WHERE concept_id=? AND voided=0", (cid,))["n"])
    if db.one("SELECT 1 FROM concepts WHERE id=? AND started=1", (cid,)):
        s += 1
    return s


def home(db: DB, cid: str) -> str:
    """The one lesson of this lesson's idea."""
    node = _node(db, cid)
    ids = lessons_of(db, node)
    if len(ids) < 2:
        return cid
    kept = (db.one("SELECT concept_id FROM cell_homes WHERE node_id=?", (node,)) or {}).get("concept_id")
    # furthest along wins; on a tie the kept home stays, then the oldest lesson
    best = max(ids, key=lambda c: (_score(db, c), c == kept, -ids.index(c)))
    if best != kept:
        db.x("INSERT OR REPLACE INTO cell_homes(node_id, concept_id, at) VALUES(?,?,?)", (node, best, now()))
    return best


def homes(db: DB) -> dict[str, str]:
    """lesson -> its home lesson, for every lesson of an idea that has more than one."""
    groups: dict[str, list[str]] = {}
    for r in db.q("SELECT concept_id, node_id FROM concept_nodes"):
        groups.setdefault(r["node_id"], []).append(r["concept_id"])
    out = {}
    for ids in groups.values():
        if len(ids) > 1:
            h = home(db, ids[0])
            for c in ids:
                out[c] = h
    return out


def sources(db: DB, cid: str) -> list[dict]:
    """The sources of this lesson's idea: one entry per book part (book, article, web page or video), the home's first."""
    ids = lessons_of(db, _node(db, cid)) or [cid]
    h = home(db, cid)
    rows = db.q(f"""SELECT p.concept_id, p.book_id, p.chapter, p.chapter_title, p.title, p.page_from, p.page_to, b.title AS book,
                           b.source_id, s.kind, s.url FROM book_parts p JOIN books b ON b.id = p.book_id
                           LEFT JOIN sources s ON s.id = b.source_id
                    WHERE p.concept_id IN ({','.join('?' * len(ids))}) ORDER BY b.created_at""", ids)
    rows.sort(key=lambda r: r["concept_id"] != h)  # the home's own part first (stable: then by book)
    return [{"bookId": r["book_id"], "sourceId": r["source_id"], "title": r["book"], "kind": r["kind"] or "book",
             "url": r["url"] or "", "chapter": r["chapter"], "chapterTitle": r["chapter_title"], "part": r["title"],
             "pages": [r["page_from"], r["page_to"]], "conceptId": r["concept_id"]} for r in rows]


def pages_label(src: dict) -> str:
    a, z = src["pages"]
    return f"p. {a}" if a == z else f"pp. {a}-{z}"


def source_text(db: DB, cid: str) -> tuple[str, str]:
    """(the text of every source of this idea, labeled by source and page; a one-line list of the sources).
    The budget is shared between the sources, so a second book never pushes out the first."""
    srcs = [s for s in sources(db, cid) if s["sourceId"]]
    if not srcs:
        return "", ""
    share = CHAPTER_CHARS // len(srcs)
    blocks = []
    for i, s in enumerate(srcs, 1):
        a, z = s["pages"]
        per = min(PAGE_CHARS, share // max(1, z - a + 1))
        rows = db.q("SELECT page, text FROM source_pages WHERE source_id=? AND page BETWEEN ? AND ? ORDER BY page", (s["sourceId"], a, z))
        body = "\n\n".join(f"[{s['title']}, p. {r['page']}]\n{r['text'][:per]}" for r in rows if r["text"].strip())
        if body:
            blocks.append(f"=== Source {i}: {s['title']} ({s['kind']}), {pages_label(s)}: “{s['part']}” ===\n{body}")
    listing = "; ".join(f"{s['title']} ({s['kind']}, {pages_label(s)})" for s in srcs)
    return "\n\n".join(blocks), listing
