"""One knowledge graph (SPEC §21): nodes, links, global state, ideas shared across goals."""

from fastapi.testclient import TestClient

from dsc import actions, graph, state
from dsc.api import create_app


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


GOOD_EXPLAIN = "Moving right doesn't change how far up you are, so each coordinate adds on its own."


def learn_vectors(db, jobs, runner):
    for item, choice in (("q-ops", 0), ("q-norm", 1), ("q-misc", 3)):
        act(db, jobs, type="answer", conceptId="c-vectors", checkId=item, choice=choice)
    runner.responses["Grading"] = {"score": 1, "feedback": "Clear.", "missing": [], "followup": ""}
    act(db, jobs, type="explain", conceptId="c-vectors", itemId="e-ops", answer=GOOD_EXPLAIN)


def outline(module_title="Vectors and coordinates"):
    return {"title": "Robotics", "why": "w", "done": "d", "tracks": [
        {"title": "Geometry", "summary": "s", "modules": [{"title": module_title, "summary": "vectors in the plane", "planned": 2}]}]}


def research_with(same_as):
    def respond(call):
        respond.prompt = call.prompt
        return {"concepts": [
            {"key": "vec", "title": "Vectors (again)", "objective": "Add vectors", "minutes": 20, "prereq_keys": [], "same_as": same_as},
            {"key": "rot", "title": "Rotations", "objective": "Rotate a vector", "minutes": 20, "prereq_keys": ["vec"],
             "card": {"bloom": "apply", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [], "misconceptions": [],
                      "sources": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}]}}]}
    return respond


def new_goal(db, jobs, runner, same_as):
    runner.responses["Curriculum"] = outline()
    runner.responses["Research"] = research_with(same_as)
    runner.responses["Fact-check"] = {"results": []}
    runner.responses["Placement"] = {"done": False, "questions": []}
    act(db, jobs, type="createGoal", layout="list", answers=[{"q": "goal", "a": "robotics"}])
    return state.active_goal(db)


def test_every_concept_gets_a_node_and_prerequisites_become_links(env):
    db, _, _ = env
    assert graph.sync(db) == 10 and graph.sync(db) == 0
    v = graph.view(db)
    ids = {n["id"] for n in v["nodes"]}
    assert "c-vectors" in ids and len(ids) == 10
    pairs = {(link["src"], link["dst"]) for link in v["links"]}
    assert ("c-vectors", "c-lincomb") in pairs and ("c-dot", "c-matmul") in pairs
    vec = next(n for n in v["nodes"] if n["id"] == "c-vectors")
    assert vec["goals"] == ["g-ai"] and vec["state"] == "learning"  # the demo has started this lesson


def test_an_idea_learned_in_one_goal_is_known_in_another(env):
    db, jobs, runner = env
    learn_vectors(db, jobs, runner)
    gid = new_goal(db, jobs, runner, same_as="c-vectors")
    # research saw the existing idea and mapped its concept to that node, reusing the card
    assert "c-vectors: Vectors" in runner.responses["Research"].prompt
    mod = f"{gid}-t0-m0"
    vec_b = db.one("SELECT id FROM concepts WHERE module_id=? AND title='Vectors (again)'", (mod,))["id"]
    assert graph.node_of(db)[vec_b] == "c-vectors"
    assert db.one("SELECT body FROM cards WHERE concept_id=?", (vec_b,))  # card reused from the sibling
    _, states = state.concept_states(db, gid)
    assert states[vec_b].state == "learned"  # learned in goal g-ai, so known here
    rot = db.one("SELECT id FROM concepts WHERE module_id=? AND title='Rotations'", (mod,))["id"]
    assert states[rot].state == "ready"  # its prerequisite is the shared, learned node
    v = graph.view(db)
    vec = next(n for n in v["nodes"] if n["id"] == "c-vectors")
    assert vec["state"] == "learned" and vec["goals"] == sorted(["g-ai", gid]) and len(vec["concepts"]) == 2
    assert ("c-vectors", rot) in {(link["src"], link["dst"]) for link in v["links"]}


def test_unknown_same_as_makes_a_new_node(env):
    db, jobs, runner = env
    gid = new_goal(db, jobs, runner, same_as="c-does-not-exist")
    vec_b = db.one("SELECT id FROM concepts WHERE module_id=? AND title='Vectors (again)'", (f"{gid}-t0-m0",))
    assert vec_b is None  # no card and no valid node: the concept is dropped, as before
    rot = db.one("SELECT id FROM concepts WHERE module_id=? AND title='Rotations'", (f"{gid}-t0-m0",))["id"]
    assert graph.node_of(db)[rot] == rot


def test_sync_inside_an_open_transaction(env):
    db, _, _ = env
    graph.sync(db)
    with db.tx():
        db.conn.execute("INSERT INTO concepts(id, module_id, ord, title, objective, minutes, prereqs, p_init, started) "
                        "VALUES('c-new', 'm-la', 99, 'New', 'o', 10, '[\"c-vectors\"]', 0.1, 0)")
        concepts, states = state.concept_states(db, "g-ai")  # syncs the new concept without a nested BEGIN
    assert states["c-new"].state == "locked" and graph.node_of(db)["c-new"] == "c-new"


def test_deleting_a_goal_keeps_shared_nodes_and_drops_its_own(env):
    db, jobs, runner = env
    gid = new_goal(db, jobs, runner, same_as="c-vectors")
    rot = db.one("SELECT id FROM concepts WHERE title='Rotations'")["id"]
    graph.sync(db)
    act(db, jobs, type="deleteGoal", id=gid)
    ids = {n["id"] for n in graph.view(db)["nodes"]}
    assert "c-vectors" in ids and rot not in ids
    assert not db.q("SELECT * FROM concept_nodes WHERE concept_id NOT IN (SELECT id FROM concepts)")


def test_graph_api(env):
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    g = client.get("/api/graph").json()
    assert len(g["nodes"]) == 10 and g["links"] and {"id", "title", "state", "goals", "concepts"} <= set(g["nodes"][0])
