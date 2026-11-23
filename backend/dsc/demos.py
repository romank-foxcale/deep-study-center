"""Generated interactive demos (SPEC §45): when a step needs something to move and no built-in widget can show it, an
agent builds a small single-file HTML demo from a precise brief. Phase 4 of the lessons rework.

Safety and trust:
- The HTML is checked here (``check``): one file, no network, no outside scripts or styles, no storage, no access to
  the page around it, a size limit. A demo with problems goes back to the agent once with the exact problems.
- The page runs it in a sandboxed iframe (scripts only: no same origin, so no cookies, no app API) with a
  Content-Security-Policy that blocks every request.
- Before the learner sees it, the page loads it hidden and operates it (every slider to both ends, every button once)
  and reports errors (``result``). A demo that fails is fixed once with the errors; if it fails again it is left out,
  and the step's text stands alone. A demo that passed is marked tested and shows at once from then on.

The demo lives in its step's section of the card: ``demo = {status, brief, html, title, watch, tries, errors, tested}``.
"""

from __future__ import annotations

import re

from . import state
from .db import DB, now

MAX_BYTES = 200_000
MAX_TRIES = 2  # the first build, and one fix after a failed check or test

SCHEMA = {"type": "object", "required": ["title", "html", "watch"], "properties": {
    "title": {"type": "string"}, "html": {"type": "string"}, "watch": {"type": "string"}}}

_FORBIDDEN = [
    (r"\bfetch\s*\(", "uses fetch(): demos may not load anything"),
    (r"XMLHttpRequest", "uses XMLHttpRequest: demos may not load anything"),
    (r"\bWebSocket\b|\bEventSource\b|sendBeacon", "opens a network connection"),
    (r"<script[^>]*\bsrc\s*=", "loads an outside script: put all code inline"),
    (r"<link\b", "loads an outside file (<link>): put all styles inline"),
    (r"@import", "imports an outside style"),
    (r"https?://(?!www\.w3\.org/)", "names an outside address: demos must work offline"),  # the SVG namespace is fine
    (r"\blocalStorage\b|\bsessionStorage\b|indexedDB|document\.cookie", "uses browser storage"),
    (r"\bwindow\.(parent|top|opener)\b|(?<![\w.])parent\.|(?<![\w.])top\.location", "reaches out of its frame"),
    (r"\beval\s*\(|new\s+Function\s*\(", "runs code from a string (eval / new Function)"),
    (r"<iframe\b|<object\b|<embed\b", "embeds another page"),
    (r"\balert\s*\(|\bconfirm\s*\(|\bprompt\s*\(", "opens a dialog (alert / confirm / prompt)"),
]


class DemoError(Exception):
    pass


def check(html: str) -> list[str]:
    """The problems that keep this HTML from being a safe, self-contained demo (empty when it is fine)."""
    problems = []
    if not html or not html.strip():
        return ["the demo is empty"]
    if len(html.encode("utf-8")) > MAX_BYTES:
        problems.append(f"the demo is larger than {MAX_BYTES // 1000} kB")
    low = html.lower()
    if "<script" not in low:
        problems.append("the demo has no script: it cannot move")
    if not re.search(r"<input\b|<button\b|<select\b|addEventListener\(\s*['\"](pointer|mouse|touch)", low):
        problems.append("the demo has no control (slider, button, select, or drag): the learner cannot operate it")
    for pattern, why in _FORBIDDEN:
        if re.search(pattern, html, re.I):
            problems.append(why)
    return problems


def request(db: DB, jobs, cid: str, sid: str, brief: str) -> None:
    """Start building a demo for a step (called by the step writer)."""
    from . import lesson_steps
    card = state.latest_card(db, cid)
    lesson_steps._save_section(db, cid, card["version"], sid, {"demo": {"status": "building", "brief": brief.strip()[:3000],
                                                                        "tries": 0, "errors": [], "tested": False}})
    if not jobs.active("lesson_demo", concept_id=cid, section_id=sid):
        jobs.enqueue("lesson_demo", "Build an interactive demo", {"concept_id": cid, "section_id": sid})


def _section(db: DB, cid: str, sid: str) -> tuple[dict, dict]:
    card = state.latest_card(db, cid)
    sec = next((s for s in (card or {}).get("sections", []) if s["id"] == sid), None)
    if not card or not sec or not sec.get("demo"):
        raise DemoError("this step has no demo")
    return card, sec


def run(jobs, jid: int, d: dict) -> dict:
    """Build (or fix) the demo of one step: the agent writes it, the code checks it, one fix round for problems."""
    from .jobs import prompt
    from .providers import Call
    from . import lesson_steps
    db = jobs.db
    cid, sid = d["concept_id"], d["section_id"]
    card, sec = _section(db, cid, sid)
    demo = dict(sec["demo"])
    errors = list(d.get("errors") or demo.get("errors") or [])
    previous = demo.get("html") if errors else ""
    body = (db.one("SELECT body FROM prose WHERE concept_id=? AND card_version=? AND section_id=?", (cid, card["version"], sid))
            or {}).get("body", "")
    for attempt in range(2):  # a build, then one fix of the problems the check finds
        jobs.progress(jid, ("fixing" if errors else "building") + f" the demo for “{sec['heading'][:50]}”")
        out = jobs.call(jid, "Lesson assets", Call(
            prompt=prompt("demo_build", brief=demo["brief"], step=f'{sec["heading"]}. {sec.get("purpose", "")}', text=body[:1500] or "(none)",
                          previous=previous or "(none: a first build)", errors="\n".join(f"- {e}" for e in errors) or "(none)"),
            schema=SCHEMA, model="sonnet", timeout=600))
        html = str(out.get("html") or "")
        problems = check(html)
        if not problems:
            break
        jobs.progress(jid, f"the check found {len(problems)} problem(s): asking for a fix")
        errors, previous = problems, html
    tries = int(demo.get("tries") or 0) + 1
    if problems:
        new = {**demo, "status": "failed", "errors": problems, "tries": tries}
    else:
        new = {**demo, "status": "ready", "html": html, "title": str(out.get("title") or "")[:80],
               "watch": str(out.get("watch") or "")[:400], "errors": [], "tries": tries, "tested": False,
               "version": int(demo.get("version") or 0) + 1, "builtAt": now()}
    lesson_steps._save_section(db, cid, card["version"], sid, {"demo": new})
    return {"status": new["status"], "problems": problems}


def result(db: DB, jobs, cid: str, sid: str, version: int, ok: bool, errors: list[str]) -> None:
    """What the page saw when it ran the demo hidden: tested, or one fix with the errors, or left out."""
    from . import lesson_steps
    card, sec = _section(db, cid, sid)
    demo = dict(sec["demo"])
    if demo.get("status") != "ready" or int(demo.get("version") or 0) != int(version):
        return  # an old version: ignore
    if ok:
        if not demo.get("tested"):
            lesson_steps._save_section(db, cid, card["version"], sid, {"demo": {**demo, "tested": True, "testedAt": now()}})
        return
    errs = [str(e)[:300] for e in errors][:8] or ["the demo failed when it was operated"]
    if int(demo.get("tries") or 0) < MAX_TRIES and not jobs.active("lesson_demo", concept_id=cid, section_id=sid):
        lesson_steps._save_section(db, cid, card["version"], sid, {"demo": {**demo, "status": "building", "errors": errs}})
        jobs.enqueue("lesson_demo", "Fix an interactive demo", {"concept_id": cid, "section_id": sid, "errors": errs})
    else:
        lesson_steps._save_section(db, cid, card["version"], sid, {"demo": {**demo, "status": "failed", "errors": errs}})


def public(demo: dict | None) -> dict | None:
    """The demo as the page gets it."""
    if not demo:
        return None
    out = {"status": demo.get("status"), "title": demo.get("title", ""), "watch": demo.get("watch", ""),
           "version": demo.get("version", 0), "tested": bool(demo.get("tested"))}
    if demo.get("status") == "ready":
        out["html"] = demo.get("html", "")
    return out
