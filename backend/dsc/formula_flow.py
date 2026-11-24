"""The formula flow of a formula page (SPEC §52): where each part of a formula comes from, as a graph the learner can
operate. The design is the approved mock "A" (web/public/_mocks/formula-graph-a.html).

A flow has **inputs** (values the learner drags, grouped into input boxes) and **formula boxes**: each box defines one
quantity from inputs and earlier boxes (``uses``), with its formula in TeX (``tex``, naming other quantities as
``{id}``), a calculator form (``expr``; a list for a small vector, whose parts are ``id_1``, ``id_2``, ...), and a short
explanation (``say``). A main box may have 1-3 **what ifs**: another form of one part (``tex``, ``expr``), why it
works or breaks (``why``) and whether the formula still does its job (``ok``).

An agent writes the flow (job ``formula_flow``, prompt ``formula_flow.md``) when a formula page is written, or when the
learner asks. Code checks it (``check``) the way the page computes it: every name is known, every box computes at the
start values and at each input's minimum and maximum, the boxes come in order (a box uses only earlier ones), and the
sizes stay small. A flow with problems goes back to the agent once, with the problems.
"""

from __future__ import annotations

import math
import re

from . import vizcheck
from .db import DB, dumps, loads, now

MAX_INPUTS, MAX_BOXES, MAX_VECTOR, MAX_WHATIF = 10, 14, 6, 3
_ID = re.compile(r"^[a-z][a-z0-9]{0,11}$")  # no "_": a vector's parts are id_1, id_2, ...
_REF = re.compile(r"\{([a-z][a-z0-9]{0,11})\}")
RESERVED = set(vizcheck.FUNCS) | set(vizcheck.CONSTS) | {"x"}

_IDEA = {"type": "object", "required": ["id", "label", "tex"], "properties": {
    "id": {"type": "string"}, "sym": {"type": "string"}, "label": {"type": "string"}, "tex": {"type": "string"},
    "say": {"type": "string"}, "input": {"type": "array", "items": {"type": "string"}},
    "uses": {"type": "array", "items": {"type": "string"}},
    "expr": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
    "whatif": {"type": "array", "items": {"type": "object", "required": ["tex", "expr", "why"], "properties": {
        "tex": {"type": "string"}, "expr": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "why": {"type": "string"}, "ok": {"type": "boolean"}}}}}}
SCHEMA = {"type": "object", "required": ["inputs", "nodes"], "properties": {
    "inputs": {"type": "array", "items": {"type": "object", "required": ["id", "sym", "label", "value"], "properties": {
        "id": {"type": "string"}, "sym": {"type": "string"}, "label": {"type": "string"}, "value": {"type": "number"},
        "min": {"type": "number"}, "max": {"type": "number"}, "step": {"type": "number"}, "fixed": {"type": "boolean"}}}},
    "nodes": {"type": "array", "items": _IDEA}}}


class FlowError(Exception):
    pass


# ---------------------------------------------------------------- computing, as the page does

def _vals(expr, env: dict[str, float]) -> list[float] | float:
    if isinstance(expr, list):
        return [vizcheck.value(e, env) for e in expr]
    return vizcheck.value(expr, env)


def _put(env: dict[str, float], nid: str, v) -> None:
    if isinstance(v, list):
        for k, x in enumerate(v, 1):
            env[f"{nid}_{k}"] = x
    else:
        env[nid] = v


def compute(spec: dict, at: dict[str, float] | None = None, swap: dict[str, object] | None = None) -> dict[str, object]:
    """Every quantity of the flow (``swap``: another expr for some boxes, a "what if")."""
    env = {i["id"]: float(i["value"]) for i in spec["inputs"]}
    env.update(at or {})
    out: dict[str, object] = dict(env)
    for n in spec["nodes"]:
        if n.get("input"):
            continue
        v = _vals((swap or {}).get(n["id"], n["expr"]), env)
        _put(env, n["id"], v)
        out[n["id"]] = v
    return out


def _bad(v) -> bool:
    return any(not math.isfinite(x) for x in v) if isinstance(v, list) else not math.isfinite(v)


# ---------------------------------------------------------------- the check

def check(raw: dict) -> tuple[dict | None, list[str]]:
    """(the clean flow or None, the problems in plain words)."""
    problems: list[str] = []
    inputs, ids = [], set()
    for i in (raw.get("inputs") or [])[:MAX_INPUTS + 1]:
        iid = str(i.get("id") or "")
        if not _ID.match(iid) or iid in RESERVED or iid in ids:
            problems.append(f"input id “{iid}”: use a short new lowercase name (letters and digits, not a function name)")
            continue
        try:
            v, lo, hi = float(i["value"]), float(i.get("min", i["value"])), float(i.get("max", i["value"]))
            step = float(i.get("step") or max((hi - lo) / 100, 1e-6))
        except (TypeError, ValueError, KeyError):
            problems.append(f"input {iid}: value, min, max and step must be numbers")
            continue
        fixed = bool(i.get("fixed")) or lo == hi
        if not fixed and not lo <= v <= hi:
            problems.append(f"input {iid}: its value {v} is outside min {lo} .. max {hi}")
            continue
        ids.add(iid)
        inputs.append({"id": iid, "sym": str(i.get("sym") or iid)[:40], "label": str(i.get("label") or "")[:60], "value": v,
                       "min": lo, "max": hi, "step": step, **({"fixed": True} if fixed else {})})
    if len(inputs) > MAX_INPUTS:
        problems.append(f"at most {MAX_INPUTS} inputs")
    if not inputs:
        problems.append("the flow has no inputs")
    grouped: set[str] = set()
    nodes: list[dict] = []
    known = set(ids)  # names an expr may use so far (inputs, earlier boxes, their vector parts)
    boxes = 0
    for n in raw.get("nodes") or []:
        nid = str(n.get("id") or "")
        if not _ID.match(nid) or nid in RESERVED or nid in ids:
            problems.append(f"box id “{nid}”: use a short new lowercase name (letters and digits)")
            continue
        refs = set(_REF.findall(str(n.get("tex") or "")))
        base = {"id": nid, "label": str(n.get("label") or "")[:60], "tex": str(n.get("tex") or "")[:400],
                "say": " ".join(str(n.get("say") or "").split())[:700]}
        if n.get("input"):
            members = [m for m in n["input"] if m in {i["id"] for i in inputs}]
            if not members:
                problems.append(f"input box {nid}: name the inputs it holds")
                continue
            grouped |= set(members)
            ids.add(nid)
            nodes.append({**base, "input": members})
            continue
        boxes += 1
        uses = [u for u in (n.get("uses") or []) if u in ids]
        missing = [u for u in (n.get("uses") or []) if u not in ids]
        if missing:
            problems.append(f"box {nid} uses {', '.join(map(str, missing))}, which are not earlier boxes")
        expr = n.get("expr")
        exprs = expr if isinstance(expr, list) else [expr]
        if not expr or len(exprs) > MAX_VECTOR or not all(isinstance(e, str) and e.strip() for e in exprs):
            problems.append(f"box {nid}: give `expr` (one calculator form, or a list of at most {MAX_VECTOR} for a vector)")
            continue
        bad_names = sorted({nm for e in exprs for nm in re.findall(r"[a-z_][a-z0-9_]*", e.lower())
                            if nm not in known and nm not in RESERVED})
        if bad_names:
            problems.append(f"box {nid}: `expr` uses {', '.join(bad_names)}, which is not an input or an earlier box")
            continue
        unknown_refs = sorted(r for r in refs if r not in ids and r != nid)
        if unknown_refs:
            problems.append(f"box {nid}: its tex names {{{', '.join(unknown_refs)}}}, which is not an input or a box")
        if not base["say"]:
            problems.append(f"box {nid}: write `say` (what it is and why it is needed)")
        whatifs = []
        for w in (n.get("whatif") or [])[:MAX_WHATIF]:
            we = w.get("expr")
            if not we or (isinstance(we, list) != isinstance(expr, list)) or (isinstance(we, list) and len(we) != len(exprs)):
                problems.append(f"box {nid}: a what-if needs an `expr` of the same shape as the box")
                continue
            whatifs.append({"tex": str(w.get("tex") or "")[:300], "expr": we, "why": " ".join(str(w.get("why") or "").split())[:500],
                            "ok": bool(w.get("ok"))})
        node = {**base, "sym": str(n.get("sym") or nid)[:40], "uses": uses, "expr": expr, "whatif": whatifs}
        ids.add(nid)
        known.add(nid)
        if isinstance(expr, list):
            known |= {f"{nid}_{k}" for k in range(1, len(exprs) + 1)}
        nodes.append(node)
    for i in inputs:
        if i["id"] not in grouped:
            problems.append(f"input {i['id']} is in no input box")
    if boxes == 0:
        problems.append("the flow has no formula box")
    if boxes > MAX_BOXES:
        problems.append(f"at most {MAX_BOXES} formula boxes")
    spec = {"inputs": inputs, "nodes": nodes}
    if not problems:  # compute it at the start values and at every input's ends, as the page will
        tries = [({}, "the start values")]
        tries += [({i["id"]: i[end]}, f"{i['id']} = {i[end]:g}") for i in inputs if not i.get("fixed") for end in ("min", "max")]
        for at, where in tries:
            vals = compute(spec, at)
            for n in nodes:
                if not n.get("input") and _bad(vals[n["id"]]):
                    problems.append(f"box {n['id']} cannot be computed at {where} (check its expr, or the input's range)")
                    break
            if problems:
                break
        for n in nodes:
            for w in n.get("whatif", []):
                if _bad(compute(spec, {}, {n["id"]: w["expr"]})[n["id"]]):
                    problems.append(f"box {n['id']}: the what-if “{w['tex']}” cannot be computed at the start values")
    return (None if problems else spec), problems


# ---------------------------------------------------------------- storage and the job

def get(db: DB, cid: str) -> dict | None:
    row = db.one("SELECT * FROM formula_flows WHERE concept_id=?", (cid,))
    if not row:
        return None
    return {"status": row["status"], "spec": loads(row["spec"], None) if row["status"] == "ready" else None,
            "error": row["error"] or None}


def request(db: DB, jobs, cid: str) -> None:
    if jobs.active("formula_flow", concept_id=cid):
        return
    db.x("INSERT OR REPLACE INTO formula_flows(concept_id, status, spec, error, at) VALUES(?,?,?,?,?)",
         (cid, "building", "{}", "", now()))
    jobs.enqueue("formula_flow", "Build the formula flow", {"concept_id": cid})


def run(jobs, jid: int, d: dict) -> dict:
    from . import formula_lessons
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    cid = d["concept_id"]
    f = db.one("SELECT * FROM formula_lessons WHERE id=?", (cid,))
    if not f:
        raise FlowError("not a formula page")
    main = formula_lessons._main_form(db, f)
    note = db.one("SELECT body FROM formula_notes WHERE concept_id=? AND key=?", (main["concept_id"], main["key"]))
    nb = loads((note or {}).get("body"), {}) or {}
    symbols = "\n".join(f'- ${s["tex"]}$: {s["meaning"]}' for s in nb.get("symbols", [])) or "(none)"
    blocks = "\n".join(f'- {b["name"]} ({b["kind"]}){": $" + b["tex"] + "$" if b["tex"] else ""}: {b["meaning"]}'
                       for b in formula_lessons.blocks(db, cid)) or "(none: it is basic)"
    previous, problems = "(none: a first version)", []
    try:
        for attempt in range(2):
            jobs.progress(jid, "fixing the flow: " + "; ".join(problems)[:200] if problems else f"building the flow of “{f['name'][:60]}”")
            out = jobs.call(jid, "Lesson assets", Call(
                prompt=prompt("formula_flow", formula=f["name"], main=main["tex"], meaning=f["meaning"] or nb.get("meaning", ""),
                              symbols=symbols, blocks=blocks, previous=previous,
                              problems="\n".join(f"- {p}" for p in problems) or "(none)"),
                schema=SCHEMA, model="opus", timeout=900))
            spec, problems = check(out)
            if spec:
                db.x("UPDATE formula_flows SET status='ready', spec=?, error='', at=? WHERE concept_id=?", (dumps(spec), now(), cid))
                return {"boxes": sum(1 for n in spec["nodes"] if not n.get("input")), "inputs": len(spec["inputs"])}
            previous = dumps(out)[:12000]
        raise FlowError("; ".join(problems)[:400])
    except Exception as e:  # noqa: BLE001 - the page shows the error and "Try again"
        db.x("UPDATE formula_flows SET status='failed', error=?, at=? WHERE concept_id=?", (str(e)[:400], now(), cid))
        raise
