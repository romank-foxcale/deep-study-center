"""Study sessions: "teach me X", with or without a goal (SPEC §22). Step 4 of the knowledge-graph rework.

Phases (``sessions.status``):
1. ``sketching``: an agent turns the topic into 4-12 ideas with their dependencies, matched to the learner's graph
   (``same_as``). Each idea becomes a node at once (existing node or a new one, origin "session"), so every answer
   below is evidence on a node. Ideas the graph already holds as learned are marked known.
2. ``probing``: quick questions on the ideas that are not known yet, one at a time, each chosen from the last answer
   (SPEC §26), at most ``PROBE_MAX``. While the learner answers, the next question is made ahead for both outcomes (a
   right answer, a miss), so it shows at once (SPEC §54). It ends with a result per idea: what the learner reasons
   from, where their reasoning stops, and the misconceptions. The teaching turns of an idea get its result.
3. ``planning``: a graph of the ideas to teach; the learner can skip ideas they know and learn them again.
4. ``teaching`` (flow B, SPEC §54): one idea at a time, fitted to what placement found. A new idea is **taught**
   first (a small worked example, then the rule, in short parts) and then **checked**. A partly known idea starts
   with one **try** problem: right → a short summary and on; a miss → only the missed part is taught, then a check.
   A wrong check gets one **repair**, written ahead for each wrong option while the learner reads the check. The learner may pick the next idea among the open ones (all needed ideas done);
   the next idea is written ahead while the learner works.
5. ``extracting``: an agent writes what the learner now holds as short statements and adds reasoning links between
   the ideas and existing nodes. Then ``done``.

Evidence: probe and check answers are recorded on the idea's node (``evidence.concept_id`` = node id), with the same
guess rule as lessons. Understanding alone does not make a node "learned" (that needs 3 right items and recall
practice, step 6), so taught ideas usually show as "learning".
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING

from . import graph, guidelines, mcq, progress, sources, state
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

PROBE_MAX = 8  # questions; one per probe job, each chosen from the answers so far
LEVELS = ("known", "partial", "unknown")
PROBE_LEVELS = (*LEVELS, "untested")

_MCQ = mcq.SCHEMA

SKETCH_SCHEMA = {"type": "object", "required": ["title", "target_key", "ideas"], "properties": {
    "title": {"type": "string"}, "target_key": {"type": "string"},
    "ideas": {"type": "array", "minItems": 1, "maxItems": 14, "items": {"type": "object",
        "required": ["key", "title", "statement", "prereq_keys"], "properties": {
            "key": {"type": "string"}, "title": {"type": "string"}, "statement": {"type": "string"},
            "prereq_keys": {"type": "array", "items": {"type": "string"}}, "same_as": {"type": "string"}}}}}}

PROBE_SCHEMA = {"type": "object", "required": ["done"], "properties": {
    "done": {"type": "boolean"},
    "question": {"type": "object", "required": ["idea_key", *_MCQ["required"]],
                 "properties": {"idea_key": {"type": "string"}, **_MCQ["properties"]}},
    "result": {"type": "object", "required": ["start", "ideas"], "properties": {
        "start": {"type": "string"},
        "ideas": {"type": "array", "items": {"type": "object",
            "required": ["idea_key", "level", "reasons_from", "runs_out", "misconceptions"], "properties": {
                "idea_key": {"type": "string"}, "level": {"enum": list(PROBE_LEVELS)},
                "reasons_from": {"type": "string"}, "runs_out": {"type": "string"},
                "misconceptions": {"type": "array", "items": {"type": "string"}}}}}}}}}

_PARTS = {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string"}}
TEACH_SCHEMA = {"type": "object", "required": ["parts", "check"], "properties": {"parts": _PARTS, "check": _MCQ}}
TRY_SCHEMA = {"type": "object", "required": ["try", "summary", "gap"], "properties": {
    "try": _MCQ, "summary": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string"}},
    "gap": TEACH_SCHEMA}}
REPAIRS_SCHEMA = {"type": "object", "required": ["repairs"], "properties": {"repairs": {"type": "array", "maxItems": 6, "items": {
    "type": "object", "required": ["option", "parts", "check"], "properties": {
        "option": {"type": "integer"}, "parts": {**_PARTS, "maxItems": 2}, "check": _MCQ}}}}}
TURN_LABEL = {"teach": "Teach the idea", "try": "A first problem", "repair": "Explain it another way",
              "repairs": "Repairs, written ahead"}
TEACH_PHASES = ("predict", "try", "explain", "check")  # rows of the Learn step (predict: old sessions only)
EXTRACT_SCHEMA = {"type": "object", "required": ["summary", "statements", "links"], "properties": {
    "summary": {"type": "string"},
    "statements": {"type": "array", "items": {"type": "object", "required": ["idea_key", "statement"], "properties": {
        "idea_key": {"type": "string"}, "statement": {"type": "string"}}}},
    "links": {"type": "array", "items": {"type": "object", "required": ["src", "dst", "why"], "properties": {
        "src": {"type": "string"}, "dst": {"type": "string"}, "why": {"type": "string"}}}}}}


# ---------------------------------------------------------------- reading

def get(db: DB, sid: str) -> dict | None:
    s = db.one("SELECT * FROM sessions WHERE id=?", (sid,))
    if s:
        s["ideas"] = loads(s["ideas"], [])
        s["plan"] = loads(s["plan"], [])
        s["source_ids"] = loads(s["source_ids"], [])
    return s


def _items(db: DB, sid: str, key: str | None = None) -> list[dict]:
    rows = db.q("SELECT * FROM session_items WHERE session_id=?" + (" AND idea_key=?" if key else "") + " ORDER BY id",
                (sid, key) if key else (sid,))
    for r in rows:
        r["item"] = loads(r["item"], {})
    return rows


def _idea(s: dict, key: str) -> dict | None:
    return next((i for i in s["ideas"] if i["key"] == key), None)


def _save(db: DB, sid: str, **fields) -> None:
    fields["updated_at"] = now()
    for k in ("ideas", "plan"):
        if k in fields:
            fields[k] = dumps(fields[k])
    db.x(f"UPDATE sessions SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), sid))


def _jobs_for(db: DB, sid: str) -> list[dict]:
    out = []
    for j in db.q("SELECT input FROM jobs WHERE kind LIKE 'session_%' AND status IN ('queued', 'running')"):
        d = loads(j["input"], {})
        if d.get("session_id") == sid:
            out.append(d)
    return out


def _active(db: DB, sid: str, idea: str | None = None, ahead: bool = True, repairs: bool = True) -> bool:
    """A session job is queued or running. ``idea``: only the jobs for that idea (or for no idea); ``ahead=False``:
    not the jobs that make the next question or idea ahead of time; ``repairs=False``: not the jobs that write the
    repairs of a check ahead of time."""
    for d in _jobs_for(db, sid):
        if not ahead and d.get("ahead"):
            continue
        if not repairs and d.get("kind") == "repairs":
            continue
        if idea is not None and d.get("idea") not in (None, idea):
            continue
        if idea is not None and isinstance(d.get("ahead"), dict):
            continue  # a placement question made ahead that is no longer needed (the plan is already made)
        return True
    return False


def _teach_rows(db: DB, sid: str, key: str) -> list[dict]:
    return [i for i in _items(db, sid, key) if i["phase"] in TEACH_PHASES]


def _mcq_ok(q: object) -> bool:
    return (isinstance(q, dict) and isinstance(q.get("options"), list) and len(q["options"]) >= 2
            and isinstance(q.get("answer"), int) and 0 <= q["answer"] < len(q["options"]) and bool(str(q.get("prompt", "")).strip()))


def start(db: DB, jobs: Jobs, topic: str, source_ids: list[str]) -> str:
    topic = " ".join(topic.split())[:500]
    if len(topic) < 3:
        raise ValueError("say what you want to learn")
    known = {r["id"] for r in db.q("SELECT id FROM sources WHERE status='ready'")}
    sid = f"s-{secrets.token_hex(4)}"
    ts = now()
    db.x("""INSERT INTO sessions(id, topic, title, status, ideas, plan, current, source_ids, summary, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
         (sid, topic, topic[:120], "sketching", "[]", "[]", 0, dumps([x for x in source_ids if x in known]), "", ts, ts))
    jobs.enqueue("session_sketch", f"Plan: {topic[:60]}", {"session_id": sid})
    return sid


def answer(db: DB, jobs: Jobs, sid: str, item_id: int, choice: int | None, thinking: str, confidence: float | None) -> None:
    s = get(db, sid)
    row = db.one("SELECT * FROM session_items WHERE id=? AND session_id=?", (item_id, sid))
    if not s or not row:
        raise ValueError("unknown question")
    if row["answered"]:
        return
    item = loads(row["item"])
    correct = choice is not None and choice == item["answer"]
    db.x("UPDATE session_items SET choice=?, answered=1, correct=?, thinking=?, confidence=?, answered_at=? WHERE id=?",
         (choice, int(correct), thinking, confidence, now(), item_id))
    if row["phase"] in ("predict", "try", "check"):  # the tutor reads how you thought (SPEC §35); the probe stays quick
        from . import reasoning
        reasoning.queue_session(db, jobs, sid, item_id, row["idea_key"], thinking)
    if row["phase"] in ("probe", "try", "check"):  # evidence on the idea's node; a prediction is not evidence
        idea = _idea(s, row["idea_key"])
        if idea and idea.get("node"):
            score = 0.5 if progress.guessed(correct, confidence, len(item["options"])) else (1.0 if correct else 0.0)
            db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, score, thinking, confidence)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                 (now(), idea["node"], f"{sid}-{item_id}", "practice", choice, int(correct), score, thinking, confidence))
    if row["phase"] == "probe":
        _probe_next(db, jobs, sid, item_id)
        return
    if row["phase"] == "try" and not correct:
        _open_gap(db, jobs, sid, row["idea_key"], item)
    if row["phase"] == "check" and not correct:
        _open_repair(db, sid, item_id)
    advance(db, jobs, sid)


def _queue_repairs(jobs: Jobs, sid: str, key: str, check_id: int) -> None:
    """While the learner reads a first check, write the repair for each of its wrong options (SPEC §54)."""
    jobs.enqueue("session_turn", TURN_LABEL["repairs"],
                 {"session_id": sid, "kind": "repairs", "idea": key, "check": check_id, "ahead": True})


def _open_repair(db: DB, sid: str, check_id: int) -> bool:
    """A missed first check: show the repair written ahead for the option chosen, with no wait. The API thread and the
    job that writes the repairs both call this; under the lock it opens only once."""
    with db.tx():
        row = db.one("SELECT * FROM session_items WHERE id=? AND session_id=? AND phase='check'", (check_id, sid))
        if not row or not row["answered"] or row["correct"] or row["choice"] is None:
            return False
        rep = (loads(row["item"], {}).get("repairs") or {}).get(str(row["choice"]))
        if not rep or db.one("SELECT 1 FROM session_items WHERE session_id=? AND idea_key=? AND id>?",
                             (sid, row["idea_key"], check_id)):
            return False
        ts = now()
        db.conn.execute("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, answered, created_at)
                           VALUES(?,?,?,?,?,?,1,?)""", (sid, row["idea_key"], "explain", 0, 0,
                                                        dumps({"parts": rep["parts"], "kind": "repair"}), ts))
        db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                        (sid, row["idea_key"], "check", 0, 1, dumps(mcq.shuffle(rep["check"])), ts))
    return True


def _after_repairs(db: DB, jobs: Jobs, sid: str, key: str, check_id: int) -> None:
    """The repairs job ended (or failed): if the learner already missed the check, open its repair, or write one now
    (for "I don't know", or when no repair fits)."""
    if _open_repair(db, sid, check_id):
        return
    row = db.one("SELECT * FROM session_items WHERE id=? AND session_id=?", (check_id, sid))
    if not row or not row["answered"] or row["correct"]:
        return
    if db.one("SELECT 1 FROM session_items WHERE session_id=? AND idea_key=? AND id>?", (sid, key, check_id)):
        return
    if any(d.get("kind") == "repair" and d.get("idea") == key for d in _jobs_for(db, sid)):
        return
    jobs.enqueue("session_turn", TURN_LABEL["repair"], {"session_id": sid, "kind": "repair", "idea": key})


def _open_gap(db: DB, jobs: Jobs, sid: str, key: str, item: dict) -> None:
    """A missed first problem: show the teaching of the part it tests (written with the problem, so no wait)."""
    gap = item.get("gap") or {}
    if not gap.get("parts") or not _mcq_ok(gap.get("check")):
        return  # advance() asks for the teaching instead
    ts = now()
    with db.tx():
        db.conn.execute("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, answered, created_at)
                           VALUES(?,?,?,?,?,?,1,?)""", (sid, key, "explain", 0, 0, dumps({"parts": gap["parts"], "kind": "gap"}), ts))
        cid = db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                              (sid, key, "check", 0, 1, dumps(mcq.shuffle(gap["check"])), ts)).lastrowid
    _queue_repairs(jobs, sid, key, cid)


def choose(db: DB, jobs: Jobs, sid: str, key: str) -> None:
    """Learn this open idea next (every idea it needs is done). Only between ideas, not in the middle of one."""
    s = get(db, sid)
    if not s or s["status"] != "teaching":
        raise ValueError("the session is not at the Learn step")
    if key not in s["plan"][s["current"]:]:
        raise ValueError("that idea is not in what is left of the plan")
    if key not in open_ideas(s):
        raise ValueError("learn the ideas it needs first")
    now_key = s["plan"][s["current"]]
    if key == now_key:
        return
    if any(r["answered"] for r in _teach_rows(db, sid, now_key) if r["phase"] != "explain"):
        raise ValueError("finish the idea you started first")
    plan = [k for k in s["plan"] if k != key]
    plan.insert(s["current"], key)
    _save(db, sid, plan=plan)
    advance(db, jobs, sid)


def open_ideas(s: dict) -> list[str]:
    """The ideas left in the plan whose needed ideas are all done (or not in the plan: known)."""
    done = set(s["plan"][:s["current"]])
    return [k for k in s["plan"][s["current"]:]
            if all(p in done or p not in s["plan"] for p in (_idea(s, k) or {}).get("prereqs", []))]


def set_known(db: DB, sid: str, key: str, known: bool) -> None:
    s = get(db, sid)
    if not s or s["status"] != "planning":
        raise ValueError("the plan can change only before teaching starts")
    for i in s["ideas"]:
        if i["key"] == key and not i.get("target"):
            i["skip"] = known
            # an idea you already know can be learned again: "again" puts it back into the plan (SPEC §30)
            i["again"] = (not known) and i.get("level") == "known"
    _save(db, sid, ideas=s["ideas"], plan=_plan(s["ideas"]))


def learn_all_again(db: DB, sid: str) -> None:
    """Put every idea of the session into the plan, also the ones you already know (to review a part). A finished session
    in which nothing was taught (every idea was already known) opens again at the plan."""
    s = get(db, sid)
    taught = db.one("SELECT 1 FROM session_items WHERE session_id=? AND phase IN ('predict', 'try', 'explain', 'check')", (sid,))
    if not s or not (s["status"] == "planning" or (s["status"] == "done" and not taught)):
        raise ValueError("the plan can change only before teaching starts")
    for i in s["ideas"]:
        i["skip"] = False
        i["again"] = i.get("level") == "known"
    _save(db, sid, ideas=s["ideas"], plan=_plan(s["ideas"]), status="planning", current=0, summary="")
    if s.get("book_part"):
        db.x("UPDATE book_parts SET status='studying' WHERE id=?", (s["book_part"],))


def start_teaching(db: DB, jobs: Jobs, sid: str) -> None:
    s = get(db, sid)
    if not s or s["status"] != "planning":
        raise ValueError("nothing to start")
    if not _plan(s["ideas"]):
        raise ValueError("there is nothing to learn in the plan; tick an idea, or choose \"Learn it again\"")
    _save(db, sid, status="teaching", plan=_plan(s["ideas"]), current=0)
    advance(db, jobs, sid)


def assess_now(db: DB, jobs: Jobs, sid: str) -> None:
    """Stop probing: drop the open question and write the result from the answers so far."""
    db.x("DELETE FROM session_items WHERE session_id=? AND phase IN ('probe_ahead') OR (session_id=? AND phase='probe' AND answered=0)",
         (sid, sid))
    s = get(db, sid)
    if not s or s["status"] != "probing" or _active(db, sid, ahead=False):
        return
    if db.one("SELECT 1 FROM session_items WHERE session_id=? AND phase='probe' AND answered=1", (sid,)):
        jobs.enqueue("session_probe", "What you know", {"session_id": sid, "assess": True})
    else:
        _to_planning(db, s)


def retry(db: DB, jobs: Jobs, sid: str) -> None:
    """Run the step of the current phase again (after a failed job)."""
    s = get(db, sid)
    if not s or _active(db, sid):
        return
    if s["status"] == "sketching":
        jobs.enqueue("session_sketch", f"Plan: {s['topic'][:60]}", {"session_id": sid})
    elif s["status"] == "probing":
        jobs.enqueue("session_probe", "Find what you know", {"session_id": sid})
    elif s["status"] == "extracting":
        jobs.enqueue("session_extract", "Add what you learned to your graph", {"session_id": sid})
    else:
        advance(db, jobs, sid)


def delete(db: DB, sid: str) -> None:
    """Remove a session. Nodes it made stay only if they have evidence or are used elsewhere."""
    made = [r["node_id"] for r in db.q("SELECT node_id FROM session_nodes WHERE session_id=? AND created=1", (sid,))]
    with db.tx():
        db.conn.execute("DELETE FROM evidence WHERE item_id LIKE ?", (f"{sid}-%",))
        db.conn.execute("DELETE FROM session_items WHERE session_id=?", (sid,))
        db.conn.execute("DELETE FROM session_nodes WHERE session_id=?", (sid,))
        db.conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        for nid in made:
            used = (db.conn.execute("SELECT 1 FROM concept_nodes WHERE node_id=?", (nid,)).fetchone()
                    or db.conn.execute("SELECT 1 FROM session_nodes WHERE node_id=?", (nid,)).fetchone()
                    or db.conn.execute("SELECT 1 FROM evidence WHERE concept_id=?", (nid,)).fetchone())
            if not used:
                db.conn.execute("DELETE FROM nodes WHERE id=? AND origin='session'", (nid,))
                db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (nid,))
                db.conn.execute("DELETE FROM links WHERE src=? OR dst=?", (nid, nid))


# ---------------------------------------------------------------- flow

def _plan(ideas: list[dict]) -> list[str]:
    """Ideas to teach, prerequisites first (topological order), the target last."""
    todo = {i["key"]: i for i in ideas
            if i.get("target") or i.get("again") or not (i.get("skip") or i.get("level") == "known")}
    order: list[str] = []
    seen: set[str] = set()

    def visit(k: str, path: tuple = ()) -> None:
        if k in seen or k not in todo or k in path:
            return
        for p in todo[k].get("prereqs", []):
            visit(p, path + (k,))
        seen.add(k)
        order.append(k)

    for i in ideas:
        if not i.get("target"):
            visit(i["key"])
    for i in ideas:
        if i.get("target"):
            visit(i["key"])
    return order


def _to_planning(db: DB, s: dict) -> None:
    _save(db, s["id"], status="planning", ideas=s["ideas"], plan=_plan(s["ideas"]))


def _first_kind(idea: dict) -> str:
    """Partly known (or known and learned again): one problem first. Anything else is taught first."""
    return "try" if idea.get("level") == "partial" or idea.get("again") else "teach"


def advance(db: DB, jobs: Jobs, sid: str) -> None:
    """Teaching: ask for the next turn of the current idea, or move on, or extract at the end."""
    s = get(db, sid)
    if not s or s["status"] != "teaching":
        return
    if s["current"] >= len(s["plan"]):
        if not _active(db, sid):
            _save(db, sid, status="extracting")
            jobs.enqueue("session_extract", "Add what you learned to your graph", {"session_id": sid})
        return
    key = s["plan"][s["current"]]
    if _active(db, sid, idea=key, repairs=False):
        return
    items = _teach_rows(db, sid, key)
    if any(not i["answered"] for i in items):
        _prefetch(db, jobs, s, key)  # the learner works on this idea: write the next one meanwhile
        return
    tries = [i for i in items if i["phase"] == "try"]
    checks = [i for i in items if i["phase"] == "check"]
    if (tries and tries[-1]["correct"] and not checks) or (checks and (checks[-1]["correct"] or len(checks) >= 2)):
        _save(db, sid, current=s["current"] + 1)  # done (after a second miss the session moves on, as before)
        advance(db, jobs, sid)
        return
    if checks and any(d.get("kind") == "repairs" and d.get("check") == checks[-1]["id"] for d in _jobs_for(db, sid)):
        return  # its repair is being written ahead: it opens when it is ready
    kind = "repair" if checks else ("teach" if items else _first_kind(_idea(s, key) or {}))
    jobs.enqueue("session_turn", TURN_LABEL[kind], {"session_id": sid, "kind": kind, "idea": key})


def _prefetch(db: DB, jobs: Jobs, s: dict, key: str) -> None:
    """Write the idea after ``key`` ahead of time (the plan is in reasoning order, so it is open once ``key`` is done)."""
    i = s["plan"].index(key) if key in s["plan"] else -1
    if i < 0 or i + 1 >= len(s["plan"]):
        return
    nxt = s["plan"][i + 1]
    if _teach_rows(db, s["id"], nxt) or _active(db, s["id"], idea=nxt):
        return
    jobs.enqueue("session_turn", "Next idea, written ahead",
                 {"session_id": s["id"], "kind": _first_kind(_idea(s, nxt) or {}), "idea": nxt, "ahead": True})
def _learner(db: DB) -> dict:
    pb = state.playbook(db)
    return {"playbook": state.playbook_text(pb), "guidelines": guidelines.text(db), "reasoning": state.reasoning_log(db)}


def _graph_context(db: DB, topic: str) -> tuple[list[dict], str]:
    """Nodes that may matter for the topic, with the learner's state, and the text for the prompt."""
    cands = graph.candidates(db, topic, k=30)
    st = graph.states(db)
    learned = [n for n in db.q("SELECT id, title, statement FROM nodes")
               if st.get(n["id"]) and st[n["id"]].state == "learned"]
    ids = {c["id"] for c in cands}
    rows = cands + [n for n in learned if n["id"] not in ids][:60]
    text = "\n".join(f'- {n["id"]}: {n["title"]} - {n["statement"][:160]} [state: {st[n["id"]].state if n["id"] in st else "new"}]'
                     for n in rows) or "(the graph is empty)"
    return rows, text


def _excerpts(db: DB, s: dict, topic: str, k: int = 6) -> str:
    if not s["source_ids"]:
        return "(none)"
    pages = None
    if s.get("book_part"):  # a book part: its own pages (SPEC §28)
        part = db.one("SELECT page_from, page_to FROM book_parts WHERE id=?", (s["book_part"],))
        if part:
            pages = (part["page_from"], part["page_to"])
    return sources.excerpts_text(sources.excerpts(db, None, topic, k=k, ids=s["source_ids"], pages=pages))


def start_from_ideas(db: DB, jobs: Jobs, topic: str, title: str, ideas: list[dict], source_ids: list[str],
                     book_part: int | None = None) -> str:
    """A session whose ideas are already known (a book part, SPEC §28): no sketch step. ``ideas`` carry their node;
    ideas the graph holds as learned are marked known, so the probe and the plan skip them."""
    st = graph.states(db)
    sid = f"s-{secrets.token_hex(4)}"
    ts = now()
    out = []
    for i in ideas:
        ns = st.get(i["node"])
        level = "known" if ns and ns.state == "learned" else None
        out.append({**i, "target": False, "level": level, "fromGraph": bool(i.get("fromGraph"))})
    unknown = [i for i in out if i["level"] != "known"]
    with db.tx():
        db.conn.execute("""INSERT INTO sessions(id, topic, title, status, ideas, plan, current, source_ids, summary,
                           created_at, updated_at, book_part) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (sid, topic[:500], title[:120], "probing" if unknown else "planning", dumps(out),
                         dumps(_plan(out)), 0, dumps(source_ids), "", ts, ts, book_part))
        for i in out:
            db.conn.execute("INSERT OR IGNORE INTO session_nodes(session_id, node_id, created) VALUES(?,?,0)", (sid, i["node"]))
    db.set_meta("last_session", sid)
    if unknown:
        jobs.enqueue("session_probe", "Find what you know", {"session_id": sid})
    return sid


def run_sketch(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    s = get(db, d["session_id"])
    nodes, gtext = _graph_context(db, s["topic"])
    lr = _learner(db)
    out = jobs.call(jid, "Study plan", Call(
        prompt=prompt("session_sketch", topic=s["topic"], graph=gtext, playbook=lr["playbook"],
                      sources=_excerpts(db, s, s["topic"])),
        schema=SKETCH_SCHEMA, model="opus", timeout=600))
    valid = {n["id"] for n in nodes}
    st = graph.states(db)
    keys = [i["key"] for i in out["ideas"]]
    if out["target_key"] not in keys:
        raise ValueError("the plan has no target idea")
    ideas, ts = [], now()
    with db.tx():
        for i in out["ideas"]:
            node = i.get("same_as") if i.get("same_as") in valid else None
            created = 0
            if not node:
                node = f"n-{secrets.token_hex(5)}"
                created = 1
                db.conn.execute("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                                (node, i["title"][:200], i["statement"][:600], "idea", ts, "session"))
                db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (node, f'{i["title"]} {i["statement"]}'))
            db.conn.execute("INSERT OR IGNORE INTO session_nodes(session_id, node_id, created) VALUES(?,?,?)", (s["id"], node, created))
            ns = st.get(node)
            level = "known" if ns and ns.state == "learned" else None
            ideas.append({"key": i["key"], "title": i["title"][:200], "statement": i["statement"][:600], "node": node,
                          "prereqs": [p for p in i["prereq_keys"] if p in keys and p != i["key"]],
                          "target": i["key"] == out["target_key"], "level": level, "fromGraph": not created})
        for i in ideas:  # reasoning links between the ideas
            for p in i["prereqs"]:
                src = next(x["node"] for x in ideas if x["key"] == p)
                if src != i["node"]:
                    db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)",
                                    (src, i["node"], "", "session"))
    unknown = [i for i in ideas if i["level"] != "known"]
    _save(db, s["id"], title=out["title"][:120] or s["title"], ideas=ideas,
          status="probing" if unknown else "planning", plan=_plan(ideas))
    if unknown:
        jobs.enqueue("session_probe", "Find what you know", {"session_id": s["id"]})
    jobs.progress(jid, f"{len(ideas)} ideas, {len(ideas) - len(unknown)} already known from your graph")
    return {"ideas": len(ideas)}


def run_probe(jobs: Jobs, jid: int, d: dict) -> dict:
    """One probe question (or the result). With ``ahead = {item, correct}``: the question that follows if the learner
    answers the open question ``item`` right (or misses it), made while they think; it waits as a ``probe_ahead`` row."""
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    s = get(db, d["session_id"])
    if s["status"] != "probing":
        return {"skipped": True}
    ahead = d.get("ahead") if isinstance(d.get("ahead"), dict) else None
    items = [i for i in _items(db, s["id"]) if i["phase"] == "probe"]
    if ahead:
        parent = next((i for i in items if i["id"] == ahead.get("item")), None)
        branch = bool(ahead.get("correct"))
        if not parent or (parent["answered"] and bool(parent["correct"]) != branch):
            return {"skipped": True}
        if not parent["answered"]:  # as if answered: right, or missed (a wrong pick or "I don't know")
            parent = {**parent, "answered": 1, "correct": int(branch), "choice": parent["item"]["answer"] if branch else None,
                      "thinking": "", "confidence": None}
            items = [parent if i["id"] == parent["id"] else i for i in items]
    if any(not i["answered"] for i in items):
        return {"skipped": True}  # a question is still open
    asked = len(items)
    must_end = bool(d.get("assess")) or asked >= PROBE_MAX
    ideas_text = "\n".join(f'- {i["key"]}: {i["title"]} - {i["statement"]}'
                           f'{" (needs: " + ", ".join(i["prereqs"]) + ")" if i["prereqs"] else ""}'
                           f'{" [target]" if i.get("target") else ""}'
                           f'{" [known from the graph]" if i["level"] == "known" else ""}' for i in s["ideas"])
    out = jobs.call(jid, "Study tutor", Call(
        prompt=prompt("session_probe", topic=s["topic"], ideas=ideas_text, answers=_answers_text(s, items),
                      asked=asked, max_questions=PROBE_MAX,
                      must_end="yes: write the result now, no more questions" if must_end else "no"),
        schema=PROBE_SCHEMA, model="sonnet", timeout=300))
    keys = {i["key"] for i in s["ideas"]}
    q = out.get("question") or {}
    usable = q.get("idea_key") in keys and _mcq_ok(q)
    finished = bool(out.get("done")) or must_end
    if not finished and not usable:
        raise ValueError("the probe returned no usable question")
    if ahead:
        if get(db, s["id"])["status"] != "probing":
            return {"skipped": True}
        it: dict = {"parent": ahead.get("item"), "branch": bool(ahead.get("correct"))}
        if finished:
            it |= {"done": True, "result": out.get("result") or {}}
        else:
            it |= mcq.shuffle({k: q[k] for k in ("prompt", "options", "answer", "explanation")})
        db.x("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
             (s["id"], "" if finished else q["idea_key"], "probe_ahead", asked + 1, 0, dumps(it), now()))
        _probe_next(db, jobs, s["id"], ahead.get("item"))  # the learner may have answered already
        return {"ahead": True}
    if finished:
        apply_result(db, s, out.get("result") or {})
        jobs.progress(jid, f"result ready after {asked} question(s)")
        return {"planned": True, "asked": asked}
    item = mcq.shuffle({k: q[k] for k in ("prompt", "options", "answer", "explanation")})
    rid = db.x("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
               (s["id"], q["idea_key"], "probe", asked + 1, 0, dumps(item), now()))
    _make_ahead(jobs, s["id"], rid)
    return {"question": asked + 1}


def _make_ahead(jobs: Jobs, sid: str, item_id: int) -> None:
    """While the learner answers ``item_id``, make the next question for a right answer and for a miss."""
    for branch in (True, False):
        jobs.enqueue("session_probe", "Next question, made ahead", {"session_id": sid, "ahead": {"item": item_id, "correct": branch}})


def _probe_next(db: DB, jobs: Jobs, sid: str, parent_id: int) -> None:
    """After a probe answer: use the question made ahead for its outcome, wait for it, or ask for one now. Both the API
    thread and a finishing job call this; the UPDATE/DELETE ... WHERE phase='probe_ahead' claims a row only once."""
    row = db.one("SELECT * FROM session_items WHERE id=? AND session_id=? AND phase='probe'", (parent_id, sid))
    s = get(db, sid)
    if not row or not row["answered"] or not s or s["status"] != "probing":
        return
    branch = bool(row["correct"])
    for r in _items(db, sid):
        it = r["item"]
        if r["phase"] != "probe_ahead" or it.get("parent") != parent_id or bool(it.get("branch")) != branch:
            continue
        if it.get("done"):  # enough: write the result now, from the real answer with its thinking and confidence
            if db.xn("DELETE FROM session_items WHERE id=? AND phase='probe_ahead'", (r["id"],)):
                db.x("DELETE FROM session_items WHERE session_id=? AND phase='probe_ahead'", (sid,))
                jobs.enqueue("session_probe", "What you know", {"session_id": sid, "assess": True})
            return
        q = {k: it[k] for k in ("prompt", "options", "answer", "explanation")}
        if db.xn("UPDATE session_items SET phase='probe', item=?, created_at=? WHERE id=? AND phase='probe_ahead'",
                 (dumps(q), now(), r["id"])):
            db.x("DELETE FROM session_items WHERE session_id=? AND phase='probe_ahead'", (sid,))
            _make_ahead(jobs, sid, r["id"])
        return
    if any(isinstance(d.get("ahead"), dict) and d["ahead"].get("item") == parent_id and bool(d["ahead"].get("correct")) == branch
           for d in _jobs_for(db, sid)):
        return  # it is being made: it is used when it is ready
    if not db.one("SELECT 1 FROM session_items WHERE session_id=? AND phase='probe' AND answered=0", (sid,)) \
            and not _active(db, sid, ahead=False):
        jobs.enqueue("session_probe", "Find what you know", {"session_id": sid})


def apply_result(db: DB, s: dict, result: dict) -> None:
    """Store the probe's result per idea and move to planning. An idea without evidence keeps no level (it is taught);
    "untested" is kept apart from "tested and missed" so the teacher does not take a guess for a finding."""
    by_key = {r.get("idea_key"): r for r in result.get("ideas") or [] if r.get("level") in PROBE_LEVELS}
    for i in s["ideas"]:
        i.pop("probe", None)  # a new result replaces an earlier one completely
        if not (i.get("fromGraph") and i["level"] == "known"):
            i["level"] = None
        r = by_key.get(i["key"])
        if not r:
            continue
        i["probe"] = {"level": r["level"], "reasonsFrom": (r.get("reasons_from") or "")[:400],
                      "runsOut": (r.get("runs_out") or "")[:400],
                      "misconceptions": [m[:300] for m in r.get("misconceptions") or [] if m.strip()][:5]}
        if i["level"] != "known" and r["level"] in LEVELS:
            i["level"] = r["level"]
    _save(db, s["id"], probe_start=(result.get("start") or "")[:1200])
    _to_planning(db, get(db, s["id"]) | {"ideas": s["ideas"]})


def probe_note(idea: dict) -> str:
    """What the probe found about one idea, for the teaching prompt."""
    p = idea.get("probe")
    if not p:
        return "(not probed: no evidence either way)"
    if p["level"] == "untested":
        return "not tested in the probe"
    parts = [f'level: {p["level"]}']
    if p.get("reasonsFrom"):
        parts.append(f'reasons from: {p["reasonsFrom"]}')
    if p.get("runsOut"):
        parts.append(f'reasoning runs out at: {p["runsOut"]}')
    if p.get("misconceptions"):
        parts.append("misconceptions: " + "; ".join(p["misconceptions"]))
    return " | ".join(parts)


def _answers_text(s: dict, items: list[dict]) -> str:
    lines = []
    for r in items:
        if not r["answered"]:
            continue
        it = r["item"]
        chose = "I don't know" if r["choice"] is None else it["options"][r["choice"]]
        res = "right" if r["correct"] else ("did not know" if r["choice"] is None else "wrong")
        line = f'- [{r["phase"]}, idea {r["idea_key"]}] {it["prompt"]} | chose: {chose} ({res})'
        if r["confidence"] is not None:
            line += (f' | confidence {round(r["confidence"] * 100)}%'
                     f' (chance: {round(mcq.chance(len(it["options"])) * 100)}%)')
        if r["thinking"]:
            line += f' | thinking: "{r["thinking"][:600]}"'
        lines.append(line)
    return "\n".join(lines) or "(none yet)"


def run_turn(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    s = get(db, d["session_id"])
    key, kind = d["idea"], d["kind"]
    idea = _idea(s, key)
    if s["status"] != "teaching" or not idea or key not in s["plan"]:
        return {"skipped": True}
    rows = _teach_rows(db, s["id"], key)
    check = None
    if kind == "repairs":
        check = next((r for r in rows if r["id"] == d.get("check") and r["phase"] == "check"), None)
        if not check or check["item"].get("repairs") or (check["answered"] and (check["correct"] or check["choice"] is None)):
            if check:
                _after_repairs(db, jobs, s["id"], key, check["id"])
            return {"skipped": True}
        rows = [r for r in rows if r["id"] < check["id"]]
    elif kind != "repair" and any(r["phase"] in ("try", "check") for r in rows):
        return {"skipped": True}  # already written (ahead of time)
    done = s["plan"][:s["current"]]
    now_key = s["plan"][s["current"]] if s["current"] < len(s["plan"]) else None
    plan_text = "\n".join(f'{n + 1}. {_idea(s, k)["title"]}{" (done)" if k in done else " (now)" if k == key else ""}'
                          for n, k in enumerate(s["plan"]))
    known = ", ".join(i["title"] for i in s["ideas"] if i["key"] not in s["plan"]) or "(none)"
    lr = _learner(db)
    lines = []
    for r in rows:
        if r["phase"] == "explain":
            lines.append(f'- teaching given: {" / ".join(r["item"].get("parts") or [r["item"].get("body", "")])[:1500]}')
    current = "\n".join(lines + [_answers_text(s, [r for r in rows if r["phase"] != "explain"])])
    if check:
        c = check["item"]
        current += (f'\n- the check they are answering now: {c["prompt"]}\n'
                    + "\n".join(f'  {n}) {o}{"  (right)" if n == c["answer"] else ""}' for n, o in enumerate(c["options"])))
    earlier = _answers_text(s, [r for r in _items(db, s["id"]) if r["phase"] in ("try", "check") and r["idea_key"] in done][-8:])
    if key != now_key:
        earlier += "\n(This idea is written ahead: the learner is still on the idea before it.)"
    linkable = _linkable(db, s, idea)
    call = Call(
        prompt=prompt("session_turn", kind=kind, topic=s["topic"], plan=plan_text, known=known,
                      links="\n".join(f"- {i}: {t}" for i, t in linkable.items()) or "(none)",
                      idea=f'{idea["title"]}: {idea["statement"]}', current=current, earlier=earlier,
                      probe=probe_note(idea), start=s.get("probe_start") or "(none)",
                      playbook=lr["playbook"], guidelines=lr["guidelines"],
                      sources=_excerpts(db, s, f'{idea["title"]} {idea["statement"]}', k=4)),
        schema={"try": TRY_SCHEMA, "repairs": REPAIRS_SCHEMA}.get(kind, TEACH_SCHEMA), model="sonnet", timeout=300)
    if check:
        try:
            out = jobs.call(jid, "Study tutor", call)
        except Exception:
            _after_repairs(db, jobs, s["id"], key, check["id"])  # missed meanwhile: write the repair now
            raise
        return _store_repairs(db, jobs, s, key, check, out, set(linkable))
    out = jobs.call(jid, "Study tutor", call)

    def parts_of(x: dict) -> list[str]:
        return [idea_links(str(p).strip(), set(linkable)) for p in (x.get("parts") or []) if str(p).strip()][:4]

    ts = now()
    with db.tx():
        if kind == "try":
            t = out.get("try")
            if not _mcq_ok(t):
                raise ValueError("the first problem has no valid answer")
            item = mcq.shuffle({k: t[k] for k in ("prompt", "options", "answer", "explanation")})
            item["summary"] = [str(x).strip()[:400] for x in out.get("summary") or [] if str(x).strip()][:4]
            gap = out.get("gap") or {}
            if parts_of(gap) and _mcq_ok(gap.get("check")):
                item["gap"] = {"parts": parts_of(gap), "check": {k: gap["check"][k] for k in ("prompt", "options", "answer", "explanation")}}
            db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                            (s["id"], key, "try", 0, 0, dumps(item), ts))
        else:
            c, parts = out.get("check"), parts_of(out)
            if not _mcq_ok(c) or not parts:
                raise ValueError("the teaching or its check is empty")
            db.conn.execute("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, answered, created_at)
                               VALUES(?,?,?,?,?,?,1,?)""", (s["id"], key, "explain", 0, 0, dumps({"parts": parts, "kind": kind}), ts))
            cid = db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                                  (s["id"], key, "check", 0, 1, dumps(mcq.shuffle({k: c[k] for k in ("prompt", "options", "answer", "explanation")})), ts)).lastrowid
    if kind == "teach":
        _queue_repairs(jobs, s["id"], key, cid)
    s = get(db, s["id"])  # read again: the learner may have reached this idea while it was written ahead
    if kind != "repair" and s["status"] == "teaching" and s["current"] < len(s["plan"]) and s["plan"][s["current"]] == key:
        _prefetch(db, jobs, s, key)
    return {"kind": kind}


def _store_repairs(db: DB, jobs: Jobs, s: dict, key: str, check: dict, out: dict, linkable: set[str]) -> dict:
    """Keep one repair per wrong option on the check row (by option number); open it if the learner missed meanwhile."""
    c = check["item"]
    reps = {}
    for r in out.get("repairs") or []:
        n = r.get("option")
        parts = [idea_links(str(p).strip(), linkable) for p in (r.get("parts") or []) if str(p).strip()][:2]
        if not isinstance(n, int) or not 0 <= n < len(c["options"]) or n == c["answer"] or not parts or not _mcq_ok(r.get("check")):
            continue
        reps[str(n)] = {"parts": parts, "check": {k: r["check"][k] for k in ("prompt", "options", "answer", "explanation")}}
    with db.tx():
        row = db.one("SELECT item FROM session_items WHERE id=?", (check["id"],))
        if row:
            item = loads(row["item"], {})
            item["repairs"] = reps
            db.conn.execute("UPDATE session_items SET item=? WHERE id=?", (dumps(item), check["id"]))
    _after_repairs(db, jobs, s["id"], key, check["id"])
    return {"kind": "repairs", "options": sorted(reps)}


def run_extract(jobs: Jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    s = get(db, d["session_id"])
    nodes, gtext = _graph_context(db, s["topic"])
    items = _items(db, s["id"])
    ideas_text = "\n".join(f'- {i["key"]} (node {i["node"]}): {i["title"]} - {i["statement"]}'
                           f'{" [taught]" if i["key"] in s["plan"] else " [already known]"}' for i in s["ideas"])
    out = jobs.call(jid, "Study plan", Call(
        prompt=prompt("session_extract", topic=s["topic"], ideas=ideas_text, graph=gtext,
                      answers=_answers_text(s, [r for r in items if r["phase"] in ("predict", "try", "check", "probe")])),
        schema=EXTRACT_SCHEMA, model="opus", timeout=600))
    by_key = {i["key"]: i for i in s["ideas"]}
    valid_nodes = {n["id"] for n in nodes} | {i["node"] for i in s["ideas"]}
    made = {r["node_id"] for r in db.q("SELECT node_id FROM session_nodes WHERE session_id=? AND created=1", (s["id"],))}

    def node_of(ref: str) -> str | None:
        return by_key[ref]["node"] if ref in by_key else (ref if ref in valid_nodes else None)

    added = 0
    with db.tx():
        for st in out["statements"]:
            i = by_key.get(st["idea_key"])
            if i and i["node"] in made and st["statement"].strip():
                db.conn.execute("UPDATE nodes SET statement=? WHERE id=?", (st["statement"].strip()[:600], i["node"]))
                db.conn.execute("DELETE FROM node_fts WHERE node_id=?", (i["node"],))
                db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (i["node"], f'{i["title"]} {st["statement"]}'))
        for link in out["links"]:
            src, dst = node_of(link["src"]), node_of(link["dst"])
            if src and dst and src != dst:
                db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)",
                                (src, dst, link["why"][:300], "session"))
                added += db.conn.execute("SELECT changes()").fetchone()[0]
    _save(db, s["id"], status="done", summary=out["summary"][:1500])
    if s.get("book_part"):
        from . import bookstudy
        bookstudy.on_session_done(db, s["id"])
    jobs.progress(jid, f"{added} new link(s) in your graph")
    return {"links": added}


# ---------------------------------------------------------------- view

def listing(db: DB) -> list[dict]:
    return [{"id": r["id"], "title": r["title"], "topic": r["topic"], "status": r["status"], "createdAt": r["created_at"]}
            for r in db.q("SELECT * FROM sessions ORDER BY created_at DESC")]


def view(db: DB, sid: str) -> dict | None:
    s = get(db, sid)
    if not s:
        return None
    items = _items(db, sid)
    open_probe = any(r["phase"] == "probe" and not r["answered"] for r in items)
    now_key = s["plan"][s["current"]] if s["status"] == "teaching" and s["current"] < len(s["plan"]) else None
    if s["status"] == "probing":  # busy only when no question is open (the next one is made ahead meanwhile)
        running = _active(db, sid, ahead=False) or (not open_probe and _active(db, sid))
    elif now_key:  # the repairs written ahead count only while the learner waits for one
        waiting = not any(not r["answered"] for r in items if r["idea_key"] == now_key and r["phase"] in TEACH_PHASES)
        running = _active(db, sid, idea=now_key, repairs=waiting)
    else:
        running = _active(db, sid, ahead=False)
    failed = None
    if not running:
        for j in db.q("SELECT status, error, input FROM jobs WHERE kind LIKE 'session_%' AND input LIKE ? ORDER BY id DESC LIMIT 6",
                      (f'%"{sid}"%',)):
            if loads(j["input"], {}).get("ahead"):
                continue  # a job made ahead that failed: the step is asked for again when it is needed
            failed = j["error"] if j["status"] == "failed" else None
            break
        stalled = ((s["status"] == "probing" and not open_probe)
                   or (now_key and not any(not r["answered"] for r in items if r["idea_key"] == now_key and r["phase"] in TEACH_PHASES)))
        if stalled and not failed:
            failed = "the next step did not come"
    from . import reasoning
    reviews = reasoning.by_session_items(db, [r["id"] for r in items if r["answered"]])
    pub = []
    for r in items:
        it = dict(r["item"])
        if r["phase"] == "probe_ahead":
            continue
        if r["phase"] == "explain":
            pub.append({"id": r["id"], "idea": r["idea_key"], "phase": "explain", "parts": it.get("parts") or [it.get("body", "")],
                        "kind": it.get("kind") or "teach", "repair": it.get("kind") == "repair"})
            continue
        q = {"id": r["id"], "idea": r["idea_key"], "phase": r["phase"], "round": r["round"], "prompt": it["prompt"],
             "options": it["options"], "answered": bool(r["answered"])}
        if r["answered"]:
            q.update(choice=r["choice"], correct=bool(r["correct"]), answer=it["answer"], explanation=it["explanation"],
                     thinking=r["thinking"], confidence=r["confidence"], review=reviews.get(r["id"]))
            if r["phase"] == "try" and r["correct"]:
                q["summary"] = it.get("summary") or []
        pub.append(q)
    st = graph.states(db)
    ideas = [{**{k: i.get(k) for k in ("key", "title", "statement", "node", "prereqs", "target", "level", "skip", "fromGraph",
                                       "probe", "again")},
              "nodeState": st[i["node"]].state if i.get("node") in st else "pending"} for i in s["ideas"]]
    return {"id": s["id"], "topic": s["topic"], "title": s["title"], "status": s["status"], "busy": running, "error": failed,
            "ideas": ideas, "plan": s["plan"], "current": s["current"], "items": pub, "summary": s["summary"],
            "probeStart": s.get("probe_start") or "", "probeMax": PROBE_MAX, "book": _book_of(db, s),
            "open": open_ideas(s) if s["status"] == "teaching" else [],
            "canChoose": bool(now_key) and not any(r["answered"] for r in items if r["idea_key"] == now_key and r["phase"] in ("predict", "try", "check")),
            "sources": s["source_ids"], "createdAt": s["created_at"]}


def _book_of(db: DB, s: dict) -> dict | None:
    """The book part a session studies, for the page (SPEC §28)."""
    if not s.get("book_part"):
        return None
    r = db.one("""SELECT p.id, p.title, p.page_from, p.page_to, p.practice_id, b.id AS book_id, b.title AS book_title
                  FROM book_parts p JOIN books b ON b.id = p.book_id WHERE p.id=?""", (s["book_part"],))
    if not r:
        return None
    return {"partId": r["id"], "part": r["title"], "pages": [r["page_from"], r["page_to"]], "id": r["book_id"],
            "title": r["book_title"], "practiceId": r["practice_id"]}


_IDEA_LINK = re.compile(r"\[([^\]\n]+)\]\(#idea/([\w-]+)\)")


def idea_links(text: str, allowed: set[str]) -> str:
    """Keep ``[text](#idea/<id>)`` links only for ideas the prompt offered; any other becomes plain text (SPEC §28)."""
    return _IDEA_LINK.sub(lambda m: m.group(0) if m.group(2) in allowed else m.group(1), text)


def _linkable(db: DB, s: dict, idea: dict) -> dict[str, str]:
    """Graph ideas a teaching turn may link (id -> title): this session's ideas, the ideas they build on or lead to,
    and graph ideas whose words match the current idea. Hovering such a link shows where the learner met the idea."""
    ids = [i["node"] for i in s["ideas"] if i.get("node")]
    near: list[str] = []
    for lk in graph.links(db):
        if lk["dst"] in ids:
            near.append(lk["src"])
        if lk["src"] in ids:
            near.append(lk["dst"])
    found = [c["id"] for c in graph.candidates(db, f'{idea["title"]} {idea["statement"]}', k=10)]
    want = list(dict.fromkeys(ids + near + found))[:40]
    if not want:
        return {}
    rows = db.q(f"SELECT id, title FROM nodes WHERE id IN ({','.join('?' * len(want))})", want)
    title = {r["id"]: r["title"] for r in rows}
    return {i: title[i] for i in want if i in title}
