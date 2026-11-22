"""Formula widgets are computed the way the page computes them (vizcheck), on widgets the real model wrote."""

import json
import math
from pathlib import Path

import pytest

from dsc import viz, vizcheck

REAL = json.loads((Path(__file__).parent / "fixtures" / "formula_widgets_real.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("item", REAL, ids=[r["source"] for r in REAL])
def test_real_widgets_are_stable_computable_and_pass_their_own_checks(item):
    clean, problems = viz.inspect(item["widget"])
    assert clean is not None, problems
    assert viz.validate(clean) == clean  # validated again on every read: nothing may change
    env = {p["name"]: p["value"] for p in clean["params"]}
    m = vizcheck._measures(clean)
    if clean.get("resultExpr"):
        assert math.isfinite(m["result"])
    if clean.get("plotExpr"):
        assert len(m["points"]) >= vizcheck.SAMPLES // 2
    for c, v in zip(clean.get("checks", []), m["checks"]):
        assert math.isfinite(v)
        if "expect" in c:
            assert vizcheck._passes(v, c["expect"]), (c, v)
    # every "what if" changes something the learner can see
    for p in clean["parts"]:
        for var in p.get("variants", []):
            mv = vizcheck._measures(clean, {p["id"]: var["expr"]})
            assert mv["result"] != m["result"] or mv["checks"] != m["checks"] or mv["points"] != m["points"]
    # every value is shown: a part has it, or (for a value inside a larger part) it gets its own row and a problem says so
    bound = {p["param"] for p in clean["parts"] if p["param"]}
    for name in env:
        assert name in bound or any(f"“{name}”" in x for x in problems)
    assert vizcheck.describe(clean).startswith("Start values")


def test_the_norm_widget_from_the_real_lesson():
    norm = next(r["widget"] for r in REAL if r["source"].endswith("la-norms/s-pythagoras"))
    clean, _ = viz.inspect(norm)
    assert {p["id"]: p["param"] for p in clean["parts"] if p["param"]} == {"px": "x", "py": "y"}
    assert vizcheck._measures(clean)["result"] == 5.0
    assert any(c["label"].startswith("(3, 4)") for c in clean["checks"])


def test_inspect_reports_and_removes_what_cannot_work():
    spec = {"type": "formula", "caption": "c", "tex": r"y = {{a}} \cdot {{k}}",
            "parts": [{"id": "a", "tex": "a", "label": "a", "param": "a"},
                      {"id": "k", "tex": "2", "label": "factor", "expr": "2",
                       "variants": [{"tex": "3", "expr": "3", "why": "changes the result"},
                                    {"tex": "2.0", "expr": "2.0", "why": "same value"}]}],
            "formulaParams": [{"name": "a", "min": 0, "max": 5, "value": 1}, {"name": "b", "min": 0, "max": 5, "value": 1}],
            "resultExpr": "a*[k]",
            "checks": [{"kind": "result", "label": "a = 1 gives 2", "expect": 2}, {"kind": "result", "label": "wrong", "expect": 7}]}
    clean, problems = viz.inspect(spec)
    assert [c["label"] for c in clean["checks"]] == ["a = 1 gives 2"]
    assert [v["expr"] for v in clean["parts"][1]["variants"]] == ["3"]
    text = " ".join(problems)
    assert "gives 2 for the real formula, not 7" in text and "changes nothing" in text and "“b” has no colored part" in text


def test_evaluator_matches_the_page():
    assert vizcheck.value("2^3^2", {}) == 512  # right-associative power, as in expr.ts
    assert vizcheck.value("-2^2", {}) == -4
    assert math.isclose(vizcheck.value("sigma*sqrt(2*pi)", {"sigma": 1}), math.sqrt(2 * math.pi))
    assert math.isnan(vizcheck.value("1/0", {})) and math.isnan(vizcheck.value("q+1", {}))
    assert vizcheck.resolve("x/[n]", {"n": "2*[m]", "m": "3"}) == "x/(2*(3))"


def test_a_plot_with_an_unknown_part_names_the_cause_once():
    spec = {"type": "formula", "caption": "c", "tex": r"y = {{a}} \cdot {{k}} \cdot x",
            "parts": [{"id": "a", "tex": "a", "label": "a", "param": "a"},
                      {"id": "k", "tex": "2", "label": "factor", "expr": "2",
                       "variants": [{"tex": "3", "expr": "3", "why": "steeper"}]}],
            "params": [{"name": "a", "min": 0, "max": 5, "value": 1}],
            "plotExpr": "[a]*[k]*[scale]*x", "checks": [{"kind": "peak", "label": "peak", "expect": 10}]}
    clean, problems = viz.inspect(spec)
    assert "plotExpr" not in clean
    assert problems[0].startswith("the plot") and "uses [scale], but no part has that id" in problems[0] and "a, k" in problems[0]
    assert "1 variant(s) and the checks that need it were removed too" in problems[1]
    assert not any("changes nothing" in x or "use [k]" in x for x in problems)  # no advice that hides the cause
