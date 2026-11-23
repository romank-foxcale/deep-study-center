"""Background agent jobs: research, outline, rendering, tutor replies, roadmap reviews, fact-checks.

Each job is a row in ``jobs`` (so the UI can show progress) and runs on a small thread pool.
Every job has a deterministic fallback for when no provider is available, so the app stays usable.
"""

from __future__ import annotations

import json
import re
import secrets
import traceback
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Callable

from . import bookstudy, demos, dictation, formula_fields, formula_lessons, formulas, lesson_graph, lesson_steps, reasoning, engine, graph, guidelines, library, mcq, ohtani, practice, probe, progress, providers, runner, session, sources, state, versions, viz, writer
from . import feedback as fb
from .db import DB, dumps, loads, now, workspace
from .providers import Call, ProviderUnavailable

Runner = Callable[[dict, Call, object], tuple[object, str]]


# Writing style of everything the learner reads (Settings → Learning): "ste" = Simplified Technical English (about 80 %).
STYLE = {"writing": "ste"}


def prompt(name: str, **fields: object) -> str:
    text = resources.files("dsc").joinpath(f"prompts/{name}.md").read_text(encoding="utf-8")
    rules = resources.files("dsc").joinpath("prompts/_rules.md").read_text(encoding="utf-8")
    if STYLE["writing"] == "ste":
        rules = rules.rstrip("\n") + "\n" + resources.files("dsc").joinpath("prompts/_ste.md").read_text(encoding="utf-8")
    fields.setdefault("rules", rules)
    if "{widgets}" in text:
        fields.setdefault("widgets", resources.files("dsc").joinpath("prompts/_widgets.md").read_text(encoding="utf-8").strip())
    # Plain replacement (not str.format) so braces in learner text or LaTeX are safe.
    for k, v in fields.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "x"


class Jobs:
    def __init__(self, db: DB, runner: Runner | None = None, inline: bool = False):
        self.db = db
        STYLE["writing"] = db.meta("writing_style", "ste") or "ste"
        self.runner = runner or providers.run_with_fallback
        self.pool = None if inline else ThreadPoolExecutor(max_workers=3, thread_name_prefix="dsc-job")
        db.x("UPDATE jobs SET status='failed', error='interrupted by restart' WHERE status IN ('queued', 'running')")

    # ---- queue

    def enqueue(self, kind: str, label: str, data: dict) -> int:
        ts = now()
        jid = self.db.x("INSERT INTO jobs(kind, status, label, input, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                        (kind, "queued", label, dumps(data), ts, ts))
        if self.pool:
            self.pool.submit(self._run, jid)
        else:
            self._run(jid)
        return jid

    def active(self, kind: str, **match: object) -> bool:
        for j in self.db.q("SELECT input FROM jobs WHERE kind=? AND status IN ('queued', 'running')", (kind,)):
            data = loads(j["input"], {})
            if all(data.get(k) == v for k, v in match.items()):
                return True
        return False

    def progress(self, jid: int, msg: str) -> None:
        row = self.db.one("SELECT progress FROM jobs WHERE id=?", (jid,))
        steps = loads(row["progress"], []) if row else []
        self.db.x("UPDATE jobs SET progress=?, updated_at=? WHERE id=?", (dumps((steps + [msg])[-60:]), now(), jid))

    def _run(self, jid: int) -> None:
        job = self.db.one("SELECT * FROM jobs WHERE id=?", (jid,))
        data = loads(job["input"], {})
        self.db.x("UPDATE jobs SET status='running', updated_at=? WHERE id=?", (now(), jid))
        handler, fallback = HANDLERS[job["kind"]]
        try:
            out = handler(self, jid, data)
            self.db.x("UPDATE jobs SET status='done', output=?, updated_at=? WHERE id=?", (dumps(out), now(), jid))
            if job["kind"] == "research_module":
                progress.research_ahead(self.db, self)  # keep going until research is one module ahead
            if job["kind"] == "lesson_step":
                lesson_steps.ensure(self.db, self, data["concept_id"])  # the next step, if the learner moved on meanwhile
                formulas.ensure(self.db, self, data["concept_id"])  # hover notes for the step's formulas
            if job["kind"] in ("formula_notes", "formula_lesson"):
                formula_fields.ensure(self.db, self)  # new formulas get their fields for the map
            if job["kind"] in ("render", "apply_feedback") and data.get("concept_id"):
                formulas.ensure(self.db, self, data["concept_id"])  # notes for the formulas of the new text
        except ProviderUnavailable as e:
            if fallback:
                fallback(self, jid, data)
            self.db.x("UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=?",
                      (f"No provider available ({e}).{' Used the offline fallback.' if fallback else ''}", now(), jid))
        except Exception as e:  # noqa: BLE001 - a failed job must never take the server down
            traceback.print_exc()
            if fallback:
                fallback(self, jid, data)
            self.db.x("UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=?", (str(e)[:500], now(), jid))

    def call(self, jid: int, role: str, call: Call) -> object:
        route = state.route(self.db, role)
        self.progress(jid, f"{role}: asking {route['provider']} ({route['model']})")
        if call.tools and call.on_event is None:  # web research: show each search and page as it happens
            call.on_event = lambda msg: self.progress(jid, msg)
        out, used = self.runner(route, call, workspace() / "jobs" / str(jid))
        if used != route["provider"]:
            self.progress(jid, f"{route['provider']} unavailable, used {used}")
        return out


# ---------------------------------------------------------------- context helpers

def _goal(db: DB) -> dict:
    gid = state.active_goal(db)
    return db.one("SELECT * FROM goals WHERE id=?", (gid,)) or {"title": "", "profile": "", "id": gid}


def _card_text(card: dict) -> str:
    keep = {k: card.get(k) for k in ("objective", "core", "formal", "why", "angles", "examples", "misconceptions")}
    keep["sections"] = [{"id": s["id"], "heading": s["heading"], "purpose": s.get("purpose", "")} for s in card.get("sections", [])]
    return json.dumps(keep, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- render

RENDER_SCHEMA = {"type": "object", "required": ["sections"], "properties": {"sections": {"type": "array", "items": {
    "type": "object", "required": ["id", "body"], "properties": {"id": {"type": "string"}, "body": {"type": "string"}}}}}}


def run_render(jobs: Jobs, jid: int, d: dict) -> dict:
    """A whole lesson goes through the writing steps (``writer.write_lesson``: plan, graphs and questions, prose,
    review). Single sections ("explain differently", a pin) get only new prose, with the stored plan's brief."""
    if d.get("full"):
        return writer.write_lesson(jobs, jid, d)
    db, cid = jobs.db, d["concept_id"]
    want = {s["id"]: s["angle"] for s in d["sections"]}
    p = writer.current_plan(db, cid, d["card_version"])
    briefs = {s["id"]: s["brief"] for s in (p or {}).get("plan", {}).get("sections", [])}
    written = writer.write_prose(jobs, jid, cid, d["card_version"], d["style"], want, briefs)
    jobs.progress(jid, f"rendered {written} section(s)")
    v = versions.sync(db, cid, by_writer=True, rewrite=bool(d.get("rewrite")))
    if v:
        jobs.progress(jid, f"saved as lesson version v{v}")
    return {"written": written}


# ---------------------------------------------------------------- tutor

def run_tutor(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    cid = d["concept_id"]
    card = state.latest_card(db, cid) or {}
    history = db.q("SELECT role, text FROM chats WHERE concept_id=? ORDER BY id DESC LIMIT 16", (cid,))[::-1]
    notes = db.q("SELECT quote, text FROM notes WHERE concept_id=? ORDER BY id DESC LIMIT 10", (cid,))
    reply = jobs.call(jid, "Tutor chat", Call(
        prompt=prompt("tutor", card=_card_text(card), goal=_goal(db)["title"], playbook=state.playbook_text(state.playbook(db)),
                      notes="\n".join(f'- {n["text"]}' + (f' (on "{n["quote"]}")' if n["quote"] else "") for n in notes) or "(none)",
                      history="\n".join(f'{m["role"]}: {m["text"]}' for m in history), section=d.get("section") or "(unknown)",
                      reasoning=state.reasoning_log(db, cid, limit=8)),
        model="sonnet", timeout=180))
    db.x("INSERT INTO chats(ts, concept_id, role, text) VALUES(?,?,?,?)", (now(), cid, "tutor", str(reply).strip()))
    return {"ok": True}


def fallback_tutor(jobs: Jobs, jid: int, d: dict) -> None:
    jobs.db.x("INSERT INTO chats(ts, concept_id, role, text) VALUES(?,?,?,?)",
              (now(), d["concept_id"], "tutor",
               "I can't reach a model right now (check Settings → Providers). Meanwhile: say in one sentence what this "
               "section claims, then test it on the smallest example you can think of."))


# ---------------------------------------------------------------- roadmap review

DIFF_SCHEMA = {"type": "object", "required": ["reason", "changes"], "properties": {
    "reason": {"type": "string"},
    "changes": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "object", "required": ["op", "title", "detail"],
                "properties": {"op": {"enum": ["insert", "compress", "deepen"]}, "title": {"type": "string"},
                               "detail": {"type": "string"}}}}}}


def run_roadmap_review(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    c = db.one("SELECT * FROM concepts WHERE id=?", (d["concept_id"],))
    m = db.one("SELECT * FROM modules WHERE id=?", (c["module_id"],))
    siblings = db.q("SELECT title, objective FROM concepts WHERE module_id=? ORDER BY ord", (m["id"],))
    out = jobs.call(jid, "Roadmap review", Call(
        prompt=prompt("roadmap_review", goal=_goal(db)["title"], playbook=state.playbook_text(state.playbook(db)),
                      module=m["title"], concepts="\n".join(f'- {s["title"]}: {s["objective"]}' for s in siblings),
                      concept=c["title"], tags=", ".join(d["tags"]), text=d.get("text") or "(none)"),
        schema=DIFF_SCHEMA, model="opus", timeout=300))
    _insert_diff(db, d["concept_id"], out["reason"], out["changes"])
    return {"changes": len(out["changes"])}


def fallback_roadmap_review(jobs: Jobs, jid: int, d: dict) -> None:
    c = jobs.db.one("SELECT title FROM concepts WHERE id=?", (d["concept_id"],))
    _insert_diff(jobs.db, d["concept_id"], f'You got lost in "{c["title"]}". A short refresher may be missing.', [
        {"op": "insert", "title": f'Refresher (before {c["title"]})', "detail": "A short review of the background this lesson assumes."},
        {"op": "deepen", "title": c["title"], "detail": "Add one more worked example to each section."}])


def _insert_diff(db: DB, concept_id: str, reason: str, changes: list[dict]) -> None:
    for ch in changes:
        ch["anchor"] = concept_id
    db.x("INSERT INTO diffs(ts, goal_id, reason, changes, status) VALUES(?,?,?,?,'pending')",
         (now(), state.active_goal(db), reason, dumps(changes)))


# ---------------------------------------------------------------- outline (new goal)

OUTLINE_SCHEMA = {"type": "object", "required": ["title", "why", "done", "tracks"], "properties": {
    "title": {"type": "string"}, "why": {"type": "string"}, "done": {"type": "string"},
    "tracks": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["title", "summary", "modules"], "properties": {
        "title": {"type": "string"}, "summary": {"type": "string"},
        "modules": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["title", "summary", "planned"], "properties": {
            "title": {"type": "string"}, "summary": {"type": "string"}, "planned": {"type": "integer"}}}}}}}}}


def run_outline(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    answers = d["answers"]
    layout = "ohtani" if d.get("layout") == "ohtani" else "list"
    ids = d.get("source_ids") or []
    base = ohtani.SCHEMA if layout == "ohtani" else OUTLINE_SCHEMA
    lines = [f"Q: {a['q']}\nA: {a['a']}" for a in answers]
    profile = "\n".join(a["a"] for a in answers[1:] if a["a"].strip() and a["a"] != "(skipped)")
    own, focus, schema = sources.contents_text(db, ids=ids), "", base
    time_answer = answers[3]["a"] if len(answers) > 3 else ""
    out = jobs.call(jid, "Curriculum", Call(
        prompt=prompt("outline_ohtani" if layout == "ohtani" else "outline",
                      answers="\n".join(lines), sources=own or "(none)", focus=focus),
        schema=schema, model="opus", timeout=600))
    gid = f"g-{slug(out['title'], 24)}-{secrets.token_hex(2)}"
    hours = next((float(x) for x in re.findall(r"\d+(?:\.\d+)?", time_answer)), 5.0)
    if layout == "ohtani":
        tracks, modules = ohtani.build(gid, out)
    else:
        tracks, modules = [], []
        for ti, t in enumerate(out["tracks"]):
            tid = f"{gid}-t{ti}"
            tracks.append({"id": tid, "ord": ti, "title": t["title"], "summary": t["summary"], "pos": ""})
            modules += [{"id": f"{tid}-m{mi}", "track_id": tid, "ord": mi, "title": m["title"], "summary": m["summary"],
                         "planned": m["planned"], "done_when": "", "requires": [], "seq": 0} for mi, m in enumerate(t["modules"])]
    with db.tx():
        db.conn.execute("INSERT INTO goals(id, title, why, done, hours, profile, created_at, layout, kind) VALUES(?,?,?,?,?,?,?,?,?)",
                        (gid, out["title"], out["why"], out["done"], hours, profile, now(), layout, "goal"))
        for t in tracks:
            db.conn.execute("INSERT INTO tracks(id, goal_id, ord, title, summary, pos) VALUES(?,?,?,?,?,?)",
                            (t["id"], gid, t["ord"], t["title"], t["summary"], t["pos"]))
        for m in modules:
            db.conn.execute("""INSERT INTO modules(id, track_id, ord, title, research, planned, summary, seq, requires, done_when)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (m["id"], m["track_id"], m["ord"], m["title"], "outline", m["planned"], m["summary"], m["seq"],
                             dumps(m["requires"]), m["done_when"]))
        db.conn.execute("INSERT INTO meta(key, value) VALUES('active_goal', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (gid,))
        for sid in ids:
            db.conn.execute("INSERT OR IGNORE INTO goal_sources(goal_id, source_id) VALUES(?,?)", (gid, sid))
    first_module = db.one("""SELECT m.id FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id=?
                             ORDER BY m.seq, t.ord, m.ord LIMIT 1""", (gid,))
    what = f"{len(tracks) - 1} areas x 8 steps and 8 merges" if layout == "ohtani" else f"{len(tracks)} tracks"
    jobs.progress(jid, f"roadmap: {what}; preparing the probe and researching the first module")
    probe.start(db, jobs, gid)
    if first_module:
        db.x("UPDATE modules SET research='researching' WHERE id=?", (first_module["id"],))
        jobs.enqueue("research_module", "Research first module", {"module_id": first_module["id"]})
    return {"goal_id": gid}


# ---------------------------------------------------------------- research a module into cards

_CHECK = mcq.SCHEMA
_CODE = {"type": "object", "required": ["prompt", "starter", "tests"], "properties": {
    "prompt": {"type": "string"}, "starter": {"type": "string"}, "tests": {"type": "string"},
    "runtime": {"enum": ["pyodide", "local"]}}}
_EXPLAIN = {"type": "object", "required": ["prompt", "rubric"], "properties": {
    "prompt": {"type": "string"}, "rubric": {"type": "array", "minItems": 1, "items": {"type": "string"}}}}
_ANGLE = {"enum": list(engine.ANGLES)}
RESEARCH_SCHEMA = {"type": "object", "required": ["concepts"], "properties": {"concepts": {"type": "array", "minItems": 1, "items": {
    "type": "object", "required": ["key", "title", "objective", "minutes", "prereq_keys"], "properties": {
        "key": {"type": "string"}, "title": {"type": "string"}, "objective": {"type": "string"},
        "reuse_key": {"type": "string"}, "same_as": {"type": "string"},
        "minutes": {"type": "integer"}, "prereq_keys": {"type": "array", "items": {"type": "string"}},
        "card": {"type": "object", "required": ["bloom", "core", "formal", "why", "angles", "examples", "misconceptions", "sources", "sections"],
                 "properties": {
                     "bloom": {"type": "string"}, "core": {"type": "string"}, "formal": {"type": "string"}, "why": {"type": "string"},
                     "angles": {"type": "array", "items": {"type": "object", "required": ["id", "label", "summary"], "properties": {
                         "id": _ANGLE, "label": {"type": "string"}, "summary": {"type": "string"}}}},
                     "examples": {"type": "array", "items": {"type": "object", "required": ["label", "domain"], "properties": {
                         "label": {"type": "string"}, "domain": {"type": "string"}}}},
                     "misconceptions": {"type": "array", "items": {"type": "string"}},
                     "sources": {"type": "array", "items": {"type": "object", "required": ["title", "url", "kind", "why"], "properties": {
                         "title": {"type": "string"}, "url": {"type": "string"},
                         "kind": {"enum": ["video", "book", "article", "paper", "interactive"]}, "why": {"type": "string"}}}},
                     "sections": {"type": "array", "minItems": 2, "items": {"type": "object", "required": ["id", "heading", "purpose", "angles"],
                                  "properties": {"id": {"type": "string"}, "heading": {"type": "string"}, "purpose": {"type": "string"},
                                                 "angles": {"type": "array", "minItems": 1, "items": _ANGLE},
                                                 "check": _CHECK, "code": _CODE, "explain": _EXPLAIN, "viz": viz.SCHEMA}}}}}}}}}}


def run_research_module(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    m = db.one("SELECT * FROM modules WHERE id=?", (d["module_id"],))
    t = db.one("SELECT * FROM tracks WHERE id=?", (m["track_id"],))
    g = db.one("SELECT * FROM goals WHERE id=?", (t["goal_id"],))
    if g["kind"] == "bookstudy" and not d.get("concept"):  # a book chapter: written from the book's pages (SPEC §31);
        # an extra lesson inserted into a book chapter is researched the normal way below
        return bookstudy.write_cards(jobs, jid, d)
    earlier = db.q("""SELECT m.title FROM modules m JOIN tracks t ON t.id=m.track_id WHERE t.goal_id=?
                      AND (m.seq, t.ord, m.ord) < (?, ?, ?) ORDER BY m.seq, t.ord, m.ord""", (g["id"], m["seq"], t["ord"], m["ord"]))
    db.x("UPDATE modules SET research='researching' WHERE id=?", (m["id"],))
    summary = m["summary"] or "no summary"
    if m["done_when"]:
        summary += f". Done when: {m['done_when']}"
    required = loads(m["requires"], [])
    if required:  # an Ohtani merge step: it joins what these steps taught
        titles = [r["title"] for r in db.q(f"SELECT title FROM modules WHERE id IN ({','.join('?' * len(required))})", required)]
        summary += f". It merges what these steps taught: {', '.join(titles)}"
    target = d.get("concept")  # single inserted concept: research just that one
    topic = f'{target["title"]} {target.get("detail", "")}' if target else f'{m["title"]} {m["summary"] or ""} {m["done_when"] or ""}'
    book = g["kind"] == "book"  # a book goal made before 0.5 (SPEC §18): more pages, the book focus
    own = sources.excerpts(db, g["id"], topic, k=12 if book else 8)
    known = graph.candidates(db, topic, exclude_module=m["id"])  # ideas the learner's graph already has
    if own:
        jobs.progress(jid, f"using {len(own)} page(s) of your sources")
    out = jobs.call(jid, "Research", Call(
        prompt=prompt("research_module", goal=g["title"], profile=g["profile"], track=t["title"],
                      module=target["title"] if target else m["title"],
                      summary=target["detail"] if target else summary,
                      earlier=", ".join(e["title"] for e in earlier) or "none",
                      planned=1 if target else (m["planned"] or 8), library=library.index_text(db),
                      sources=sources.excerpts_text(own), focus=prompt("_book_research") if book else "",
                      graph=graph.candidates_text(known)),
        schema=RESEARCH_SCHEMA, model="opus", tools=("WebSearch", "WebFetch"), timeout=1800, max_turns=60))
    concepts = []
    for c in (out["concepts"][:1] if target else out["concepts"]):
        reused = library.take(db, c["reuse_key"]) if c.get("reuse_key") else None
        if reused:  # an existing fact-checked card from the shared library
            c = {**c, "card": reused, "reused": True}
        node = c.get("same_as") if c.get("same_as") in {n["id"] for n in known} else None
        c = {**c, "node": node}
        if node and not c.get("card"):  # the same idea is already in the graph: reuse its newest card
            sib = db.one("""SELECT k.body, k.fact_check FROM concept_nodes n JOIN cards k ON k.concept_id = n.concept_id
                            WHERE n.node_id=? ORDER BY k.checked_at DESC, k.version DESC LIMIT 1""", (node,))
            if sib:
                c = {**c, "card": loads(sib["body"]), "reused": sib["fact_check"] == "passed"}
        if c.get("card"):
            concepts.append(c)
    # Compute every graph as the page will; one fix round with an agent for a graph that does not work.
    for c in concepts:
        if c.get("reused"):
            continue
        for s in c["card"].get("sections", []):
            if s.get("viz"):
                spec, notes = writer.check_viz(jobs, jid, {**c["card"], "objective": c["objective"]}, s, s["viz"])
                if spec:
                    s["viz"] = spec
                else:
                    s.pop("viz", None)
                if notes:
                    s["vizNotes"] = notes
    keymap = {c["key"]: (target["id"] if target else f'{m["id"]}-{slug(c["key"], 30)}') for c in concepts}
    base_ord = db.one("SELECT COALESCE(MAX(ord), -1) AS o FROM concepts WHERE module_id=?", (m["id"],))["o"] + 1
    ts = now()
    with db.tx():
        for i, c in enumerate(concepts):
            cid = keymap[c["key"]]
            for s in c["card"]["sections"]:
                if "viz" in s:
                    s["viz"] = viz.validate(s["viz"])
                    if not s["viz"]:
                        del s["viz"]
                if s.get("code") and s["code"].get("runtime") not in ("pyodide", "local"):
                    s["code"]["runtime"] = "pyodide"
                if s.get("check"):
                    s["check"] = {**mcq.shuffle(s["check"]), "id": f'q-{s["id"]}'}
                if s.get("code"):
                    s["code"]["id"] = f'x-{s["id"]}'
                if s.get("explain"):
                    s["explain"]["id"] = f'e-{s["id"]}'
            prereqs = [keymap[k] for k in c["prereq_keys"] if k in keymap]
            if target:
                db.conn.execute("UPDATE concepts SET objective=?, minutes=? WHERE id=?", (c["objective"], c["minutes"], cid))
            else:
                db.conn.execute("INSERT OR REPLACE INTO concepts VALUES(?,?,?,?,?,?,?,?,0)",
                                (cid, m["id"], base_ord + i, c["title"], c["objective"], c["minutes"], dumps(prereqs), 0.1))
            if c.get("node") and not target:
                graph.attach(db, cid, c["node"])  # same idea as an existing node: knowledge is shared across goals
            body = {**c["card"], "objective": c["objective"]}
            ver = (db.conn.execute("SELECT COALESCE(MAX(version), 0) FROM cards WHERE concept_id=?", (cid,)).fetchone()[0]) + 1
            db.conn.execute("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
                            (cid, ver, dumps(body), "passed" if c.get("reused") else "pending", ts))
        db.conn.execute("UPDATE modules SET research='ready' WHERE id=?", (m["id"],))
    jobs.progress(jid, f"wrote {len(concepts)} concept card(s); fact-checking next")
    to_check = [keymap[c["key"]] for c in concepts if not c.get("reused")]
    if to_check:
        jobs.enqueue("fact_check", f"Fact-check {m['title']}", {"concept_ids": to_check})
    return {"concepts": len(concepts)}


def fallback_research_module(jobs: Jobs, jid: int, d: dict) -> None:
    m = jobs.db.one("SELECT research FROM modules WHERE id=?", (d["module_id"],))
    if m and m["research"] == "researching":
        # A single inserted lesson must not turn a researched module back into an outline.
        jobs.db.x("UPDATE modules SET research=? WHERE id=?", (d.get("prev_research") or "outline", d["module_id"]))


FACT_SCHEMA = {"type": "object", "required": ["results"], "properties": {"results": {"type": "array", "items": {
    "type": "object", "required": ["key", "verdict", "issues"], "properties": {
        "key": {"type": "string"}, "verdict": {"enum": ["passed", "needs-revision"]},
        "issues": {"type": "array", "items": {"type": "string"}}}}}}}


def run_fact_check(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    cards = {cid: state.latest_card(db, cid) for cid in d["concept_ids"]}
    payload = json.dumps({cid: {k: v for k, v in c.items() if k not in ("conceptId", "factCheck", "checkedAt")}
                          for cid, c in cards.items() if c}, ensure_ascii=False)
    out = jobs.call(jid, "Fact-check", Call(prompt=prompt("fact_check", cards=payload), schema=FACT_SCHEMA, model="opus", timeout=900))
    for r in out["results"]:
        c = cards.get(r["key"])
        if c:
            body = loads(db.one("SELECT body FROM cards WHERE concept_id=? AND version=?", (r["key"], c["version"]))["body"])
            body["factIssues"] = r["issues"]
            db.x("UPDATE cards SET fact_check=?, body=?, checked_at=? WHERE concept_id=? AND version=?",
                 (r["verdict"], dumps(body), now(), r["key"], c["version"]))
    return {"checked": len(out["results"])}


# ---------------------------------------------------------------- explain-back grading

GRADE_SCHEMA = {"type": "object", "required": ["score", "feedback", "missing", "followup", "parts", "assumption", "follow", "truth",
                                               "takeaway"], "properties": {
    "score": {"enum": [0, 0.5, 1]}, "feedback": {"type": "string"},
    "missing": {"type": "array", "items": {"type": "string"}}, "followup": {"type": "string"},
    "parts": reasoning.SCHEMA["properties"]["parts"], "assumption": {"type": "string"},
    "follow": {"type": "array", "items": {"type": "string"}}, "truth": {"type": "string"}, "takeaway": {"type": "string"}}}


def run_grade(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    g = db.one("SELECT * FROM gradings WHERE id=?", (d["grading_id"],))
    card = state.latest_card(db, g["concept_id"]) or {}
    sec = next(s for s in card.get("sections", []) if s.get("explain", {}).get("id") == g["item_id"])
    concept = db.one("SELECT title FROM concepts WHERE id=?", (g["concept_id"],))
    drawing = workspace() / "drawings" / g["drawing"] if g.get("drawing") else None
    answer = g["answer"]
    if drawing and drawing.exists():
        answer += ("\n\n[The learner also worked on a drawing board: the attached image. Read their calculation or "
                   "sketch there and grade it with the words; say in the feedback where a step on the board goes wrong.]")
    out = jobs.call(jid, "Grading", Call(
        prompt=prompt("grade", concept=concept["title"], question=sec["explain"]["prompt"],
                      rubric="\n".join(f"- {r}" for r in sec["explain"]["rubric"]), answer=answer),
        schema=GRADE_SCHEMA, model="sonnet", timeout=240,
        images=(drawing,) if drawing and drawing.exists() else ()))
    score = float(out["score"])
    review = reasoning.clean(out, g["answer"])  # the parts of the answer marked, the assumption, where it breaks (SPEC §35)
    keep = {k: review[k] for k in ("parts", "assumption", "follow", "truth", "takeaway")}
    db.x("UPDATE gradings SET status='graded', score=?, feedback=?, missing=?, followup=?, review=? WHERE id=?",
         (score, out["feedback"], dumps(out.get("missing", [])), out.get("followup") or "",
          dumps(keep) if keep["parts"] or keep["assumption"] or keep["truth"] else None, g["id"]))
    if progress.record_evidence(db, g["concept_id"], g["item_id"], score, angle=d.get("angle")):
        progress.on_finished(db, jobs, g["concept_id"])
    return {"score": score}


def fallback_grade(jobs: Jobs, jid: int, d: dict) -> None:
    jobs.db.x("UPDATE gradings SET status='ungraded', feedback=? WHERE id=?",
              ("No grader is available right now (see Settings → Providers). Your answer is saved; try again later.",
               d["grading_id"]))


# ---------------------------------------------------------------- weekly reflection

REFLECT_SCHEMA = {"type": "object", "required": ["summary", "proposals"], "properties": {
    "summary": {"type": "string"},
    "proposals": {"type": "array", "maxItems": 4, "items": {"type": "object", "required": ["dimension", "value", "why"], "properties": {
        "dimension": {"enum": ["angle", "example-domain", "format", "pace", "depth", "rigor"]},
        "value": {"type": "string"}, "verdict": {"enum": ["works", "avoid", "trying"]},
        "delta": {"type": "integer"}, "why": {"type": "string"}}}}}}


def _reflection_inputs(db: DB) -> dict:
    items = db.q("SELECT f.*, c.title FROM feedback f JOIN concepts c ON c.id = f.concept_id WHERE f.deleted = 0 ORDER BY f.id DESC LIMIT 40")
    outcomes = db.q("""SELECT angle, COUNT(*) AS n, AVG(COALESCE(score, correct)) AS avg FROM evidence
                       WHERE angle IS NOT NULL AND voided = 0 GROUP BY angle""")
    return {
        "feedback": "\n".join(f'- [{f["title"]}] ({f["kind"]}) {", ".join(loads(f["tags"]))}' + (f': "{f["text"]}"' if f["text"] else "")
                              for f in items) or "(no feedback yet)",
        "outcomes": "\n".join(f'- {o["angle"]}: {o["n"]} answers, {o["avg"] * 100:.0f}% correct' for o in outcomes) or "(none yet)",
        "reverts": versions.reverts_text(db),
        "notes": db.one("SELECT COUNT(*) AS n FROM notes")["n"],
        "studied": db.one("SELECT COUNT(*) AS n FROM renditions WHERE studied = 1")["n"],
        "fb_count": len(items), "outcome_rows": outcomes,
    }


def run_reflect(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    x = _reflection_inputs(db)
    out = jobs.call(jid, "Reflection", Call(
        prompt=prompt("reflect", goal=_goal(db)["title"], playbook=state.playbook_text(state.playbook(db)),
                      feedback=x["feedback"], outcomes=x["outcomes"], notes=x["notes"], studied=x["studied"],
                      reverts=x["reverts"]),
        schema=REFLECT_SCHEMA, model="opus", timeout=600))
    proposals = [{**p, "status": "pending"} for p in out["proposals"]
                 if (p["dimension"] in engine.ADJUST_KEYS and p.get("delta")) or p.get("verdict")]
    db.x("INSERT INTO reflections(ts, summary, proposals, source) VALUES(?,?,?,?)", (now(), out["summary"], dumps(proposals), "llm"))
    db.set_meta("last_reflection", now())
    return {"proposals": len(proposals)}


def fallback_reflect(jobs: Jobs, jid: int, d: dict) -> None:
    """Offline: a plain summary from the numbers, with no proposals."""
    db = jobs.db
    x = _reflection_inputs(db)
    best = max(x["outcome_rows"], key=lambda o: o["avg"], default=None)
    parts = [f'You gave feedback {x["fb_count"]} time(s) and wrote {x["notes"]} note(s).']
    if best:
        parts.append(f'Your practice went best after {best["angle"]} explanations ({best["avg"] * 100:.0f}% correct).')
    parts.append("A model wasn't available, so this reflection has no proposals.")
    db.x("INSERT INTO reflections(ts, summary, proposals, source) VALUES(?,?,?,?)", (now(), " ".join(parts), "[]", "offline"))
    db.set_meta("last_reflection", now())

# ---------------------------------------------------------------- card refresh

REFRESH_SCHEMA = {"type": "object", "required": ["changed", "summary", "changes"], "properties": {
    "changed": {"type": "boolean"}, "summary": {"type": "string"},
    "changes": {"type": "array", "items": {"type": "string"}},
    "card": RESEARCH_SCHEMA["properties"]["concepts"]["items"]["properties"]["card"]}}


def run_refresh_card(jobs: Jobs, jid: int, d: dict) -> dict:
    """Review one card against the web; store a proposal (never a new version) if it should change."""
    db = jobs.db
    cid = d["concept_id"]
    card = state.latest_card(db, cid)
    if not card:
        return {"changed": False}
    body = {k: v for k, v in card.items() if k not in ("conceptId", "version", "factCheck", "checkedAt", "factIssues")}
    out = jobs.call(jid, "Card refresh", Call(
        prompt=prompt("refresh_card", card=json.dumps(body, ensure_ascii=False, indent=1), written=card["checkedAt"],
                      today=now()[:10], claims="\n".join(f"- {c}" for c in d.get("claims") or []) or "(none)"),
        schema=REFRESH_SCHEMA, model="opus", tools=("WebSearch", "WebFetch"), timeout=1200, max_turns=40))
    db.x("UPDATE cards SET refreshed_at=? WHERE concept_id=? AND version=?", (now(), cid, card["version"]))
    if not out.get("changed") or not out.get("card"):
        jobs.progress(jid, f"no changes needed: {out.get('summary', '')}"[:300])
        return {"changed": False, "summary": out.get("summary", "")}
    new = {**out["card"], "objective": out["card"].get("objective") or card["objective"]}
    old_ids = {s["id"]: s for s in card.get("sections", [])}
    for s in new.get("sections", []):
        prev = old_ids.get(s["id"], {})
        if s.get("check") and not prev.get("check"):  # a new check; a kept one keeps its order for past answers
            s["check"] = mcq.shuffle(s["check"])
        for kind, prefix in (("check", "q"), ("code", "x"), ("explain", "e")):
            if s.get(kind):  # keep item ids stable so past answers still line up
                s[kind]["id"] = prev.get(kind, {}).get("id") or f'{prefix}-{s["id"]}'
        if "viz" in s:
            spec, notes = writer.check_viz(jobs, jid, new, s, s["viz"])
            if spec:
                s["viz"] = spec
            else:
                del s["viz"]
            if notes:
                s["vizNotes"] = notes
        if s.get("code") and s["code"].get("runtime") not in ("pyodide", "local"):
            s["code"]["runtime"] = "pyodide"
    db.x("UPDATE card_proposals SET status='superseded' WHERE concept_id=? AND status='pending'", (cid,))
    db.x("INSERT INTO card_proposals(ts, concept_id, base_version, body, summary, changes, status) VALUES(?,?,?,?,?,?,'pending')",
         (now(), cid, card["version"], dumps(new), out["summary"], dumps(out["changes"])))
    jobs.progress(jid, f"proposed {len(out['changes'])} change(s)")
    return {"changed": True}



# ---------------------------------------------------------------- feedback: sort and apply (SPEC §11)

CLASSIFY_SCHEMA = {"type": "object", "required": ["kind", "why"], "properties": {
    "kind": {"enum": list(fb.KINDS)}, "why": {"type": "string"}}}


def run_classify_feedback(jobs: Jobs, jid: int, d: dict) -> dict:
    """The agent's proposal for an item's kind. Never overrides the learner's own choice."""
    db = jobs.db
    f = db.one("SELECT * FROM feedback WHERE id=?", (d["feedback_id"],))
    if not f or f["deleted"] or f["kind_source"] == "learner":
        return {"skipped": True}
    c = db.one("SELECT title FROM concepts WHERE id=?", (f["concept_id"],))
    card = state.latest_card(db, f["concept_id"]) or {}
    heading = next((s["heading"] for s in card.get("sections", []) if s["id"] == f["section_id"]), None)
    out = jobs.call(jid, "Feedback", Call(
        prompt=prompt("classify_feedback", concept=c["title"] if c else f["concept_id"],
                      target=f'section "{heading}"' if heading else "the whole lesson",
                      tags=", ".join(loads(f["tags"], [])) or "(none)", text=f["text"] or "(none)"),
        schema=CLASSIFY_SCHEMA, model="haiku", timeout=120))
    f = db.one("SELECT * FROM feedback WHERE id=?", (d["feedback_id"],))  # the learner may have edited it meanwhile
    if f and not f["deleted"] and f["kind_source"] != "learner" and out["kind"] != f["kind"]:
        fb.resignal(db, f["id"], kind=out["kind"], kind_source="agent")
        jobs.progress(jid, f'kind: {out["kind"]} ({out["why"]})'[:300])
    elif f and f["kind_source"] == "auto":
        db.x("UPDATE feedback SET kind_source='agent' WHERE id=?", (f["id"],))
    return {"kind": out["kind"]}


APPLY_SCHEMA = {"type": "object", "required": ["items", "sections", "changes", "summary"], "properties": {
    "items": {"type": "array", "items": {"type": "object", "required": ["id", "kind", "why"], "properties": {
        "id": {"type": "integer"}, "kind": {"enum": list(fb.KINDS)}, "why": {"type": "string"}}}},
    "sections": {"type": "array", "items": {"type": "object", "required": ["id", "body"], "properties": {
        "id": {"type": "string"}, "body": {"type": "string"}}}},
    "changes": {"type": "array", "items": {"type": "object",
                "required": ["section_id", "feedback_ids", "why", "how", "technique", "related_because"],
                "properties": {"section_id": {"type": "string"}, "feedback_ids": {"type": "array", "items": {"type": "integer"}},
                               "why": {"type": "string"}, "how": {"type": "string"}, "technique": {"type": "string"},
                               "related_because": {"type": "string"}}}},
    "summary": {"type": "string"}}}


def _target(f: dict) -> str:
    """Where a feedback item points: the whole lesson, a section, or a quoted part of a section."""
    ref = loads(f["ref"], None) if f.get("ref") else None
    where = f["section_id"] or "whole lesson"
    if not ref:
        return where
    what = {"text": "the text", "formula": "the formula", "viz": "the interactive graph"}[ref["kind"]]
    quote = f' {json.dumps(ref["quote"], ensure_ascii=False)}' if ref.get("quote") else ""
    return f"{where}, about {what}{quote}"


def _apply_inputs(db: DB, d: dict) -> tuple[dict, dict, list[dict], dict]:
    cid = d["concept_id"]
    base = versions.get(db, cid, d["base_version"])
    card = state.latest_card(db, cid)
    if not base or not card:
        raise ValueError("the lesson version to revise no longer exists")
    ids = d["feedback_ids"]
    rows = db.q(f"SELECT * FROM feedback WHERE deleted=0 AND id IN ({','.join('?' * len(ids))}) ORDER BY id", ids)
    return base, card, rows, {s["id"]: s for s in card["sections"]}


def _save_applied(jobs: Jobs, jid: int, d: dict, base: dict, sections: dict[str, str], angles: dict[str, str],
                  changes: list[dict], summary: str, source: str) -> int:
    db, cid = jobs.db, d["concept_id"]
    applied = sorted({i for c in changes for i in c["feedbackIds"]})
    pb = state.playbook(db)
    v = versions.create(db, cid, parent=base["version"], card_version=base["card_version"],
                        playbook_version=pb["version"], style=base["style"], angles=angles,
                        sections={**base["sections"], **sections}, source="apply", summary=summary,
                        feedback_ids=applied, changes=changes, chosen=True)
    # The applied version already answers the current playbook ("me" feedback included): not stale.
    db.x("UPDATE renditions SET card_version=?, playbook_version=?, style=?, section_angles=? WHERE concept_id=?",
         (base["card_version"], pb["version"], base["style"], dumps(angles), cid))
    left = [i for i in d["feedback_ids"] if i not in applied]
    jobs.progress(jid, f"lesson version v{v}: {len(changes)} change(s)" + (f"; not applied: #{', #'.join(map(str, left))}" if left else ""))
    return v


def run_apply_feedback(jobs: Jobs, jid: int, d: dict) -> dict:
    """One agent call revises the lesson for the selected feedback. The fact guard keeps it to prose."""
    db, cid = jobs.db, d["concept_id"]
    base, card, rows, secs = _apply_inputs(db, d)
    if not rows:
        return {"version": None}
    pb, g = state.playbook(db), _goal(db)
    lesson_text = "\n\n".join(
        f'## {sid} "{secs[sid]["heading"]}" (angle: {base["angles"].get(sid)})\n{body}'
        for sid, body in base["sections"].items() if sid in secs)
    fb_text = "\n".join(
        f'- #{f["id"]} kind={f["kind"]} target={_target(f)} tags={", ".join(loads(f["tags"], [])) or "-"}'
        f' words={json.dumps(f["text"] or "", ensure_ascii=False)}' for f in rows)
    out = jobs.call(jid, "Feedback", Call(
        prompt=prompt("apply_feedback", card=_card_text(card), goal=g["title"], profile=g["profile"],
                      playbook=state.playbook_text(pb), reverts=versions.reverts_text(db), base=base["version"],
                      guidelines=guidelines.text(db),
                      lesson=lesson_text, feedback=fb_text, **pb["adjust"]),
        schema=APPLY_SCHEMA, model="sonnet", timeout=420))
    by_id = {f["id"]: f for f in rows}
    # Items the agent sees as fact claims go to the card check, unless the learner said otherwise.
    facts = [by_id[i["id"]] for i in out.get("items", []) if i["kind"] == "fact" and i["id"] in by_id
             and by_id[i["id"]]["kind_source"] != "learner"]
    for f in facts:
        fb.resignal(db, f["id"], kind="fact", kind_source="agent")
    if facts:
        from .actions import route_facts
        route_facts(db, jobs, cid, [db.one("SELECT * FROM feedback WHERE id=?", (f["id"],)) for f in facts])
        jobs.progress(jid, f"sent to the card check: #{', #'.join(str(f['id']) for f in facts)}")
    fact_ids = {f["id"] for f in facts}
    for i in out.get("items", []):  # the agent's view of the other kinds, as a proposal
        f = by_id.get(i["id"])
        if f and i["id"] not in fact_ids and f["kind_source"] == "auto" and i["kind"] != f["kind"]:
            fb.resignal(db, f["id"], kind=i["kind"], kind_source="agent")
    accepted, rejected = versions.fact_guard(card, base["sections"], out.get("sections", []))
    for r in rejected:
        jobs.progress(jid, f'fact guard rejected {r["sectionId"]}: {r["reason"]}')
    allowed = set(by_id) - fact_ids
    changes = []
    for c in out.get("changes", []):
        ids = [i for i in c.get("feedback_ids", []) if i in allowed]
        if c.get("section_id") not in accepted or not ids:
            continue
        # Scope: feedback about one part changes that part. Another section may change only when the agent
        # says why it is directly relevant or has the same issue; whole-lesson feedback may change any section.
        targets = {by_id[i]["section_id"] for i in ids}
        related = (c.get("related_because") or "").strip()
        if None not in targets and c["section_id"] not in targets and not related:
            jobs.progress(jid, f'dropped {c["section_id"]}: outside the part your feedback is about, with no reason given')
            continue
        changes.append({"sectionId": c["section_id"], "feedbackIds": ids, "why": c.get("why", ""),
                        "how": c.get("how", ""), "technique": (c.get("technique") or "").strip()[:60],
                        "relatedBecause": related if c["section_id"] not in targets else ""})
    for sid in accepted:  # every accepted section needs an explanation, or it is not taken
        if not any(c["sectionId"] == sid for c in changes):
            jobs.progress(jid, f"dropped {sid}: no reason given for the change")
    sections = {sid: body for sid, body in accepted.items() if any(c["sectionId"] == sid for c in changes)}
    if not sections:
        jobs.progress(jid, "no change was made to the lesson")
        return {"version": None, "rejected": rejected}
    v = _save_applied(jobs, jid, d, base, sections, dict(base["angles"]), changes, out.get("summary") or "Applied your feedback", "apply")
    return {"version": v, "rejected": rejected}


def fallback_apply_feedback(jobs: Jobs, jid: int, d: dict) -> None:
    """Offline: no model can rewrite prose, but an already-written angle can replace the one that missed.
    Each targeted section switches to the next angle that has cached prose for the same card and style."""
    db, cid = jobs.db, d["concept_id"]
    try:
        base, card, rows, secs = _apply_inputs(db, d)
    except ValueError:
        return
    ranking = engine.angle_ranking(state.playbook(db))
    angles, sections, changes = dict(base["angles"]), {}, []
    for f in rows:
        if f["kind"] == "fact":
            continue
        for sid in ([f["section_id"]] if f["section_id"] in secs else list(secs)):
            if sid in sections:
                continue
            cur = angles.get(sid)
            avail = secs[sid].get("angles") or list(engine.ANGLES)
            for a in [x for x in ranking if x in avail and x != cur]:
                row = db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                             (cid, base["card_version"], sid, a, base["style"]))
                if row:
                    angles[sid], sections[sid] = a, row["body"]
                    changes.append({"sectionId": sid, "feedbackIds": [f["id"]], "why": "Your feedback on this section",
                                    "how": f"Switched from the {cur} to the {a} angle (offline: no model was available, "
                                           "so an already-written explanation was used)", "technique": f"{a} angle"})
                    break
    if not sections:
        jobs.progress(jid, "offline: no other written explanation to switch to; try again when a model is available")
        return
    pinned = {**(state.rendition_row(db, cid) or {}).get("pinned", {}), **{sid: angles[sid] for sid in sections}}
    db.x("UPDATE renditions SET pinned=? WHERE concept_id=?", (dumps(pinned), cid))
    _save_applied(jobs, jid, d, base, sections, angles, changes, "Switched angles (offline)", "apply")



# ---------------------------------------------------------------- lesson guidelines (SPEC §12)

GUIDE_SCHEMA = {"type": "object", "required": ["items", "summary"], "properties": {
    "items": {"type": "array", "maxItems": guidelines.MAX_ITEMS, "items": {"type": "object",
              "required": ["text", "why", "feedback_ids", "by_learner"], "properties": {
                  "text": {"type": "string"}, "why": {"type": "string"},
                  "feedback_ids": {"type": "array", "items": {"type": "integer"}}, "by_learner": {"type": "boolean"}}}},
    "summary": {"type": "string"}}}


def _guideline_inputs(db: DB) -> dict:
    fb_rows = db.q("""SELECT f.*, c.title FROM feedback f JOIN concepts c ON c.id = f.concept_id
                      WHERE f.deleted = 0 ORDER BY f.id DESC LIMIT 60""")
    status = versions.feedback_status(db, fb_rows)
    feedback = "\n".join(
        f'- #{f["id"]} [{f["title"]}] kind={f["kind"]} status={status[f["id"]]["state"]} target={_target(f)}'
        f' tags={", ".join(loads(f["tags"], [])) or "-"} words={json.dumps(f["text"] or "", ensure_ascii=False)}' for f in fb_rows)
    kept = [c for v in db.q("SELECT changes FROM lesson_versions WHERE source='apply' ORDER BY ts DESC LIMIT 30")
            for c in loads(v["changes"], [])]
    applied = "\n".join(f'- {c.get("how", "")} (technique: {c.get("technique") or "n/a"})' for c in kept[:20]) or "(none)"
    g = guidelines.current(db)
    cur = "\n".join(f'- {"[learner] " if it.get("byLearner") else ""}{it["text"]}' for it in (g or {}).get("items", [])) or "(none yet)"
    return {"feedback": feedback or "(no feedback yet)", "applied": applied, "current": cur, "count": len(fb_rows)}


def run_distill_guidelines(jobs: Jobs, jid: int, d: dict) -> dict:
    """Distill the main points and patterns of all feedback so far into lesson guidelines, then write the next lesson."""
    db = jobs.db
    x = _guideline_inputs(db)
    if not x["count"] and not guidelines.current(db):
        jobs.progress(jid, "no feedback yet: nothing to learn from")
        _prewrite_next(jobs, jid, d)
        return {"version": None}
    out = jobs.call(jid, "Feedback", Call(
        prompt=prompt("distill_guidelines", goal=_goal(db)["title"], playbook=state.playbook_text(state.playbook(db)),
                      feedback=x["feedback"], applied=x["applied"], reverts=versions.reverts_text(db), current=x["current"]),
        schema=GUIDE_SCHEMA, model="sonnet", timeout=300))
    old = guidelines.current(db) or {"items": []}
    mine = [it for it in old["items"] if it.get("byLearner")]
    items = [{"text": it["text"], "why": it["why"], "feedbackIds": it.get("feedback_ids", []), "byLearner": it.get("by_learner")}
             for it in out["items"]]
    # The learner's own lines are never dropped by the job.
    texts = {" ".join(it["text"].lower().split()) for it in items}
    items = [{**it, "byLearner": True} for it in mine if " ".join(it["text"].lower().split()) not in texts] + items
    v = guidelines.save(db, items, "agent", out.get("summary", ""))
    jobs.progress(jid, f"lesson guidelines v{v}: {min(len(items), guidelines.MAX_ITEMS)} point(s)")
    _prewrite_next(jobs, jid, d)
    return {"version": v}


def fallback_distill_guidelines(jobs: Jobs, jid: int, d: dict) -> None:
    """Offline: keep the guidelines as they are, but still write the next lesson."""
    _prewrite_next(jobs, jid, d)


def _prewrite_next(jobs: Jobs, jid: int, d: dict) -> None:
    nxt = d.get("next")
    if nxt and state.latest_card(jobs.db, nxt):
        title = jobs.db.one("SELECT title FROM concepts WHERE id=?", (nxt,))["title"]
        jobs.progress(jid, f"writing your next lesson: {title}")
        progress.prewrite(jobs.db, jobs, nxt)


HANDLERS: dict[str, tuple[Callable, Callable | None]] = {
    "dictation_model": (dictation.run_download, None),
    "book_map": (bookstudy.run_map, None),
    "reasoning_review": (reasoning.run, reasoning.fallback),
    "formula_notes": (formulas.run, None),
    "formula_fields": (formula_fields.run, None),
    "lesson_graph": (lesson_graph.run, None),
    "lesson_step": (lesson_steps.run, None),
    "lesson_demo": (demos.run, None),
    "formula_lesson": (formula_lessons.run, None),
    "formula_open": (lambda jobs, jid, d: {"parts": formula_lessons.open_node(jobs, jid, d["node"])}, None),
    "render": (run_render, None),
    "tutor": (run_tutor, fallback_tutor),
    "roadmap_review": (run_roadmap_review, fallback_roadmap_review),
    "outline": (run_outline, None),
    "ingest_source": (lambda jobs, jid, d: sources.ingest(jobs.db, d["source_id"], lambda m: jobs.progress(jid, m)),
                      lambda jobs, jid, d: jobs.db.x("UPDATE sources SET status='error' WHERE id=?", (d["source_id"],))),
    "research_module": (run_research_module, fallback_research_module),
    "fact_check": (run_fact_check, None),
    "grade": (run_grade, fallback_grade),
    "probe_round": (probe.run_round, None),
    "session_sketch": (session.run_sketch, None),
    "session_probe": (session.run_probe, None),
    "session_turn": (session.run_turn, None),
    "session_extract": (session.run_extract, None),
    "practice_next": (practice.run_next, None),
    "practice_judge": (practice.run_judge, None),
    "reflect": (run_reflect, fallback_reflect),
    "runner_setup": (lambda jobs, jid, d: runner.setup(lambda msg: jobs.progress(jid, msg)), None),
    "refresh_card": (run_refresh_card, None),
    "classify_feedback": (run_classify_feedback, None),
    "apply_feedback": (run_apply_feedback, fallback_apply_feedback),
    "distill_guidelines": (run_distill_guidelines, fallback_distill_guidelines),
    "runner_docker_setup": (lambda jobs, jid, d: runner.setup_docker(lambda msg: jobs.progress(jid, msg)), None),
}
