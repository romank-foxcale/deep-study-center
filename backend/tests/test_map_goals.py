"""Goals on the map (SPEC §53): researched by the goal agent, scored per idea, new cells placed, blocks added."""

import pytest

from dsc import actions, graph, map_goals

RESEARCH = {"direction": "Understand vectors and their products well enough to build models.",
            "blocks": [{"title": "Dot product & similarity", "says": "already on the map by title"},
                       {"title": "Vectors", "says": "on the map by id", "same_as": "c-vectors"},
                       {"title": "Eigenvalues", "says": "How a matrix stretches its special directions."}],
            "scores": [{"id": "c-lincomb", "score": 0.7}, {"id": "c-nope", "score": 1}, {"id": "c-span", "score": 3}]}


@pytest.fixture
def goal(env):
    db, jobs, runner = env
    prompts = []

    def agent(call):
        prompts.append(call.prompt)
        if "The new ideas" in call.prompt:
            new = [line.split(":")[0][2:] for line in call.prompt.split("The new ideas")[1].splitlines() if line.startswith("- ")]
            out = [{"id": i, "score": 0.9} for i in new if "eig" in i or "goal" in i]
            if "Eigenvalues" in call.prompt.split("The new ideas")[0]:
                blk = call.prompt.split("Eigenvalues")[0].rsplit("- ", 1)[1].split(":")[0]
                out += [{"id": i, "score": 1, "block": blk} for i in new if i == "n-eigen"]
            return {"scores": out}
        return RESEARCH
    runner.responses["Research"] = agent
    actions.dispatch(db, jobs, {"type": "addMapGoal", "title": "Master linear algebra for ML"})
    return db, jobs, runner, db.meta("last_map_goal"), prompts


def the_goal(db, gid):
    return next(g for g in graph.view(db)["mapGoals"] if g["id"] == gid)


def test_a_new_goal_is_researched_and_every_idea_gets_a_score(goal):
    db, jobs, runner, gid, prompts = goal
    g = the_goal(db, gid)
    assert g["direction"].startswith("Understand vectors") and g["researched"] and not g["busy"] and g["color"] and g["angle"] == -40
    assert "c-vectors: Vectors" in prompts[0] and "Master linear algebra for ML" in prompts[0]
    assert g["scores"]["c-vectors"] == 1 and g["scores"]["c-dot"] == 1 and g["scores"]["c-lincomb"] == 0.7
    assert g["scores"]["c-span"] == 1 and "c-nope" not in g["scores"]  # clamped; an unknown id is dropped
    assert [b["title"] for b in g["blocks"]] == ["Eigenvalues"]  # blocks already on the map are not "missing"
    actions.dispatch(db, jobs, {"type": "addMapGoal", "title": "Reliable data systems"})
    assert [x["angle"] for x in graph.view(db)["mapGoals"]] == [-40, 150]  # each goal at its own edge


def test_new_cells_are_scored_and_a_cell_that_is_a_missing_block_fills_it(goal):
    db, jobs, runner, gid, prompts = goal
    db.x("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES('n-eigen', 'Eigenvalues', 'e', 'concept', 'x', 'session')")
    db.x("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES('n-css', 'CSS grid', 'c', 'concept', 'x', 'session')")
    assert set(map_goals.unscored(db)[gid]) >= {"n-eigen", "n-css"}
    map_goals.ensure_scores(db, jobs)
    g = the_goal(db, gid)
    assert g["scores"]["n-eigen"] == 1 and g["scores"]["n-css"] == map_goals.DEFAULT  # a side road is scored too
    assert g["blocks"] == [] and map_goals.unscored(db) == {}


def test_a_missing_block_can_be_added_and_goals_renamed_and_removed(goal):
    db, jobs, runner, gid, prompts = goal
    bid = the_goal(db, gid)["blocks"][0]["id"]
    actions.dispatch(db, jobs, {"type": "addGoalBlock", "goalId": gid, "blockId": bid})
    nid = db.meta("last_gap_idea")
    v = graph.view(db)
    assert any(n["id"] == nid and n["title"] == "Eigenvalues" for n in v["nodes"]) and the_goal(db, gid)["scores"][nid] == 1
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "addGoalBlock", "goalId": gid, "blockId": bid})
    actions.dispatch(db, jobs, {"type": "renameMapGoal", "goalId": gid, "title": "Linear algebra, deeply"})
    assert the_goal(db, gid)["title"] == "Linear algebra, deeply" and len(prompts) >= 2
    actions.dispatch(db, jobs, {"type": "removeMapGoal", "goalId": gid})
    assert graph.view(db)["mapGoals"] == []
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "addMapGoal", "title": "ab"})


def test_a_formula_without_a_page_serves_a_goal_like_its_lesson(goal):
    db, jobs, runner, gid, prompts = goal
    db.x("""INSERT INTO formula_notes(concept_id, key, tex, body, created_at) VALUES('c-lincomb', 'k1', 'a u + b v', '{"name": "Lin comb"}', 'x')""")
    v = graph.view(db)
    fx = next(n for n in v["nodes"] if n["id"].startswith("fx:"))
    assert next(g for g in v["mapGoals"] if g["id"] == gid)["scores"][fx["id"]] == 0.7  # c-lincomb's score
