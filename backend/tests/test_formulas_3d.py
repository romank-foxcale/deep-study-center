"""Formula hover notes and the 3D surface widget (SPEC §33)."""

from dsc import formulas, lesson, viz

CID = "c-lincomb"


def test_formulas_are_found_and_keyed_without_spaces():
    text = (r"A sum $$w = \sum_i c_i v_i$$ and $a(1, 0) + b(1, 1) = (3, 2)$, a lone $x$, and again $$ w=\sum_i c_i v_i $$."
            "\n\n" r"$$\begin{aligned}" "\n" r"a &= 1\\" "\n" r"b &= 2" "\n" r"\end{aligned}$$")
    found = formulas.extract(text)
    assert found[0] == r"w = \sum_i c_i v_i" and "a(1, 0) + b(1, 1) = (3, 2)" in found and "x" not in found
    assert len([f for f in found if "sum" in f]) == 1  # the same formula with other spaces is one formula
    assert any(f.startswith(r"\begin{aligned}") for f in found)
    assert formulas.key("a &= 1\\\\\n b") == "a&=1\\\\b"


def test_notes_are_written_once_with_symbols_and_ideas(env):
    db, jobs, runner = env
    db.set_meta("formula_notes", "1")
    seen = []

    def reply(call):
        seen.append(call.prompt)
        n = sum(1 for line in call.prompt.splitlines() if line[:3].rstrip(". ").isdigit() and ". " in line[:5])
        return {"formulas": [{"n": i + 1, "name": f"Formula {i + 1}", "meaning": "It says something.",
                              "symbols": [{"tex": "c_i", "meaning": "a weight"}], "ideas": ["c-lincomb", "n-not-offered"]}
                             for i in range(n)]}
    runner.responses["Formula notes"] = reply
    runner.responses["Renditions"] = lambda call: {"sections": [
        {"id": line.split()[1], "body": "Combine: $$w = c_1 v_1 + c_2 v_2$$ and solve $a + b = 3$."}
        for line in call.prompt.splitlines() if line.startswith("- s-")]}
    v = lesson.open_lesson(db, jobs, CID)
    notes = lesson.view(db, CID)["formulas"]
    assert seen and "w = c_1 v_1 + c_2 v_2" in seen[0] and "- c-lincomb:" in seen[0]
    note = notes[formulas.key("w = c_1 v_1 + c_2 v_2")]
    assert note["name"].startswith("Formula") and note["symbols"] == [{"tex": "c_i", "meaning": "a weight"}]
    assert [i["id"] for i in note["ideas"]] == ["c-lincomb"] and note["ideas"][0]["here"]  # ids not offered are dropped
    calls = len(seen)
    lesson.open_lesson(db, jobs, CID)
    assert len(seen) == calls and v is not None  # saved: not written again


def test_the_3d_surface_is_checked():
    ok = viz.validate({"type": "surface3d", "caption": "valley", "expr": "0.15*x^2 + 2*y^2", "start": [-2.7, 1.5],
                       "optimizers": ["sgd", "adam", "bogus", "adam"], "lr": 5, "steps": 1000})
    assert ok["optimizers"] == ["sgd", "adam"] and ok["lr"] == 2.0 and ok["steps"] == 300 and ok["ymin"] == -3.0
    assert viz.validate({"type": "surface3d", "caption": "", "expr": "z*x"}) is None  # only x and y
    assert viz.validate({"type": "surface3d", "caption": "", "expr": "x^2+y^2", "start": [99, 0]})["start"] == [3.0, 0.0]
