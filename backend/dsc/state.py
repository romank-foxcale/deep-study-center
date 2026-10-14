"""Read side: build the snapshots the UI renders. Nothing here writes."""

from __future__ import annotations

from datetime import datetime, timezone

from . import engine, providers, runner
from .db import DB, loads


def active_goal(db: DB) -> str | None:
    return db.meta("active_goal")


def playbook(db: DB) -> dict:
    return engine.replay_playbook(db.q("SELECT * FROM signals ORDER BY id"))


def concepts_raw(db: DB, goal_id: str) -> list[dict]:
    rows = db.q("""SELECT c.* FROM concepts c JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id = ? ORDER BY t.ord, m.ord, c.ord""", (goal_id,))
    bodies = {r["concept_id"]: loads(r["body"]) for r in db.q(
        """SELECT c.concept_id, c.body FROM cards c WHERE c.version = (SELECT MAX(version) FROM cards WHERE concept_id = c.concept_id)""")}
    for r in rows:
        r["prereqs"] = loads(r["prereqs"], [])
        r["explain_items"] = [s["explain"]["id"] for s in bodies.get(r["id"], {}).get("sections", []) if s.get("explain")]
    return rows


def concept_states(db: DB, goal_id: str) -> tuple[list[dict], dict[str, engine.ConceptState]]:
    concepts = concepts_raw(db, goal_id)
    ids = [c["id"] for c in concepts]
    ev = db.q(f"SELECT * FROM evidence WHERE concept_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids) if ids else []
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
    cards = {cid: latest_card(db, cid) for cid in {r["concept_id"] for r in rows}}
    for r in rows:
        key = f'{r["concept_id"]}:{r["item_id"]}'
        item = {"choice": r["choice"], "correct": bool(r["correct"]), "score": r["score"]}
        check = next((s["check"] for s in (cards[r["concept_id"]] or {}).get("sections", [])
                      if s.get("check", {}).get("id") == r["item_id"]), None)
        if check:
            item.update(answer=check["answer"], explanation=check["explanation"])
        out[key] = item
    return out


def gradings(db: DB, concept_ids: list[str]) -> dict:
    """Latest explain-back attempt per (concept, item): pending, graded or ungraded."""
    out: dict[str, dict] = {}
    if not concept_ids:
        return out
    for g in db.q(f"SELECT * FROM gradings WHERE concept_id IN ({','.join('?' * len(concept_ids))}) ORDER BY id", concept_ids):
        out[f'{g["concept_id"]}:{g["item_id"]}'] = {
            "id": g["id"], "status": g["status"], "answer": g["answer"], "score": g["score"],
            "feedback": g["feedback"], "missing": loads(g["missing"], []), "followup": g["followup"]}
    return out


def placement(db: DB, goal_id: str) -> dict:
    """Placement diagnostic state for a goal (question shown without its key)."""
    tracks = db.q("SELECT id FROM tracks WHERE goal_id=? ORDER BY ord", (goal_id,))
    order = [[m["id"] for m in db.q("SELECT id FROM modules WHERE track_id=? ORDER BY ord", (t["id"],))] for t in tracks]
    items = {r["module_id"]: loads(r["item"]) for r in db.q("SELECT * FROM placement_items WHERE goal_id=?", (goal_id,))}
    answers = db.q("SELECT * FROM placement_answers WHERE goal_id=? ORDER BY id", (goal_id,))
    asked_tracks = [[m for m in t if m in items] for t in order]
    res = engine.placement([t for t in asked_tracks if t], answers)
    nxt = res["next"]
    question = None
    if nxt:
        m = db.one("SELECT title FROM modules WHERE id=?", (nxt,))
        question = {"moduleId": nxt, "module": m["title"], "prompt": items[nxt]["prompt"], "options": items[nxt]["options"]}
    counts = {k: sum(1 for v in res["status"].values() if v == k) for k in ("known", "gap", "uncertain")}
    return {"available": bool(items), "finished": db.meta(f"placement_done:{goal_id}") == "1",
            "asked": res["asked"], "done": res["done"], "question": question, "counts": counts,
            "status": res["status"]}


def snapshot(db: DB) -> dict:
    gid = active_goal(db)
    pb = playbook(db)
    from . import library
    base = {"playbook": pb, "providers": providers.status(), "routes": routes(db), "jobs": jobs(db),
            "library": library.listing(db),
            "runner": {"setUp": runner.is_set_up(), "packages": list(runner.PACKAGES)},
            "ankiExport": db.meta("last_anki_export"),
            "goals": [{"id": g["id"], "title": g["title"]} for g in db.q("SELECT id, title FROM goals ORDER BY created_at")]}
    if not gid:
        return {**base, "goal": None, "tracks": [], "modules": [], "concepts": [], "cards": [], "renditions": [],
                "feedback": [], "notes": [], "diffs": [], "chats": {}, "answers": {}, "reviews": [], "gradings": {},
                "placement": None, "reflections": reflections(db), "settings": settings(db), "cardProposals": []}

    g = db.one("SELECT * FROM goals WHERE id=?", (gid,))
    tracks = db.q("SELECT * FROM tracks WHERE goal_id=? ORDER BY ord", (gid,))
    modules = db.q("""SELECT m.* FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id=? ORDER BY t.ord, m.ord""", (gid,))
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
                 "hoursPerWeek": g["hours"], "profile": g["profile"]},
        "tracks": [{"id": t["id"], "title": t["title"], "summary": t["summary"],
                    "moduleIds": [m["id"] for m in modules if m["track_id"] == t["id"]]} for t in tracks],
        "modules": [{"id": m["id"], "trackId": m["track_id"], "title": m["title"], "research": m["research"], "known": bool(m["known"]),
                     "summary": m["summary"], "plannedConcepts": m["planned"],
                     "conceptIds": [c["id"] for c in concepts if c["module_id"] == m["id"]]} for m in modules],
        "concepts": [{"id": c["id"], "moduleId": c["module_id"], "title": c["title"], "objective": c["objective"],
                      "minutes": c["minutes"], "prereqs": c["prereqs"], "state": states[c["id"]].state,
                      "mastery": states[c["id"]].mastery} for c in concepts],
        "cards": [public_card(c) for c in cards],
        "renditions": rends,
        "feedback": [{"id": f["id"], "ts": f["ts"], "conceptId": f["concept_id"], "sectionId": f["section_id"],
                      "tags": loads(f["tags"]), "text": f["text"], "effects": loads(f["effects"])}
                     for f in db.q(f"SELECT * FROM feedback WHERE concept_id IN {in_goal} ORDER BY id DESC", ids)],
        "notes": [{"id": n["id"], "ts": n["ts"], "conceptId": n["concept_id"], "quote": n["quote"], "text": n["text"]}
                  for n in db.q(f"SELECT * FROM notes WHERE concept_id IN {in_goal} ORDER BY id DESC", ids)],
        "diffs": [{"id": d["id"], "ts": d["ts"], "reason": d["reason"], "changes": loads(d["changes"]), "status": d["status"]}
                  for d in db.q("SELECT * FROM diffs WHERE goal_id=? ORDER BY id DESC", (gid,))],
        "chats": _chats(db, ids),
        "answers": answers(db, ids),
        "gradings": gradings(db, ids),
        "placement": placement(db, gid),
        "reflections": reflections(db),
        "settings": settings(db),
        "cardProposals": card_proposals(db, ids),
        "reviews": [{"conceptId": r["concept_id"], "due": r["due"], "isDue": r["due"] <= now}
                    for r in db.q(f"SELECT * FROM reviews WHERE concept_id IN {in_goal} ORDER BY due", ids)],
    }


def _chats(db: DB, ids: list[str]) -> dict:
    out: dict[str, list] = {}
    if not ids:
        return out
    for m in db.q(f"SELECT * FROM chats WHERE concept_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids):
        out.setdefault(m["concept_id"], []).append({"role": m["role"], "text": m["text"]})
    return out


def settings(db: DB) -> dict:
    from . import planner
    p = planner.settings(db)
    return {"autoResearch": db.meta("auto_research", "1") == "1", "autoRefresh": db.meta("auto_refresh", "1") == "1",
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
    return [{"role": r["role"], "description": r["description"], "provider": r["provider"], "model": r["model"]}
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
