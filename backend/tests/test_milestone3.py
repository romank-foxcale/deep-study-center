"""Explain-back grading, placement, research-ahead, reflection, and the Codex/Cursor adapters."""

import json
import subprocess
from pathlib import Path

import pytest

from dsc import actions, engine, lesson, providers, state
from dsc.api import maybe_reflect


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


GOOD = "Moving right doesn't change how far up you are, so each coordinate just adds up on its own."


# ---------------------------------------------------------------- explain-back

def test_explain_back_is_graded_by_the_grader_with_partial_credit(env):
    db, jobs, runner = env
    v = lesson.open_lesson(db, jobs, "c-vectors")
    ex = next(s["explain"] for s in v["sections"] if s["explain"])
    assert ex["id"] == "e-ops" and "rubric" not in ex  # rubric hidden from the learner
    assert all("rubric" not in (s.get("explain") or {}) for c in state.snapshot(db)["cards"] for s in c["sections"])

    runner.responses["Grading"] = {"score": 0.5, "feedback": "Right idea, add a picture.", "missing": ["example"], "followup": "Can you draw it?"}
    s = act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer=GOOD, angle="geometric")
    role, call = runner.calls[-1]
    assert role == "Grading" and f"<learner>\n{GOOD}\n</learner>" in call.prompt and "tip-to-tail" in call.prompt
    g = s["gradings"]["c-vectors:e-ops"]
    assert (g["status"], g["score"], g["missing"], g["followup"]) == ("graded", 0.5, ["example"], "Can you draw it?")
    assert s["answers"]["c-vectors:e-ops"]["score"] == 0.5 and not s["answers"]["c-vectors:e-ops"]["correct"]


def test_explain_back_needs_real_text_and_survives_no_provider(env):
    db, jobs, runner = env
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer="idk")
    runner.unavailable = True
    s = act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer=GOOD)
    assert s["gradings"]["c-vectors:e-ops"]["status"] == "ungraded"
    assert "c-vectors:e-ops" not in s["answers"]  # no evidence without a grade


def test_soft_evidence_moves_bkt_between_fail_and_pass():
    p = 0.4
    assert engine.bkt(p, 0.0) < engine.bkt(p, 0.5) < engine.bkt(p, 1.0)


# ---------------------------------------------------------------- research ahead

def _research(call):
    return {"concepts": [{"key": "k1", "title": "Derivatives", "objective": "o", "minutes": 20, "prereq_keys": [],
                          "card": {"bloom": "apply", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                                   "misconceptions": [], "sources": [],
                                   "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"],
                                                 "explain": {"prompt": "Why?", "rubric": ["r"]}}]}}]}


def test_research_stays_one_module_ahead(env):
    db, jobs, runner = env
    runner.responses["Research"] = _research
    runner.responses["Fact-check"] = {"results": []}
    lesson.open_lesson(db, jobs, "c-vectors")
    assert not any(r == "Research" for r, _ in runner.calls)  # off by default in tests

    act(db, jobs, type="setSetting", key="autoResearch", value=True)
    researched = [r for r, _ in runner.calls if r == "Research"]
    assert len(researched) == 1  # m-calc (next after linear algebra), and no further
    mods = {m["id"]: m for m in state.snapshot(db)["modules"]}
    assert mods["m-calc"]["research"] == "ready" and mods["m-prob"]["research"] == "outline"
    card = state.latest_card(db, mods["m-calc"]["conceptIds"][0])
    assert card["sections"][0]["explain"]["id"] == "e-s-1"
    lesson.open_lesson(db, jobs, "c-vectors")
    assert len([r for r, _ in runner.calls if r == "Research"]) == 1


# ---------------------------------------------------------------- reflection

def test_reflection_proposals_change_the_playbook_only_when_accepted(env):
    db, jobs, runner = env
    runner.responses["Reflection"] = {"summary": "Code lands, arrows don't.", "proposals": [
        {"dimension": "angle", "value": "geometric", "verdict": "avoid", "why": "3 framing complaints"},
        {"dimension": "pace", "value": "pace", "delta": -1, "why": "too fast twice"},
        {"dimension": "angle", "value": "computational", "why": "no verdict: dropped"}]}
    for _ in range(3):
        act(db, jobs, type="feedback", conceptId="c-vectors", tags=["too-fast"], text="")
    maybe_reflect(db, jobs)
    s = state.snapshot(db)
    r = s["reflections"][0]
    assert r["summary"].startswith("Code lands") and len(r["proposals"]) == 2
    before = state.playbook(db)
    s = act(db, jobs, type="decideProposal", reflectionId=r["id"], index=0, accept=True)
    geo = next(e for e in s["playbook"]["entries"] if e["value"] == "geometric")
    assert geo["verdict"] == "avoid" and s["playbook"]["version"] > before["version"]
    s = act(db, jobs, type="decideProposal", reflectionId=r["id"], index=1, accept=False)
    assert s["playbook"]["adjust"]["pace"] == before["adjust"]["pace"]
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="decideProposal", reflectionId=r["id"], index=1, accept=True)
    maybe_reflect(db, jobs)  # not again within a week
    assert len([c for c, _ in runner.calls if c == "Reflection"]) == 1


def test_reflection_offline_fallback(env):
    db, jobs, runner = env
    runner.unavailable = True
    s = act(db, jobs, type="reflect")
    assert s["reflections"][0]["source"] == "offline" and s["reflections"][0]["proposals"] == []


# ---------------------------------------------------------------- adapters

def test_strict_schema_and_json_extraction():
    schema = {"type": "object", "required": ["a"], "properties": {
        "a": {"type": "string"}, "b": {"type": "array", "items": {"type": "object", "properties": {"c": {"type": "integer"}}}}}}
    st = providers.strict_schema(schema)
    assert st["required"] == ["a", "b"] and st["additionalProperties"] is False
    assert st["properties"]["b"]["anyOf"][1] == {"type": "null"}
    assert st["properties"]["b"]["anyOf"][0]["items"]["required"] == ["c"]
    assert providers.extract_json('Sure:\n```json\n{"a": "x", "b": null}\n```') == {"a": "x", "b": None}
    assert providers.drop_nulls({"a": "x", "b": None, "l": [{"c": None}]}) == {"a": "x", "l": [{}]}
    with pytest.raises(providers.ProviderError):
        providers.extract_json("no json here")


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_codex_adapter_command_auth_and_output(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, env=kw["env"], input=kw["input"])
        Path(cmd[cmd.index("--output-last-message") + 1]).write_text('{"n": 4, "extra": null}', encoding="utf-8")
        return FakeProc(stdout="ignored")

    monkeypatch.setattr(providers.shutil, "which", lambda b: f"/bin/{b}")
    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    out = providers.CodexCLI().run(providers.Call(prompt="hi", schema={"type": "object", "properties": {"n": {"type": "integer"}}},
                                                  model="default", tools=("WebSearch",)), tmp_path)
    assert out == {"n": 4}
    cmd = seen["cmd"]
    assert cmd[1:3] == ["--search", "exec"] and cmd[-1] == "-" and seen["input"] == "hi"  # --search is a top-level option
    assert ["--sandbox", "read-only"] == cmd[cmd.index("--sandbox"):cmd.index("--sandbox") + 2]
    assert "--model" not in cmd and "--output-schema" in cmd
    assert "OPENAI_API_KEY" not in seen["env"]
    schema = json.loads((tmp_path / "codex-schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False


def test_codex_rate_limit_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda b: f"/bin/{b}")
    monkeypatch.setattr(providers.subprocess, "run", lambda cmd, **kw: FakeProc(stderr="You've hit your usage limit", returncode=1))
    with pytest.raises(providers.ProviderUnavailable):
        providers.CodexCLI().run(providers.Call(prompt="hi"), tmp_path)


def test_cursor_adapter_parses_result_and_strips_api_key(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, env=kw["env"])
        return FakeProc(stdout=json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                           "result": 'Here you go: {"score": 1}'}))

    monkeypatch.setattr(providers.shutil, "which", lambda b: "/bin/agent" if b == "agent" else None)
    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    monkeypatch.setenv("CURSOR_API_KEY", "key")
    out = providers.CursorCLI().run(providers.Call(prompt="grade", schema={"type": "object"}), tmp_path)
    assert out == {"score": 1}
    assert seen["cmd"][0] == "/bin/agent" and "--mode" in seen["cmd"] and "JSON Schema" in seen["cmd"][-1]
    assert "CURSOR_API_KEY" not in seen["env"]


def test_fallback_to_claude_uses_the_call_model(monkeypatch, tmp_path):
    used = []

    class Missing(providers.Provider):
        name = "codex"

        def run(self, call, cwd):
            raise providers.ProviderUnavailable("missing")

    class Claude(providers.Provider):
        name = "claude"

        def run(self, call, cwd):
            used.append(call.model)
            return "ok"

    monkeypatch.setitem(providers.PROVIDERS, "codex", Missing())
    monkeypatch.setitem(providers.PROVIDERS, "claude", Claude())
    out, name = providers.run_with_fallback({"provider": "codex", "model": "default"}, providers.Call(prompt="x", model="opus"), tmp_path)
    assert (out, name, used) == ("ok", "claude", ["opus"])
