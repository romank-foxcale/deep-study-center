"""Interactive visuals as data: agents pick a built-in widget and its parameters; the frontend
renders it. No agent-written code ever runs in the browser. ``validate`` drops anything malformed."""

from __future__ import annotations

import re

LIMIT = 10.0
FUNCTIONS = {"sin", "cos", "tan", "exp", "log", "sqrt", "abs", "tanh", "sigmoid", "relu", "max", "min"}
_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|([a-z_][a-z0-9_]*)|(\*\*|[-+*/^(),]))")

SCHEMA = {"type": "object", "required": ["type", "caption"], "properties": {
    "type": {"enum": ["vectors2d", "lincomb2d", "matrix2d", "plot"]},
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


def validate(spec) -> dict | None:
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
    return None
