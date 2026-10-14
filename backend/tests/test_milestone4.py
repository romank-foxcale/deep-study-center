"""Local runner, visuals, shared library, search and Anki export."""

import sqlite3
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from dsc import actions, lesson, library, runner, state, viz
from dsc.api import create_app


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def learn_vectors(db, jobs, runner_fake):
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice)
    runner_fake.responses["Grading"] = {"score": 1, "feedback": "ok", "missing": [], "followup": ""}
    return act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer="Each axis moves independently, so the parts add up.")


# ---------------------------------------------------------------- local runner

@pytest.mark.parametrize("src", [
    "import os", "import subprocess as sp", "from socket import socket", "from pathlib import Path",
    "open('secrets.txt')", "__import__('os')", "().__class__.__bases__[0].__subclasses__()",
    "getattr(x, 'system')", "exec('print(1)')", "import urllib.request", "from . import x",
])
def test_static_check_blocks_dangerous_code(src):
    assert runner.static_check(src)


def test_static_check_allows_ordinary_exercise_code():
    src = ("import torch\nimport numpy as np\nimport math\n"
           "class M(torch.nn.Module):\n    def __init__(self):\n        super().__init__()\n"
           "def f(x):\n    return torch.tensor(x).sum().item() + math.sqrt(4)\n"
           "assert f([1, 2]) == 5.0\nprint(f'All tests passed {np.pi:.2f}')\n")
    assert runner.static_check(src) == []
    assert runner.static_check("def f(:\n") and "syntax" in runner.static_check("def f(:\n")[0]


def test_runner_executes_in_isolated_python(tmp_path, monkeypatch):
    monkeypatch.setenv("DSC_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(runner, "python_path", lambda: sys.executable)
    monkeypatch.setenv("SECRET_TOKEN", "do-not-pass")
    ok = runner.run("def add(a, b):\n    return a + b\n", "assert add(2, 3) == 5\nprint('All tests passed ✓')", "t1")
    assert ok == {"passed": True, "output": "All tests passed ✓"}
    bad = runner.run("def add(a, b):\n    return a - b\n", "assert add(2, 3) == 5, 'add(2, 3) should be 5'\nprint('All tests passed')", "t2")
    assert not bad["passed"] and "add(2, 3) should be 5" in bad["output"]
    # the environment is minimal: tokens from the parent process are not passed on
    leak = runner.run("import json", "print(json.dumps(sorted(__import__('os').environ)))", "t3")  # bypasses the static check on purpose
    assert "SECRET_TOKEN" not in leak["output"]


def test_run_endpoint_requires_setup_approval_and_a_clean_check(env, monkeypatch):
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    body = {"conceptId": "c-lincomb", "itemId": "x-neuron", "code": "import torch\ndef neuron(x):\n    return x[:1]\n"}
    monkeypatch.setattr(runner, "is_set_up", lambda: False)
    assert client.post("/api/run", json=body).json() == {"status": "needs_setup"}

    monkeypatch.setattr(runner, "is_set_up", lambda: True)
    calls = []
    monkeypatch.setattr(runner, "run", lambda code, tests, rid: calls.append(code) or {"passed": True, "output": "All tests passed"})
    r = client.post("/api/run", json=body).json()
    assert r["status"] == "needs_approval" and "torch.tensor([3.0, 4.0, 2.0])" in r["tests"] and not calls
    r = client.post("/api/run", json={**body, "approve": True}).json()
    assert r == {"status": "ran", "passed": True, "output": "All tests passed"}
    assert state.snapshot(db)["answers"]["c-lincomb:x-neuron"]["correct"]
    r = client.post("/api/run", json={**body, "code": "import os\n" + body["code"]}).json()
    assert r["status"] == "blocked" and "os" in r["problems"][0] and len(calls) == 1

    # changed tests (a new card version) need a new approval
    from dsc.db import dumps
    card = state.latest_card(db, "c-lincomb")
    sec = next(s for s in card["sections"] if s["id"] == "s-neuron")
    sec["code"]["tests"] += "\nprint('extra')"
    body_json = {k: v for k, v in card.items() if k not in ("conceptId", "version", "factCheck", "checkedAt")}
    db.x("INSERT INTO cards VALUES(?,?,?,?,?)", ("c-lincomb", card["version"] + 1, dumps(body_json), "passed", "2026-10-14"))
    assert client.post("/api/run", json=body).json()["status"] == "needs_approval"
    assert client.post("/api/run", json={"conceptId": "c-vectors", "itemId": "x-vec", "code": ""}).status_code == 400


# ---------------------------------------------------------------- visuals

def test_viz_validation_keeps_only_safe_specs():
    assert viz.validate({"type": "plot", "expr": "a*sin(b*x) + relu(x)^2", "xmin": -3, "xmax": 3, "caption": "c",
                         "params": [{"name": "a", "min": 0, "max": 2, "value": 1}, {"name": "b", "min": 0, "max": 5, "value": 9}]}) == {
        "type": "plot", "caption": "c", "expr": "a*sin(b*x) + relu(x)^2", "xmin": -3.0, "xmax": 3.0,
        "params": [{"name": "a", "min": 0.0, "max": 2.0, "value": 1.0}, {"name": "b", "min": 0.0, "max": 5.0, "value": 5.0}]}
    for expr in ("__import__('os')", "x; alert(1)", "fetch(x)", "constructor(x)", "x" * 200, "c*x"):
        assert viz.validate({"type": "plot", "expr": expr, "caption": ""}) is None, expr
    assert viz.validate({"type": "matrix2d", "matrix": [[1, 99], [0, 1]], "caption": ""})["matrix"] == [[1.0, 10.0], [0.0, 1.0]]
    assert viz.validate({"type": "matrix2d", "matrix": [[1, "x"], [0, 1]]}) is None
    assert viz.validate({"type": "script", "code": "alert(1)"}) is None
    assert viz.validate({"type": "vectors2d", "vectors": []}) is None


def test_lesson_view_carries_viz_and_local_runtime(env):
    db, jobs, runner_fake = env
    runner_fake.responses["Renditions"] = lambda call: {"sections": [
        {"id": line.split()[1], "body": "t"} for line in call.prompt.splitlines() if line.startswith("- s-")]}
    v = lesson.open_lesson(db, jobs, "c-lincomb")
    reach = next(s for s in v["sections"] if s["id"] == "s-reach")
    assert reach["viz"]["type"] == "lincomb2d"
    assert next(s for s in v["sections"] if s["id"] == "s-neuron")["code"]["runtime"] == "local"


# ---------------------------------------------------------------- shared library

def _research_reusing(call):
    assert "- vectors: Vectors" in call.prompt  # the library index is offered to the researcher
    return {"concepts": [
        {"key": "vec", "title": "Vectors", "objective": "o", "minutes": 20, "prereq_keys": [], "reuse_key": "vectors"},
        {"key": "new", "title": "Derivative", "objective": "o", "minutes": 20, "prereq_keys": ["vec"],
         "card": {"bloom": "apply", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [], "misconceptions": [],
                  "sources": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"],
                                               "viz": {"type": "plot", "expr": "import os", "caption": "bad"},
                                               "code": {"prompt": "p", "starter": "", "tests": "print('All tests passed')", "runtime": "gpu"}}]}},
        {"key": "ghost", "title": "Missing", "objective": "o", "minutes": 5, "prereq_keys": [], "reuse_key": "nope"}]}


def test_promoted_cards_are_reused_by_research(env):
    db, jobs, runner_fake = env
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="promoteCard", conceptId="c-lincomb")  # fact-check pending
    s = act(db, jobs, type="promoteCard", conceptId="c-vectors")
    assert s["library"][0]["key"] == "vectors" and s["library"][0]["version"] == 1

    runner_fake.responses["Research"] = _research_reusing
    runner_fake.responses["Fact-check"] = lambda call: {"results": []}
    s = act(db, jobs, type="researchModule", moduleId="m-calc")
    calc = next(m for m in s["modules"] if m["id"] == "m-calc")
    assert len(calc["conceptIds"]) == 2  # the unknown reuse_key without a card is dropped
    reused = state.latest_card(db, "m-calc-vec")
    assert reused["factCheck"] == "passed" and reused["core"] == state.latest_card(db, "c-vectors")["core"]
    fresh = state.latest_card(db, "m-calc-new")
    assert "viz" not in fresh["sections"][0] and fresh["sections"][0]["code"]["runtime"] == "pyodide"
    checked = [c for role, c in runner_fake.calls if role == "Fact-check"]
    assert len(checked) == 1 and "m-calc-vec" not in checked[0].prompt  # reused cards aren't re-checked
    assert state.snapshot(db)["library"][0]["uses"] == 1


# ---------------------------------------------------------------- search

def test_search_finds_notes_lessons_and_cards(env):
    db, jobs, _ = env
    lesson.open_lesson(db, jobs, "c-vectors")
    act(db, jobs, type="addNote", conceptId="c-vectors", text="Remember: norms are not additive", quote="triangle inequality")
    hits = library.search(db, "additive")
    assert hits[0]["kind"] == "note" and "[[additive]]" in hits[0]["snippet"]
    kinds = {h["kind"] for h in library.search(db, "tip")}
    assert "lesson" in kinds
    assert any(h["kind"] == "card" and h["conceptId"] == "c-vectors" for h in library.search(db, "componentwise"))
    assert library.search(db, "   ") == [] and library.search(db, "zzzqqq") == []
    client = TestClient(create_app(db=db, jobs=jobs))
    assert client.get("/api/search", params={"q": "additive"}).json()[0]["conceptId"] == "c-vectors"


# ---------------------------------------------------------------- Anki

def test_anki_export_contains_learned_concepts_only(env, tmp_path):
    db, jobs, runner_fake = env
    learn_vectors(db, jobs, runner_fake)
    path = library.export_anki(db)
    with zipfile.ZipFile(path) as z:
        (tmp_path / "c.db").write_bytes(z.read("collection.anki2"))
    notes = [r[0] for r in sqlite3.connect(tmp_path / "c.db").execute("SELECT flds FROM notes")]
    assert len(notes) == 4  # 3 checks + 1 explain-back, all from Vectors
    assert any("\\(2 \\cdot (1, -3) + (0, 4)\\)" in n for n in notes)  # $math$ converted for Anki
    assert all("Vectors" in n for n in notes)
    assert state.snapshot(db)["ankiExport"].endswith("|4")
