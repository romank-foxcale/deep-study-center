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

from . import engine, library, progress, providers, runner, state, viz
from .db import DB, dumps, loads, now, workspace
from .providers import Call, ProviderUnavailable

Runner = Callable[[dict, Call, object], tuple[object, str]]


def prompt(name: str, **fields: object) -> str:
    text = resources.files("dsc").joinpath(f"prompts/{name}.md").read_text(encoding="utf-8")
    rules = resources.files("dsc").joinpath("prompts/_rules.md").read_text(encoding="utf-8")
    fields.setdefault("rules", rules)
    # Plain replacement (not str.format) so braces in learner text or LaTeX are safe.
    for k, v in fields.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "x"


class Jobs:
    def __init__(self, db: DB, runner: Runner | None = None, inline: bool = False):
        self.db = db
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
        self.db.x("UPDATE jobs SET progress=?, updated_at=? WHERE id=?", (dumps(steps + [msg]), now(), jid))

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
    db = jobs.db
    card = state.latest_card(db, d["concept_id"])
    pb, g = state.playbook(db), _goal(db)
    want = {s["id"]: s["angle"] for s in d["sections"]}
    heads = {s["id"]: s for s in card["sections"]}
    lines = "\n".join(f'- {sid} "{heads[sid]["heading"]}" ({heads[sid].get("purpose", "")}) -> angle: {a}' for sid, a in want.items())
    out = jobs.call(jid, "Renditions", Call(
        prompt=prompt("render", card=_card_text(card), goal=g["title"], profile=g["profile"],
                      playbook=state.playbook_text(pb), sections=lines, **pb["adjust"]),
        schema=RENDER_SCHEMA, model="sonnet", timeout=300))
    written = 0
    for s in out.get("sections", []):
        if s["id"] in want and s["body"].strip():
            db.x("INSERT OR REPLACE INTO prose VALUES(?,?,?,?,?,?,?,?)",
                 (d["concept_id"], d["card_version"], s["id"], want[s["id"]], d["style"], s["body"].strip(), "llm", now()))
            written += 1
    jobs.progress(jid, f"rendered {written} section(s)")
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
                      history="\n".join(f'{m["role"]}: {m["text"]}' for m in history), section=d.get("section") or "(unknown)"),
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
    out = jobs.call(jid, "Curriculum", Call(
        prompt=prompt("outline", answers="\n".join(f"Q: {a['q']}\nA: {a['a']}" for a in answers)),
        schema=OUTLINE_SCHEMA, model="opus", timeout=600))
    gid = f"g-{slug(out['title'], 24)}-{secrets.token_hex(2)}"
    profile = "\n".join(a["a"] for a in answers[1:] if a["a"].strip() and a["a"] != "(skipped)")
    hours = next((float(x) for x in re.findall(r"\d+(?:\.\d+)?", answers[3]["a"] if len(answers) > 3 else "")), 5.0)
    first_module = None
    with db.tx():
        db.conn.execute("INSERT INTO goals(id, title, why, done, hours, profile, created_at) VALUES(?,?,?,?,?,?,?)",
                        (gid, out["title"], out["why"], out["done"], hours, profile, now()))
        for ti, t in enumerate(out["tracks"]):
            tid = f"{gid}-t{ti}"
            db.conn.execute("INSERT INTO tracks VALUES(?,?,?,?,?)", (tid, gid, ti, t["title"], t["summary"]))
            for mi, m in enumerate(t["modules"]):
                mid = f"{tid}-m{mi}"
                first_module = first_module or mid
                db.conn.execute("INSERT INTO modules(id, track_id, ord, title, research, planned, summary) VALUES(?,?,?,?,?,?,?)",
                                (mid, tid, mi, m["title"], "outline", m["planned"], m["summary"]))
        db.conn.execute("INSERT INTO meta(key, value) VALUES('active_goal', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (gid,))
    jobs.progress(jid, f"roadmap: {len(out['tracks'])} tracks; writing a placement quiz and researching the first module")
    jobs.enqueue("placement_bank", "Write placement quiz", {"goal_id": gid})
    if first_module:
        db.x("UPDATE modules SET research='researching' WHERE id=?", (first_module,))
        jobs.enqueue("research_module", "Research first module", {"module_id": first_module})
    return {"goal_id": gid}


# ---------------------------------------------------------------- research a module into cards

_CHECK = {"type": "object", "required": ["prompt", "options", "answer", "explanation"], "properties": {
    "prompt": {"type": "string"}, "options": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
    "answer": {"type": "integer"}, "explanation": {"type": "string"}}}
_CODE = {"type": "object", "required": ["prompt", "starter", "tests"], "properties": {
    "prompt": {"type": "string"}, "starter": {"type": "string"}, "tests": {"type": "string"},
    "runtime": {"enum": ["pyodide", "local"]}}}
_EXPLAIN = {"type": "object", "required": ["prompt", "rubric"], "properties": {
    "prompt": {"type": "string"}, "rubric": {"type": "array", "minItems": 1, "items": {"type": "string"}}}}
_ANGLE = {"enum": list(engine.ANGLES)}
RESEARCH_SCHEMA = {"type": "object", "required": ["concepts"], "properties": {"concepts": {"type": "array", "minItems": 1, "items": {
    "type": "object", "required": ["key", "title", "objective", "minutes", "prereq_keys"], "properties": {
        "key": {"type": "string"}, "title": {"type": "string"}, "objective": {"type": "string"},
        "reuse_key": {"type": "string"},
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
    earlier = db.q("""SELECT m.title FROM modules m JOIN tracks t ON t.id=m.track_id WHERE t.goal_id=?
                      AND (t.ord < ? OR (t.ord = ? AND m.ord < ?)) ORDER BY t.ord, m.ord""", (g["id"], t["ord"], t["ord"], m["ord"]))
    db.x("UPDATE modules SET research='researching' WHERE id=?", (m["id"],))
    target = d.get("concept")  # single inserted concept: research just that one
    out = jobs.call(jid, "Research", Call(
        prompt=prompt("research_module", goal=g["title"], profile=g["profile"], track=t["title"],
                      module=target["title"] if target else m["title"],
                      summary=target["detail"] if target else (m["summary"] or "no summary"),
                      earlier=", ".join(e["title"] for e in earlier) or "none",
                      planned=1 if target else (m["planned"] or 8), library=library.index_text(db)),
        schema=RESEARCH_SCHEMA, model="opus", tools=("WebSearch", "WebFetch"), timeout=1800, max_turns=60))
    concepts = []
    for c in (out["concepts"][:1] if target else out["concepts"]):
        reused = library.take(db, c["reuse_key"]) if c.get("reuse_key") else None
        if reused:  # an existing fact-checked card from the shared library
            c = {**c, "card": reused, "reused": True}
        if c.get("card"):
            concepts.append(c)
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
                    s["check"]["id"] = f'q-{s["id"]}'
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
        jobs.db.x("UPDATE modules SET research='outline' WHERE id=?", (d["module_id"],))


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

GRADE_SCHEMA = {"type": "object", "required": ["score", "feedback", "missing", "followup"], "properties": {
    "score": {"enum": [0, 0.5, 1]}, "feedback": {"type": "string"},
    "missing": {"type": "array", "items": {"type": "string"}}, "followup": {"type": "string"}}}


def run_grade(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    g = db.one("SELECT * FROM gradings WHERE id=?", (d["grading_id"],))
    card = state.latest_card(db, g["concept_id"]) or {}
    sec = next(s for s in card.get("sections", []) if s.get("explain", {}).get("id") == g["item_id"])
    concept = db.one("SELECT title FROM concepts WHERE id=?", (g["concept_id"],))
    out = jobs.call(jid, "Grading", Call(
        prompt=prompt("grade", concept=concept["title"], question=sec["explain"]["prompt"],
                      rubric="\n".join(f"- {r}" for r in sec["explain"]["rubric"]), answer=g["answer"]),
        schema=GRADE_SCHEMA, model="sonnet", timeout=240))
    score = float(out["score"])
    db.x("UPDATE gradings SET status='graded', score=?, feedback=?, missing=?, followup=? WHERE id=?",
         (score, out["feedback"], dumps(out.get("missing", [])), out.get("followup") or "", g["id"]))
    progress.record_evidence(db, g["concept_id"], g["item_id"], score, angle=d.get("angle"))
    return {"score": score}


def fallback_grade(jobs: Jobs, jid: int, d: dict) -> None:
    jobs.db.x("UPDATE gradings SET status='ungraded', feedback=? WHERE id=?",
              ("No grader is available right now (see Settings → Providers). Your answer is saved; try again later.",
               d["grading_id"]))


# ---------------------------------------------------------------- placement question bank

PLACEMENT_SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "required": ["module_id", "prompt", "options", "answer", "explanation"], "properties": {
        "module_id": {"type": "string"}, "prompt": {"type": "string"},
        "options": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"}},
        "answer": {"type": "integer"}, "explanation": {"type": "string"}}}}}}


def run_placement_bank(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    g = db.one("SELECT * FROM goals WHERE id=?", (d["goal_id"],))
    mods = db.q("""SELECT m.id, m.title, m.summary FROM modules m JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id=? ORDER BY t.ord, m.ord""", (g["id"],))
    out = jobs.call(jid, "Placement", Call(
        prompt=prompt("placement", goal=g["title"], profile=g["profile"],
                      modules="\n".join(f'{m["id"]}: {m["title"]} - {m["summary"] or ""}' for m in mods)),
        schema=PLACEMENT_SCHEMA, model="sonnet", timeout=600))
    ids = {m["id"] for m in mods}
    n = 0
    for it in out["items"]:
        if it["module_id"] in ids and 0 <= it["answer"] < len(it["options"]):
            db.x("INSERT OR REPLACE INTO placement_items VALUES(?,?,?)", (g["id"], it["module_id"], dumps(it)))
            n += 1
    jobs.progress(jid, f"{n} placement questions ready")
    return {"items": n}


# ---------------------------------------------------------------- weekly reflection

REFLECT_SCHEMA = {"type": "object", "required": ["summary", "proposals"], "properties": {
    "summary": {"type": "string"},
    "proposals": {"type": "array", "maxItems": 4, "items": {"type": "object", "required": ["dimension", "value", "why"], "properties": {
        "dimension": {"enum": ["angle", "example-domain", "format", "pace", "depth", "rigor"]},
        "value": {"type": "string"}, "verdict": {"enum": ["works", "avoid", "trying"]},
        "delta": {"type": "integer"}, "why": {"type": "string"}}}}}}


def _reflection_inputs(db: DB) -> dict:
    fb = db.q("SELECT f.*, c.title FROM feedback f JOIN concepts c ON c.id = f.concept_id ORDER BY f.id DESC LIMIT 40")
    outcomes = db.q("""SELECT angle, COUNT(*) AS n, AVG(COALESCE(score, correct)) AS avg FROM evidence
                       WHERE angle IS NOT NULL AND voided = 0 GROUP BY angle""")
    return {
        "feedback": "\n".join(f'- [{f["title"]}] {", ".join(loads(f["tags"]))}' + (f': "{f["text"]}"' if f["text"] else "")
                              for f in fb) or "(no feedback yet)",
        "outcomes": "\n".join(f'- {o["angle"]}: {o["n"]} answers, {o["avg"] * 100:.0f}% correct' for o in outcomes) or "(none yet)",
        "notes": db.one("SELECT COUNT(*) AS n FROM notes")["n"],
        "studied": db.one("SELECT COUNT(*) AS n FROM renditions WHERE studied = 1")["n"],
        "fb_count": len(fb), "outcome_rows": outcomes,
    }


def run_reflect(jobs: Jobs, jid: int, d: dict) -> dict:
    db = jobs.db
    x = _reflection_inputs(db)
    out = jobs.call(jid, "Reflection", Call(
        prompt=prompt("reflect", goal=_goal(db)["title"], playbook=state.playbook_text(state.playbook(db)),
                      feedback=x["feedback"], outcomes=x["outcomes"], notes=x["notes"], studied=x["studied"]),
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
                      today=now()[:10]),
        schema=REFRESH_SCHEMA, model="opus", tools=("WebSearch", "WebFetch"), timeout=1200, max_turns=40))
    db.x("UPDATE cards SET refreshed_at=? WHERE concept_id=? AND version=?", (now(), cid, card["version"]))
    if not out.get("changed") or not out.get("card"):
        jobs.progress(jid, f"no changes needed: {out.get('summary', '')}"[:300])
        return {"changed": False, "summary": out.get("summary", "")}
    new = {**out["card"], "objective": out["card"].get("objective") or card["objective"]}
    old_ids = {s["id"]: s for s in card.get("sections", [])}
    for s in new.get("sections", []):
        prev = old_ids.get(s["id"], {})
        for kind, prefix in (("check", "q"), ("code", "x"), ("explain", "e")):
            if s.get(kind):  # keep item ids stable so past answers still line up
                s[kind]["id"] = prev.get(kind, {}).get("id") or f'{prefix}-{s["id"]}'
        if "viz" in s:
            s["viz"] = viz.validate(s["viz"])
            if not s["viz"]:
                del s["viz"]
        if s.get("code") and s["code"].get("runtime") not in ("pyodide", "local"):
            s["code"]["runtime"] = "pyodide"
    db.x("UPDATE card_proposals SET status='superseded' WHERE concept_id=? AND status='pending'", (cid,))
    db.x("INSERT INTO card_proposals(ts, concept_id, base_version, body, summary, changes, status) VALUES(?,?,?,?,?,?,'pending')",
         (now(), cid, card["version"], dumps(new), out["summary"], dumps(out["changes"])))
    jobs.progress(jid, f"proposed {len(out['changes'])} change(s)")
    return {"changed": True}


HANDLERS: dict[str, tuple[Callable, Callable | None]] = {
    "render": (run_render, None),
    "tutor": (run_tutor, fallback_tutor),
    "roadmap_review": (run_roadmap_review, fallback_roadmap_review),
    "outline": (run_outline, None),
    "research_module": (run_research_module, fallback_research_module),
    "fact_check": (run_fact_check, None),
    "grade": (run_grade, fallback_grade),
    "placement_bank": (run_placement_bank, None),
    "reflect": (run_reflect, fallback_reflect),
    "runner_setup": (lambda jobs, jid, d: runner.setup(lambda msg: jobs.progress(jid, msg)), None),
    "refresh_card": (run_refresh_card, None),
}
