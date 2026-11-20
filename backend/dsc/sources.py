"""The learner's own sources: books, articles and posts as PDF files (SPEC §17).

A PDF is saved in the workspace (``sources/<id>.pdf``). A background job reads its text page by page and its table of
contents (the PDF outline), and adds the pages to a full-text index. A goal uses the sources the learner chose for it:
the roadmap outline reads their tables of contents, and the research of each module gets the pages that match it best,
so cards are based on them and cite "Title, p. N". A scanned PDF without a text layer is kept but marked "no text".
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from .db import DB, dumps, loads, now, workspace

KINDS = ("book", "article", "post", "other")
MAX_BYTES = 200 * 1024 * 1024
EXCERPT_CHARS = 900  # one page's text in a research prompt, at most
_WORD = re.compile(r"[\w']+")
_STOP = {"the", "and", "for", "with", "from", "into", "that", "this", "what", "how", "why", "are", "its", "their", "your",
         "you", "of", "to", "in", "on", "a", "an", "is", "as", "by", "or", "at", "be", "it", "we", "using", "use", "via"}


def clean(text: str) -> str:
    """Text that SQLite can store: join split UTF-16 surrogate pairs, replace lone ones, and squeeze white space.
    Some PDFs give math letters (U+1D400...) as two separate surrogates, which UTF-8 cannot encode."""
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return " ".join(text.replace("\x00", " ").split())


def folder() -> Path:
    path = workspace() / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(sid: str) -> Path:
    return folder() / f"{sid}.pdf"


def add(db: DB, data: bytes, filename: str, kind: str = "book") -> str:
    """Save an uploaded PDF and create its row (status "reading"); the ingest job reads it."""
    if not data.startswith(b"%PDF"):
        raise ValueError("this is not a PDF file")
    if len(data) > MAX_BYTES:
        raise ValueError("the file is larger than 200 MB")
    stem = Path(filename or "source.pdf").stem
    title = re.sub(r"[_\-]+", " ", stem).strip()[:200] or "Untitled"
    sid = f"src-{secrets.token_hex(4)}"
    file_path(sid).write_bytes(data)
    db.x("""INSERT INTO sources(id, title, author, kind, filename, bytes, pages, status, outline, added_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
         (sid, title, "", kind if kind in KINDS else "book", Path(filename or "").name[:200], len(data), 0, "reading", "[]", now()))
    return sid


def ingest(db: DB, sid: str, progress=lambda msg: None) -> dict:
    """Read the PDF: metadata title/author, outline (table of contents) and text per page, into the index."""
    from pypdf import PdfReader

    reader = PdfReader(str(file_path(sid)))
    meta = reader.metadata or {}
    title = clean(str(getattr(meta, "title", None) or meta.get("/Title") or ""))
    author = clean(str(getattr(meta, "author", None) or meta.get("/Author") or ""))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page must not stop the book
            text = ""
        pages.append(clean(text))
        if (i + 1) % 50 == 0:
            progress(f"read {i + 1} of {len(reader.pages)} pages")
    outline = _outline(reader)
    with_text = sum(1 for t in pages if len(t) > 40)
    status = "ready" if pages and with_text >= max(1, len(pages) // 5) else "no_text"
    with db.tx():
        db.conn.execute("DELETE FROM source_pages WHERE source_id=?", (sid,))
        db.conn.execute("DELETE FROM source_fts WHERE source_id=?", (sid,))
        db.conn.executemany("INSERT INTO source_pages(source_id, page, text) VALUES(?,?,?)",
                            [(sid, n + 1, t) for n, t in enumerate(pages)])
        db.conn.executemany("INSERT INTO source_fts(source_id, page, text) VALUES(?,?,?)",
                            [(sid, n + 1, t) for n, t in enumerate(pages) if t])
        row = db.conn.execute("SELECT title FROM sources WHERE id=?", (sid,)).fetchone()
        keep_title = row and row[0] and row[0] != Path(row[0]).stem  # the learner's own title wins
        db.conn.execute("UPDATE sources SET pages=?, status=?, outline=?, author=?, title=? WHERE id=?",
                        (len(pages), status, dumps(outline), author[:200],
                         (title[:200] if title and len(title) > 3 and not keep_title else row[0]), sid))
    return {"pages": len(pages), "status": status, "outline": len(outline)}


def _outline(reader) -> list[dict]:
    """The PDF's bookmarks as [{title, page, level}] (empty when the PDF has none)."""
    out: list[dict] = []

    def walk(items, level: int):
        for it in items:
            if isinstance(it, list):
                walk(it, level + 1)
                continue
            try:
                page = reader.get_destination_page_number(it) + 1
            except Exception:  # noqa: BLE001
                page = None
            title = clean(str(getattr(it, "title", "") or ""))
            if title:
                out.append({"title": title[:160], "page": page, "level": level})
            if len(out) >= 400:
                return

    try:
        walk(reader.outline or [], 0)
    except Exception:  # noqa: BLE001 - a broken outline is just no outline
        return []
    return out


def delete(db: DB, sid: str) -> None:
    with db.tx():
        for t in ("source_pages", "source_fts", "goal_sources"):
            db.conn.execute(f"DELETE FROM {t} WHERE source_id=?", (sid,))
        db.conn.execute("DELETE FROM sources WHERE id=?", (sid,))
    file_path(sid).unlink(missing_ok=True)


def link(db: DB, goal_id: str, sid: str, on: bool) -> None:
    if on:
        db.x("INSERT OR IGNORE INTO goal_sources(goal_id, source_id) VALUES(?,?)", (goal_id, sid))
    else:
        db.x("DELETE FROM goal_sources WHERE goal_id=? AND source_id=?", (goal_id, sid))


def for_goal(db: DB, goal_id: str | None) -> list[dict]:
    if not goal_id:
        return []
    return db.q("""SELECT s.* FROM sources s JOIN goal_sources g ON g.source_id = s.id
                   WHERE g.goal_id=? ORDER BY s.added_at""", (goal_id,))


def listing(db: DB) -> list[dict]:
    links: dict[str, list[str]] = {}
    for r in db.q("SELECT * FROM goal_sources"):
        links.setdefault(r["source_id"], []).append(r["goal_id"])
    return [{"id": s["id"], "title": s["title"], "author": s["author"], "kind": s["kind"], "filename": s["filename"],
             "pages": s["pages"], "status": s["status"], "addedAt": s["added_at"], "goalIds": links.get(s["id"], []),
             "outline": len(loads(s["outline"], []))}
            for s in db.q("SELECT * FROM sources ORDER BY added_at DESC")]


def contents_text(db: DB, goal_id: str | None = None, ids: list[str] | None = None, limit: int = 120) -> str:
    """Tables of contents of the goal's sources (or the given ones), for the roadmap outline."""
    rows = for_goal(db, goal_id) if ids is None else [s for s in db.q("SELECT * FROM sources") if s["id"] in ids]
    blocks = []
    for s in rows:
        toc = [t for t in loads(s["outline"], []) if t["level"] <= 1][:limit]
        by = f' by {s["author"]}' if s["author"] else ""
        head = f'- {s["kind"]} “{s["title"]}”{by}, {s["pages"]} pages'
        lines = []
        for t in toc:
            page = f' (p. {t["page"]})' if t["page"] else ""
            lines.append("  " + "  " * t["level"] + t["title"] + page)
        if lines:
            head += ":\n" + "\n".join(lines)
        elif s["status"] == "no_text":
            head += " (scanned, no text)"
        blocks.append(head)
    return "\n".join(blocks)


def excerpts(db: DB, goal_id: str | None, topic: str, k: int = 8, ids: list[str] | None = None) -> list[dict]:
    """The pages of the goal's sources (or of the given source ids) that match a topic best (full-text search)."""
    pool = [x for x in db.q("SELECT * FROM sources") if x["id"] in ids] if ids is not None else for_goal(db, goal_id)
    srcs = {x["id"]: x for x in pool if x["status"] == "ready"}
    terms = [t for t in dict.fromkeys(_WORD.findall(topic.lower())) if len(t) > 2 and t not in _STOP][:12]
    if not srcs or not terms:
        return []
    marks = ",".join("?" * len(srcs))
    match = " OR ".join(f'"{t}"*' for t in terms)
    with db.lock:
        rows = db.conn.execute(f"""SELECT source_id, page, text FROM source_fts WHERE source_fts MATCH ?
                                   AND source_id IN ({marks}) ORDER BY bm25(source_fts) LIMIT ?""",
                               (match, *srcs, k)).fetchall()
    return [{"sourceId": r[0], "title": srcs[r[0]]["title"], "page": int(r[1]), "text": r[2][:EXCERPT_CHARS]} for r in rows]


def excerpts_text(items: list[dict]) -> str:
    if not items:
        return "(none)"
    return "\n\n".join(f'[{e["title"]}, p. {e["page"]}] (cite as url "source:{e["sourceId"]}#page={e["page"]}")\n{e["text"]}'
                       for e in items)
