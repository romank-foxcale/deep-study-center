"""Numeric checks of a formula widget (viz type "formula"), the same way the page computes it.

``viz.validate`` checks the syntax; this module computes the widget at its start values, as ``Formula.tsx`` does:
the result, the plot, every check, and every "what if" variant. A part that cannot work is removed, and each problem
is reported in plain words, so an agent can fix the widget and the learner can see what was changed.

The expression language is the one of ``web/src/components/viz/expr.ts``: numbers, names, + - * / ^ (or **),
parentheses, and a few functions. Nothing is ever evaluated with Python's ``eval``.
"""

from __future__ import annotations

import math
import re

FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "log": math.log, "sqrt": math.sqrt,
    "abs": abs, "tanh": math.tanh, "sigmoid": lambda z: 1 / (1 + math.exp(-z)), "relu": lambda z: max(0.0, z),
    "max": max, "min": min,
}
CONSTS = {"e": math.e, "pi": math.pi}
_TOKEN = re.compile(r"\s*(\d+\.?\d*|\.\d+|[a-z_][a-z0-9_]*|\*\*|[-+*/^(),])")
REF = re.compile(r"\[([a-z][a-z0-9_]{0,15})\]")
SAMPLES = 400
TOLERANCE = 0.02  # a check with `expect` passes within 2 % (or 0.01)


# ---------------------------------------------------------------- the evaluator (mirrors expr.ts)

def parse(src: str):
    src = src.lower()
    tokens, pos = [], 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            if src[pos:].strip():
                raise ValueError(f"unexpected character in {src!r}")
            break
        tokens.append(m.group(1))
        pos = m.end()
    i = 0

    def peek():
        return tokens[i] if i < len(tokens) else None

    def take():
        nonlocal i
        i += 1
        return tokens[i - 1] if i - 1 < len(tokens) else None

    def primary():
        t = take()
        if t is None:
            raise ValueError("unexpected end")
        if t[0].isdigit() or t[0] == ".":
            return ("num", float(t))
        if t == "(":
            n = total()
            if take() != ")":
                raise ValueError("expected )")
            return n
        if t == "-":
            return ("neg", power())
        if t[0].isalpha() or t[0] == "_":
            if peek() == "(":
                if t not in FUNCS:
                    raise ValueError(f"unknown function {t}")
                take()
                args = [total()]
                while peek() == ",":
                    take()
                    args.append(total())
                if take() != ")":
                    raise ValueError("expected )")
                return ("call", t, args)
            return ("var", t)
        raise ValueError(f"unexpected {t}")

    def power():
        base = primary()
        if peek() in ("^", "**"):
            take()
            return ("bin", "^", base, power())
        return base

    def product():
        n = power()
        while peek() in ("*", "/"):
            op = take()
            n = ("bin", op, n, power())
        return n

    def total():
        n = product()
        while peek() in ("+", "-"):
            op = take()
            n = ("bin", op, n, product())
        return n

    tree = total()
    if i != len(tokens):
        raise ValueError("trailing input")
    return tree


def evaluate(node, env: dict[str, float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        if node[1] in env:
            return env[node[1]]
        if node[1] in CONSTS:
            return CONSTS[node[1]]
        raise ValueError(f"unknown name {node[1]}")
    if kind == "neg":
        return -evaluate(node[1], env)
    if kind == "call":
        return float(FUNCS[node[1]](*[evaluate(a, env) for a in node[2]]))
    a, b = evaluate(node[2], env), evaluate(node[3], env)
    op = node[1]
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b
    return math.pow(a, b)


def value(expr: str | None, env: dict[str, float]) -> float:
    """The value of an expression, or NaN when it cannot be computed (unknown name, division by zero, ...)."""
    if not expr:
        return math.nan
    try:
        v = evaluate(parse(expr), env)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return math.nan
    return v if isinstance(v, float) and math.isfinite(v) else math.nan


def resolve(expr: str, part_expr: dict[str, str], depth: int = 0) -> str:
    """Replace [part] references with the part's calculator form, in parentheses."""
    if depth > 3:
        return expr
    return REF.sub(lambda m: f"({resolve(part_expr[m.group(1)], part_expr, depth + 1)})" if m.group(1) in part_expr
                   else "nan_ref", expr)


# ---------------------------------------------------------------- measuring a widget like the page does

def _measures(spec: dict, swap: dict[str, str] | None = None) -> dict:
    """Result, plot points and check values at the start values; `swap` replaces parts' calculator forms."""
    env = {p["name"]: p["value"] for p in spec.get("params", [])}
    forms = {p["id"]: p["expr"] for p in spec.get("parts", []) if p.get("expr")}
    forms.update(swap or {})
    res_expr = resolve(spec["resultExpr"], forms) if spec.get("resultExpr") else None
    plot_expr = resolve(spec["plotExpr"], forms) if spec.get("plotExpr") else None
    out = {"result": value(res_expr, env), "points": [], "checks": []}
    var = spec.get("plotVar") or "x"
    tree = None
    if plot_expr:
        try:
            tree = parse(plot_expr)
        except ValueError:
            tree = None
    if tree is not None:
        lo, hi = spec.get("xmin", -5.0), spec.get("xmax", 5.0)
        for i in range(SAMPLES + 1):
            x = lo + (hi - lo) * i / SAMPLES
            try:
                y = evaluate(tree, {**env, var: x, "x": x})
            except (ValueError, ZeroDivisionError, OverflowError, TypeError):
                continue
            if math.isfinite(y):
                out["points"].append((x, y))

    def at(x: float) -> float:
        return value(plot_expr, {**env, var: x, "x": x}) if plot_expr else math.nan

    pts = out["points"]
    for c in spec.get("checks", []):
        if c["kind"] == "result":
            v = out["result"]
        elif c["kind"] == "at":
            v = at(c["at"])
        elif len(pts) < 2:
            v = math.nan
        elif c["kind"] == "peak":
            v = max(p[1] for p in pts)
        else:  # area (trapezoids, as the page computes it)
            v = sum((pts[i][0] - pts[i - 1][0]) * (pts[i][1] + pts[i - 1][1]) / 2 for i in range(1, len(pts)))
        out["checks"].append(v)
    return out


def _passes(v: float, expect: float) -> bool:
    return math.isfinite(v) and abs(v - expect) <= max(TOLERANCE * abs(expect), 0.01)


def _fmt(v: float) -> str:
    return "not computable" if not math.isfinite(v) else f"{v:.3g}"


def inspect(spec: dict) -> tuple[dict, list[str]]:
    """Compute a validated formula widget and remove what cannot work. Returns (cleaned spec, problems)."""
    if not isinstance(spec, dict) or spec.get("type") != "formula":
        return spec, []
    spec = {**spec, "parts": [dict(p) for p in spec.get("parts", [])], "checks": list(spec.get("checks", []))}
    problems: list[str] = []
    env = {p["name"]: p["value"] for p in spec.get("params", [])}

    # every value the learner can set must belong to a part of the formula (only the formula's own parts change)
    bound = {p["param"] for p in spec["parts"] if p.get("param")}
    for p in spec.get("params", []):
        if p["name"] not in bound:
            problems.append(f'the value “{p["name"]}” has no colored part in the formula, so the learner cannot change it; '
                            f'give the part that shows {p["name"]} the param “{p["name"]}”')

    # a part's calculator form must compute at the start values
    for p in spec["parts"]:
        if p.get("expr") and not math.isfinite(value(p["expr"], env)):
            problems.append(f'part “{p["id"]}”: its expr “{p["expr"]}” cannot be computed with the values '
                            f'{", ".join(env) or "(none)"}; its "what if" was removed')
            p.pop("expr", None)
            p.pop("variants", None)

    real = _measures(spec)
    if spec.get("resultExpr") and not math.isfinite(real["result"]):
        problems.append(f'the result “{spec["resultExpr"]}” cannot be computed at the start values; it was removed '
                        '(a result may use only values the learner sets)')
        spec.pop("resultExpr", None)
        spec.pop("resultTex", None)
    if spec.get("plotExpr") and len(real["points"]) < SAMPLES // 2:
        problems.append(f'the plot “{spec["plotExpr"]}” cannot be computed over most of its range; it was removed')
        for k in ("plotExpr", "plotVar", "xmin", "xmax"):
            spec.pop(k, None)
    if "resultExpr" not in spec or "plotExpr" not in spec:
        real = _measures(spec)

    kept, values = [], []
    for c, v in zip(spec["checks"], real["checks"]):
        if not math.isfinite(v):
            problems.append(f'check “{c["label"]}” cannot be computed; it was removed')
        elif "expect" in c and not _passes(v, c["expect"]):
            problems.append(f'check “{c["label"]}” gives {_fmt(v)} for the real formula, not {_fmt(c["expect"])}; '
                            'it was removed (the real formula must pass its own checks)')
        else:
            kept.append(c)
            values.append(v)
    spec["checks"] = kept
    real["checks"] = values

    # a "what if" variant must change something the learner can see: the result, a check or the plot
    for p in spec["parts"]:
        good = []
        for var in p.get("variants", []):
            m = _measures(spec, {p["id"]: var["expr"]})
            same_result = (not math.isfinite(m["result"]) and not math.isfinite(real["result"])) or m["result"] == real["result"]
            same_checks = all(a == b for a, b in zip(m["checks"], real["checks"]))
            same_plot = m["points"] == real["points"]
            if same_result and same_checks and same_plot:
                problems.append(f'variant “{var["expr"]}” of part “{p["id"]}” changes nothing the learner can see; it was removed '
                                f'(use [{p["id"]}] in plotExpr or resultExpr)')
            else:
                good.append(var)
        if "variants" in p:
            if good:
                p["variants"] = good
            else:
                p.pop("variants")
    if not spec["checks"]:
        spec.pop("checks")
    if not spec.get("resultExpr") and not spec.get("plotExpr"):
        problems.append("the widget shows no result and no plot, so a change teaches nothing; add resultExpr or plotExpr")
    return spec, problems


def describe(spec: dict) -> str:
    """The widget's real numbers in one paragraph, for the lesson reviewer."""
    if not isinstance(spec, dict) or spec.get("type") != "formula":
        return ""
    real = _measures(spec)
    env = ", ".join(f'{p["name"]} = {p["value"]:g}' for p in spec.get("params", [])) or "no values"
    parts = [f"Start values: {env}."]
    if spec.get("resultExpr"):
        parts.append(f'Result {spec["resultExpr"]} = {_fmt(real["result"])}.')
    for c, v in zip(spec.get("checks", []), real["checks"]):
        parts.append(f'Check “{c["label"]}”: real {_fmt(v)}' + (f' (expects {_fmt(c["expect"])})' if "expect" in c else "") + ".")
    for p in spec.get("parts", []):
        for var in p.get("variants", []):
            m = _measures(spec, {p["id"]: var["expr"]})
            nums = "; ".join(f'{c["label"]}: {_fmt(v)}' for c, v in zip(spec.get("checks", []), m["checks"]))
            res = f'result {_fmt(m["result"])}' if spec.get("resultExpr") else ""
            parts.append(f'With “{var["expr"]}” for {p["id"]}: {", ".join(x for x in (res, nums) if x) or "plot changes"}. '
                         f'Its why: “{var["why"]}”')
    return " ".join(parts)

