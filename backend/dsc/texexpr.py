"""The calculator form of a simple TeX part of a formula, so the learner can edit the whole colored part (x^2, not x).

x^2 -> x^(2), \\sigma\\sqrt{2\\pi} -> sigma*sqrt(2*pi), 1/2 -> 1/2, \\frac{a}{b} -> ((a)/(b)).
Anything it does not fully understand gives None (the part then keeps no calculator form). The result is checked
with the widget's own parser (``vizcheck.parse``).
"""

from __future__ import annotations

import re

from .vizcheck import parse

GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "nu", "pi", "rho", "sigma", "tau", "phi", "omega"}
FUNCS = {"exp", "log", "sin", "cos", "tan", "tanh"}
_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def tex_to_expr(tex: str) -> str | None:
    s = tex.replace("\\left", "").replace("\\right", "").replace("\\,", "").replace("\\!", "").strip()
    if not s or "{{" in s:
        return None
    pos = 0

    def seq(stop: str | None) -> list[str] | None:
        """Atoms and operators up to `stop` (or the end), with implicit multiplication between atoms."""
        nonlocal pos
        items: list[str] = []
        while pos < len(s):
            ch = s[pos]
            if stop is not None and ch == stop:
                return items
            if ch.isspace():
                pos += 1
                continue
            if ch in "+-*/":
                items.append(ch)
                pos += 1
                continue
            if ch == "^":
                pos += 1
                exp = group()
                if exp is None or not items or items[-1] in "+-*/":
                    return None
                items[-1] = f"{items[-1]}^({exp})"
                continue
            a = atom()
            if a is None:
                return None
            if a == "*":
                items.append("*")
                continue
            if items and items[-1] not in "+-*/":
                items.append("*")
            items.append(a)
        return items if stop is None else None

    def group() -> str | None:
        """A {...} group, or a single digit or letter (as in x^2 or \\frac12)."""
        nonlocal pos
        if pos < len(s) and s[pos] == "{":
            pos += 1
            inner = seq("}")
            if inner is None:
                return None
            pos += 1
            return "".join(inner)
        if pos < len(s) and (s[pos].isdigit() or s[pos].isalpha()):
            pos += 1
            return s[pos - 1].lower()
        return atom()

    def atom() -> str | None:
        nonlocal pos
        if pos >= len(s):
            return None
        ch = s[pos]
        m = _NUMBER.match(s, pos)
        if m:
            pos = m.end()
            return m.group(0)
        if ch.isalpha():
            pos += 1
            return ch.lower()
        if ch in "({":
            close = ")" if ch == "(" else "}"
            pos += 1
            inner = seq(close)
            if inner is None:
                return None
            pos += 1
            return f"({''.join(inner)})"
        if ch == "\\":
            m = _COMMAND.match(s, pos)
            if not m:
                return None
            name = m.group(1)
            pos = m.end()
            if name in GREEK:
                return name
            if name in ("cdot", "times"):
                return "*"
            if name == "sqrt":
                g = group()
                return None if g is None else f"sqrt({g})"
            if name in ("frac", "dfrac", "tfrac"):
                a = group()
                b = group()
                return None if a is None or b is None else f"(({a})/({b}))"
            if name in FUNCS:
                g = group()
                return None if g is None else f"{name}({g})"
            return None
        return None

    items = seq(None)
    if not items or items[-1] in "+-*/":
        return None
    out = "".join(items)
    # tidy: drop parentheses around a single number or name (not a function's own): x^(2) -> x^2, ((1)/(2)) -> 1/2
    for _ in range(4):
        out = re.sub(r"(?<![a-z_])\(([a-z_][a-z0-9_]*|\d+(?:\.\d+)?)\)", r"\1", out)
        out = re.sub(r"(?<![a-z_])\((\d+(?:\.\d+)?/\d+(?:\.\d+)?)\)(?![\^])", r"\1", out)
    try:
        parse(out)
    except ValueError:
        return None
    return out
