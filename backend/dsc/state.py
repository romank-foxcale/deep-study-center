"""Read side: build the snapshots the UI renders. Nothing here writes."""

from __future__ import annotations

from datetime import datetime, timezone

from . import apikey, dictation, engine, providers, runner
from .db import DB, loads, workspace


def active_goal(db: DB) -> str | None:
    return db.meta("active_goal")


def playbook(db: DB) -> dict:
    return engine.replay_playbook(db.q("SELECT * FROM signals ORDER BY id"))


def concepts_raw(db: DB, goal_id: str) -> list[dict]:
    rows = db.q("""SELECT c.* FROM concepts c JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id = ? ORDER BY m.seq, t.ord, m.ord, c.ord""", (goal_id,))
    bodies = {r["concept_id"]: loads(r["body"]) for r in db.q(
        """SELECT c.concept_id, c.body FROM cards c WHERE c.version = (SELECT MAX(version) FROM cards WHERE concept_id = c.concept_id)""")}
    for r in rows:
        r["prereqs"] = loads(r["prereqs"], [])
        r["explain_items"] = [s["explain"]["id"] for s in bodies.get(r["id"], {}).get("sections", []) if s.get("explain")]
    _add_module_requires(db, goal_id, rows)
    return rows


def _add_module_requires(db: DB, goal_id: str, rows: list[dict]) -> None:
    """A module with ``requires`` (an Ohtani merge step) stays locked until every concept of those modules
    is learned. A required module that is not researched yet adds a placeholder prerequisite, so it stays
    locked; one that placement marked as known adds nothing."""
    mods = db.q("""SELECT m.id, m.requires, m.known FROM modules m JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id = ?""", (goal_id,))
    known = {m["id"] for m in mods if m["known"]}
    by_module: dict[str, list[str]] = {}
    for r in rows:
        by_module.setdefault(r["module_id"], []).append(r["id"])
    for m in mods:
        extra = []
        for rm in loads(m["requires"], []):
            if rm not in known:
                extra += by_module.get(rm) or [f"module:{rm}"]
        if extra:
            for r in rows:
                if r["module_id"] == m["id"]:
                    r["prereqs"] = r["prereqs"] + [p for p in extra if p not in r["prereqs"]]


def concept_states(db: DB, goal_id: str) -> tuple[list[dict], dict[str, engine.ConceptState]]:
    concepts = concepts_raw(db, goal_id)
    from . import graph
    ev = graph.evidence_for(db, [c["id"] for c in concepts])  # shared nodes: what was learned in other goals counts
    return concepts, engine.derive_concepts(concepts, ev)


def latest_card(db: DB, concept_id: str) -> dict | None:
    row = db.one("SELECT * FROM cards WHERE concept_id=? ORDER BY version DESC LIMIT 1", (concept_id,))
    if not row:
        return None
    return {"conceptId": concept_id, "version": row["version"], "factCheck": row["fact_check"],
            "checkedAt": row["checked_at"], **loads(row["body"])}


def public_card(card: dict) -> dict:
    """Card without answer keys or grading rubrics (the learner sees them only after answering)."""
    out = dict(card)
    sections = []
    for s in card.get("sections", []):
        s = dict(s)
        if s.get("check"):
            s["check"] = strip_check(s["check"])
        if s.get("explain"):
            s["explain"] = strip_explain(s["explain"])
        sections.append(s)
    out["sections"] = sections
    return out


def strip_check(check: dict) -> dict:
    return {k: v for k, v in check.items() if k not in ("answer", "explanation")}


def strip_explain(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("rubric", "exemplar")}


def rendition_row(db: DB, concept_id: str) -> dict | None:
    r = db.one("SELECT * FROM renditions WHERE concept_id=?", (concept_id,))
    if r:
        r["section_angles"], r["pinned"] = loads(r["section_angles"], {}), loads(r["pinned"], {})
    return r


def is_stale(r: dict | None, card: dict | None, pb: dict) -> bool:
    if not r:
        return False
    return r["playbook_version"] < pb["version"] or (card is not None and r["card_version"] < card["version"])


def answers(db: DB, concept_ids: list[str]) -> dict:
    """Latest answer per (concept, item), with the key revealed once answered."""
    out: dict[str, dict] = {}
    if not concept_ids:
        return out
    rows = db.q(f"""SELECT * FROM evidence WHERE voided=0 AND kind='practice' AND concept_id IN ({','.join('?' * len(concept_ids))})
                    ORDER BY id""", concept_ids)
    from .writer import effective_sections  # quiz questions made for this learner have their own keys
    cards = {cid: latest_card(db, cid) for cid in {r["concept_id"] for r in rows}}
    secs = {cid: effective_sections(db, cid, c) + (c or {}).get("sections", []) for cid, c in cards.items()}
    for r in rows:
        key = f'{r["concept_id"]}:{r["item_id"]}'
        item = {"choice": r["choice"], "correct": bool(r["correct"]), "score": r["score"],
                "thinking": r["thinking"] or "", "confidence": r["confidence"], "evidenceId": r["id"]}
        check = next((s["check"] for s in secs[r["concept_id"]] if (s.get("check") or {}).get("id") == r["item_id"]), None)
        if check:
            item.update(answer=check["answer"], explanation=check["explanation"])
        out[key] = item
    from . import reasoning
    reviews = reasoning.by_evidence(db, [v["evidenceId"] for v in out.values()])
    for v in out.values():
        v["review"] = reviews.get(v["evidenceId"])
    return out


def reasoning_log(db: DB, concept_id: str | None = None, limit: int = 10) -> str:
    """The learner's recent answers with their thinking and confidence, newest first, for the agents.
    Only answers with thinking or a confidence are listed: they show how the learner reasons, not just the result."""
    where = "voided=0 AND (thinking != '' OR confidence IS NOT NULL)" + (" AND concept_id=?" if concept_id else "")
    rows = db.q(f"SELECT * FROM evidence WHERE {where} ORDER BY id DESC LIMIT ?", ((concept_id,) if concept_id else ()) + (limit,))
    grads = db.q("SELECT * FROM gradings WHERE status='graded'" + (" AND concept_id=?" if concept_id else "")
                 + " ORDER BY id DESC LIMIT ?", ((concept_id,) if concept_id else ()) + (max(3, limit // 3),))
    from .writer import effective_sections
    titles = {r["id"]: r["title"] for r in db.q("SELECT id, title FROM concepts")}
    checks: dict[str, dict] = {}
    lines = []
    for r in rows:
        cid = r["concept_id"]
        if cid not in checks:
            card = latest_card(db, cid)
            checks[cid] = {s["check"]["id"]: s["check"] for s in effective_sections(db, cid, card) + (card or {}).get("sections", [])
                           if s.get("check")} if card else {}
        c = checks[cid].get(r["item_id"])
        result = "right" if r["correct"] else "wrong"
        if r["correct"] and r["confidence"] is not None and r["confidence"] <= 0.25:
            result = "right, but a guess"
        elif not r["correct"] and (r["confidence"] or 0) >= 0.75:
            result = "wrong while sure (a likely misconception)"
        head = f'- [{titles.get(cid, cid)}{", review" if r["kind"] == "review" else ""}] '
        if c:
            chose = c["options"][r["choice"]] if r["choice"] is not None and 0 <= r["choice"] < len(c["options"]) else "?"
            head += f'Q: {c["prompt"][:200]} | chose: {chose[:120]} ({result})'
        else:
            head += f"exercise {r['item_id']} ({result})"
        if r["confidence"] is not None:
            head += f' | confidence {round(r["confidence"] * 100)}%'
        if r["thinking"]:
            head += f' | thinking: "{r["thinking"][:600]}"'
        lines.append(head)
    for g in grads:
        conf = f', confidence {round(g["confidence"] * 100)}%' if g["confidence"] is not None else ""
        lines.append(f'- [{titles.get(g["concept_id"], g["concept_id"])}, explain-back, score {g["score"]}{conf}] '
                     f'"{g["answer"][:500]}" | grader: {(g["feedback"] or "")[:200]}')
    return "\n".join(lines) or "(none yet)"


def gradings(db: DB, concept_ids: list[str]) -> dict:
    from . import reasoning
    """Latest explain-back attempt per (concept, item): pending, graded or ungraded."""
    out: dict[str, dict] = {}
    if not concept_ids:
        return out
    for g in db.q(f"SELECT * FROM gradings WHERE concept_id IN ({','.join('?' * len(concept_ids))}) ORDER BY id", concept_ids):
        out[f'{g["concept_id"]}:{g["item_id"]}'] = {
            "id": g["id"], "status": g["status"], "answer": g["answer"], "score": g["score"],
            "feedback": g["feedback"], "missing": loads(g["missing"], []), "followup": g["followup"],
            "drawing": g.get("drawing"), "review": reasoning.grading_review(g)}
    return out


def probe_view(db: DB, gid: str) -> dict:
    from . import probe
    running = any(loads(j["input"], {}).get("goal_id") == gid
                  for j in db.q("SELECT input FROM jobs WHERE kind='probe_round' AND status IN ('queued', 'running')"))
    failed = db.one("""SELECT error FROM jobs WHERE kind='probe_round' AND input LIKE ? ORDER BY id DESC LIMIT 1""", (f'%"{gid}"%',))
    v = probe.view(db, gid, running)
    v["dismissed"] = db.meta(f"probe_dismissed:{gid}") == "1"
    v["error"] = (failed or {}).get("error") if not running and v["status"] != "done" else None
    return v


def snapshot(db: DB) -> dict:
    gid = active_goal(db)
    pb = playbook(db)
    from . import bookstudy, practice, session, sources
    from . import guidelines
    base = {"playbook": pb, "guidelines": guidelines.current(db), "providers": providers.status(), "apiKey": apikey.status(), "routes": routes(db), "jobs": jobs(db),
            "sources": sources.listing(db),
            "sessions": session.listing(db), "lastSession": db.meta("last_session"),
            "dictation": dictation.status(db),
            "studyBooks": bookstudy.listing(db), "lastBook": db.meta("last_book"), "mapView": db.meta("map_view") if db.meta("map_view") in ("hex", "tree") else "hex",
            "practices": practice.listing(db), "lastPractice": db.meta("last_practice"),
            "runner": runner_status(db),
            "backups": {"folder": str(workspace() / "backups"), "last": db.meta("last_backup"), "items": _backups()[:5]},
            "firstRun": db.meta("first_run") == "1" and not db.one("SELECT 1 FROM goals LIMIT 1"),
            "goals": [{"id": g["id"], "title": g["title"]} for g in db.q("SELECT id, title FROM goals WHERE kind != 'bookstudy' ORDER BY created_at")]}
    if not gid:
        return {**base, "goal": None, "tracks": [], "modules": [], "concepts": [], "cards": [], "renditions": [],
                "feedback": [], "notes": [], "diffs": [], "chats": {}, "answers": {}, "reviews": [], "gradings": {},
                "probe": None, "reflections": reflections(db), "settings": settings(db), "cardProposals": []}

    g = db.one("SELECT * FROM goals WHERE id=?", (gid,))
    tracks = db.q("SELECT * FROM tracks WHERE goal_id=? ORDER BY ord", (gid,))
    modules = db.q("""SELECT m.* FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id=? ORDER BY m.seq, t.ord, m.ord""", (gid,))
    concepts, states = concept_states(db, gid)
    ids = [c["id"] for c in concepts]
    cards = [c for c in (latest_card(db, i) for i in ids) if c]
    card_by = {c["conceptId"]: c for c in cards}
    rends = []
    for i in ids:
        r = rendition_row(db, i)
        if r:
            rends.append({"conceptId": i, "cardVersion": r["card_version"], "playbookVersion": r["playbook_version"],
                          "studied": bool(r["studied"]), "stale": is_stale(r, card_by.get(i), pb),
                          "sectionAngles": r["section_angles"], "pinned": r["pinned"]})
    in_goal = f"({','.join('?' * len(ids))})" if ids else "('')"
    now = datetime.now(timezone.utc).isoformat()
    return {
        **base,
        "goal": {"id": g["id"], "title": g["title"], "why": g["why"], "doneLooksLike": g["done"],
                 "hoursPerWeek": g["hours"], "profile": g["profile"], "layout": g["layout"], "kind": g["kind"]},
        "tracks": [{"id": t["id"], "title": t["title"], "summary": t["summary"], "pos": t["pos"],
                    "moduleIds": [m["id"] for m in modules if m["track_id"] == t["id"]]} for t in tracks],
        "modules": [{"id": m["id"], "trackId": m["track_id"], "title": m["title"], "research": m["research"], "known": bool(m["known"]),
                     "summary": m["summary"], "plannedConcepts": m["planned"], "ord": m["ord"],
                     "requires": loads(m["requires"], []), "doneWhen": m["done_when"],
                     "conceptIds": [c["id"] for c in concepts if c["module_id"] == m["id"]]} for m in modules],
        "concepts": [{"id": c["id"], "moduleId": c["module_id"], "title": c["title"], "objective": c["objective"],
                      "minutes": c["minutes"], "prereqs": [p for p in c["prereqs"] if p in states], "state": states[c["id"]].state,
                      "mastery": states[c["id"]].mastery} for c in concepts],
        "cards": [public_card(c) for c in cards],
        "renditions": rends,
        "feedback": feedback_items(db, ids),
        "notes": [{"id": n["id"], "ts": n["ts"], "conceptId": n["concept_id"], "quote": n["quote"], "text": n["text"]}
                  for n in db.q(f"SELECT * FROM notes WHERE concept_id IN {in_goal} ORDER BY id DESC", ids)],
        "diffs": [{"id": d["id"], "ts": d["ts"], "reason": d["reason"], "changes": loads(d["changes"]), "status": d["status"]}
                  for d in db.q("SELECT * FROM diffs WHERE goal_id=? ORDER BY id DESC", (gid,))],
        "chats": _chats(db, ids),
        "answers": answers(db, ids),
        "gradings": gradings(db, ids),
        "probe": probe_view(db, gid),
        "reflections": reflections(db),
        "settings": settings(db),
        "cardProposals": card_proposals(db, ids),
    }


def feedback_items(db: DB, ids: list[str]) -> list[dict]:
    """The feedback log with each item's kind and status (pending, applied in vN, reverted, ...)."""
    if not ids:
        return []
    from . import versions
    rows = db.q(f"SELECT * FROM feedback WHERE deleted=0 AND concept_id IN ({','.join('?' * len(ids))}) ORDER BY id DESC", ids)
    status = versions.feedback_status(db, rows)
    return [{"id": f["id"], "ts": f["ts"], "conceptId": f["concept_id"], "sectionId": f["section_id"],
             "tags": loads(f["tags"]), "text": f["text"], "effects": loads(f["effects"]), "kind": f["kind"],
             "kindSource": f["kind_source"], "angle": f["angle"], "updatedAt": f["updated_at"], "status": status[f["id"]],
             "ref": loads(f["ref"]) if f["ref"] else None}
            for f in rows]


def _chats(db: DB, ids: list[str]) -> dict:
    out: dict[str, list] = {}
    if not ids:
        return out
    for m in db.q(f"SELECT * FROM chats WHERE concept_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids):
        out.setdefault(m["concept_id"], []).append({"role": m["role"], "text": m["text"]})
    return out


def runner_status(db: DB) -> dict:
    return {"setUp": runner.is_set_up(), "packages": list(runner.PACKAGES), "mode": runner.mode(db),
            "dockerReady": runner.mode(db) == "docker" and runner.docker_ready()}


def _backups() -> list[dict]:
    from . import backup
    return backup.listing()


def settings(db: DB) -> dict:
    from . import planner
    p = planner.settings(db)
    return {"autoResearch": db.meta("auto_research", "1") == "1", "autoRefresh": db.meta("auto_refresh", "1") == "1",
            "lessonWriting": db.meta("lesson_writing", "steps"), "writingStyle": db.meta("writing_style", "ste") or "ste",
            "weeklyHours": p["weekly_hours"], "studyDays": p["study_days"], "startTime": p["start_time"]}


def card_proposals(db: DB, concept_ids: list[str]) -> list[dict]:
    if not concept_ids:
        return []
    rows = db.q(f"""SELECT * FROM card_proposals WHERE status = 'pending' AND concept_id IN ({','.join('?' * len(concept_ids))})
                    ORDER BY id DESC""", concept_ids)
    out = []
    for r in rows:
        current = latest_card(db, r["concept_id"]) or {}
        out.append({"id": r["id"], "ts": r["ts"], "conceptId": r["concept_id"], "baseVersion": r["base_version"],
                    "summary": r["summary"], "changes": loads(r["changes"], []),
                    "diff": card_diff(current, loads(r["body"], {}))})
    return out


def card_diff(old: dict, new: dict) -> list[dict]:
    """Field-level differences the learner reviews before approving a new card version."""
    out = []
    for k in ("objective", "core", "formal", "why"):
        if (old.get(k) or "") != (new.get(k) or ""):
            out.append({"field": k, "before": old.get(k) or "", "after": new.get(k) or ""})
    for k in ("misconceptions",):
        if old.get(k, []) != new.get(k, []):
            out.append({"field": k, "before": "\n".join(old.get(k, [])), "after": "\n".join(new.get(k, []))})
    old_src, new_src = {s["url"]: s for s in old.get("sources", [])}, {s["url"]: s for s in new.get("sources", [])}
    added = [f'{s["title"]} ({u})' for u, s in new_src.items() if u not in old_src]
    removed = [f'{s["title"]} ({u})' for u, s in old_src.items() if u not in new_src]
    if added or removed:
        out.append({"field": "sources", "before": "\n".join(removed), "after": "\n".join(added)})
    def norm(s: dict) -> dict:  # compare with defaults filled in, so normalisation alone isn't a "change"
        if s.get("code"):
            s = {**s, "code": {"runtime": "pyodide", **s["code"]}}
        return s

    old_secs = {s["id"]: norm(s) for s in old.get("sections", [])}
    new_secs = {s["id"]: norm(s) for s in new.get("sections", [])}
    for sid in list(old_secs) + [x for x in new_secs if x not in old_secs]:
        a, b = old_secs.get(sid), new_secs.get(sid)
        if a == b:
            continue
        label = (b or a)["heading"]
        if not b:
            out.append({"field": f"section: {label}", "before": "removed", "after": ""})
        elif not a:
            out.append({"field": f"section: {label}", "before": "", "after": "new section"})
        else:
            parts = [k for k in ("heading", "purpose", "angles", "check", "code", "explain", "viz") if a.get(k) != b.get(k)]
            out.append({"field": f"section: {label}", "before": "", "after": "changed: " + ", ".join(parts)})
    return out


def reflections(db: DB) -> list[dict]:
    return [{"id": r["id"], "ts": r["ts"], "summary": r["summary"], "proposals": loads(r["proposals"], []), "source": r["source"]}
            for r in db.q("SELECT * FROM reflections ORDER BY id DESC LIMIT 5")]


def routes(db: DB) -> list[dict]:
    rec = providers.RECOMMENDED
    return [{"role": r["role"], "description": r["description"], "provider": r["provider"], "model": r["model"],
             "recommended": {"provider": rec[r["role"]][0], "model": rec[r["role"]][1], "why": rec[r["role"]][2]}
             if r["role"] in rec else None}
            for r in db.q("SELECT * FROM routes ORDER BY ord")]


def route(db: DB, role: str) -> dict:
    return db.one("SELECT * FROM routes WHERE role=?", (role,)) or {"role": role, "provider": "claude", "model": "sonnet"}


def jobs(db: DB) -> list[dict]:
    rows = db.q("""SELECT * FROM jobs WHERE status IN ('queued', 'running')
                   OR id IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 10) ORDER BY id DESC""")
    return [{"id": j["id"], "kind": j["kind"], "status": j["status"], "label": j["label"],
             "progress": loads(j["progress"], []), "error": j["error"], "updatedAt": j["updated_at"],
             "input": {k: v for k, v in loads(j["input"], {}).items() if k in ("concept_id", "module_id")}}
            for j in rows]


def playbook_text(pb: dict) -> str:
    lines = [f'- {e["dimension"]} "{e["value"]}": {e["verdict"]} (score {e["score"]:.2f}, evidence {e["evidence"]:.1f})'
             + (f' - {e["note"]}' if e["note"] else "") for e in pb["entries"]]
    a = pb["adjust"]
    lines.append(f'- adjustments: pace {a["pace"]}, depth {a["depth"]}, rigor {a["rigor"]}')
    return "\n".join(lines)
