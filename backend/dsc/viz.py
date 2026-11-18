"""Interactive visuals as data: agents pick a built-in widget and its parameters; the frontend
renders it. No agent-written code ever runs in the browser. ``validate`` drops anything malformed."""

from __future__ import annotations

import re

from . import texexpr, vizcheck

LIMIT = 10.0
FUNCTIONS = {"sin", "cos", "tan", "exp", "log", "sqrt", "abs", "tanh", "sigmoid", "relu", "max", "min"}
_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|([a-z_][a-z0-9_]*)|(\*\*|[-+*/^(),]))")

SCHEMA = {"type": "object", "required": ["type", "caption"], "properties": {
    "type": {"enum": ["vectors2d", "lincomb2d", "matrix2d", "plot", "formula"]},
    # formula: an annotated, draggable formula. `tex` uses {{id}} for each part; a part has its own TeX (it may contain
    # other {{id}}), a short label, a color, and optionally the parameter it shows (dragged left/right to change it).
    "tex": {"type": "string"},
    "parts": {"type": "array", "maxItems": 6, "items": {"type": "object", "required": ["id", "tex", "label"], "properties": {
        "id": {"type": "string"}, "tex": {"type": "string"}, "label": {"type": "string"},
        "color": {"enum": ["green", "purple", "pink", "orange", "blue", "teal"]}, "side": {"enum": ["above", "below"]},
        "param": {"type": "string"}, "expr": {"type": "string"},
        "variants": {"type": "array", "maxItems": 4, "items": {"type": "object", "required": ["tex", "expr", "why"], "properties": {
            "tex": {"type": "string"}, "expr": {"type": "string"}, "why": {"type": "string"}}}}}}},
    "checks": {"type": "array", "maxItems": 3, "items": {"type": "object", "required": ["kind", "label"], "properties": {
        "kind": {"enum": ["area", "peak", "at", "result"]}, "label": {"type": "string"}, "at": {"type": "number"},
        "expect": {"type": "number"}}}},
    "formulaParams": {"type": "array", "maxItems": 3, "items": {"type": "object", "required": ["name", "min", "max", "value"], "properties": {
        "name": {"type": "string"}, "min": {"type": "number"}, "max": {"type": "number"}, "value": {"type": "number"},
        "effect": {"type": "string"}}}},
    "resultExpr": {"type": "string"}, "resultTex": {"type": "string"},
    "plotExpr": {"type": "string"}, "plotVar": {"type": "string"},
    "caption": {"type": "string"},
    "vectors": {"type": "array", "maxItems": 4, "items": {"type": "object", "required": ["x", "y", "label"], "properties": {
        "x": {"type": "number"}, "y": {"type": "number"}, "label": {"type": "string"}}}},
    "showSum": {"type": "boolean"},
    "u": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
    "v": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
    "target": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
    "matrix": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}}},
    "expr": {"type": "string"}, "xmin": {"type": "number"}, "xmax": {"type": "number"},
    "params": {"type": "array", "maxItems": 3, "items": {"type": "object", "required": ["name", "min", "max", "value"], "properties": {
        "name": {"type": "string"}, "min": {"type": "number"}, "max": {"type": "number"}, "value": {"type": "number"}}}},
}}


def _num(v, lo: float = -LIMIT, hi: float = LIMIT) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return max(lo, min(hi, float(v)))


def _pair(v) -> list[float] | None:
    if not isinstance(v, list) or len(v) != 2:
        return None
    a, b = _num(v[0]), _num(v[1])
    return None if a is None or b is None else [a, b]


def expr_ok(expr: str, names: set[str]) -> bool:
    """Only numbers, x, declared parameters, + - * / ^ ( ) , and whitelisted functions."""
    if not isinstance(expr, str) or not 0 < len(expr) <= 120:
        return False
    pos = 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            return expr[pos:].strip() == ""
        if m.group(2) and m.group(2) not in FUNCTIONS | names | {"x", "e", "pi"}:
            return False
        pos = m.end()
    return True


def validate(spec, numeric: bool = True) -> dict | None:
    if not isinstance(spec, dict):
        return None
    t, caption = spec.get("type"), str(spec.get("caption") or "")[:200]
    if t == "vectors2d":
        vecs = []
        for v in (spec.get("vectors") or [])[:4]:
            x, y = _num(v.get("x")) if isinstance(v, dict) else None, _num(v.get("y")) if isinstance(v, dict) else None
            if x is not None and y is not None:
                vecs.append({"x": x, "y": y, "label": str(v.get("label") or "")[:12]})
        return {"type": t, "caption": caption, "vectors": vecs, "showSum": bool(spec.get("showSum"))} if vecs else None
    if t == "lincomb2d":
        u, v = _pair(spec.get("u")), _pair(spec.get("v"))
        if not u or not v:
            return None
        out = {"type": t, "caption": caption, "u": u, "v": v}
        if _pair(spec.get("target")):
            out["target"] = _pair(spec.get("target"))
        return out
    if t == "matrix2d":
        m = spec.get("matrix")
        rows = [_pair(r) for r in m] if isinstance(m, list) and len(m) == 2 else None
        return {"type": t, "caption": caption, "matrix": rows} if rows and all(rows) else None
    if t == "plot":
        params = []
        for p in (spec.get("params") or [])[:3]:
            if not isinstance(p, dict) or not re.fullmatch(r"[a-z]", str(p.get("name", ""))) or p["name"] in ("x", "e"):
                continue
            lo, hi = _num(p.get("min"), -100, 100), _num(p.get("max"), -100, 100)
            val = _num(p.get("value"), -100, 100)
            if None not in (lo, hi, val) and lo < hi:
                params.append({"name": p["name"], "min": lo, "max": hi, "value": max(lo, min(hi, val))})
        expr = str(spec.get("expr") or "").strip().lower()
        if not expr_ok(expr, {p["name"] for p in params}):
            return None
        xmin, xmax = _num(spec.get("xmin"), -100, 100), _num(spec.get("xmax"), -100, 100)
        if xmin is None or xmax is None or xmin >= xmax:
            xmin, xmax = -5.0, 5.0
        return {"type": t, "caption": caption, "expr": expr, "xmin": xmin, "xmax": xmax, "params": params}
    if t == "formula":
        return _formula(spec, caption, numeric)
    return None


# TeX commands that could reach outside the formula (links, HTML attributes, images, macros) are never accepted.
_UNSAFE_TEX = re.compile(r"\\(?:html\w*|href|url|includegraphics|class|style|data|def|gdef|edef|xdef|let|newcommand|"
                         r"renewcommand|providecommand|operatorname\*?\s*\{\s*\\|require|raisebox)", re.I)
_PART_ID = re.compile(r"[a-z][a-z0-9_]{0,15}")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]{0,15})\}\}")
COLORS = ("green", "purple", "pink", "orange", "blue", "teal")


def _tex_ok(tex: object, limit: int) -> bool:
    return isinstance(tex, str) and 0 < len(tex) <= limit and not _UNSAFE_TEX.search(tex)


def _formula(spec: dict, caption: str, numeric: bool = True) -> dict | None:
    """An annotated formula: colored parts with labels; parts bound to a parameter can be dragged to change it, and an
    optional plot of `plotExpr` follows the parameters (with the starting curve dashed)."""
    tex = spec.get("tex")
    if not _tex_ok(tex, 400):
        return None
    params = []
    # Agents write `formulaParams`; a validated spec (stored, then validated again on every read) has `params`.
    # `x` may be a parameter too: it is then the value the learner sets, and a plot over x marks it.
    for p in (spec.get("formulaParams") or spec.get("params") or [])[:3]:
        name = str(p.get("name", "")) if isinstance(p, dict) else ""
        if not re.fullmatch(r"[a-z][a-z0-9]{0,7}", name) or name in FUNCTIONS | {"e", "pi"}:
            continue
        lo, hi, val = _num(p.get("min"), -100, 100), _num(p.get("max"), -100, 100), _num(p.get("value"), -100, 100)
        if None not in (lo, hi, val) and lo < hi:
            params.append({"name": name, "min": lo, "max": hi, "value": max(lo, min(hi, val)),
                           "effect": " ".join(str(p.get("effect") or "").split())[:140],
                           "label": " ".join(str(p.get("label") or "").split())[:60]})
    names = {p["name"] for p in params}
    # A plot over x whose x the learner cannot set: make x a value with a slider over the plot's range, so the
    # result and the checks can use it (lessons written before x could be a parameter).
    implicit_x = False
    plot_raw = str(spec.get("plotExpr") or "").strip().lower()
    if "x" not in names and str(spec.get("plotVar") or "x") in ("x", "") and \
            re.search(r"(?<![a-z0-9_])x(?![a-z0-9_])", _REF.sub("", plot_raw)) and len(params) < 3:
        lo, hi = _num(spec.get("xmin"), -100, 100), _num(spec.get("xmax"), -100, 100)
        if lo is None or hi is None or lo >= hi:
            lo, hi = -5.0, 5.0
        params.append({"name": "x", "min": lo, "max": hi, "value": round(lo + 0.8 * (hi - lo), 1), "effect": "",
                       "label": "x: the value across the plot"})
        names.add("x")
        implicit_x = True
    parts, seen = [], set()
    for i, p in enumerate((spec.get("parts") or [])[:6]):
        if not isinstance(p, dict) or not _PART_ID.fullmatch(str(p.get("id", ""))) or p["id"] in seen or not _tex_ok(p.get("tex"), 200):
            continue
        seen.add(p["id"])
        part = {"id": p["id"], "tex": p["tex"], "label": " ".join(str(p.get("label") or "").split())[:90],
                "color": p.get("color") if p.get("color") in COLORS else COLORS[i % len(COLORS)],
                "side": p.get("side") if p.get("side") in ("above", "below") else ("above" if i % 2 == 0 else "below"),
                "param": p.get("param") if p.get("param") in names else None}
        # The part in calculator form, so the widget can compute with it, and "what if" variants of it.
        pexpr = str(p.get("expr") or "").strip().lower()
        if not pexpr:  # so the learner edits the whole colored part (x^2, not only x): read it from simple TeX
            pexpr = texexpr.tex_to_expr(p["tex"]) or ""
        if pexpr and expr_ok(pexpr, names):
            part["expr"] = pexpr
            variants = []
            for v in (p.get("variants") or [])[:4]:
                if not isinstance(v, dict) or not _tex_ok(v.get("tex"), 120):
                    continue
                vexpr = str(v.get("expr") or "").strip().lower()
                if expr_ok(vexpr, names) and vexpr != pexpr:
                    variants.append({"tex": v["tex"], "expr": vexpr, "why": " ".join(str(v.get("why") or "").split())[:240]})
            if variants:
                part["variants"] = variants
        parts.append(part)
    # Only the formula's own variables can be changed, through the part that shows them: a value without a part gets
    # the part whose TeX shows its symbol (y in "y^2", \sigma in "\sigma\sqrt{2\pi}" when no other part is \sigma).
    for prm in params:
        if any(p["param"] == prm["name"] for p in parts):
            continue
        sym = rf"\\{prm['name']}(?![a-zA-Z])" if len(prm["name"]) > 1 else rf"(?<![\\a-zA-Z]){prm['name']}(?![a-zA-Z])"
        host = next((p for p in parts if not p["param"] and not _PLACEHOLDER.search(p["tex"]) and re.search(sym, p["tex"])), None)
        if host:
            host["param"] = prm["name"]
    if implicit_x and not any(p["param"] == "x" for p in parts):
        params.pop()  # an x slider only when a part of the formula shows x
        names.discard("x")
        implicit_x = False
    elif implicit_x:
        params[-1]["label"] = ""
    used = set(_PLACEHOLDER.findall(tex)) | {x for p in parts for x in _PLACEHOLDER.findall(p["tex"])}
    if not parts or not used <= seen or not set(_PLACEHOLDER.findall(tex)):
        return None
    if any(p["id"] in _PLACEHOLDER.findall(p["tex"]) for p in parts):
        return None  # a part may not contain itself
    out = {"type": "formula", "caption": caption, "tex": tex, "parts": parts, "params": params}
    computable = {p["id"] for p in parts if p.get("expr")}

    def ok(e: str) -> bool:
        """An expression of the parameters (and x) that may use [part] for a part's calculator form."""
        refs = _REF.findall(e)
        return set(refs) <= computable and expr_ok(_REF.sub("(1)", e), names)

    # The live result: a number computed from the parameters ("‖v‖ = 5.00"), shown with the formula filled in.
    result = str(spec.get("resultExpr") or "").strip().lower()
    free_x = "x" not in names and re.search(r"(?<![a-z0-9_])x(?![a-z0-9_])", _REF.sub("", result))
    if result and ok(result) and not free_x and _tex_ok(spec.get("resultTex") or "y", 80):  # a number needs every value set
        out.update(resultExpr=result, resultTex=spec.get("resultTex") or "")
    # The plot: y over x, or over one parameter (plotVar) with a dot at its current value.
    expr = str(spec.get("plotExpr") or "").strip().lower()
    var = str(spec.get("plotVar") or "x")
    if var not in names:
        var = "x"
    if expr and ok(expr):
        param = next((p for p in params if p["name"] == var), None)
        xmin, xmax = _num(spec.get("xmin"), -100, 100), _num(spec.get("xmax"), -100, 100)
        if xmin is None or xmax is None or xmin >= xmax:
            xmin, xmax = (param["min"], param["max"]) if param else (-5.0, 5.0)
        out.update(plotExpr=expr, plotVar=var, xmin=xmin, xmax=xmax)
    # Checks: what the real formula makes true, measured live for the real formula and for a variant.
    checks = []
    for c in (spec.get("checks") or [])[:3]:
        if not isinstance(c, dict) or c.get("kind") not in CHECKS or (c["kind"] != "result" and "plotExpr" not in out):
            continue
        if c["kind"] == "result" and "resultExpr" not in out:
            continue
        item = {"kind": c["kind"], "label": " ".join(str(c.get("label") or CHECKS[c["kind"]]).split())[:80]}
        if c["kind"] == "at":
            at = _num(c.get("at"), -100, 100)
            if at is None:
                continue
            item["at"] = at
        expect = _num(c.get("expect"), -1e6, 1e6)
        if expect is not None:
            item["expect"] = expect
        checks.append(item)
    if checks:
        out["checks"] = checks
    # Compute it as the page will: remove a result, plot, check or variant that cannot work (vizcheck).
    return vizcheck.inspect(out)[0] if numeric else out


def inspect(spec) -> tuple[dict | None, list[str]]:
    """Validate a widget and say in plain words what was removed and why (for the agent that wrote it, and for the
    learner's warning). Problems are counted against the agent's raw spec, so silent drops are reported too."""
    out = validate(spec)
    if not isinstance(spec, dict) or spec.get("type") != "formula":
        return out, ([] if out or not spec else ["the graph is not valid and was removed"])
    if out is None:
        return None, ["the formula widget is not valid (unsafe or empty TeX, a {{part}} that does not exist, or no parts), so it was removed"]
    syntax = validate(spec, numeric=False)
    raw = vizcheck.inspect(syntax)[1] if syntax else []
    problems = list(dict.fromkeys(raw))
    raw_parts = {p.get("id"): p for p in spec.get("parts") or [] if isinstance(p, dict)}
    kept = {p["id"]: p for p in out["parts"]}
    for pid, p in raw_parts.items():
        if pid not in kept:
            problems.append(f'part “{pid}” was removed (bad id or unsafe TeX)')
            continue
        if p.get("param") and not kept[pid].get("param"):
            problems.append(f'part “{pid}”: its param “{p["param"]}” is not one of the values, so it has no slider')
        lost = len(p.get("variants") or []) - len(kept[pid].get("variants") or [])
        if lost > 0 and not any(f'of part “{pid}”' in x for x in problems):
            problems.append(f'part “{pid}”: {lost} variant(s) were removed (bad TeX or expression, or the same as the real form)')
    if len(spec.get("checks") or []) > len(out.get("checks") or []) and not any(x.startswith("check") for x in problems):
        problems.append("some checks were removed (unknown kind, or they need a plot or result the widget does not have)")
    return out, problems



_REF = re.compile(r"\[([a-z][a-z0-9_]{0,15})\]")
# area: integral of the plot over its range; peak: its highest value; at: its value at a point; result: the result.
CHECKS = {"area": "area under the curve", "peak": "highest point", "at": "value at a point", "result": "result"}
