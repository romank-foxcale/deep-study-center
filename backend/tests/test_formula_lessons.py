"""Formula lessons and the colored formula frames (SPEC §34)."""

import pytest

from dsc import actions, formulas, lesson, state
from dsc.db import dumps

CID, OTHER = "c-lincomb", "c-vectors"
FORM_A = r"w = c_1 v_1 + c_2 v_2"
FORM_B = r"\mathbf{w} = \sum_i c_i \mathbf{v}_i"


def note(db, cid, tex, kind="idea", fid=None):
    db.x("""INSERT INTO formula_notes(concept_id, key, tex, body, created_at, kind, formula_id, matched_at) VALUES(?,?,?,?,?,?,?,?)""",
         (cid, formulas.key(tex), tex, dumps({"name": "Linear combination", "meaning": "A weighted sum of vectors.",
                                               "symbols": [{"tex": "c_i", "meaning": "weight"}], "ideas": []}), "2026-01-01", kind, fid,
          "2026-01-01"))


def card_reply(call):
    card_reply.prompts.append(call.prompt)
    return {"card": {"bloom": "understand", "core": "A weighted sum.", "formal": FORM_A, "why": "w", "examples": [],
                     "misconceptions": [], "sections": [
                         {"id": "s-parts", "heading": "What each part means", "purpose": "p", "angles": ["algebraic"],
                          "viz": {"type": "formula", "caption": "w", "tex": "w = {{c}} v", "parts": [
                              {"id": "c", "tex": "c", "label": "weight", "color": "green", "param": "c"}],
                              "formulaParams": [{"name": "c", "min": 0, "max": 2, "value": 1, "effect": "longer"}], "resultExpr": "c"}},
                         {"id": "s-origin", "heading": "Where it comes from", "purpose": "p", "angles": ["geometric"],
                          "explain": {"prompt": "Derive it.", "work": True, "rubric": ["scale", "add"]}},
                         {"id": "s-use", "heading": "Use it", "purpose": "p", "angles": ["algebraic"],
                          "check": {"prompt": "q?", "options": ["a", "b", "c", "d"], "explanation": "e", "answer": 0}}]}}


@pytest.fixture
def fx(env):
    db, jobs, runner = env
    card_reply.prompts = []
    runner.responses["Research"] = card_reply
    runner.responses["Renditions"] = lambda call: {"sections": [{"id": line.split()[1], "body": "text"}
                                                                for line in call.prompt.splitlines() if line.startswith("- s-")]}
    note(db, CID, FORM_A)
    note(db, CID, r"a + b = 3", kind="step")
    return db, jobs, runner


def frames(db, cid):
    return {k: (n["status"], (n["formula"] or {}).get("id")) for k, n in formulas.notes(db, cid).items()}


def test_a_new_formula_is_gray_and_a_step_is_neutral(fx):
    db, jobs, runner = fx
    f = frames(db, CID)
    assert f[formulas.key(FORM_A)] == ("gray", None) and f[formulas.key("a + b = 3")] == ("step", None)


def test_make_a_formula_lesson_then_learn_it_turns_the_frame_green(fx):
    db, jobs, runner = fx
    actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    fid = db.one("SELECT id FROM formula_lessons")["id"]
    c = db.one("SELECT * FROM concepts WHERE id=?", (fid,))
    base = db.one("SELECT * FROM concepts WHERE id=?", (CID,))
    assert c["module_id"] == base["module_id"] and c["ord"] == base["ord"] + 1 and c["title"] == "Linear combination"
    p = card_reply.prompts[0]
    assert FORM_A in p and "MUST have a `viz` of type \"formula\"" in p and "A weighted sum of vectors." in p
    v = lesson.view(db, fid)
    assert v["sections"][0]["viz"]["type"] == "formula" and v["sections"][1]["explain"]["work"] is True
    assert v["formulaLesson"]["forms"][0]["from"]["id"] == CID
    assert frames(db, CID)[formulas.key(FORM_A)] == ("gray", fid)  # a lesson exists, not learned yet
    with pytest.raises(actions.ActionError):  # one lesson per formula
        actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    from types import SimpleNamespace
    from dsc import graph
    real = graph.states
    graph.states = lambda db_: {**real(db_), fid: SimpleNamespace(state="learned", mastery=0.97)}  # the learner learned it
    try:
        assert frames(db, CID)[formulas.key(FORM_A)] == ("green", fid)
    finally:
        graph.states = real


def test_another_form_is_orange_and_can_be_added_and_preferred(fx):
    db, jobs, runner = fx
    actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    fid = db.one("SELECT id FROM formula_lessons")["id"]
    note(db, OTHER, FORM_B, fid=fid)  # the notes job matched it to the formula lesson (another form)
    assert frames(db, OTHER)[formulas.key(FORM_B)] == ("orange", fid)
    n = len(card_reply.prompts)
    actions.dispatch(db, jobs, {"type": "addFormulaForm", "conceptId": OTHER, "key": formulas.key(FORM_B), "formulaId": fid})
    assert frames(db, OTHER)[formulas.key(FORM_B)][1] == fid and frames(db, OTHER)[formulas.key(FORM_B)][0] != "orange"
    assert len(card_reply.prompts) == n + 1 and FORM_B in card_reply.prompts[-1]  # written again with both forms
    assert state.latest_card(db, fid)["version"] == 2
    actions.dispatch(db, jobs, {"type": "preferFormulaForm", "formulaId": fid, "key": formulas.key(FORM_B)})
    assert "Main form: $" + FORM_B in card_reply.prompts[-1] and "preferred form" in card_reply.prompts[-1]
    assert lesson.view(db, fid)["formulaLesson"]["preferred"] == formulas.key(FORM_B)


def test_notes_are_matched_again_after_a_formula_lesson_is_made(fx):
    db, jobs, runner = fx
    db.set_meta("formula_notes", "1")
    note(db, OTHER, FORM_B)  # written before any formula lesson existed
    actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    fid = db.one("SELECT id FROM formula_lessons")["id"]
    assert formulas.stale(db, OTHER)
    runner.responses["Formula notes"] = lambda call: ({"matches": [{"n": 1, "kind": "idea", "formula": fid}]} if "You match formulas" in call.prompt
                                                      else {"formulas": []})
    formulas.ensure(db, jobs, OTHER)
    assert frames(db, OTHER)[formulas.key(FORM_B)] == ("orange", fid) and not formulas.stale(db, OTHER)


def test_notes_from_before_kinds_get_their_kind_once(fx):
    db, jobs, runner = fx
    db.set_meta("formula_notes", "1")
    db.x("UPDATE formula_notes SET matched_at=NULL, kind='idea' WHERE concept_id=?", (CID,))  # written by an older version
    assert formulas.stale(db, CID)
    runner.responses["Formula notes"] = lambda call: ({"matches": [{"n": 1, "kind": "idea", "formula": ""},
                                                                   {"n": 2, "kind": "step", "formula": ""}]}
                                                      if "You match formulas" in call.prompt else {"formulas": []})
    formulas.ensure(db, jobs, CID)
    assert not formulas.stale(db, CID) and frames(db, CID)[formulas.key("a + b = 3")] == ("step", None)
