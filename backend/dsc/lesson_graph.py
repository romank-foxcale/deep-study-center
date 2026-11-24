"""The lesson plan graph (SPEC §42): a book lesson is planned before it is written, and the learner approves the plan.

A plan is a small graph from what the learner already holds to the lesson's one idea: held nodes (not taught again),
foundations, reasoning steps, formulas, and the goal. Each node says how it will be shown (example, interactive,
figure, text, derivation). The learner reads it while it is made, cuts nodes ("I know this"), asks for another form,
adds notes, re-plans (a new version), and approves. Approving writes the lesson, guided by the plan.

Plans are kept per (lesson, version) in ``lesson_graphs``; the learner's notes in ``lesson_graph_notes``. A note sent
while a plan is being made ("steering") is used by the next version, which starts by itself when the running one ends.
"""

from __future__ import annotations

from . import graph
from .db import DB, dumps, loads, now

KINDS = ("held", "foundation", "step", "formula", "goal")
FORMS = ("example", "interactive", "figure", "text", "derivation", "none")
NOTE_KINDS = ("cut", "other", "note", "plan", "steer")


class PlanError(Exception):
    pass


SCHEMA = {"type": "object", "required": ["approach", "goal", "nodes", "edges"], "properties": {
    "approach": {"type": "string"}, "goal": {"type": "string"},
    "nodes": {"type": "array", "items": {"type": "object", "required": ["key", "kind", "title", "says", "form"], "properties": {
        "key": {"type": "string"}, "kind": {"enum": list(KINDS)}, "title": {"type": "string"}, "says": {"type": "string"},
        "form": {"enum": list(FORMS)}, "why_form": {"type": "string"}, "pages": {"type": "string"}, "links_to": {"type": "string"}}}},
    "edges": {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}}}}


# ---------------------------------------------------------------- reading

def latest(db: DB, cid: str) -> dict | None:
    row = db.one("SELECT * FROM lesson_graphs WHERE concept_id=? ORDER BY version DESC LIMIT 1", (cid,))
    return _row(row) if row else None


def approved(db: DB, cid: str) -> dict | None:
    row = db.one("SELECT * FROM lesson_graphs WHERE concept_id=? AND status='approved' ORDER BY version DESC LIMIT 1", (cid,))
    return _row(row) if row else None


def _row(r: dict) -> dict:
    return {"conceptId": r["concept_id"], "version": r["version"], "status": r["status"], "approach": r["approach"],
            "goal": r["goal"], "nodes": loads(r["nodes"], []), "edges": loads(r["edges"], []), "error": r["error"],
            "createdAt": r["created_at"], "approvedAt": r["approved_at"]}


def view(db: DB, cid: str) -> dict:
    """The plan screen: the newest version, what changed since the version before, the notes, and the running job."""
    from . import state
    rows = db.q("SELECT * FROM lesson_graphs WHERE concept_id=? ORDER BY version", (cid,))
    cur = _row(rows[-1]) if rows else None
    done = [r for r in rows[:-1] if r["status"] in ("ready", "approved")]  # compare with the last finished version
    prev = _row(done[-1]) if done else None
    if cur and prev:
        before = {n["key"]: n for n in prev["nodes"]}
        for n in cur["nodes"]:
            old = before.get(n["key"])
            n["change"] = "new" if not old else "changed" if (old["says"], old["form"], old["kind"]) != (n["says"], n["form"], n["kind"]) else ""
        cur["removed"] = [n["title"] for k, n in before.items() if k not in {x["key"] for x in cur["nodes"]}]
    notes = [{"id": r["id"], "version": r["version"], "node": r["node"], "kind": r["kind"], "text": r["text"], "at": r["at"],
              "used": r["used_in"]} for r in db.q("SELECT * FROM lesson_graph_notes WHERE concept_id=? ORDER BY id", (cid,))]
    job = next((j for j in state.jobs(db) if j["kind"] == "lesson_graph" and j["input"].get("concept_id") == cid
                and j["status"] in ("queued", "running")), None)
    if cur and cur["status"] == "planning" and not job:  # the app stopped while planning
        cur["status"], cur["error"] = "failed", "interrupted: the app stopped while planning"
    if cur and not cur["nodes"] and prev:  # while a new version is made (or failed): the last finished one, to look at
        cur["shown"] = prev
    return {"plan": cur, "versions": [r["version"] for r in rows], "notes": notes,
            "job": {"id": job["id"], "status": job["status"], "progress": job.get("progress") or []} if job else None,
            "pending": sum(1 for n in notes if n["used"] is None)}


# ---------------------------------------------------------------- actions

def start(db: DB, jobs, cid: str, force: bool = False) -> int | None:
    """Make the next plan version (the first one, or a re-plan with the notes not used yet). None when one is running
    (``force``: the running one is ending and starts the next one itself)."""
    _lesson(db, cid)
    if not force and jobs.active("lesson_graph", concept_id=cid):
        return None
    with db.tx():  # two opens at the same time make one version, not two
        row = db.conn.execute("SELECT MAX(version), SUM(status='planning') FROM lesson_graphs WHERE concept_id=?", (cid,)).fetchone()
        if row[1] and not force and jobs.active("lesson_graph", concept_id=cid):
            return None
        db.conn.execute("UPDATE lesson_graphs SET status='failed', error='interrupted' WHERE concept_id=? AND status='planning'", (cid,))
        version = (row[0] or 0) + 1
        db.conn.execute("""INSERT INTO lesson_graphs(concept_id, version, status, approach, goal, nodes, edges, error, created_at,
                           approved_at) VALUES(?,?,?,?,?,?,?,?,?,NULL)""", (cid, version, "planning", "", "", "[]", "[]", "", now()))
    return jobs.enqueue("lesson_graph", "Plan this lesson", {"concept_id": cid, "version": version})


def note(db: DB, jobs, cid: str, kind: str, text: str = "", node: str = "") -> None:
    """A learner note on the plan: on a node (cut, other, note), on the whole plan (plan), or while it is made (steer)."""
    if kind not in NOTE_KINDS:
        raise PlanError("unknown kind of note")
    cur = latest(db, cid)
    if not cur:
        raise PlanError("this lesson has no plan yet")
    if node and node not in {n["key"] for n in cur["nodes"]}:
        raise PlanError("unknown node")
    if kind in ("note", "plan", "steer") and not text.strip():
        raise PlanError("the note is empty")
    if kind == "cut":  # pressing "I know this" again takes it back
        old = db.one("""SELECT id FROM lesson_graph_notes WHERE concept_id=? AND node=? AND kind='cut' AND used_in IS NULL""",
                     (cid, node))
        if old:
            db.x("DELETE FROM lesson_graph_notes WHERE id=?", (old["id"],))
            return
    db.x("INSERT INTO lesson_graph_notes(concept_id, version, node, kind, text, at, used_in) VALUES(?,?,?,?,?,?,NULL)",
         (cid, cur["version"], node, kind, text.strip()[:1000], now()))


def approve(db: DB, jobs, cid: str) -> None:
    """Approve the newest plan and write the lesson with it."""
    cur = latest(db, cid)
    if not cur or cur["status"] not in ("ready", "approved"):
        raise PlanError("there is no finished plan to approve")
    if jobs.active("lesson_graph", concept_id=cid):
        raise PlanError("a new version of the plan is being made")
    db.x("UPDATE lesson_graphs SET status='approved', approved_at=? WHERE concept_id=? AND version=?", (now(), cid, cur["version"]))
    from . import bookstudy
    bookstudy.write_planned(db, jobs, cid)


def _lesson(db: DB, cid: str) -> dict:
    row = db.one("""SELECT p.*, c.objective, b.title AS book, b.source_id FROM book_parts p JOIN concepts c ON c.id = p.concept_id
                    JOIN books b ON b.id = p.book_id WHERE p.concept_id=?""", (cid,))
    if not row:
        raise PlanError("only a book lesson has a plan")
    return row


# ---------------------------------------------------------------- the job

def run(jobs, jid: int, d: dict) -> dict:
    from . import cells
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    cid, version = d["concept_id"], d["version"]
    x = _lesson(db, cid)
    started = now()
    notes = db.q("SELECT * FROM lesson_graph_notes WHERE concept_id=? AND used_in IS NULL ORDER BY id", (cid,))
    earlier = db.q("SELECT * FROM lesson_graph_notes WHERE concept_id=? AND used_in IS NOT NULL ORDER BY id", (cid,))
    prev = db.one("SELECT * FROM lesson_graphs WHERE concept_id=? AND version<? AND status IN ('ready','approved') ORDER BY version DESC LIMIT 1",
                  (cid, version))
    text, listing = cells.source_text(db, cid)  # every source of this idea (SPEC §49)
    jobs.progress(jid, f"reading {listing.count(';') + 1} source(s): {listing[:120]}" if listing else "no source text")
    text = text or "(no text)"
    jobs.progress(jid, "looking up what you hold in your map")
    held = _held(db, cid, f"{x['title']} {x['summary']} {text[:3000]}")
    try:
        out = jobs.call(jid, "Research", Call(
            prompt=prompt("lesson_plan", book=listing or x["book"], chapter=x["chapter_title"], title=x["title"],
                          covers=x["summary"] or x["objective"] or "", ideas="; ".join(loads(x["ideas"], [])) or "-",
                          pages=f"{x['page_from']}-{x['page_to']}", held=held, previous=_previous_text(prev),
                          notes=_notes_text(notes, prev), earlier=_notes_text(earlier, prev), text=text),
            schema=SCHEMA, model="opus", timeout=900))
        jobs.progress(jid, "checking the plan: every step builds on one before it")
        plan = clean(out, set(_ids(db)))
    except Exception as e:  # noqa: BLE001 - the screen shows the error and a "try again"
        db.x("UPDATE lesson_graphs SET status='failed', error=? WHERE concept_id=? AND version=?", (str(e)[:400], cid, version))
        raise
    with db.tx():
        db.conn.execute("""UPDATE lesson_graphs SET status='ready', approach=?, goal=?, nodes=?, edges=?, error='' WHERE concept_id=? AND version=?""",
                        (plan["approach"], plan["goal"], dumps(plan["nodes"]), dumps(plan["edges"]), cid, version))
        for n in notes:
            db.conn.execute("UPDATE lesson_graph_notes SET used_in=? WHERE id=?", (version, n["id"]))
    # notes the learner sent while this version was made: the next version starts by itself ("steering")
    if db.one("SELECT 1 FROM lesson_graph_notes WHERE concept_id=? AND used_in IS NULL AND at>=?", (cid, started)):
        jobs.progress(jid, "your notes came in while planning: making the next version with them")
        start(db, jobs, cid, force=True)
    return {"nodes": len(plan["nodes"]), "version": version}


def _ids(db: DB) -> list[str]:
    return [r["id"] for r in db.q("SELECT id FROM nodes")]


def _held(db: DB, cid: str, text: str) -> str:
    """What the learner may already hold: this lesson's prerequisites and the closest ideas of the map, with states,
    and the formulas met in lessons."""
    from . import formula_fields
    st = graph.states(db)
    own = graph.node_of(db).get(cid, cid)
    near = [lk["src"] for lk in graph.links(db) if lk["dst"] == own] + [c["id"] for c in graph.candidates(db, text, k=25)]
    rows = {r["id"]: r for r in db.q("SELECT id, title FROM nodes")}
    lines = [f'- {i}: {rows[i]["title"]} ({st[i].state if i in st else "pending"})' for i in dict.fromkeys(near)
             if i in rows and i != own][:35]
    fx = formula_fields.all_formulas(db)
    formulas = [f'- {v["name"]}: ${v["tex"]}$' for v in list(fx.values())[:40] if v["name"]]
    return ("Ideas (id: title (state)):\n" + ("\n".join(lines) or "(none)") +
            "\n\nFormulas the learner has met in lessons (name: form):\n" + ("\n".join(formulas) or "(none)"))


def _previous_text(prev: dict | None) -> str:
    if not prev:
        return "(none: this is the first version)"
    nodes = loads(prev["nodes"], [])
    return (f'Version {prev["version"]}. Approach: {prev["approach"]}\n' +
            "\n".join(f'- {n["key"]} [{n["kind"]}, {n["form"]}]: {n["title"]}. {n["says"]}' for n in nodes) +
            "\nEdges: " + ", ".join(f"{a}->{b}" for a, b in loads(prev["edges"], [])))


def _notes_text(notes: list[dict], prev: dict | None) -> str:
    if not notes:
        return "(none)"
    title = {n["key"]: n["title"] for n in loads(prev["nodes"], [])} if prev else {}
    say = {"cut": "I already know this: leave it out (make it a held node or drop it)",
           "other": "show this another way", "note": "", "plan": "", "steer": ""}
    out = []
    for n in notes:
        where = f'node {n["node"]} ("{title.get(n["node"], n["node"])}")' if n["node"] else "the whole plan"
        out.append(f'- On {where}: {" ".join(x for x in (say[n["kind"]], n["text"]) if x)}')
    return "\n".join(out)


def clean(out: dict, known_ids: set[str]) -> dict:
    """Check the model's plan: unique keys, known kinds and forms, edges between existing nodes, no cycles, one goal."""
    import re
    nodes, seen = [], set()
    for n in out.get("nodes") or []:
        key = re.sub(r"[^a-z0-9_-]+", "-", str(n.get("key") or "").lower()).strip("-")[:40]
        if not key or key in seen or not str(n.get("title") or "").strip():
            continue
        seen.add(key)
        kind = n.get("kind") if n.get("kind") in KINDS else "step"
        link = str(n.get("links_to") or "")
        nodes.append({"key": key, "kind": kind, "title": str(n["title"]).strip()[:80], "says": str(n.get("says") or "").strip()[:400],
                      "form": n.get("form") if n.get("form") in FORMS else ("none" if kind == "held" else "text"),
                      "whyForm": str(n.get("why_form") or "").strip()[:200], "pages": str(n.get("pages") or "")[:80],
                      "linksTo": link if link in known_ids else ""})
    if not nodes:
        raise PlanError("the plan has no nodes")
    keys = {n["key"] for n in nodes}
    norm = lambda s: re.sub(r"[^a-z0-9_-]+", "-", str(s).lower()).strip("-")[:40]  # noqa: E731
    edges: list[list[str]] = []
    for e in out.get("edges") or []:
        if isinstance(e, (list, tuple)) and len(e) == 2:
            a, b = norm(e[0]), norm(e[1])
            if a in keys and b in keys and a != b and [a, b] not in edges and not _reaches(edges, b, a):
                edges.append([a, b])  # an edge that closes a cycle is dropped
    if not any(n["kind"] == "goal" for n in nodes):
        sinks = [n for n in nodes if not any(a == n["key"] for a, _ in edges)]
        (sinks[-1] if sinks else nodes[-1])["kind"] = "goal"
    return {"approach": str(out.get("approach") or "").strip()[:1200], "goal": str(out.get("goal") or "").strip()[:400],
            "nodes": nodes, "edges": edges}


def _reaches(edges: list[list[str]], a: str, b: str) -> bool:
    todo, seen = [a], set()
    while todo:
        x = todo.pop()
        if x == b:
            return True
        if x in seen:
            continue
        seen.add(x)
        todo += [t for f, t in edges if f == x]
    return False


def as_text(plan: dict) -> str:
    """The approved plan, for the lesson writer."""
    nodes = [n for n in plan["nodes"] if n["kind"] != "held"]
    return (f'Approach: {plan["approach"]}\nGoal: {plan["goal"]}\nSteps, in order (kind, form: title. what it says):\n' +
            "\n".join(f'{i + 1}. [{n["kind"]}, {n["form"]}] {n["title"]}. {n["says"]}' for i, n in enumerate(_ordered(plan))
                      if n in nodes) +
            "\nThe learner already holds (do not teach again): " +
            (", ".join(n["title"] for n in plan["nodes"] if n["kind"] == "held") or "-"))


def _ordered(plan: dict) -> list[dict]:
    """Nodes in an order where each comes after what it needs (stable on the model's order)."""
    keys = [n["key"] for n in plan["nodes"]]
    need = {k: {a for a, b in plan["edges"] if b == k} for k in keys}
    out: list[str] = []
    while len(out) < len(keys):
        nxt = next((k for k in keys if k not in out and need[k] <= set(out)), None)
        out.append(nxt or next(k for k in keys if k not in out))
    by = {n["key"]: n for n in plan["nodes"]}
    return [by[k] for k in out]
