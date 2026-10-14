"""Read side: build the snapshots the UI renders. Nothing here writes."""

from __future__ import annotations

from datetime import datetime, timezone

from . import engine, providers
from .db import DB, loads


def active_goal(db: DB) -> str | None:
    return db.meta("active_goal")


def playbook(db: DB) -> dict:
    return engine.replay_playbook(db.q("SELECT * FROM signals ORDER BY id"))


def concepts_raw(db: DB, goal_id: str) -> list[dict]:
    rows = db.q("""SELECT c.* FROM concepts c JOIN modules m ON m.id = c.module_id JOIN tracks t ON t.id = m.track_id
                   WHERE t.goal_id = ? ORDER BY t.ord, m.ord, c.ord""", (goal_id,))
    for r in rows:
        r["prereqs"] = loads(r["prereqs"], [])
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
    """Card without answer keys (the learner sees keys only after answering)."""
    out = dict(card)
    out["sections"] = [{**s, "check": strip_check(s["check"])} if s.get("check") else s for s in card.get("sections", [])]
    return out


def strip_check(check: dict) -> dict:
    return {k: v for k, v in check.items() if k not in ("answer", "explanation")}


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
        item = {"choice": r["choice"], "correct": bool(r["correct"])}
        check = next((s["check"] for s in (cards[r["concept_id"]] or {}).get("sections", [])
                      if s.get("check", {}).get("id") == r["item_id"]), None)
        if check:
            item.update(answer=check["answer"], explanation=check["explanation"])
        out[key] = item
    return out


def snapshot(db: DB) -> dict:
    gid = active_goal(db)
    pb = playbook(db)
    base = {"playbook": pb, "providers": providers.status(), "routes": routes(db), "jobs": jobs(db),
            "goals": [{"id": g["id"], "title": g["title"]} for g in db.q("SELECT id, title FROM goals ORDER BY created_at")]}
    if not gid:
        return {**base, "goal": None, "tracks": [], "modules": [], "concepts": [], "cards": [], "renditions": [],
                "feedback": [], "notes": [], "diffs": [], "chats": {}, "answers": {}, "reviews": []}

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
        "modules": [{"id": m["id"], "trackId": m["track_id"], "title": m["title"], "research": m["research"],
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
