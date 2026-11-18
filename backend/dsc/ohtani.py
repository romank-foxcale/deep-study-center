"""Ohtani table (Mandala Chart) roadmap: one goal, 8 areas x 8 steps, and 8 merge steps.

Grid: nine 3x3 blocks. The goal is the center cell of the center block. Each outer block is one area
(a track, ``pos`` TL..ML in clockwise ring order); its 8 cells around the area name are the area's
steps (modules), clockwise from the top-left cell. The 8 cells around the goal are merge steps (the
modules of a ninth track with ``pos`` C): merge i joins area i with its clockwise neighbour, and
``requires`` lists the steps of those two areas it builds on. Each step's sub-steps are its concepts.

``modules.seq`` is the global learning order: steps by wave (from the outline), interleaved across
areas, each merge right after the last step it requires.
"""

from __future__ import annotations

RING = ["TL", "TM", "TR", "MR", "BR", "BM", "BL", "ML"]
MAX_WAVE = 12

_STEP = {"type": "object", "required": ["title", "summary", "done_when", "planned", "wave"], "properties": {
    "title": {"type": "string"}, "summary": {"type": "string"}, "done_when": {"type": "string"},
    "planned": {"type": "integer"}, "wave": {"type": "integer"}}}
_REF = {"type": "object", "required": ["area", "step"], "properties": {"area": {"type": "integer"}, "step": {"type": "integer"}}}

SCHEMA = {"type": "object", "required": ["title", "why", "done", "areas", "merges"], "properties": {
    "title": {"type": "string"}, "why": {"type": "string"}, "done": {"type": "string"},
    "areas": {"type": "array", "minItems": 8, "maxItems": 8, "items": {
        "type": "object", "required": ["title", "summary", "pair_reason", "steps"], "properties": {
            "title": {"type": "string"}, "summary": {"type": "string"}, "pair_reason": {"type": "string"},
            "steps": {"type": "array", "minItems": 8, "maxItems": 8, "items": _STEP}}}},
    "merges": {"type": "array", "minItems": 8, "maxItems": 8, "items": {
        "type": "object", "required": ["title", "summary", "done_when", "planned", "requires"], "properties": {
            "title": {"type": "string"}, "summary": {"type": "string"}, "done_when": {"type": "string"},
            "planned": {"type": "integer"}, "requires": {"type": "array", "items": _REF}}}}}}


def _clamp(v: object, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def build(gid: str, out: dict) -> tuple[list[dict], list[dict]]:
    """Model output -> (tracks, modules) rows ready to insert. Tolerates sloppy numbers: waves are
    clamped and made non-decreasing within an area, and merge requirements outside the merge's two
    areas are dropped (a merge with none left requires both areas' capstones)."""
    areas = out["areas"][:8]
    merges = out["merges"][:8]
    if len(areas) != 8 or len(merges) != 8 or any(len(a["steps"]) < 8 for a in areas):
        raise ValueError("an Ohtani table needs 8 areas of 8 steps and 8 merges")
    tracks, modules, keys = [], [], {}
    for ai, a in enumerate(areas):
        tid = f"{gid}-t{ai}"
        tracks.append({"id": tid, "ord": ai, "title": a["title"], "summary": a["summary"], "pos": RING[ai]})
        wave = 1
        for si, st in enumerate(a["steps"][:8]):
            wave = max(wave, _clamp(st.get("wave"), 1, MAX_WAVE, wave))
            mid = f"{tid}-m{si}"
            modules.append({"id": mid, "track_id": tid, "ord": si, "title": st["title"], "summary": st["summary"],
                            "done_when": st["done_when"], "planned": _clamp(st.get("planned"), 1, 20, 6), "requires": []})
            keys[mid] = (wave, 0, si, ai)
    cid = f"{gid}-tc"
    tracks.append({"id": cid, "ord": 8, "title": "Merges", "pos": "C",
                   "summary": "Each step joins two neighbouring areas in one task toward the goal."})
    for i, mg in enumerate(merges):
        pair = (i, (i + 1) % 8)
        req = []
        for r in mg.get("requires") or []:
            a_i, s_i = _clamp(r.get("area"), 1, 8, 0) - 1, _clamp(r.get("step"), 1, 8, 8) - 1
            mid = f"{gid}-t{a_i}-m{s_i}"
            if a_i in pair and mid not in req:
                req.append(mid)
        for a_i in pair:  # a merge needs something from both of its areas
            if not any(m.startswith(f"{gid}-t{a_i}-") for m in req):
                req.append(f"{gid}-t{a_i}-m7")
        reason = areas[i].get("pair_reason", "").strip()
        summary = mg["summary"] + (f" Why these two: {reason}" if reason else "")
        mid = f"{cid}-m{i}"
        modules.append({"id": mid, "track_id": cid, "ord": i, "title": mg["title"], "summary": summary,
                        "done_when": mg["done_when"], "planned": _clamp(mg.get("planned"), 1, 20, 6), "requires": req})
        keys[mid] = (max(keys[r][0] for r in req), 1, max(keys[r][2] for r in req), i)
    for n, mid in enumerate(sorted(keys, key=keys.__getitem__), start=1):
        next(m for m in modules if m["id"] == mid)["seq"] = n
    return tracks, modules
