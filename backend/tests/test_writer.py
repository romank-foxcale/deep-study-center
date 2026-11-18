"""Writing a lesson in steps: planner, graphs and questions, prose, reviewer (SPEC §14)."""

from dsc import actions, lesson, state, versions, writer

CID = "c-lincomb"  # a demo lesson without prose: opening it writes the whole lesson


def prose_reply(tag="text"):
    return lambda call: {"sections": [{"id": line.split()[1], "body": f"{tag} {line.split()[1]}"}
                                      for line in call.prompt.splitlines() if line.startswith("- s-")]}


def plan_reply(card, **over):
    secs = []
    for s in card["sections"]:
        p = {"id": s["id"], "angle": (s.get("angles") or ["geometric"])[0], "brief": f"brief for {s['id']}", "viz": "keep", "check": "keep"}
        p.update(over.get(s["id"], {}))
        secs.append(p)
    return {"summary": "numbers first, then pictures", "sections": secs}


def test_whole_lesson_goes_through_plan_assets_prose_and_review(env):
    db, jobs, runner = env
    card = state.latest_card(db, CID)
    target = card["sections"][1]["id"]
    alt = next(a for a in target_angles(card, target) if a != (card["sections"][1].get("angles") or ["x"])[0])
    runner.responses["Lesson planner"] = plan_reply(card, **{target: {"angle": alt, "viz": "new", "check": "new"}})
    runner.responses["Lesson assets"] = {"sections": [{"id": target, "why": "a picture first",
        "viz": {"type": "vectors2d", "caption": "Two arrows", "vectors": [{"x": 1, "y": 2, "label": "u"}]},
        "check": {"prompt": "Which is a linear combination of u and v?", "options": ["2u + 3v", "u * v", "|u|", "u / v"],
                  "answer": 0, "explanation": "Scale and add."}}]}
    runner.responses["Renditions"] = prose_reply()
    runner.responses["Lesson review"] = {"summary": "one problem", "issues": [
        {"section_id": target, "part": "prose", "problem": "too abstract", "fix": "start with numbers", "source": "guideline 1"}]}

    v = lesson.open_lesson(db, jobs, CID)
    roles = [r for r, _ in runner.calls]
    assert roles[:3] == ["Lesson planner", "Lesson assets", "Renditions"] and roles[3] == "Lesson review" and roles[4] == "Renditions"
    first_prose = [c for r, c in runner.calls if r == "Renditions"][0].prompt
    assert f"Plan: brief for {target}" in first_prose and 'Graph: vectors2d, "Two arrows"' in first_prose
    fix_prose = [c for r, c in runner.calls if r == "Renditions"][1].prompt
    assert "Fix: start with numbers" in fix_prose

    sec = next(s for s in v["sections"] if s["id"] == target)
    assert sec["angle"] == alt and sec["vizMine"] and sec["checkMine"] and sec["check"]["id"] == f"p-{target}"
    assert "answer" not in sec["check"]  # the key stays hidden
    assert v["plan"]["summary"] == "numbers first, then pictures" and v["plan"]["review"]["fixed"] == [target]
    assert len(versions.all_versions(db, CID)) == 1  # the draft before the fix never became a version

    # the question made for this learner is graded with its own key
    actions.dispatch(db, jobs, {"type": "answer", "conceptId": CID, "checkId": f"p-{target}", "choice": 0})
    assert state.answers(db, [CID])[f"{CID}:p-{target}"]["correct"]


def target_angles(card, sid):
    return next(s for s in card["sections"] if s["id"] == sid).get("angles") or ["geometric", "algebraic", "computational"]


def test_a_new_quiz_question_with_a_wrong_key_is_dropped_by_the_review(env):
    db, jobs, runner = env
    card = state.latest_card(db, CID)
    target = next(s["id"] for s in card["sections"] if s.get("check"))
    runner.responses["Lesson planner"] = plan_reply(card, **{target: {"check": "new"}})
    runner.responses["Lesson assets"] = {"sections": [{"id": target, "why": "x", "check": {
        "prompt": "2 + 2?", "options": ["3", "4", "5"], "answer": 0, "explanation": "wrong key"}}]}
    runner.responses["Renditions"] = prose_reply()
    runner.responses["Lesson review"] = {"summary": "bad key", "issues": [
        {"section_id": target, "part": "check", "problem": "the marked answer is wrong", "fix": "drop it", "source": ""}]}
    v = lesson.open_lesson(db, jobs, CID)
    sec = next(s for s in v["sections"] if s["id"] == target)
    assert not sec["checkMine"] and sec["check"]["id"] == next(s for s in card["sections"] if s["id"] == target)["check"]["id"]
    assert v["plan"]["review"]["dropped"] == [f"{target}:check"]


def test_without_planner_and_reviewer_the_lesson_is_still_written(env):
    db, jobs, runner = env
    runner.responses["Renditions"] = prose_reply()  # no responses for the other roles: those steps fail
    v = lesson.open_lesson(db, jobs, CID)
    assert all(s["body"] and s["body"].startswith("text") for s in v["sections"])
    assert not any(s["vizMine"] or s["checkMine"] for s in v["sections"]) and v["plan"] is None
    job = next(j for j in state.snapshot(db)["jobs"] if j["kind"] == "render")
    assert job["status"] == "done" and any("plan: skipped" in m for m in job["progress"])


def test_explain_differently_uses_the_stored_brief(env):
    db, jobs, runner = env
    card = state.latest_card(db, CID)
    runner.responses["Lesson planner"] = plan_reply(card)
    runner.responses["Renditions"] = prose_reply()
    runner.responses["Lesson review"] = {"summary": "fine", "issues": []}
    lesson.open_lesson(db, jobs, CID)
    sid = card["sections"][0]["id"]
    other = next(a for a in target_angles(card, sid) if a != lesson.view(db, CID)["sections"][0]["angle"])
    n = len(runner.calls)
    actions.dispatch(db, jobs, {"type": "explainDifferently", "conceptId": CID, "sectionId": sid, "angle": other})
    new = [(r, c) for r, c in runner.calls[n:]]
    assert [r for r, _ in new] == ["Renditions"] and f"Plan: brief for {sid}" in new[0][1].prompt
    assert writer.current_plan(db, CID, card["version"])["plan"]["summary"]


def test_one_call_setting_writes_the_lesson_with_the_text_writer_only(env):
    db, jobs, runner = env
    actions.dispatch(db, jobs, {"type": "setSetting", "key": "lessonWriting", "value": "single"})
    assert state.snapshot(db)["settings"]["lessonWriting"] == "single"
    runner.responses["Renditions"] = prose_reply()
    v = lesson.open_lesson(db, jobs, CID)
    assert [r for r, _ in runner.calls] == ["Renditions"] and all(s["body"] for s in v["sections"]) and v["plan"] is None


def test_recommended_routes(env, monkeypatch):
    from dsc import providers
    db, jobs, _ = env
    routes = {r["role"]: r for r in state.snapshot(db)["routes"]}
    assert routes["Lesson planner"]["recommended"]["model"] == "opus" and routes["Lesson planner"]["recommended"]["why"]
    db.x("UPDATE routes SET model='haiku' WHERE role='Renditions'")
    monkeypatch.setattr(providers, "status", lambda: [{"id": "claude", "detected": True}, {"id": "codex", "detected": False}])
    actions.dispatch(db, jobs, {"type": "useRecommendedRoutes"})
    routes = {r["role"]: r for r in state.snapshot(db)["routes"]}
    assert routes["Renditions"]["model"] == "sonnet"
    assert (routes["Fact-check"]["provider"], routes["Fact-check"]["model"]) == ("claude", "opus")  # Codex not installed


def test_refresh_for_current_me_writes_the_whole_lesson_again_as_a_new_version(env):
    db, jobs, runner = env
    card = state.latest_card(db, CID)
    runner.responses["Lesson planner"] = plan_reply(card)
    runner.responses["Renditions"] = prose_reply("first")
    runner.responses["Lesson review"] = {"summary": "fine", "issues": []}
    lesson.open_lesson(db, jobs, CID)
    runner.responses["Renditions"] = prose_reply("again")
    actions.dispatch(db, jobs, {"type": "refresh", "conceptId": CID})
    v = lesson.view(db, CID)
    assert all(s["body"].startswith("again") for s in v["sections"]) and v["head"] == 2
    assert versions.get(db, CID, 2)["summary"].startswith("Written again")


def test_formula_widget_validation():
    from dsc import viz
    gauss = {"type": "formula", "caption": "The normal distribution",
             "tex": r"p(x) = \frac{1}{{{norm}}} \exp\left(-\frac{(x - {{mu}})^2}{2{{sigma}}^2}\right)",
             "parts": [{"id": "norm", "tex": r"{{sigma}}\sqrt{2\pi}", "label": "keeps the area under the curve at 1", "color": "green"},
                       {"id": "mu", "tex": r"\mu", "label": "mean: where the bell is centered", "color": "pink", "param": "mu"},
                       {"id": "sigma", "tex": r"\sigma", "label": "standard deviation: how wide the bell is", "color": "purple",
                        "side": "below", "param": "sigma"}],
             "formulaParams": [{"name": "mu", "min": -3, "max": 3, "value": 0}, {"name": "sigma", "min": 0.2, "max": 3, "value": 1}],
             "plotExpr": "exp(-((x-mu)^2)/(2*sigma^2))/(sigma*sqrt(2*pi))", "xmin": -5, "xmax": 5}
    out = viz.validate(gauss)
    assert out and out["type"] == "formula" and [p["param"] for p in out["parts"]] == [None, "mu", "sigma"]
    assert out["plotExpr"] and out["params"][1]["name"] == "sigma"
    # unsafe TeX, unknown parts and a part containing itself are refused
    assert viz.validate({**gauss, "tex": r"\href{http://x}{click} {{mu}}"}) is None
    assert viz.validate({**gauss, "tex": r"p = {{nope}}"}) is None
    assert viz.validate({**gauss, "parts": [{"id": "mu", "tex": r"{{mu}}", "label": "x"}], "tex": "{{mu}}"}) is None
    bad = {**gauss, "parts": [{**gauss["parts"][1], "tex": r"\htmlClass{x}{\mu}"}], "tex": "{{mu}}"}
    assert viz.validate(bad) is None
    # a bad plot formula drops only the plot
    assert "plotExpr" not in viz.validate({**gauss, "plotExpr": "__import__('os')"})


def test_formula_result_and_plot_over_a_parameter():
    from dsc import viz
    norm = {"type": "formula", "caption": "c", "tex": r"\lVert v \rVert = \sqrt{ {{a}}^2 + {{b}}^2 }",
            "parts": [{"id": "a", "tex": "a", "label": "x step", "param": "a"}, {"id": "b", "tex": "b", "label": "y step", "param": "b"}],
            "formulaParams": [{"name": "a", "min": 0, "max": 6, "value": 3, "effect": "longer"},
                              {"name": "b", "min": 0, "max": 6, "value": 4}],
            "resultExpr": "sqrt(a^2 + b^2)", "resultTex": r"\lVert v \rVert", "plotExpr": "sqrt(a^2 + b^2)", "plotVar": "a"}
    out = viz.validate(norm)
    assert out["resultExpr"] == "sqrt(a^2 + b^2)" and out["plotVar"] == "a" and (out["xmin"], out["xmax"]) == (0, 6)
    assert out["params"][0]["effect"] == "longer"
    assert "resultExpr" not in viz.validate({**norm, "resultExpr": "sqrt(z)"})  # unknown name: no result
    assert viz.validate({**norm, "plotVar": "nope"})["plotVar"] == "x"


def test_formula_variants_part_references_and_checks():
    from dsc import viz
    spec = {"type": "formula", "caption": "c", "tex": r"p(x) = \frac{1}{ {{norm}} } e^{-x^2/2{{sigma}}^2}",
            "parts": [{"id": "norm", "tex": r"{{sigma}}\sqrt{2\pi}", "label": "normalizer", "expr": "sigma*sqrt(2*pi)",
                       "variants": [{"tex": "1", "expr": "1", "why": "area not 1"},
                                    {"tex": r"\href{x}{y}", "expr": "2", "why": "unsafe"},
                                    {"tex": "2", "expr": "__import__", "why": "bad expr"},
                                    {"tex": "same", "expr": "sigma*sqrt(2*pi)", "why": "same as real"}]},
                      {"id": "sigma", "tex": r"\sigma", "label": "width", "param": "sigma"}],
            "formulaParams": [{"name": "sigma", "min": 0.2, "max": 3, "value": 1}],
            "plotExpr": "exp(-(x^2)/(2*sigma^2))/[norm]",
            "checks": [{"kind": "area", "label": "area", "expect": 1}, {"kind": "at", "label": "at 0", "at": 0},
                       {"kind": "result", "label": "no result here"}]}
    out = viz.validate(spec)
    assert out["parts"][0]["variants"] == [{"tex": "1", "expr": "1", "why": "area not 1"}]
    assert out["plotExpr"] == "exp(-(x^2)/(2*sigma^2))/[norm]"
    assert [c["kind"] for c in out["checks"]] == ["area", "at"]  # "result" needs a resultExpr
    assert "plotExpr" not in viz.validate({**spec, "plotExpr": "exp(-x)/[nope]"})  # unknown part reference
    assert "checks" not in viz.validate({**spec, "plotExpr": None})  # area needs a plot
