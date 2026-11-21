"""Recall practice (SPEC §24): make understood ideas usable. Step 6 of the knowledge-graph rework.

Understanding an idea is not the same as recalling it when a problem calls for it. Recall works from cues, so
practice widens and strengthens them: a stream of problems that adapt.

- A practice is a short run of problems (default 5) over a set of ideas (graph nodes): what is due, ideas picked on the
  map, or the learner's own problem (text, or a page of one of their PDFs).
- Difficulty is a level 1-4 (``LEVELS``): how many ideas a problem combines and how new its setting is. A clean solve
  raises it; a hard solve or giving up lowers it.
- The learner writes their thinking in chunks (typed or dictated). An agent judges each chunk: solved, progress, or
  stuck / wrong direction, with the smallest hint that moves them on, never the solution. The learner can ask for a
  hint or give up (then the worked solution shows).
- Result per problem: score 1.0 solved without hints, 0.7 with one hint, 0.4 with more, 0 given up. It is evidence on
  each target idea ("practice", or "review" once the idea is learned, so it can become strong or rusty) and updates
  the idea's own schedule (``node_reviews``, FSRS, as lesson reviews).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from . import engine, graph, guidelines, state
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

PROBLEMS = 5
PICK = 6  # ideas in a "what is due" practice
LEVELS = {
    1: "one idea, in a setting close to how it was taught",
    2: "one idea, in a new setting (different numbers, domain or wording; the cue is less obvious)",
    3: "two ideas combined, in a new setting",
    4: "two or three ideas combined, in an unfamiliar setting where the learner must first see which ideas apply",
}
LIT = ("learned", "mastered", "rusty")

PROBLEM_SCHEMA = {"type": "object", "required": ["title", "prompt", "node_ids", "solution", "steps"], "properties": {
    "title": {"type": "string"}, "prompt": {"type": "string"},
    "node_ids": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
    "solution": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}}}}
JUDGE_SCHEMA = {"type": "object", "required": ["verdict", "feedback"], "properties": {
    "verdict": {"enum": ["solved", "progress", "stuck", "wrong"]},
    "feedback": {"type": "string"}, "hint": {"type": "string"}}}


# ---------------------------------------------------------------- which ideas

def due(db: DB, at: str | None = None) -> list[dict]:
    """Ideas to practise, most urgent first: due idea reviews, due lesson reviews (as their ideas), then ideas being
    learned that were never practised (taught in a session or a lesson)."""
    at = at or now()
    nodes = graph.node_of(db)
    st = graph.states(db)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    out: dict[str, dict] = {}
    for r in db.q("SELECT node_id, due FROM node_reviews WHERE due <= ? ORDER BY due", (at,)):
        out.setdefault(r["node_id"], {"nodeId": r["node_id"], "reason": "due", "due": r["due"]})
    for r in db.q("SELECT concept_id, due FROM reviews WHERE due <= ? ORDER BY due", (at,)):
        nid = nodes.get(r["concept_id"])
        if nid and not db.one("SELECT 1 FROM node_reviews WHERE node_id=? AND due > ?", (nid, at)):
            out.setdefault(nid, {"nodeId": nid, "reason": "due", "due": r["due"]})
    practised = {r["node_id"] for r in db.q("SELECT node_id FROM node_reviews")}
    fresh = sorted((nid for nid, s in st.items() if s.state == "learning" and s.mastery >= 0.2 and nid not in practised),
                   key=lambda nid: -st[nid].mastery)
    for nid in fresh:
        out.setdefault(nid, {"nodeId": nid, "reason": "new", "due": None})
    return [{**v, "title": titles.get(v["nodeId"], v["nodeId"]), "state": st[v["nodeId"]].state if v["nodeId"] in st else "pending"}
            for v in out.values() if v["nodeId"] in titles]


def due_count(db: DB) -> int:
    return sum(1 for d in due(db) if d["reason"] == "due")


# ---------------------------------------------------------------- learner actions

def start(db: DB, jobs: Jobs, node_ids: list[str] | None = None, own: str = "", source: dict | None = None) -> str:
    known = {r["id"] for r in db.q("SELECT id FROM nodes")}
    ids = [n for n in (node_ids or []) if n in known]
    own = " ".join((own or "").split())[:3000]
    page_text = ""
    if source and source.get("id"):
        row = db.one("SELECT text FROM source_pages WHERE source_id=? AND page=?", (source["id"], int(source.get("page") or 0)))
        if not row:
            raise ValueError("that page has no text")
        page_text = row["text"][:4000]
    if not ids and not own and not page_text:
        ids = [d["nodeId"] for d in due(db)[:PICK]]
    if not ids and not own and not page_text:
        raise ValueError("nothing to practise yet: learn something first")
    count = 1 if (own or page_text) and not node_ids else PROBLEMS
    title = (own[:60] or (f"Page {source.get('page')} of your source" if page_text else "")) or \
        ", ".join(r["title"] for r in db.q(f"SELECT title FROM nodes WHERE id IN ({','.join('?' * len(ids))})", ids))[:120]
    pid = f"p-{secrets.token_hex(4)}"
    ts = now()
    db.x("""INSERT INTO practices(id, title, node_ids, own, status, level, count, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
         (pid, title or "Practice", dumps(ids), dumps({"text": own, "page": page_text, "source": source or {}}),
          "active", 1, count, ts, ts))
    jobs.enqueue("practice_next", "Write a practice problem", {"practice_id": pid})
    return pid


def submit(db: DB, jobs: Jobs, item_id: int, text: str, want_hint: bool = False) -> None:
    it = db.one("SELECT * FROM practice_items WHERE id=?", (item_id,))
    if not it or it["status"] != "open":
        raise ValueError("this problem is closed")
    text = (text or "").strip()[:4000]
    if not text and not want_hint:
        raise ValueError("write some thinking first")
    chunks = loads(it["chunks"], [])
    chunks.append({"text": text, "ts": now(), "askedHint": want_hint})
    db.x("UPDATE practice_items SET chunks=? WHERE id=?", (dumps(chunks), item_id))
    jobs.enqueue("practice_judge", "Read your thinking", {"item_id": item_id, "hint": want_hint})


def give_up(db: DB, jobs: Jobs, item_id: int) -> None:
    it = db.one("SELECT * FROM practice_items WHERE id=?", (item_id,))
    if not it or it["status"] != "open":
        raise ValueError("this problem is closed")
    _close(db, jobs, it, "given_up")


def retry(db: DB, jobs: Jobs, pid: str) -> None:
    """After a failed job: judge the last thinking again, or write the next problem."""
    if _busy(db, pid):
        return
    it = db.one("SELECT * FROM practice_items WHERE practice_id=? AND status='open' ORDER BY id DESC LIMIT 1", (pid,))
    chunks = loads(it["chunks"], []) if it else []
    if it and chunks and "verdict" not in chunks[-1]:
        jobs.enqueue("practice_judge", "Read your thinking", {"item_id": it["id"], "hint": chunks[-1].get("askedHint", False)})
    else:
        next_problem(db, jobs, pid)


def stop(db: DB, pid: str) -> None:
    db.x("UPDATE practice_items SET status='skipped' WHERE practice_id=? AND status='open' AND chunks='[]'", (pid,))
    db.x("UPDATE practices SET status='done', updated_at=? WHERE id=?", (now(), pid))


def next_problem(db: DB, jobs: Jobs, pid: str, from_judge: bool = False) -> None:
    p = db.one("SELECT * FROM practices WHERE id=?", (pid,))
    # called from the judge job, which is itself still running: only another "next problem" job blocks
    if not p or p["status"] != "active" or _busy(db, pid, ("practice_next",) if from_judge else None):
        return
    if db.one("SELECT 1 FROM practice_items WHERE practice_id=? AND status='open'", (pid,)):
        return
    if db.one("SELECT COUNT(*) AS n FROM practice_items WHERE practice_id=?", (pid,))["n"] >= p["count"]:
        db.x("UPDATE practices SET status='done', updated_at=? WHERE id=?", (now(), pid))
        return
    jobs.enqueue("practice_next", "Write a practice problem", {"practice_id": pid})


def _busy(db: DB, pid: str, kinds: tuple[str, ...] | None = None) -> bool:
    ids = {r["id"] for r in db.q("SELECT id FROM practice_items WHERE practice_id=?", (pid,))}
    for j in db.q("SELECT kind, input FROM jobs WHERE kind LIKE 'practice_%' AND status IN ('queued', 'running')"):
        if kinds and j["kind"] not in kinds:
            continue
        d = loads(j["input"], {})
        if d.get("practice_id") == pid or d.get("item_id") in ids:
            return True
    return False


# ---------------------------------------------------------------- results

def score_of(status: str, hints: int) -> float:
    if status != "solved":
        return 0.0
    return 1.0 if hints == 0 else (0.7 if hints == 1 else 0.4)


def _close(db: DB, jobs: Jobs, it: dict, status: str, from_judge: bool = False) -> None:
    """End a problem: score, evidence and schedule per target idea, the next level, and the next problem."""
    ts = now()
    score = score_of(status, it["hints"])
    problem = loads(it["problem"])
    st = graph.states(db)
    with db.tx():
        db.conn.execute("UPDATE practice_items SET status=?, score=?, ended_at=? WHERE id=?", (status, score, ts, it["id"]))
        for nid in problem["node_ids"]:
            lit = nid in st and st[nid].state in LIT
            db.conn.execute("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score, thinking)
                               VALUES(?,?,?,?,?,?,?)""",
                            (ts, nid, f"{it['practice_id']}-{it['id']}", "review" if lit else "practice",
                             int(score >= engine.PASS_SCORE), score,
                             " / ".join(c["text"] for c in loads(it["chunks"], []) if c["text"])[:1500]))
            row = db.conn.execute("SELECT card FROM node_reviews WHERE node_id=?", (nid,)).fetchone()
            card, due_at = engine.review(row[0], score >= engine.PASS_SCORE, ts) if row else \
                engine.review(engine.new_card(ts), score >= engine.PASS_SCORE, ts)
            db.conn.execute("INSERT OR REPLACE INTO node_reviews(node_id, card, due, last_at) VALUES(?,?,?,?)",
                            (nid, card, due_at, ts))
        p = db.conn.execute("SELECT level FROM practices WHERE id=?", (it["practice_id"],)).fetchone()
        level = p[0]
        if status == "solved" and it["hints"] == 0:
            level = min(4, level + 1)
        elif status != "solved" or it["hints"] >= 2:
            level = max(1, level - 1)
        db.conn.execute("UPDATE practices SET level=?, updated_at=? WHERE id=?", (level, ts, it["practice_id"]))
    next_problem(db, jobs, it["practice_id"], from_judge)


# ---------------------------------------------------------------- agent jobs

def _nodes_text(db: DB, ids: list[str]) -> str:
    st = graph.states(db)
    rows = db.q(f"SELECT id, title, statement FROM nodes WHERE id IN ({','.join('?' * len(ids))})", ids) if ids else []
    return "\n".join(f'- {r["id"]}: {r["title"]} - {r["statement"][:300]} [state: {st[r["id"]].state if r["id"] in st else "new"}]'
                     for r in rows) or "(none)"


def _history(db: DB, pid: str) -> str:
    lines = []
    for r in db.q("SELECT * FROM practice_items WHERE practice_id=? ORDER BY id", (pid,)):
        pr = loads(r["problem"])
        lines.append(f'- "{pr["title"]}" on {", ".join(pr["node_ids"])}: {r["status"]}, {r["hints"]} hint(s)')
    return "\n".join(lines) or "(first problem)"


def run_next(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    p = db.one("SELECT * FROM practices WHERE id=?", (d["practice_id"],))
    if not p or p["status"] != "active":
        return {"skipped": True}
    ids = loads(p["node_ids"], [])
    own = loads(p["own"], {})
    pool = ids
    if not pool:  # an own problem: offer the ideas of the graph that match it
        pool = [n["id"] for n in graph.candidates(db, f'{own.get("text", "")} {own.get("page", "")}', k=12)]
    own_text = own.get("text") or ""
    if own.get("page"):
        own_text += f'\n\nPage of the learner\'s source:\n{own["page"]}'
    out = jobs.call(jid, "Practice", Call(
        prompt=prompt("practice_next", ideas=_nodes_text(db, pool), level=p["level"], level_text=LEVELS[p["level"]],
                      history=_history(db, p["id"]), own=own_text.strip() or "(none)",
                      playbook=state.playbook_text(state.playbook(db)), reasoning=state.reasoning_log(db, limit=8)),
        schema=PROBLEM_SCHEMA, model="sonnet", timeout=300))
    valid = set(pool)
    node_ids = [n for n in out["node_ids"] if n in valid][:3]
    if not node_ids and not own_text:
        raise ValueError("the problem names none of the ideas")
    if not out["prompt"].strip() or not out["solution"].strip():
        raise ValueError("the problem or its solution is empty")
    problem = {"title": out["title"][:120], "prompt": out["prompt"].strip(), "node_ids": node_ids, "level": p["level"],
               "solution": out["solution"].strip(), "steps": [s[:300] for s in out["steps"]][:8]}
    db.x("INSERT INTO practice_items(practice_id, problem, status, hints, chunks, created_at) VALUES(?,?,?,?,?,?)",
         (p["id"], dumps(problem), "open", 0, "[]", now()))
    return {"level": p["level"]}


def run_judge(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    it = db.one("SELECT * FROM practice_items WHERE id=?", (d["item_id"],))
    if not it or it["status"] != "open":
        return {"skipped": True}
    problem = loads(it["problem"])
    chunks = loads(it["chunks"], [])
    earlier = "\n".join(f'- thinking: "{c["text"]}"' + (f' | you said: {c["feedback"]}' if c.get("feedback") else "")
                        + (f' | hint given: {c["hint"]}' if c.get("hint") else "") for c in chunks[:-1]) or "(none)"
    out = jobs.call(jid, "Practice", Call(
        prompt=prompt("practice_judge", problem=problem["prompt"], solution=problem["solution"],
                      steps="\n".join(f"- {s}" for s in problem["steps"]) or "(none)", earlier=earlier,
                      latest=chunks[-1]["text"] or "(no new thinking)", wants_hint="yes" if d.get("hint") else "no",
                      hints=it["hints"], guidelines=guidelines.text(db)),
        schema=JUDGE_SCHEMA, model="sonnet", timeout=240))
    verdict = out["verdict"]
    hint = (out.get("hint") or "").strip() if (d.get("hint") or verdict in ("stuck", "wrong")) and verdict != "solved" else ""
    chunks[-1].update(verdict=verdict, feedback=out["feedback"].strip()[:800], hint=hint[:600])
    hints = it["hints"] + (1 if hint else 0)
    db.x("UPDATE practice_items SET chunks=?, hints=? WHERE id=?", (dumps(chunks), hints, it["id"]))
    if verdict == "solved":
        _close(db, jobs, {**it, "hints": hints, "chunks": dumps(chunks)}, "solved", from_judge=True)
    return {"verdict": verdict}


# ---------------------------------------------------------------- view

def listing(db: DB) -> list[dict]:
    return [{"id": r["id"], "title": r["title"], "status": r["status"], "createdAt": r["created_at"]}
            for r in db.q("SELECT * FROM practices ORDER BY created_at DESC LIMIT 30")]


def view(db: DB, pid: str) -> dict | None:
    p = db.one("SELECT * FROM practices WHERE id=?", (pid,))
    if not p:
        return None
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    busy = _busy(db, pid)
    failed = None
    if not busy:
        ids = [r["id"] for r in db.q("SELECT id FROM practice_items WHERE practice_id=?", (pid,))]
        for j in db.q("SELECT status, error, input FROM jobs WHERE kind LIKE 'practice_%' ORDER BY id DESC LIMIT 40"):
            dd = loads(j["input"], {})
            if dd.get("practice_id") == pid or dd.get("item_id") in ids:
                failed = j["error"] if j["status"] == "failed" else None
                break
    items = []
    for r in db.q("SELECT * FROM practice_items WHERE practice_id=? ORDER BY id", (pid,)):
        pr = loads(r["problem"])
        closed = r["status"] != "open"
        items.append({"id": r["id"], "title": pr["title"], "prompt": pr["prompt"], "level": pr["level"],
                      "ideas": [{"id": n, "title": titles.get(n, n)} for n in pr["node_ids"]],
                      "status": r["status"], "hints": r["hints"], "score": r["score"], "chunks": loads(r["chunks"], []),
                      "solution": pr["solution"] if closed else None})
    return {"id": p["id"], "title": p["title"], "status": p["status"], "level": p["level"], "levelText": LEVELS[p["level"]],
            "count": p["count"], "busy": busy, "error": failed, "items": items,
            "ideas": [{"id": n, "title": titles.get(n, n)} for n in loads(p["node_ids"], [])]}


def schedule(db: DB) -> dict:
    """For the page: what is due now and when the next idea comes due."""
    items = due(db)
    nxt = db.one("SELECT MIN(due) AS d FROM node_reviews WHERE due > ?", (now(),))
    return {"due": items[:30], "dueCount": sum(1 for d in items if d["reason"] == "due"),
            "newCount": sum(1 for d in items if d["reason"] == "new"), "next": (nxt or {}).get("d")}
