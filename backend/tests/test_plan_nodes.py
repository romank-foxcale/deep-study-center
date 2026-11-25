"""The steps of a planned lesson as ideas on the knowledge map (SPEC §46)."""

import copy
import json

import pytest

from dsc import actions, engine, graph, lesson
import test_lesson_graph
from test_bookstudy import book, lessons  # noqa: F401 - fixtures are used by name
from test_lesson_graph import planned  # noqa: F401
from test_lesson_steps import answer, step_reply


@pytest.fixture
def mapped(planned, monkeypatch):  # noqa: F811
    """An approved step lesson ("Attention") whose held node links to the map idea of the "Softmax" lesson."""
    db, jobs, runner, bid, cid, prompts, research = planned
    softmax = lessons(db, bid)["Softmax"]["conceptId"]
    plan = copy.deepcopy(test_lesson_graph.PLAN)
    plan["nodes"][0]["links_to"] = softmax
    monkeypatch.setattr(test_lesson_graph, "PLAN", plan)
    step_reply.prompts = []
    runner.responses["Renditions"] = step_reply
    runner.responses["Lesson assets"] = lambda call: {"type": "nonsense"}
    lesson.open_lesson(db, jobs, cid)
    actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    return db, jobs, bid, cid, softmax


def node(view, nid):
    return next(n for n in view["nodes"] if n["id"] == nid)


def test_each_taught_step_is_an_idea_next_to_its_lesson_linked_as_the_plan_says(mapped):
    db, jobs, bid, cid, softmax = mapped
    v = graph.view(db)
    scores, weights = f"pn-{cid}-scores", f"pn-{cid}-weights"
    steps = [n for n in v["nodes"] if n["kind"] == "step"]
    assert {n["id"] for n in steps} == {scores, weights}  # foundations and steps; not held, formula or goal nodes
    s = node(v, scores)
    assert s["title"] == "Scores from dot products" and s["statement"] == "$q \\cdot k$ is a score."
    assert s["step"] == {"conceptId": cid, "lesson": "Attention", "sectionId": "s-scores"} and s["books"] == [bid]
    lesson_node = node(v, cid)
    assert lesson_node["books"] == [bid]
    plan_links = {(x["src"], x["dst"]) for x in v["links"] if x["origin"] == "plan"}
    # held -> step, step -> step, and the formula node joined across: weights -> (weighted sum) -> the lesson's idea
    assert plan_links == {(softmax, weights), (scores, weights), (weights, cid)}
    d = graph.node_detail(db, scores)
    assert d["books"][0]["conceptId"] == cid and [x["id"] for x in d["leadsTo"]] == [weights]


def test_a_steps_check_is_evidence_on_its_idea_and_a_learned_lesson_lifts_its_steps(mapped, monkeypatch):
    db, jobs, bid, cid, softmax = mapped
    scores, weights = f"pn-{cid}-scores", f"pn-{cid}-weights"
    answer(db, jobs, cid, "s-scores", right=False)
    st = graph.states(db)
    assert st[scores].state == "learning" and st[weights].state != "learning"
    answer(db, jobs, cid, "s-scores", right=True)
    assert graph.states(db)[scores].mastery > st[scores].mastery
    assert graph.states(db)[cid].state != "learned"

    class Learned:
        state, mastery = "learned", 0.97
    real = engine.derive_concepts
    monkeypatch.setattr(engine, "derive_concepts", lambda pseudo, ev: {**real(pseudo, ev), cid: Learned})
    lifted = graph.states(db)  # the lesson is learned: a step whose own last answer was right shares its state
    assert lifted[scores] is Learned and lifted[weights] is Learned
    monkeypatch.setattr(engine, "derive_concepts", real)
    answer(db, jobs, cid, "s-scores", right=False)  # its own last answer is wrong: it keeps its own state
    monkeypatch.setattr(engine, "derive_concepts", lambda pseudo, ev: {**real(pseudo, ev), cid: Learned})
    assert graph.states(db)[scores] is not Learned


def test_a_new_card_replaces_the_steps_and_a_lesson_without_a_plan_has_none(mapped):
    db, jobs, bid, cid, softmax = mapped
    assert {n["id"] for n in graph.view(db)["nodes"] if n["kind"] == "step"}
    row = db.one("SELECT version, body FROM cards WHERE concept_id=? ORDER BY version DESC LIMIT 1", (cid,))
    body = json.loads(row["body"])
    body["steps"] = False  # "Write it now without a plan": a plain card
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
         (cid, row["version"] + 1, json.dumps(body), "skipped", "2026-11-24"))
    v = graph.view(db)
    assert not [n for n in v["nodes"] if n["kind"] == "step"] and not [x for x in v["links"] if x["origin"] == "plan"]
    assert not db.q("SELECT 1 FROM plan_nodes")


def test_a_step_the_plan_links_to_an_idea_on_the_map_is_that_idea(planned, monkeypatch):  # noqa: F811
    db, jobs, runner, bid, cid, prompts, research = planned
    softmax = lessons(db, bid)["Softmax"]["conceptId"]
    plan = copy.deepcopy(test_lesson_graph.PLAN)
    plan["nodes"][1]["links_to"] = softmax  # "Scores from dot products" is already on the map (here: the Softmax idea)
    monkeypatch.setattr(test_lesson_graph, "PLAN", plan)
    step_reply.prompts = []
    runner.responses["Renditions"] = step_reply
    runner.responses["Lesson assets"] = lambda call: {"type": "nonsense"}
    lesson.open_lesson(db, jobs, cid)
    actions.dispatch(db, jobs, {"type": "approveLessonPlan", "conceptId": cid})
    v = graph.view(db)
    assert [n["id"] for n in v["nodes"] if n["kind"] == "step"] == [f"pn-{cid}-weights"]  # no copy of the linked idea
    assert (softmax, f"pn-{cid}-weights") in {(x["src"], x["dst"]) for x in v["links"] if x["origin"] == "plan"}
    before = graph.states(db)[softmax].mastery
    answer(db, jobs, cid, "s-scores", right=True)  # the step's check counts on the linked idea
    assert graph.states(db)[softmax].mastery > before
