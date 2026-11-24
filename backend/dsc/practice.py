"""Recall practice (SPEC §24): make understood ideas usable. Step 6 of the knowledge-graph rework.

Understanding an idea is not the same as recalling it when a problem calls for it. Recall works from cues, so
practice widens and strengthens them: a stream of problems that adapt.

- A practice is a short run of problems (default 5) over a set of ideas (graph nodes): ideas picked on the map or in
  the picker, the weakest ideas, or the learner's own problem (text, or a page of one of their PDFs).
- Difficulty is a level 1-4 (``LEVELS``): how many ideas a problem combines and how new its setting is. A clean solve
  raises it; a hard solve or giving up lowers it.
- The learner writes their thinking in chunks (typed or dictated). An agent judges each chunk: solved, progress, or
  stuck / wrong direction, with the smallest hint that moves them on, never the solution. The learner can ask for a
  hint or give up (then the worked solution shows).
- Result per problem: score 1.0 solved without hints, 0.7 with one hint, 0.4 with more, 0 given up. It is evidence on
  each target idea. There is no schedule (SPEC §48): the learner chooses what to practise.

Phase 3 of the lessons rework (SPEC §44):
- What to practise is picked from a tree (``targets``): books → chapters → lessons → their steps, the fields of the
  Formulas country with their formulas, or the weakest ideas. Chosen steps and formulas become the run's focus.
- Problems switch ideas (never the same idea twice in a row), move from recall to telling two cases apart to combining
  ideas, and are solved by the writer first. Hints climb a ladder, one rung per request.
- After a problem the learner reads the verdict and the solution; the next problem is written meanwhile but shown only
  when they press "Next problem" (``advance``).
- At the end, missed and hint-heavy problems come back once, in a new setting (retests, at most ``RETESTS``).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from . import engine, graph, guidelines, state
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

PROBLEMS = 5
PICK = 6  # ideas in a practice of the weakest ideas (when nothing is picked)
RETESTS = 3  # at most this many retests at the end of a run
SURFACES = ("applied", "formal", "mixed")
HINT_RUNGS = ("look again at a given", "name the kind of pattern", "name the area of ideas", "name the idea",
              "outline the first move", "show the worked step")
LEVELS = {
    1: "one idea, in a setting close to how it was taught",
    2: "one idea, in a new setting (different numbers, domain or wording; the cue is less obvious)",
    3: "two ideas combined, in a new setting",
    4: "two or three ideas combined, in an unfamiliar setting where the learner must first see which ideas apply",
}
LIT = ("learned",)

PROBLEM_SCHEMA = {"type": "object", "required": ["title", "prompt", "node_ids", "solution", "steps"], "properties": {
    "title": {"type": "string"}, "prompt": {"type": "string"}, "mode": {"enum": ["recall", "tell_apart", "combine"]},
    "node_ids": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
    "solution": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}}}}
JUDGE_SCHEMA = {"type": "object", "required": ["verdict", "feedback"], "properties": {
    "verdict": {"enum": ["solved", "progress", "stuck", "wrong"]},
    "feedback": {"type": "string"}, "hint": {"type": "string"}, "rung": {"type": "integer"}}}


# ---------------------------------------------------------------- which ideas

# ---------------------------------------------------------------- learner actions

def start(db: DB, jobs: Jobs, node_ids: list[str] | None = None, own: str = "", source: dict | None = None,
          focus: dict | None = None, formulas: list[str] | None = None, count: int | None = None, surface: str = "mixed",
          title: str = "") -> str:
    known = {r["id"] for r in db.q("SELECT id FROM nodes")}
    of = graph.node_of(db)  # a lesson id stands for its idea on the map
    ids = list(dict.fromkeys(of.get(n, n) for n in (node_ids or [])))
    ids = [n for n in ids if n in known]
    picked_formulas = []
    if formulas:  # formulas picked from the Formulas country: practise them through the lessons they come from
        from . import formula_fields
        every = formula_fields.all_formulas(db)
        nodes = graph.node_of(db)
        for k in dict.fromkeys(formulas):
            if k not in every:
                continue
            picked_formulas.append({"name": every[k]["name"], "tex": every[k]["tex"]})
            hosts = [nodes.get(r["concept_id"], r["concept_id"]) for r in db.q("SELECT concept_id FROM formula_notes WHERE key=?", (k,))]
            hosts += [nodes.get(r["formula_id"], r["formula_id"]) for r in db.q("SELECT formula_id FROM formula_forms WHERE key=?", (k,))]
            ids += [h for h in hosts if h in known and h not in ids]
    clean_focus = {n: [str(t)[:120] for t in v][:12] for n, v in (focus or {}).items() if n in ids and isinstance(v, list)}
    own = " ".join((own or "").split())[:3000]
    page_text = ""
    if source and source.get("id"):
        row = db.one("SELECT text FROM source_pages WHERE source_id=? AND page=?", (source["id"], int(source.get("page") or 0)))
        if not row:
            raise ValueError("that page has no text")
        page_text = row["text"][:4000]
    if not ids and not own and not page_text:
        ids = [w["nodeId"] for w in weakest(db)[:PICK]]
    if not ids and not own and not page_text:
        raise ValueError("nothing to practise yet: learn something first")
    count = 1 if (own or page_text) and not ids else max(1, min(30, int(count or PROBLEMS)))
    title = (str(title or "").strip()[:120] or own[:60] or (f"Page {source.get('page')} of your source" if page_text else "")) or \
        ", ".join(r["title"] for r in db.q(f"SELECT title FROM nodes WHERE id IN ({','.join('?' * len(ids))})", ids))[:120]
    pid = f"p-{secrets.token_hex(4)}"
    ts = now()
    db.x("""INSERT INTO practices(id, title, node_ids, own, status, level, count, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
         (pid, title or "Practice", dumps(ids), dumps({"text": own, "page": page_text, "source": source or {}, "focus": clean_focus,
                                                       "formulas": picked_formulas, "surface": surface if surface in SURFACES else "mixed"}),
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
    db.x("UPDATE practice_items SET status='skipped' WHERE practice_id=? AND status IN ('open', 'waiting') AND chunks='[]'", (pid,))
    db.x("UPDATE practices SET status='done', updated_at=? WHERE id=?", (now(), pid))


def next_problem(db: DB, jobs: Jobs, pid: str, from_judge: bool = False) -> None:
    p = db.one("SELECT * FROM practices WHERE id=?", (pid,))
    # called from the judge job, which is itself still running: only another "next problem" job blocks
    if not p or p["status"] != "active" or _busy(db, pid, ("practice_next",) if from_judge else None):
        return
    if db.one("SELECT 1 FROM practice_items WHERE practice_id=? AND status IN ('open', 'waiting')", (pid,)):
        return
    items = db.q("SELECT * FROM practice_items WHERE practice_id=? ORDER BY id", (pid,))
    main = [r for r in items if not loads(r["problem"]).get("retestOf")]
    if len(main) < p["count"]:
        jobs.enqueue("practice_next", "Write a practice problem", {"practice_id": pid})
        return
    # the end: missed and hint-heavy problems come back once, in a new setting
    done_again = {loads(r["problem"]).get("retestOf") for r in items} - {None}
    weak = [r for r in main if r["status"] in ("solved", "given_up") and (r["score"] or 0) < 0.7 and r["id"] not in done_again]
    if weak and len(done_again) < RETESTS:
        jobs.enqueue("practice_next", "Write a retest", {"practice_id": pid, "retest_of": weak[0]["id"]})
        return
    db.x("UPDATE practices SET status='done', updated_at=? WHERE id=?", (now(), pid))


def advance(db: DB, pid: str) -> None:
    """"Next problem": show the problem written while the learner read the last one (or as soon as it is written)."""
    p = db.one("SELECT * FROM practices WHERE id=?", (pid,))
    if not p or p["status"] != "active":
        raise ValueError("this practice is over")
    if db.one("SELECT 1 FROM practice_items WHERE practice_id=? AND status='open'", (pid,)):
        return
    w = db.one("SELECT id FROM practice_items WHERE practice_id=? AND status='waiting' ORDER BY id LIMIT 1", (pid,))
    if w:
        db.x("UPDATE practice_items SET status='open', created_at=? WHERE id=?", (now(), w["id"]))
    else:  # still being written: it opens when it is ready
        own = loads(p["own"], {})
        db.x("UPDATE practices SET own=? WHERE id=?", (dumps({**own, "wantNext": True}), pid))


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
    """End a problem: score and evidence per target idea, the next level, and the next problem."""
    ts = now()
    score = score_of(status, it["hints"])
    problem = loads(it["problem"])
    with db.tx():
        db.conn.execute("UPDATE practice_items SET status=?, score=?, ended_at=? WHERE id=?", (status, score, ts, it["id"]))
        for nid in problem["node_ids"]:
            db.conn.execute("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score, thinking)
                               VALUES(?,?,?,?,?,?,?)""",
                            (ts, nid, f"{it['practice_id']}-{it['id']}", "practice",
                             int(score >= engine.PASS_SCORE), score,
                             " / ".join(c["text"] for c in loads(it["chunks"], []) if c["text"])[:1500]))
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
        lines.append(f'- "{pr["title"]}" ({pr.get("mode") or "recall"}) on {", ".join(pr["node_ids"])}: {r["status"]}, '
                     f'{r["hints"]} hint(s)' + (" [a retest]" if pr.get("retestOf") else ""))
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
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    focus = "\n".join(f'- {titles.get(n, n)} ({n}): {", ".join(v)}' for n, v in (own.get("focus") or {}).items() if v)
    formulas_text = "\n".join(f'- {f["name"]}: ${f["tex"]}$' for f in own.get("formulas") or [])
    retest = ""
    if d.get("retest_of"):
        old = db.one("SELECT * FROM practice_items WHERE id=?", (d["retest_of"],))
        if old:
            op = loads(old["problem"])
            retest = (f'This is a RETEST of a problem the learner {"gave up on" if old["status"] == "given_up" else "solved only with hints"}: '
                      f'"{op["prompt"][:800]}" (ideas {", ".join(op["node_ids"])}). Write a new problem on the same ideas, in a new '
                      'setting and with new numbers: not the same surface.')
    last = db.one("SELECT problem FROM practice_items WHERE practice_id=? ORDER BY id DESC LIMIT 1", (p["id"],))
    out = jobs.call(jid, "Practice", Call(
        prompt=prompt("practice_next", ideas=_nodes_text(db, pool), level=p["level"], level_text=LEVELS[p["level"]],
                      history=_history(db, p["id"]), own=own_text.strip() or "(none)",
                      focus=focus or "(none: the whole of each idea)", formulas=formulas_text or "(none)",
                      surface=own.get("surface") or "mixed", retest=retest or "(no: a normal problem)",
                      last=", ".join(loads(last["problem"])["node_ids"]) if last else "(none)",
                      playbook=state.playbook_text(state.playbook(db)), reasoning=state.reasoning_log(db, limit=8)),
        schema=PROBLEM_SCHEMA, model="sonnet", timeout=300))
    valid = set(pool)
    node_ids = [n for n in out["node_ids"] if n in valid][:3]
    if not node_ids and not own_text:
        raise ValueError("the problem names none of the ideas")
    if not out["prompt"].strip() or not out["solution"].strip():
        raise ValueError("the problem or its solution is empty")
    problem = {"title": out["title"][:120], "prompt": out["prompt"].strip(), "node_ids": node_ids, "level": p["level"],
               "mode": out.get("mode") if out.get("mode") in ("recall", "tell_apart", "combine") else "recall",
               "solution": out["solution"].strip(), "steps": [s[:300] for s in out["steps"]][:8]}
    if d.get("retest_of"):
        problem["retestOf"] = d["retest_of"]
    # the first problem opens at once; later ones wait for "Next problem" (the learner reads the last solution first)
    first = not db.one("SELECT 1 FROM practice_items WHERE practice_id=?", (p["id"],))
    want = bool(own.get("wantNext"))
    db.x("INSERT INTO practice_items(practice_id, problem, status, hints, chunks, created_at) VALUES(?,?,?,?,?,?)",
         (p["id"], dumps(problem), "open" if first or want else "waiting", 0, "[]", now()))
    if want:
        db.x("UPDATE practices SET own=? WHERE id=?", (dumps({k: v for k, v in own.items() if k != "wantNext"}), p["id"]))
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
                      hints=it["hints"], guidelines=guidelines.text(db),
                      rung=f'{min(it["hints"], len(HINT_RUNGS) - 1)} ("{HINT_RUNGS[min(it["hints"], len(HINT_RUNGS) - 1)]}")',
                      rungs="\n".join(f"{i}. {r}" for i, r in enumerate(HINT_RUNGS))),
        schema=JUDGE_SCHEMA, model="sonnet", timeout=240))
    verdict = out["verdict"]
    hint = (out.get("hint") or "").strip() if (d.get("hint") or verdict in ("stuck", "wrong")) and verdict != "solved" else ""
    rung = out.get("rung") if isinstance(out.get("rung"), int) else it["hints"]
    chunks[-1].update(verdict=verdict, feedback=out["feedback"].strip()[:800], hint=hint[:600],
                      rung=max(0, min(len(HINT_RUNGS) - 1, rung)) if hint else None)
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
        closed = r["status"] not in ("open", "waiting")
        waiting = r["status"] == "waiting"
        items.append({"id": r["id"], "title": "" if waiting else pr["title"], "prompt": "" if waiting else pr["prompt"],
                      "level": pr["level"], "mode": pr.get("mode") or "recall", "retest": bool(pr.get("retestOf")),
                      "ideas": [{"id": n, "title": titles.get(n, n)} for n in pr["node_ids"]],
                      "status": r["status"], "hints": r["hints"], "score": r["score"], "chunks": loads(r["chunks"], []),
                      "solution": pr["solution"] if closed else None})
    retests = sum(1 for i in items if i["retest"])
    own = loads(p["own"], {})
    return {"id": p["id"], "title": p["title"], "status": p["status"], "level": p["level"], "levelText": LEVELS[p["level"]],
            "count": p["count"] + retests, "retests": retests, "busy": busy, "error": failed, "items": items,
            "rungs": list(HINT_RUNGS), "surface": own.get("surface") or "mixed", "wantNext": bool(own.get("wantNext")),
            "focus": own.get("focus") or {}, "formulas": own.get("formulas") or [],
            "ideas": [{"id": n, "title": titles.get(n, n)} for n in loads(p["node_ids"], [])]}


# ---------------------------------------------------------------- what to practise (SPEC §44)

def targets(db: DB) -> dict:
    """The picker: books → chapters → lessons (each an idea of the map) → their steps or sections; the fields of the
    Formulas country with their formulas; and the weakest ideas."""
    from . import formula_fields
    st = graph.states(db)
    nodes = graph.node_of(db)
    written = {r["concept_id"]: loads(r["body"], {}) for r in db.q(
        "SELECT c.concept_id, c.body FROM cards c JOIN (SELECT concept_id, MAX(version) AS v FROM cards GROUP BY concept_id) m "
        "ON m.concept_id = c.concept_id AND m.v = c.version")}
    started = {r["id"] for r in db.q("SELECT id FROM concepts WHERE started=1")}
    books = []
    for b in db.q("SELECT id, title FROM books ORDER BY created_at"):
        chapters = []
        for ch in db.q("SELECT chapter, title FROM book_chapters WHERE book_id=? ORDER BY chapter", (b["id"],)):
            lessons = []
            for x in db.q("""SELECT concept_id, title FROM book_parts WHERE book_id=? AND chapter=? AND concept_id IS NOT NULL
                             ORDER BY ord""", (b["id"], ch["chapter"])):
                cid = x["concept_id"]
                nid = nodes.get(cid, cid)
                s = st.get(nid)
                card = written.get(cid) or {}
                lessons.append({"conceptId": cid, "nodeId": nid, "title": x["title"], "state": s.state if s else "pending",
                                "mastery": round(s.mastery, 2) if s else 0.0, "studied": cid in started or cid in written,
                                "parts": [sec["heading"] for sec in card.get("sections", [])][:14]})
            if lessons:
                chapters.append({"chapter": ch["chapter"], "title": ch["title"], "lessons": lessons})
        if chapters:
            books.append({"id": b["id"], "title": b["title"], "chapters": chapters})
    tags = formula_fields.tags(db)
    every = formula_fields.all_formulas(db)
    fields = []
    for fid, ftitle in formula_fields.FIELDS:
        fs = [{"key": k, "name": v["name"], "tex": v["tex"]} for k, v in every.items() if fid in (tags.get(k) or []) and v["name"]]
        if fs:
            fields.append({"id": fid, "title": ftitle, "formulas": fs[:60]})
    return {"books": books, "fields": fields, "weakest": weakest(db)}


def weakest(db: DB, k: int = 12) -> list[dict]:
    """Ideas the learner has worked on that hold least: low mastery, recent misses, many hints."""
    st = graph.states(db)
    nodes = graph.node_of(db)
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM nodes")}
    misses: dict[str, int] = {}
    for r in db.q("SELECT concept_id, correct, score FROM evidence WHERE voided=0 ORDER BY id DESC LIMIT 600"):
        nid = nodes.get(r["concept_id"], r["concept_id"])
        if not r["correct"] or (r["score"] is not None and r["score"] < 0.7):
            misses[nid] = misses.get(nid, 0) + 1
    out = []
    for nid, s in st.items():
        if nid not in titles or s.state in ("pending", "locked", "ready") and not misses.get(nid):
            continue
        weak = (1 - s.mastery) + 0.3 * misses.get(nid, 0)
        if s.state == "learned" and s.mastery >= 0.98 and not misses.get(nid):
            continue
        out.append({"nodeId": nid, "title": titles[nid], "state": s.state, "mastery": round(s.mastery, 2),
                    "misses": misses.get(nid, 0), "weak": round(weak, 2)})
    return sorted(out, key=lambda x: -x["weak"])[:k]
