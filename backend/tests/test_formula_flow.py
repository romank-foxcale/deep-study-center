"""The formula flow of a formula page (SPEC §52): written by an agent, checked by code the way the page computes it."""

import copy

import pytest

from dsc import actions, formula_flow, lesson

SPEED = {"inputs": [{"id": "d", "sym": "d", "label": "distance, km", "value": 120, "min": 1, "max": 500, "step": 1},
                    {"id": "t", "sym": "t", "label": "time, h", "value": 1.5, "min": 0.1, "max": 10, "step": 0.1}],
         "nodes": [{"id": "trip", "label": "the trip", "input": ["d", "t"], "tex": "{d} km in {t} h", "say": "What you measured."},
                   {"id": "v", "sym": "v", "label": "speed", "uses": ["trip"], "tex": "{v} = {d}/{t}", "expr": "d/t", "say": "Distance per hour.",
                    "whatif": [{"tex": "{v} = {d} t", "expr": "d*t", "why": "The unit would be km·h.", "ok": False}]},
                   {"id": "h", "sym": "t_{100}", "label": "hours for 100 km", "uses": ["v"], "tex": "{h} = 100/{v}", "expr": "100/v",
                    "say": "The time for 100 km."}]}
SOFTMAX = {"inputs": [{"id": "z1", "sym": "z_1", "label": "score 1", "value": 2, "min": -4, "max": 4},
                      {"id": "z2", "sym": "z_2", "label": "score 2", "value": 1, "min": -4, "max": 4}],
           "nodes": [{"id": "z", "label": "scores", "input": ["z1", "z2"], "tex": "z = ({z1}, {z2})", "say": "The scores."},
                     {"id": "ez", "sym": "e", "label": "positive", "uses": ["z"], "tex": "{ez}_i = exp(z_i)", "expr": ["exp(z1)", "exp(z2)"],
                      "say": "Make them positive.", "whatif": [{"tex": "z_i^2", "expr": ["z1^2", "z2^2"], "why": "Order is lost.", "ok": False}]},
                     {"id": "s", "sym": "S", "label": "total", "uses": ["ez"], "tex": "{s} = sum", "expr": "ez_1 + ez_2", "say": "The total."},
                     {"id": "p", "sym": "p", "label": "softmax", "uses": ["ez", "s"], "tex": "{p}_i", "expr": ["ez_1/s", "ez_2/s"], "say": "Weights."}]}


def test_a_good_flow_passes_and_computes_like_the_page():
    spec, problems = formula_flow.check(copy.deepcopy(SPEED))
    assert problems == [] and [n["id"] for n in spec["nodes"]] == ["trip", "v", "h"]
    vals = formula_flow.compute(spec)
    assert vals["v"] == 80 and round(vals["h"], 4) == 1.25
    assert formula_flow.compute(spec, swap={"v": "d*t"})["v"] == 180  # a what-if changes the box and every box below
    spec, problems = formula_flow.check(copy.deepcopy(SOFTMAX))
    p = formula_flow.compute(spec)["p"]
    assert problems == [] and abs(sum(p) - 1) < 1e-9 and p[0] > p[1]


@pytest.mark.parametrize("change, problem", [
    (lambda f: f["nodes"][2].update(expr="100/w"), "uses w, which is not an input or an earlier box"),
    (lambda f: f["nodes"][1].update(uses=["h"]), "uses h, which are not earlier boxes"),
    (lambda f: f["inputs"][1].update(min=0), "cannot be computed at t = 0"),
    (lambda f: f["nodes"][0].update(input=["d"]), "input t is in no input box"),
    (lambda f: f["inputs"][0].update(id="exp"), "input id “exp”"),
    (lambda f: f["nodes"][1].update(say=""), "box v: write `say`"),
    (lambda f: f["nodes"][2].update(tex="{h} = 100/{q}"), "its tex names {q}"),
    (lambda f: f["nodes"][1]["whatif"][0].update(expr=["d", "t"]), "same shape as the box"),
])
def test_the_check_names_every_problem(change, problem):
    f = copy.deepcopy(SPEED)
    change(f)
    spec, problems = formula_flow.check(f)
    assert spec is None and any(problem in p for p in problems), problems


@pytest.fixture
def page(env):
    db, jobs, runner = env
    db.x("INSERT INTO formula_lessons(id, name, source_concept, preferred, created_at) VALUES('c-dot', 'Speed', 'c-vectors', NULL, 'x')")
    db.x("INSERT INTO formula_forms(formula_id, key, tex, concept_id, added_at) VALUES('c-dot', 'v=d/t', 'v = d/t', 'c-vectors', 'x')")
    return db, jobs, runner


def test_the_job_fixes_a_flow_once_and_the_page_gets_it(page):
    db, jobs, runner = page
    broken = copy.deepcopy(SPEED)
    broken["nodes"][2]["expr"] = "100/w"
    prompts = []
    runner.responses["Lesson assets"] = lambda call: prompts.append(call.prompt) or copy.deepcopy(broken if len(prompts) == 1 else SPEED)
    actions.dispatch(db, jobs, {"type": "makeFormulaFlow", "conceptId": "c-dot"})
    assert len(prompts) == 2 and "box h: `expr` uses w" in prompts[1] and "v = d/t" in prompts[0]
    flow = lesson.view(db, "c-dot")["formulaLesson"]["flow"]
    assert flow["status"] == "ready" and [n["id"] for n in flow["spec"]["nodes"]] == ["trip", "v", "h"]


def test_a_flow_that_stays_broken_fails_and_only_a_formula_page_has_one(page):
    db, jobs, runner = page
    runner.responses["Lesson assets"] = lambda call: {"inputs": [], "nodes": []}
    actions.dispatch(db, jobs, {"type": "makeFormulaFlow", "conceptId": "c-dot"})  # the job fails; the page shows why
    flow = formula_flow.get(db, "c-dot")
    assert flow["status"] == "failed" and "no inputs" in flow["error"]
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "makeFormulaFlow", "conceptId": "c-vectors"})
