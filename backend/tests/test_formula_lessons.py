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


def blocks_reply(call):
    if "You break one formula" not in call.prompt:
        return {"formulas": [], "matches": []}
    blocks_reply.prompts.append(call.prompt)
    return {"blocks": [
        {"name": "Multiplying numbers", "kind": "formula", "tex": "a \\cdot b", "meaning": "Multiply two numbers.", "ref": "", "basic": True},
        {"name": "Product notation", "kind": "notation", "tex": "\\prod_i a_i", "meaning": "Multiply all terms.", "ref": "",
         "basic": True},
        {"name": "Scaling a vector", "kind": "formula", "tex": "c\\,\\mathbf{v}", "meaning": "Multiply every part of a vector by a number.",
         "ref": "", "basic": False},
        {"name": "Adding vectors", "kind": "formula", "tex": "\\mathbf{u} + \\mathbf{v}", "meaning": "Add matching parts.",
         "ref": "c-vectors", "basic": False}]}


blocks_reply.prompts = []


@pytest.fixture
def fx(env):
    db, jobs, runner = env
    card_reply.prompts = []
    runner.responses["Research"] = card_reply
    runner.responses["Formula notes"] = blocks_reply
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
    assert FORM_A in p and "Read it aloud" in p and "A weighted sum of vectors." in p
    assert "Scaling a vector (formula)" in p and "does not know it yet" in p
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


def test_every_writer_gets_the_preferred_form(fx):
    from dsc import guidelines
    db, jobs, runner = fx
    actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    fid = db.one("SELECT id FROM formula_lessons")["id"]
    assert "prefers" not in guidelines.text(db)  # one form, nothing chosen
    note(db, OTHER, FORM_B, fid=fid)
    actions.dispatch(db, jobs, {"type": "addFormulaForm", "conceptId": OTHER, "key": formulas.key(FORM_B), "formulaId": fid})
    actions.dispatch(db, jobs, {"type": "preferFormulaForm", "formulaId": fid, "key": formulas.key(FORM_B)})
    text = guidelines.text(db)
    assert "write “Linear combination” as $" + FORM_B + "$" in text and FORM_A in text and "symbol by symbol" in text
    seen = []
    runner.responses["Renditions"] = lambda call: (seen.append(call.prompt), {"sections": []})[1]
    lesson.refresh(db, jobs, OTHER, by_learner=True)
    assert seen and FORM_B in seen[0] and "prefers" in seen[0]  # the lesson writer of another lesson sees it


def test_a_formula_is_built_from_blocks_and_missing_blocks_are_learned_first(fx):
    db, jobs, runner = fx
    blocks_reply.prompts = []
    actions.dispatch(db, jobs, {"type": "makeFormulaLesson", "conceptId": CID, "key": formulas.key(FORM_A)})
    fid = db.one("SELECT id FROM formula_lessons")["id"]
    assert len(blocks_reply.prompts) == 1 and FORM_A in blocks_reply.prompts[0]
    info = lesson.view(db, fid)["formulaLesson"]
    by = {b["name"]: b for b in info["blocks"]}
    assert by["Multiplying numbers"]["state"] == "known" and by["Multiplying numbers"]["basic"]
    assert by["Scaling a vector"]["state"] == "new" and by["Scaling a vector"]["link"] is None
    assert by["Product notation"]["state"] == "new" and not by["Product notation"]["basic"]  # a notation is never basic
    assert by["Adding vectors"]["link"]["id"] == "c-vectors" and by["Adding vectors"]["link"]["kind"] == "idea"
    assert info["missing"] == 2
    n = len(card_reply.prompts)
    actions.dispatch(db, jobs, {"type": "learnBlocksFirst", "formulaId": fid})
    block = db.one("SELECT * FROM formula_lessons WHERE name='Scaling a vector'")
    assert db.one("SELECT kind FROM formula_lessons WHERE name='Product notation'")["kind"] == "notation"
    c, f = (db.one("SELECT * FROM concepts WHERE id=?", (i,)) for i in (block["id"], fid))
    assert c["module_id"] == f["module_id"] and c["ord"] < f["ord"]  # the block comes before the formula built from it
    assert len(card_reply.prompts) == n + 2 and any("Scaling a vector" in p for p in card_reply.prompts[-2:])
    info = lesson.view(db, fid)["formulaLesson"]
    assert info["missing"] == 0 and next(b for b in info["blocks"] if b["name"] == "Scaling a vector")["link"]["id"] == block["id"]
    assert lesson.view(db, block["id"])["formulaLesson"]["usedIn"][0]["id"] == fid
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "learnBlocksFirst", "formulaId": fid})
