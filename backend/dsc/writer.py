"""Writing one learner's lesson in steps, each by its own agent (SPEC §14):

1. Planner: per section the angle (a mix, see ``engine.choose_angles``), a brief for the writer, and whether the card's
   graph and quiz question fit this learner (keep / new / none).
2. Asset writer: the graphs and quiz questions the planner asked for, made for this learner from the card.
3. Prose writer: the section text, following each section's brief (and later the reviewer's fixes).
4. Reviewer: checks the whole lesson against the guidelines, playbook and recent feedback, and checks the new graphs
   and questions. Sections with prose problems are rewritten once; a new graph or question with a problem is dropped
   (the card's one is shown instead).

Every step reads the lesson guidelines. Only the prose writer is required: if a model is not available for another
step, the lesson is still written (with the card's graphs and questions). The plan, the assets made for this learner
and the review are stored per (lesson, card version) in ``lesson_plans``; the card itself never changes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from . import engine, guidelines, state, versions, viz, vizcheck
from .db import DB, dumps, loads, now
from .providers import Call

if TYPE_CHECKING:
    from .jobs import Jobs

PLAN_SCHEMA = {"type": "object", "required": ["sections", "summary"], "properties": {
    "summary": {"type": "string"},
    "sections": {"type": "array", "items": {"type": "object", "required": ["id", "angle", "brief", "viz", "check"], "properties": {
        "id": {"type": "string"}, "angle": {"enum": list(engine.ANGLES)}, "brief": {"type": "string"},
        "viz": {"enum": ["keep", "new", "none"]}, "check": {"enum": ["keep", "new"]}}}}}}

_CHECK = {"type": "object", "required": ["prompt", "options", "answer", "explanation"], "properties": {
    "prompt": {"type": "string"}, "options": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"}},
    "answer": {"type": "integer"}, "explanation": {"type": "string"}}}
ASSETS_SCHEMA = {"type": "object", "required": ["sections"], "properties": {"sections": {"type": "array", "items": {
    "type": "object", "required": ["id", "why"], "properties": {
        "id": {"type": "string"}, "why": {"type": "string"}, "viz": viz.SCHEMA, "check": _CHECK}}}}}

REVIEW_SCHEMA = {"type": "object", "required": ["issues", "summary"], "properties": {
    "summary": {"type": "string"},
    "issues": {"type": "array", "items": {"type": "object", "required": ["section_id", "part", "problem", "fix", "source"], "properties": {
        "section_id": {"type": "string"}, "part": {"enum": ["prose", "viz", "check"]}, "problem": {"type": "string"},
        "fix": {"type": "string"}, "source": {"type": "string"}}}}}}


# ---------------------------------------------------------------- stored plans and the effective lesson

def current_plan(db: DB, cid: str, card_version: int | None) -> dict | None:
    row = db.one("SELECT * FROM lesson_plans WHERE concept_id=? AND card_version=?", (cid, card_version)) if card_version else None
    if not row:
        return None
    return {"cardVersion": row["card_version"], "ts": row["ts"], "plan": loads(row["plan"], {}),
            "assets": loads(row["assets"], {}), "review": loads(row["review"], {})}


def _save(db: DB, cid: str, card_version: int, **parts: object) -> None:
    old = current_plan(db, cid, card_version) or {"plan": {}, "assets": {}, "review": {}}
    vals = {k: parts.get(k, old[k]) for k in ("plan", "assets", "review")}
    db.x("""INSERT INTO lesson_plans(concept_id, card_version, ts, plan, assets, review) VALUES(?,?,?,?,?,?)
            ON CONFLICT(concept_id, card_version) DO UPDATE SET ts=excluded.ts, plan=excluded.plan, assets=excluded.assets,
            review=excluded.review""", (cid, card_version, now(), dumps(vals["plan"]), dumps(vals["assets"]), dumps(vals["review"])))


def effective_sections(db: DB, cid: str, card: dict | None) -> list[dict]:
    """The card's sections with this learner's graphs and quiz questions in place of the card's ones.
    Each section gets ``vizMine`` / ``checkMine`` (made for this learner)."""
    if not card:
        return []
    p = current_plan(db, cid, card.get("version"))
    plan = {s["id"]: s for s in (p or {}).get("plan", {}).get("sections", [])}
    assets = (p or {}).get("assets", {})
    out = []
    for s in card.get("sections", []):
        s = dict(s)
        mine = assets.get(s["id"], {})
        s["vizMine"] = s["checkMine"] = False
        if mine.get("viz"):
            s["viz"], s["vizMine"] = mine["viz"], True
            s["vizNotes"] = mine.get("vizNotes") or []
        elif plan.get(s["id"], {}).get("viz") == "none":
            s.pop("viz", None)
        if mine.get("check"):
            s["check"], s["checkMine"] = mine["check"], True
        out.append(s)
    return out


def recent_feedback(db: DB, limit: int = 12) -> str:
    rows = db.q("""SELECT f.tags, f.text, f.kind, c.title FROM feedback f LEFT JOIN concepts c ON c.id = f.concept_id
                   WHERE f.deleted=0 ORDER BY f.id DESC LIMIT ?""", (limit,))
    lines = []
    for r in rows:
        tags = ", ".join(loads(r["tags"], []))
        lines.append(f'- on "{r["title"] or "?"}" ({r["kind"]}): {tags}{": " if tags and r["text"] else ""}{(r["text"] or "")[:300]}')
    return "\n".join(lines) or "(none yet)"


def _card_text(card: dict) -> str:
    keep = {k: card.get(k) for k in ("objective", "core", "formal", "why", "angles", "examples", "misconceptions")}
    keep["sections"] = [{"id": s["id"], "heading": s["heading"], "purpose": s.get("purpose", "")} for s in card.get("sections", [])]
    return json.dumps(keep, ensure_ascii=False, indent=1)


def _learner(db: DB) -> dict:
    gid = state.active_goal(db)
    g = db.one("SELECT * FROM goals WHERE id=?", (gid,)) or {"title": "", "profile": ""}
    pb = state.playbook(db)
    return {"goal": g["title"], "profile": g["profile"], "pb": pb, "playbook": state.playbook_text(pb),
            "guidelines": guidelines.text(db), "feedback": recent_feedback(db), "reasoning": state.reasoning_log(db)}


# ---------------------------------------------------------------- the steps

def write_prose(jobs: Jobs, jid: int, cid: str, card_version: int, style: str, want: dict[str, str],
                briefs: dict[str, str] | None = None, fixes: dict[str, str] | None = None) -> int:
    """Write the prose of the given sections (sid -> angle) and cache it; returns how many were written."""
    from .jobs import prompt
    db = jobs.db
    card = state.latest_card(db, cid)
    secs = {s["id"]: s for s in effective_sections(db, cid, card)}
    lr = _learner(db)
    lines = []
    for sid, a in want.items():
        s = secs[sid]
        line = f'- {sid} "{s["heading"]}" ({s.get("purpose", "")}) -> angle: {a}'
        if s.get("viz"):
            line += f'. Graph: {s["viz"].get("type")}, "{s["viz"].get("caption", "")}"'
        if (briefs or {}).get(sid):
            line += f". Plan: {briefs[sid]}"
        if (fixes or {}).get(sid):
            line += f". Fix: {fixes[sid]}"
        lines.append(line)
    out = jobs.call(jid, "Renditions", Call(
        prompt=prompt("render", card=_card_text(card), goal=lr["goal"], profile=lr["profile"], playbook=lr["playbook"],
                      sections="\n".join(lines), guidelines=lr["guidelines"], reasoning=lr["reasoning"], **lr["pb"]["adjust"]),
        schema={"type": "object", "required": ["sections"], "properties": {"sections": {"type": "array", "items": {
            "type": "object", "required": ["id", "body"], "properties": {"id": {"type": "string"}, "body": {"type": "string"}}}}}},
        model="sonnet", timeout=300))
    written = 0
    for s in out.get("sections", []):
        if s["id"] in want and s["body"].strip():
            db.x("INSERT OR REPLACE INTO prose VALUES(?,?,?,?,?,?,?,?)",
                 (cid, card_version, s["id"], want[s["id"]], style, s["body"].strip(), "llm", now()))
            written += 1
    return written


def _optional(jobs: Jobs, jid: int, step: str, fn):
    """Run an optional step; without a model (or on a bad answer) the lesson is written without it."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - an optional step must never stop the lesson
        jobs.progress(jid, f"{step}: skipped ({str(e)[:120]})")
        return None


def plan(jobs: Jobs, jid: int, cid: str, card: dict, r: dict) -> dict | None:
    from .jobs import prompt
    db = jobs.db
    lr = _learner(db)
    pinned = r.get("pinned") or {}
    lines = []
    for s in card["sections"]:
        suggest = r["section_angles"].get(s["id"])
        line = (f'- {s["id"]} "{s["heading"]}" ({s.get("purpose", "")}); allowed angles: {", ".join(s.get("angles") or engine.ANGLES)}; '
                f'suggested: {suggest}{" (pinned)" if s["id"] in pinned else ""}')
        line += f'; graph: {s["viz"].get("type")} "{s["viz"].get("caption", "")}"' if s.get("viz") else "; graph: none"
        line += f'; quiz: "{s["check"]["prompt"]}"' if s.get("check") else "; quiz: none"
        lines.append(line)
    out = jobs.call(jid, "Lesson planner", Call(
        prompt=prompt("plan_lesson", card=_card_text(card), sections="\n".join(lines), goal=lr["goal"], profile=lr["profile"],
                      playbook=lr["playbook"], guidelines=lr["guidelines"], feedback=lr["feedback"], reasoning=lr["reasoning"]),
        schema=PLAN_SCHEMA, model="sonnet", timeout=240))
    by = {s["id"]: s for s in card["sections"]}
    clean = []
    for p in out.get("sections", []):
        s = by.get(p.get("id"))
        if not s:
            continue
        allowed = s.get("angles") or list(engine.ANGLES)
        angle = pinned.get(s["id"]) or (p["angle"] if p.get("angle") in allowed else r["section_angles"].get(s["id"]))
        clean.append({"id": s["id"], "angle": angle, "brief": (p.get("brief") or "").strip()[:600],
                      "viz": p.get("viz") if p.get("viz") in ("keep", "new", "none") else "keep",
                      "check": p.get("check") if p.get("check") in ("keep", "new") else "keep"})
    return {"summary": (out.get("summary") or "")[:400], "sections": clean}


def check_viz(jobs: Jobs, jid: int, card: dict, section: dict, raw: dict) -> tuple[dict | None, list[str]]:
    """Compute a widget as the page will (viz.inspect). If something cannot work, send the widget and the exact
    problems back to an agent once, and keep the better version. Returns (widget or None, notes for the learner):
    the notes say what the app had to fix or remove, so the learner's lesson can show it."""
    from .jobs import prompt
    clean, problems = viz.inspect(raw)
    if not problems:
        return clean, []
    jobs.progress(jid, f'graph in “{section.get("heading", section.get("id"))}”: {len(problems)} problem(s), asking for a fix')
    try:
        fixed = jobs.call(jid, "Lesson assets", Call(
            prompt=prompt("fix_widget", card=_card_text(card) if card.get("sections") else json.dumps(card, ensure_ascii=False)[:4000],
                          section=section.get("heading", ""), purpose=section.get("purpose", ""),
                          widget=json.dumps(raw, ensure_ascii=False, indent=1), problems="\n".join(f"- {p}" for p in problems)),
            schema=viz.SCHEMA, model="sonnet", timeout=240))
        clean2, problems2 = viz.inspect(fixed)
    except Exception as e:  # noqa: BLE001 - without a fix the cleaned widget is still shown
        jobs.progress(jid, f"graph fix skipped ({str(e)[:100]})")
        clean2, problems2 = None, problems
    if clean2 is not None and (clean is None or len(problems2) < len(problems)):
        notes = [f"The app found {len(problems)} problem(s) in this graph and the writer fixed "
                 f"{len(problems) - len(problems2)}."] + problems2
        return clean2, notes
    return clean, problems


def make_assets(jobs: Jobs, jid: int, cid: str, card: dict, plan_: dict) -> dict:
    from .jobs import prompt
    db = jobs.db
    by = {s["id"]: s for s in card["sections"]}
    asks = [p for p in plan_["sections"] if p["viz"] == "new" or p["check"] == "new"]
    if not asks:
        return {}
    lines = []
    for p in asks:
        s = by[p["id"]]
        want = [w for w, on in (("a graph", p["viz"] == "new"), ("a quiz question", p["check"] == "new")) if on]
        lines.append(f'- {p["id"]} "{s["heading"]}" ({s.get("purpose", "")}): make {" and ".join(want)}. Planner: {p["brief"]}')
    out = jobs.call(jid, "Lesson assets", Call(
        prompt=prompt("lesson_assets", card=_card_text(card), guidelines=guidelines.text(db), requests="\n".join(lines)),
        schema=ASSETS_SCHEMA, model="sonnet", timeout=300))
    wanted = {p["id"]: p for p in asks}
    assets: dict[str, dict] = {}
    for a in out.get("sections", []):
        p = wanted.get(a.get("id"))
        if not p:
            continue
        item: dict = {"why": (a.get("why") or "")[:300]}
        if p["viz"] == "new" and a.get("viz"):
            spec, notes = check_viz(jobs, jid, card, by[p["id"]], a["viz"])
            if spec:
                item["viz"] = spec
                if notes:
                    item["vizNotes"] = notes
        c = a.get("check")
        if p["check"] == "new" and c and isinstance(c.get("options"), list) and 2 <= len(c["options"]) <= 5 \
                and isinstance(c.get("answer"), int) and 0 <= c["answer"] < len(c["options"]):
            item["check"] = {"id": f'p-{p["id"]}', "prompt": c["prompt"], "options": [str(o) for o in c["options"]],
                             "answer": c["answer"], "explanation": c.get("explanation", "")}
        if item.get("viz") or item.get("check"):
            assets[p["id"]] = item
    return assets


def review(jobs: Jobs, jid: int, cid: str, card: dict, r: dict) -> dict:
    from .jobs import prompt
    db = jobs.db
    lr = _learner(db)
    parts = []
    for s in effective_sections(db, cid, card):
        a = r["section_angles"].get(s["id"])
        body = db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=? AND angle=? AND style=?",
                      (cid, r["card_version"], s["id"], a, r["style"]))
        block = [f'## {s["id"]} "{s["heading"]}" (angle: {a})', (body or {}).get("body") or "(not written)"]
        if s.get("viz"):
            block.append(f'Graph{" (made for you)" if s["vizMine"] else ""}: {json.dumps(s["viz"], ensure_ascii=False)}')
            numbers = vizcheck.describe(s["viz"])
            if numbers:  # what the page will show, computed: the reviewer checks each "why" against these
                block.append(f"Graph numbers (computed as the page shows them): {numbers}")
        if s.get("check"):
            c = s["check"]
            block.append(f'Quiz{" (made for you)" if s["checkMine"] else ""}: {c["prompt"]} Options: '
                         + " | ".join(f"{i}) {o}" for i, o in enumerate(c["options"])) + f'. Marked answer: {c.get("answer")}')
        parts.append("\n".join(block))
    out = jobs.call(jid, "Lesson review", Call(
        prompt=prompt("review_lesson", card=_card_text(card), playbook=lr["playbook"], guidelines=lr["guidelines"],
                      feedback=lr["feedback"], lesson="\n\n".join(parts)),
        schema=REVIEW_SCHEMA, model="sonnet", timeout=300))
    ids = {s["id"] for s in card["sections"]}
    issues = [{"sectionId": i["section_id"], "part": i["part"], "problem": i["problem"][:300], "fix": i["fix"][:300],
               "source": (i.get("source") or "")[:200]}
              for i in out.get("issues", []) if i.get("section_id") in ids and i.get("part") in ("prose", "viz", "check")]
    return {"summary": (out.get("summary") or "")[:400], "issues": issues}


def write_lesson(jobs: Jobs, jid: int, d: dict) -> dict:
    """The whole lesson: plan → graphs and questions → prose → review → one round of fixes."""
    db, cid = jobs.db, d["concept_id"]
    card = state.latest_card(db, cid)
    r = state.rendition_row(db, cid)
    if not card or not r or r["card_version"] != d["card_version"]:
        return {"written": 0}
    want = {s["id"]: s["angle"] for s in d["sections"]}

    jobs.progress(jid, "planning the lesson for you")
    p = _optional(jobs, jid, "plan", lambda: plan(jobs, jid, cid, card, r))
    briefs: dict[str, str] = {}
    if p:
        angles = dict(r["section_angles"])
        for s in p["sections"]:
            briefs[s["id"]] = s["brief"]
            if s["id"] in angles and s["angle"] != angles[s["id"]]:
                angles[s["id"]] = s["angle"]
                if s["id"] in want:
                    want[s["id"]] = s["angle"]
        db.x("UPDATE renditions SET section_angles=? WHERE concept_id=?", (dumps(angles), cid))
        r = state.rendition_row(db, cid)
        _save(db, cid, card["version"], plan=p, assets={}, review={})
        mix = sorted(set(angles.values()))
        jobs.progress(jid, f"plan: {', '.join(mix)}; {sum(1 for s in p['sections'] if s['viz'] == 'new')} new graph(s), "
                           f"{sum(1 for s in p['sections'] if s['check'] == 'new')} new question(s)")
        assets = _optional(jobs, jid, "graphs and questions", lambda: make_assets(jobs, jid, cid, card, p))
        if assets:
            _save(db, cid, card["version"], assets=assets)
            jobs.progress(jid, f"made {sum(1 for a in assets.values() if a.get('viz'))} graph(s) and "
                               f"{sum(1 for a in assets.values() if a.get('check'))} question(s) for you")

    jobs.progress(jid, "writing the text")
    written = write_prose(jobs, jid, cid, card["version"], r["style"], want, briefs)

    rv = _optional(jobs, jid, "review", lambda: review(jobs, jid, cid, card, state.rendition_row(db, cid)))
    if rv is not None:
        fixes: dict[str, str] = {}
        dropped = []
        stored = (current_plan(db, cid, card["version"]) or {}).get("assets", {})
        for i in rv["issues"]:
            if i["part"] == "prose":
                fixes[i["sectionId"]] = (fixes.get(i["sectionId"], "") + " " + i["fix"]).strip()
            elif stored.get(i["sectionId"], {}).get(i["part"]):
                stored[i["sectionId"]].pop(i["part"], None)  # back to the card's graph or question
                dropped.append(f'{i["sectionId"]}:{i["part"]}')
        stored = {k: v for k, v in stored.items() if v.get("viz") or v.get("check")}
        fixed = []
        if fixes:
            r2 = state.rendition_row(db, cid)
            jobs.progress(jid, f"review: fixing {len(fixes)} section(s)")
            redo = {sid: r2["section_angles"][sid] for sid in fixes if sid in r2["section_angles"]}
            ok = _optional(jobs, jid, "fixes", lambda: write_prose(jobs, jid, cid, card["version"], r2["style"], redo, briefs, fixes))
            fixed = sorted(redo) if ok else []
        _save(db, cid, card["version"], assets=stored, review={**rv, "fixed": fixed, "dropped": dropped})
        jobs.progress(jid, f"review: {len(rv['issues'])} problem(s) found" + (f", {len(fixed)} section(s) rewritten" if fixed else ""))

    v = versions.sync(db, cid, by_writer=True, rewrite=bool(d.get("rewrite")))
    if v:
        jobs.progress(jid, f"saved as lesson version v{v}")
    return {"written": written, "planned": bool(p), "reviewed": rv is not None}
