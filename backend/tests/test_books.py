"""Book goals (SPEC §18): the 80/20 core of chosen sources, the list of what was left out, and bringing a chapter back."""

import pytest

from dsc import actions, books, sources, state
from tests.test_ohtani import outline as ohtani_outline
from tests.test_sources import make_pdf

BOOK = make_pdf(["Markov decision processes define states and actions", "The Bellman equation gives the value of a state",
                 "A history of reinforcement learning research", "Policy gradients follow the gradient of return"],
                title="Deep RL Book",
                outline=[("Ch 1 MDPs", 1), ("Ch 2 Bellman", 2), ("Ch 3 History", 3), ("Ch 4 Policy gradients", 4)])
POST = make_pdf(["Reward shaping changes the reward to speed up learning", "Shaping must keep the optimal policy"],
                title="Shaping post")
ANSWERS = [{"q": "Why these sources?", "a": "I need RL for a robotics job"}, {"q": "Time?", "a": "3 hours a week"}]


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def card(key):
    return {"key": key, "title": key.title(), "objective": "o", "minutes": 15, "prereq_keys": [],
            "card": {"bloom": "understand", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                     "misconceptions": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}],
                     "sources": [{"title": "Deep RL Book, p. 2", "url": "source:x#page=2", "kind": "book", "why": "w"}]}}


SELECTION = [
    {"source": 1, "chapter": "Ch 1 MDPs", "pages": "1", "rank": "core", "why": "the frame", "step": "Values"},
    {"source": 1, "chapter": "Ch 2 Bellman", "pages": "2", "rank": "core", "why": "the key equation", "step": "values"},
    {"source": 1, "chapter": "Ch 3 History", "pages": "3", "rank": "skip", "why": "a story", "step": "Values"},
    {"source": 1, "chapter": "Ch 4 Policy gradients", "pages": "4", "rank": "skip", "why": "not needed for the job",
     "step": "a step that does not exist about gradients"},
    {"source": 2, "chapter": "Reward shaping", "pages": "1-2", "rank": "supporting", "why": "an example", "step": "Shaping"},
    {"source": 9, "chapter": "Unknown source", "pages": "", "rank": "core", "why": "x", "step": "Values"},
    {"source": 1, "chapter": "Bad rank", "pages": "", "rank": "maybe", "why": "x", "step": "Values"},
]


def list_outline():
    return {"title": "The core of Deep RL Book", "why": "w", "done": "d", "selection": SELECTION, "tracks": [
        {"title": "Core", "summary": "s", "modules": [
            {"title": "Values", "summary": "The Bellman equation (Ch 1-2 of Deep RL Book, pp. 1-2)", "planned": 2},
            {"title": "Shaping", "summary": "Reward shaping post", "planned": 1},
            {"title": "Policy learning", "summary": "learning a policy with gradients", "planned": 1}]}]}


@pytest.fixture
def two_sources(env):
    db, jobs, runner = env
    ids = []
    for data, name in ((BOOK, "rl.pdf"), (POST, "post.pdf")):
        sid = sources.add(db, data, name)
        sources.ingest(db, sid)
        ids.append(sid)
    runner.responses["Research"] = {"concepts": [card("bellman")]}
    runner.responses["Fact-check"] = {"results": []}
    runner.responses["Placement"] = {"items": []}
    return db, jobs, runner, ids


def test_book_goal_builds_from_the_core_and_lists_what_was_left_out(two_sources):
    db, jobs, runner, ids = two_sources
    runner.responses["Curriculum"] = list_outline()
    s = act(db, jobs, type="createGoal", kind="book", layout="list", sourceIds=ids, answers=ANSWERS)
    g = s["goal"]
    assert g["kind"] == "book" and g["title"] == "The core of Deep RL Book" and g["hoursPerWeek"] == 3.0
    assert "robotics job" in g["profile"]
    assert sorted(next(x for x in s["sources"] if x["id"] == i)["goalIds"] == [g["id"]] for i in ids) == [True, True]

    call = next(c for role, c in runner.calls if role == "Curriculum")
    assert "80/20" in call.prompt and "selection" in call.schema["required"]
    assert "1. book “Deep RL Book”" in call.prompt and "Ch 2 Bellman (p. 2)" in call.prompt
    # a source without a table of contents is shown by the first words of its pages
    assert "no table of contents" in call.prompt and "p. 2: Shaping must keep" in call.prompt
    # the profile of earlier goals stands in for the questions a book goal does not ask
    demo = db.one("SELECT profile FROM goals WHERE kind='goal'")["profile"]
    assert demo and "earlier goals" in call.prompt and demo in call.prompt and demo in g["profile"]

    cuts = {c["chapter"]: c for c in s["bookCuts"]}
    assert set(cuts) == {"Ch 1 MDPs", "Ch 2 Bellman", "Ch 3 History", "Ch 4 Policy gradients", "Reward shaping"}
    mods = {m["title"]: m["id"] for m in s["modules"]}
    assert cuts["Ch 2 Bellman"]["status"] == "kept" and cuts["Ch 2 Bellman"]["moduleId"] == mods["Values"]
    assert cuts["Reward shaping"]["sourceId"] == ids[1] and cuts["Reward shaping"]["rank"] == "supporting"
    assert cuts["Ch 3 History"]["status"] == "cut"
    # an unknown step name falls back to the step with the most words in common
    assert cuts["Ch 4 Policy gradients"]["moduleId"] == mods["Policy learning"]
    outline_job = next(j for j in s["jobs"] if j["kind"] == "outline")
    assert "3 chapter(s) kept, 2 left out" in " ".join(outline_job["progress"])

    # research of a book goal gets more of the sources' pages and is told to teach what they say
    research = next(c for role, c in runner.calls if role == "Research")
    assert "This is a book goal" in research.prompt and "[Deep RL Book, p. 2]" in research.prompt


def test_book_goal_needs_readable_sources(two_sources):
    db, jobs, runner, ids = two_sources
    with pytest.raises(actions.ActionError, match="at least one source"):
        actions.dispatch(db, jobs, {"type": "createGoal", "kind": "book", "sourceIds": ["src-nope"], "answers": ANSWERS})
    db.x("UPDATE sources SET status='reading' WHERE id=?", (ids[0],))
    with pytest.raises(actions.ActionError, match="still being read"):
        actions.dispatch(db, jobs, {"type": "createGoal", "kind": "book", "sourceIds": ids, "answers": ANSWERS})
    db.x("UPDATE sources SET status='no_text' WHERE id=?", (ids[0],))
    with pytest.raises(actions.ActionError, match="no text"):
        actions.dispatch(db, jobs, {"type": "createGoal", "kind": "book", "sourceIds": ids, "answers": ANSWERS})
    assert not any(role == "Curriculum" for role, _ in runner.calls)


def test_bringing_back_a_chapter(two_sources):
    db, jobs, runner, ids = two_sources
    runner.responses["Curriculum"] = list_outline()
    s = act(db, jobs, type="createGoal", kind="book", layout="list", sourceIds=ids, answers=ANSWERS)
    cuts = {c["chapter"]: c for c in s["bookCuts"]}
    mods = {m["title"]: m for m in s["modules"]}
    assert mods["Values"]["research"] == "ready" and mods["Policy learning"]["research"] == "outline"

    # a step that is still an outline: the chapter joins its plan, and its research will cover it
    s = act(db, jobs, type="restoreCut", id=cuts["Ch 4 Policy gradients"]["id"])
    m = next(x for x in s["modules"] if x["title"] == "Policy learning")
    assert "Ch 4 Policy gradients (pp. 4) of “Deep RL Book”" in m["summary"] and m["plannedConcepts"] == 2
    assert next(c for c in s["bookCuts"] if c["chapter"] == "Ch 4 Policy gradients")["status"] == "restored"

    # a researched step: a new lesson at its end, researched on its own from the pages
    runner.responses["Research"] = {"concepts": [card("history")]}
    s = act(db, jobs, type="restoreCut", id=cuts["Ch 3 History"]["id"])
    restored = next(c for c in s["bookCuts"] if c["chapter"] == "Ch 3 History")
    assert restored["status"] == "restored" and restored["conceptId"]
    values = next(x for x in s["modules"] if x["title"] == "Values")
    assert values["conceptIds"][-1] == restored["conceptId"] and values["research"] == "ready"
    assert any(c["conceptId"] == restored["conceptId"] for c in s["cards"])
    research = [c for role, c in runner.calls if role == "Research"][-1]
    assert "brought it back after the 80/20 cut" in research.prompt

    with pytest.raises(actions.ActionError, match="not left out"):
        actions.dispatch(db, jobs, {"type": "restoreCut", "id": restored["id"]})
    with pytest.raises(actions.ActionError, match="not left out"):
        actions.dispatch(db, jobs, {"type": "restoreCut", "id": cuts["Ch 1 MDPs"]["id"]})


def test_book_goal_as_an_ohtani_table_maps_chapters_to_area_steps(two_sources):
    db, jobs, runner, ids = two_sources
    out = ohtani_outline()
    out["selection"] = [{"source": 1, "chapter": "Ch 2 Bellman", "pages": "2", "rank": "core", "why": "w", "step": "A3 step 2"},
                        {"source": 1, "chapter": "Ch 3 History", "pages": "3", "rank": "skip", "why": "w", "step": "Merge 1"}]
    runner.responses["Curriculum"] = out
    s = act(db, jobs, type="createGoal", kind="book", sourceIds=ids, answers=ANSWERS)
    assert s["goal"]["layout"] == "ohtani" and s["goal"]["kind"] == "book"
    call = next(c for role, c in runner.calls if role == "Curriculum")
    assert "Ohtani" in call.prompt and "80/20" in call.prompt and "merges" in call.schema["required"]
    cuts = {c["chapter"]: c for c in s["bookCuts"]}
    assert cuts["Ch 2 Bellman"]["moduleId"] == next(m["id"] for m in s["modules"] if m["title"] == "A3 step 2")
    # a left-out chapter never maps to a merge step; bringing it back still lands in an area step
    s = act(db, jobs, type="restoreCut", id=cuts["Ch 3 History"]["id"])
    target = next(c for c in s["bookCuts"] if c["chapter"] == "Ch 3 History")["moduleId"]
    assert not next(m for m in s["modules"] if m["id"] == target)["requires"]


def test_a_normal_goal_has_no_book_parts(two_sources):
    db, jobs, runner, ids = two_sources
    runner.responses["Curriculum"] = {k: v for k, v in list_outline().items() if k != "selection"}
    s = act(db, jobs, type="createGoal", layout="list", sourceIds=ids[:1],
            answers=[{"q": "goal", "a": "learn RL"}, {"q": "k", "a": ""}, {"q": "w", "a": ""}, {"q": "t", "a": "4 h"}])
    call = next(c for role, c in runner.calls if role == "Curriculum")
    assert "80/20 core" not in call.prompt and "{focus}" not in call.prompt and "selection" not in call.schema["required"]
    assert s["goal"]["kind"] == "goal" and s["bookCuts"] == []
    research = next(c for role, c in runner.calls if role == "Research")
    assert "This is a book goal" not in research.prompt and "{focus}" not in research.prompt


def test_best_module_prefers_the_named_step_then_word_overlap():
    mods = [{"id": "a", "title": "Values", "summary": "Bellman"}, {"id": "b", "title": "Policies", "summary": "gradients"}]
    assert books.best_module(mods, "  VALUES ") == "a"
    assert books.best_module(mods, "nothing", "Policy gradients chapter") == "b"
    assert books.best_module(mods, "zzz", "qqq") is None and books.best_module([], "Values") is None
