"""Study sessions: "teach me X", with or without a goal (SPEC §22). Step 4 of the knowledge-graph rework.

Phases (``sessions.status``):
1. ``sketching``: an agent turns the topic into 4-12 ideas with their dependencies, matched to the learner's graph
   (``same_as``). Each idea becomes a node at once (existing node or a new one, origin "session"), so every answer
   below is evidence on a node. Ideas the graph already holds as learned are marked known.
2. ``probing``: short rounds of quick questions on the ideas that are not known yet (like the probe, SPEC §20).
3. ``planning``: the ideas to teach, prerequisites first and the target last. The learner can mark ideas as known.
4. ``teaching``: one idea at a time: **predict** (a question before any explanation) → **explain** (short, fitted to
   the prediction and the learner's thinking) + **check**. A wrong check gets one **repair** step.
5. ``extracting``: an agent writes what the learner now holds as short statements and adds reasoning links between
   the ideas and existing nodes. Then ``done``.

Evidence: probe and check answers are recorded on the idea's node (``evidence.concept_id`` = node id), with the same
guess rule as lessons. Understanding alone does not make a node "learned" (that needs 3 right items and recall
practice, step 6), so taught ideas usually show as "learning".
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from . import graph, guidelines, progress, sources, state
from .db import DB, dumps, loads, now

if TYPE_CHECKING:
    from .jobs import Jobs

PROBE_ROUND = 4
PROBE_MAX_ROUNDS = 3
PROBE_MAX = 12
LEVELS = ("known", "partial", "unknown")

_MCQ = {"type": "object", "required": ["prompt", "options", "answer", "explanation"], "properties": {
    "prompt": {"type": "string"}, "options": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
    "answer": {"type": "integer"}, "explanation": {"type": "string"}}}

SKETCH_SCHEMA = {"type": "object", "required": ["title", "target_key", "ideas"], "properties": {
    "title": {"type": "string"}, "target_key": {"type": "string"},
    "ideas": {"type": "array", "minItems": 1, "maxItems": 14, "items": {"type": "object",
        "required": ["key", "title", "statement", "prereq_keys"], "properties": {
            "key": {"type": "string"}, "title": {"type": "string"}, "statement": {"type": "string"},
            "prereq_keys": {"type": "array", "items": {"type": "string"}}, "same_as": {"type": "string"}}}}}}

PROBE_SCHEMA = {"type": "object", "required": ["done", "questions"], "properties": {
    "done": {"type": "boolean"},
    "questions": {"type": "array", "maxItems": PROBE_ROUND, "items": {"type": "object",
        "required": ["idea_key", "prompt", "options", "answer", "explanation"],
        "properties": {"idea_key": {"type": "string"}, **_MCQ["properties"]}}},
    "levels": {"type": "array", "items": {"type": "object", "required": ["idea_key", "level"], "properties": {
        "idea_key": {"type": "string"}, "level": {"enum": list(LEVELS)}}}}}}

PREDICT_SCHEMA = {"type": "object", "required": ["predict"], "properties": {"predict": _MCQ}}
EXPLAIN_SCHEMA = {"type": "object", "required": ["body", "check"], "properties": {"body": {"type": "string"}, "check": _MCQ}}
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


def _active(db: DB, sid: str) -> bool:
    return any(loads(j["input"], {}).get("session_id") == sid
               for j in db.q("SELECT input FROM jobs WHERE kind LIKE 'session_%' AND status IN ('queued', 'running')"))


# ---------------------------------------------------------------- learner actions

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
    if row["phase"] in ("probe", "check"):  # evidence on the idea's node; a prediction is not evidence
        idea = _idea(s, row["idea_key"])
        if idea and idea.get("node"):
            score = 0.5 if progress.guessed(correct, confidence) else (1.0 if correct else 0.0)
            db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, score, thinking, confidence)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                 (now(), idea["node"], f"{sid}-{item_id}", "practice", choice, int(correct), score, thinking, confidence))
    if row["phase"] == "probe":
        if not db.one("SELECT 1 FROM session_items WHERE session_id=? AND phase='probe' AND answered=0", (sid,)):
            jobs.enqueue("session_probe", "Find what you know", {"session_id": sid})
    else:
        advance(db, jobs, sid)


def set_known(db: DB, sid: str, key: str, known: bool) -> None:
    s = get(db, sid)
    if not s or s["status"] != "planning":
        raise ValueError("the plan can change only before teaching starts")
    for i in s["ideas"]:
        if i["key"] == key and not i.get("target"):
            i["skip"] = known
    _save(db, sid, ideas=s["ideas"], plan=_plan(s["ideas"]))


def start_teaching(db: DB, jobs: Jobs, sid: str) -> None:
    s = get(db, sid)
    if not s or s["status"] != "planning":
        raise ValueError("nothing to start")
    _save(db, sid, status="teaching", plan=_plan(s["ideas"]), current=0)
    advance(db, jobs, sid)


def assess_now(db: DB, jobs: Jobs, sid: str) -> None:
    """Stop probing: drop open questions and plan from what is known so far."""
    db.x("DELETE FROM session_items WHERE session_id=? AND phase='probe' AND answered=0", (sid,))
    s = get(db, sid)
    if s and s["status"] == "probing" and not _active(db, sid):
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
    todo = {i["key"]: i for i in ideas if i.get("target") or not (i.get("skip") or i.get("level") == "known")}
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


def advance(db: DB, jobs: Jobs, sid: str) -> None:
    """Teaching: ask for the next turn of the current idea, or move on, or extract at the end."""
    s = get(db, sid)
    if not s or s["status"] != "teaching" or _active(db, sid):
        return
    if s["current"] >= len(s["plan"]):
        _save(db, sid, status="extracting")
        jobs.enqueue("session_extract", "Add what you learned to your graph", {"session_id": sid})
        return
    key = s["plan"][s["current"]]
    items = [i for i in _items(db, sid, key) if i["phase"] != "probe"]
    if any(not i["answered"] for i in items):
        return  # waiting for the learner
    checks = [i for i in items if i["phase"] == "check"]
    if not any(i["phase"] == "predict" for i in items):
        jobs.enqueue("session_turn", "Next step", {"session_id": sid, "kind": "predict", "idea": key})
    elif not checks:
        jobs.enqueue("session_turn", "Explain", {"session_id": sid, "kind": "explain", "idea": key})
    elif checks[-1]["correct"] or len(checks) >= 2:
        _save(db, sid, current=s["current"] + 1)
        advance(db, jobs, sid)
    else:
        jobs.enqueue("session_turn", "Explain again", {"session_id": sid, "kind": "repair", "idea": key})


# ---------------------------------------------------------------- agent jobs

def _learner(db: DB) -> dict:
    pb = state.playbook(db)
    return {"playbook": state.playbook_text(pb), "guidelines": guidelines.text(db), "reasoning": state.reasoning_log(db)}


def _graph_context(db: DB, topic: str) -> tuple[list[dict], str]:
    """Nodes that may matter for the topic, with the learner's state, and the text for the prompt."""
    cands = graph.candidates(db, topic, k=30)
    st = graph.states(db)
    learned = [n for n in db.q("SELECT id, title, statement FROM nodes")
               if st.get(n["id"]) and st[n["id"]].state in ("learned", "mastered")]
    ids = {c["id"] for c in cands}
    rows = cands + [n for n in learned if n["id"] not in ids][:60]
    text = "\n".join(f'- {n["id"]}: {n["title"]} - {n["statement"][:160]} [state: {st[n["id"]].state if n["id"] in st else "new"}]'
                     for n in rows) or "(the graph is empty)"
    return rows, text


def _excerpts(db: DB, s: dict, topic: str, k: int = 6) -> str:
    if not s["source_ids"]:
        return "(none)"
    return sources.excerpts_text(sources.excerpts(db, None, topic, k=k, ids=s["source_ids"]))


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
            level = "known" if ns and ns.state in ("learned", "mastered") else None
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
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    s = get(db, d["session_id"])
    if s["status"] != "probing":
        return {"skipped": True}
    items = [i for i in _items(db, s["id"]) if i["phase"] == "probe"]
    rounds = max((i["round"] for i in items), default=0)
    asked = sum(1 for i in items if i["answered"])
    must_end = rounds >= PROBE_MAX_ROUNDS or asked >= PROBE_MAX
    ideas_text = "\n".join(f'- {i["key"]}: {i["title"]} - {i["statement"]}'
                           f'{" (needs: " + ", ".join(i["prereqs"]) + ")" if i["prereqs"] else ""}'
                           f'{" [known from the graph]" if i["level"] == "known" else ""}' for i in s["ideas"])
    out = jobs.call(jid, "Study tutor", Call(
        prompt=prompt("session_probe", topic=s["topic"], ideas=ideas_text, answers=_answers_text(s, items),
                      asked=asked, max_questions=PROBE_MAX, round_size=PROBE_ROUND,
                      must_end="yes: give the levels now, no more questions" if must_end else "no"),
        schema=PROBE_SCHEMA, model="sonnet", timeout=300))
    keys = {i["key"] for i in s["ideas"]}
    questions = [q for q in out.get("questions") or [] if q["idea_key"] in keys and 0 <= q["answer"] < len(q["options"])]
    if not (out.get("done") or must_end or questions):
        raise ValueError("the probe returned no usable questions")
    if out.get("done") or must_end:
        levels = {lv["idea_key"]: lv["level"] for lv in out.get("levels") or [] if lv["level"] in LEVELS}
        for i in s["ideas"]:
            if i["level"] != "known" and i["key"] in levels:
                i["level"] = levels[i["key"]]
        _to_planning(db, s)
        return {"planned": True}
    with db.tx():
        for n, q in enumerate(questions[:PROBE_ROUND]):
            db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                            (s["id"], q["idea_key"], "probe", rounds + 1, n,
                             dumps({k: q[k] for k in ("prompt", "options", "answer", "explanation")}), now()))
    return {"round": rounds + 1}


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
            line += f' | confidence {round(r["confidence"] * 100)}%'
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
    if s["status"] != "teaching" or not idea:
        return {"skipped": True}
    done = s["plan"][:s["current"]]
    plan_text = "\n".join(f'{n + 1}. {_idea(s, k)["title"]}{" (done)" if k in done else " (now)" if k == key else ""}'
                          for n, k in enumerate(s["plan"]))
    known = ", ".join(i["title"] for i in s["ideas"] if i["key"] not in s["plan"]) or "(none)"
    lr = _learner(db)
    now_items = [i for i in _items(db, s["id"], key) if i["phase"] != "probe"]
    lines = []
    for r in now_items:
        if r["phase"] == "explain":
            lines.append(f'- explanation given: {r["item"]["body"][:1500]}')
    current = "\n".join(lines + [_answers_text(s, [r for r in now_items if r["phase"] != "explain"])])
    earlier = _answers_text(s, [r for r in _items(db, s["id"]) if r["phase"] == "check" and r["idea_key"] in done][-8:])
    out = jobs.call(jid, "Study tutor", Call(
        prompt=prompt("session_turn", kind=kind, topic=s["topic"], plan=plan_text, known=known,
                      idea=f'{idea["title"]}: {idea["statement"]}', current=current, earlier=earlier,
                      playbook=lr["playbook"], guidelines=lr["guidelines"],
                      sources=_excerpts(db, s, f'{idea["title"]} {idea["statement"]}', k=4)),
        schema=PREDICT_SCHEMA if kind == "predict" else EXPLAIN_SCHEMA, model="sonnet", timeout=300))
    ts = now()
    with db.tx():
        if kind == "predict":
            q = out["predict"]
            if not 0 <= q["answer"] < len(q["options"]):
                raise ValueError("the prediction question has no valid answer")
            db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                            (s["id"], key, "predict", 0, 0, dumps(q), ts))
        else:
            c = out["check"]
            if not 0 <= c["answer"] < len(c["options"]) or not out["body"].strip():
                raise ValueError("the explanation or its check is empty")
            db.conn.execute("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, answered, created_at)
                               VALUES(?,?,?,?,?,?,1,?)""", (s["id"], key, "explain", 0, 0, dumps({"body": out["body"].strip(), "kind": kind}), ts))
            db.conn.execute("INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)",
                            (s["id"], key, "check", 0, 1, dumps(c), ts))
    return {"kind": kind}


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
                      answers=_answers_text(s, [r for r in items if r["phase"] in ("predict", "check", "probe")])),
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
    running = _active(db, sid)
    failed = None
    if not running:
        j = db.one("SELECT status, error FROM jobs WHERE kind LIKE 'session_%' AND input LIKE ? ORDER BY id DESC LIMIT 1",
                   (f'%"{sid}"%',))
        failed = j["error"] if j and j["status"] == "failed" else None
    items = _items(db, sid)
    pub = []
    for r in items:
        it = dict(r["item"])
        if r["phase"] == "explain":
            pub.append({"id": r["id"], "idea": r["idea_key"], "phase": "explain", "body": it["body"], "repair": it.get("kind") == "repair"})
            continue
        q = {"id": r["id"], "idea": r["idea_key"], "phase": r["phase"], "round": r["round"], "prompt": it["prompt"],
             "options": it["options"], "answered": bool(r["answered"])}
        if r["answered"]:
            q.update(choice=r["choice"], correct=bool(r["correct"]), answer=it["answer"], explanation=it["explanation"],
                     thinking=r["thinking"], confidence=r["confidence"])
        pub.append(q)
    st = graph.states(db)
    ideas = [{**{k: i.get(k) for k in ("key", "title", "statement", "node", "prereqs", "target", "level", "skip", "fromGraph")},
              "nodeState": st[i["node"]].state if i.get("node") in st else "pending"} for i in s["ideas"]]
    return {"id": s["id"], "topic": s["topic"], "title": s["title"], "status": s["status"], "busy": running, "error": failed,
            "ideas": ideas, "plan": s["plan"], "current": s["current"], "items": pub, "summary": s["summary"],
            "sources": s["source_ids"], "createdAt": s["created_at"]}
