"""Book goals: the 80/20 core of one or more of the learner's own sources (SPEC §18).

A book goal is for a learner who has no time to read whole books. Its scope is the sources they chose (PDF books,
articles, posts). The outline agent ranks every chapter of every source as core, supporting or skip, and builds the
roadmap (Ohtani table or classic) only from the core and supporting chapters. Every ranked chapter is stored in
``book_cuts``, so the learner sees what was kept and what was left out, and can bring a left-out chapter back: it
becomes a lesson in the step it fits best (or part of that step's plan while the step is not researched yet).
"""

from __future__ import annotations

import re

from .db import DB, dumps, loads, now

RANKS = ("core", "supporting", "skip")
RESEARCH_EXCERPTS = 12  # pages per module for a book goal (a normal goal gets 8)
_WORD = re.compile(r"[a-z0-9]+")

_PICK = {"type": "object", "required": ["source", "chapter", "pages", "rank", "why", "step"], "properties": {
    "source": {"type": "integer"}, "chapter": {"type": "string"}, "pages": {"type": "string"},
    "rank": {"enum": list(RANKS)}, "why": {"type": "string"}, "step": {"type": "string"}}}


def schema(base: dict) -> dict:
    """The outline schema of a layout, plus the ranked chapters (`selection`)."""
    return {**base, "required": [*base["required"], "selection"],
            "properties": {**base["properties"], "selection": {"type": "array", "minItems": 1, "items": _PICK}}}


def ready_sources(db: DB, ids: list[str]) -> list[dict]:
    """The chosen sources in the order given; raises ValueError when one cannot be used for a book goal."""
    rows = {s["id"]: s for s in db.q("SELECT * FROM sources")}
    out = []
    for sid in dict.fromkeys(ids):
        s = rows.get(sid)
        if not s:
            continue
        if s["status"] == "reading":
            raise ValueError(f"“{s['title']}” is still being read; start when it is ready")
        if s["status"] != "ready":
            raise ValueError(f"“{s['title']}” has no text the app can read (a scan or a broken file)")
        out.append(s)
    if not out:
        raise ValueError("choose at least one source")
    return out


def structure_text(db: DB, ids: list[str], toc_limit: int = 160, samples: int = 60) -> str:
    """Numbered sources with their tables of contents. A source without one gets the first words of sampled pages,
    so the agent can still find its parts."""
    rows = {s["id"]: s for s in db.q("SELECT * FROM sources")}
    blocks = []
    for n, sid in enumerate([i for i in ids if i in rows], 1):
        s = rows[sid]
        by = f' by {s["author"]}' if s["author"] else ""
        head = f'{n}. {s["kind"]} “{s["title"]}”{by}, {s["pages"]} pages'
        toc = [t for t in loads(s["outline"], []) if t["level"] <= 2][:toc_limit]
        if toc:
            lines = [f'   {"  " * t["level"]}{t["title"]}' + (f' (p. {t["page"]})' if t["page"] else "") for t in toc]
            blocks.append(head + ", table of contents:\n" + "\n".join(lines))
            continue
        pages = db.q("SELECT page, text FROM source_pages WHERE source_id=? AND text != '' ORDER BY page", (sid,))
        step = max(1, len(pages) // samples)
        lines = [f'   p. {p["page"]}: {p["text"][:110]}' for p in pages[::step][:samples]]
        blocks.append(head + ", no table of contents; the first words of some pages:\n" + "\n".join(lines))
    return "\n".join(blocks)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def best_module(modules: list[dict], step: str, chapter: str = "") -> str | None:
    """The module a ranked chapter belongs to: the step title the agent named, else the best word overlap."""
    if not modules:
        return None
    key = " ".join(step.lower().split())
    for m in modules:
        if " ".join(m["title"].lower().split()) == key:
            return m["id"]
    want = _words(f"{step} {chapter}")
    scored = [(len(want & _words(f'{m["title"]} {m.get("summary", "")}')), -i, m["id"]) for i, m in enumerate(modules)]
    best = max(scored)
    return best[2] if best[0] > 0 else None


def save(db: DB, gid: str, selection: list[dict], source_ids: list[str], modules: list[dict]) -> None:
    """Store the ranked chapters (inside the outline's transaction). Unknown sources and ranks are dropped."""
    for i, p in enumerate(selection):
        n = p.get("source")
        if not isinstance(n, int) or not 1 <= n <= len(source_ids) or p.get("rank") not in RANKS:
            continue
        chapter = " ".join(str(p.get("chapter") or "").split())[:200]
        if not chapter:
            continue
        status = "cut" if p["rank"] == "skip" else "kept"
        db.conn.execute("""INSERT INTO book_cuts(goal_id, ord, source_id, chapter, pages, rank, why, module_id, status)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (gid, i, source_ids[n - 1], chapter, str(p.get("pages") or "")[:40], p["rank"],
                         str(p.get("why") or "")[:400], best_module(modules, str(p.get("step") or ""), chapter), status))


def listing(db: DB, gid: str) -> list[dict]:
    titles = {s["id"]: s["title"] for s in db.q("SELECT id, title FROM sources")}
    return [{"id": r["id"], "sourceId": r["source_id"], "sourceTitle": titles.get(r["source_id"], "(deleted source)"),
             "chapter": r["chapter"], "pages": r["pages"], "rank": r["rank"], "why": r["why"], "moduleId": r["module_id"],
             "status": r["status"], "conceptId": r["concept_id"]}
            for r in db.q("SELECT * FROM book_cuts WHERE goal_id=? ORDER BY ord", (gid,))]


def restore(db: DB, jobs, cut_id: int) -> None:
    """Bring a left-out chapter back into the roadmap.

    A step that is still an outline gets the chapter in its summary and one more planned lesson, so its research
    covers it. A researched (or researching) step gets a new lesson at its end, researched on its own from the pages."""
    r = db.one("SELECT * FROM book_cuts WHERE id=?", (cut_id,))
    if not r or r["status"] != "cut":
        raise ValueError("this chapter is not left out")
    mods = db.q("""SELECT m.* FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id=?
                   ORDER BY m.seq, t.ord, m.ord""", (r["goal_id"],))
    areas = [m for m in mods if not loads(m["requires"], [])] or mods  # never a merge step
    mid = r["module_id"] if any(m["id"] == r["module_id"] for m in areas) else best_module(areas, "", r["chapter"])
    m = next((x for x in areas if x["id"] == mid), areas[0] if areas else None)
    if not m:
        raise ValueError("the goal has no steps")
    src = db.one("SELECT title FROM sources WHERE id=?", (r["source_id"],))
    where = f'{r["chapter"]}' + (f' (pp. {r["pages"]})' if r["pages"] else "") + f' of “{src["title"] if src else "the source"}”'
    if m["research"] == "outline":
        db.x("UPDATE modules SET summary=?, planned=planned+1 WHERE id=?",
             (f'{m["summary"]} Also covers (brought back by the learner): {where}.', m["id"]))
        db.x("UPDATE book_cuts SET status='restored', restored_at=?, module_id=? WHERE id=?", (now(), m["id"], cut_id))
        return
    slug = re.sub(r"[^a-z0-9]+", "-", r["chapter"].lower()).strip("-")[:30] or str(cut_id)
    cid = f'{m["id"]}-bb-{slug}'
    detail = f"{where}. The learner brought it back after the 80/20 cut, which had left it out: {r['why']}"
    with db.tx():
        o = db.conn.execute("SELECT COALESCE(MAX(ord), -1) + 1 FROM concepts WHERE module_id=?", (m["id"],)).fetchone()[0]
        db.conn.execute("INSERT OR IGNORE INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                        (cid, m["id"], o, r["chapter"], detail, 15, dumps([]), 0.1))
        db.conn.execute("UPDATE book_cuts SET status='restored', restored_at=?, module_id=?, concept_id=? WHERE id=?",
                        (now(), m["id"], cid, cut_id))
    jobs.enqueue("research_module", f"Research {r['chapter']}",
                 {"module_id": m["id"], "prev_research": m["research"],
                  "concept": {"id": cid, "title": r["chapter"], "detail": detail}})
