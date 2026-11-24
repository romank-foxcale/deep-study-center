"""One cell per idea (SPEC §49): two books with the same idea give one lesson, written from both books."""

import copy

from dsc import actions, bookstudy, cells, lesson, lesson_graph
from dsc.db import dumps
import test_lesson_graph
from test_bookstudy import book, cards_reply, lessons, map_reply  # noqa: F401 - fixtures are used by name


def add_second_book(db):
    db.x("""INSERT INTO sources(id, title, author, kind, filename, bytes, pages, status, outline, added_at)
            VALUES('src-2', 'Second Book', 'B. Author', 'book', 'second.pdf', 1, 3, 'ready', ?, '2026-01-02')""", (dumps([]),))
    for p in range(1, 4):
        text = f"second book page {p}: attention as a soft lookup of values by keys"
        db.x("INSERT INTO source_pages(source_id, page, text) VALUES('src-2', ?, ?)", (p, text))
        db.x("INSERT INTO source_fts(source_id, page, text) VALUES('src-2', ?, ?)", (p, text))


def test_a_second_book_joins_the_idea_and_the_one_lesson_is_planned_from_both(book):  # noqa: F811
    db, jobs, runner = book
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-1"})
    b1 = db.meta("last_book")
    att = lessons(db, b1)["Attention"]["conceptId"]
    add_second_book(db)

    def mapper(call):
        if "Second Book" in call.prompt:
            return {"summary": "Attention, again.", "lessons": [
                {"key": "att2", "title": "Attention as lookup", "covers": "Attention.", "pages": "1-3", "ideas": ["lookup"],
                 "prereq_keys": [], "same_as": att}]}
        return map_reply(call)
    runner.responses["Book map"] = mapper
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-2"})
    b2 = db.meta("last_book")
    assert b2 != b1
    row = lessons(db, b2)["Attention as lookup"]
    assert row["conceptId"] == att and row["ownConceptId"] != att  # the second book's row opens the one lesson
    assert {b["title"] for b in row["alsoIn"]} == {"Inference Book"}
    assert [s["title"] for s in cells.sources(db, att)] == ["Inference Book", "Second Book"]
    assert cells.home(db, row["ownConceptId"]) == att

    plans = []

    def research(call):
        if "You plan one lesson of a book" in call.prompt:
            plans.append(call.prompt)
            return copy.deepcopy(test_lesson_graph.PLAN)
        return cards_reply(call)
    runner.responses["Research"] = research
    lesson.open_lesson(db, jobs, att)
    p = plans[0]
    assert "Sources of this idea: Inference Book (book, p. 4); Second Book (book, pp. 1-3)" in p
    assert "=== Source 1: Inference Book" in p and "=== Source 2: Second Book" in p and "[Second Book, p. 2]" in p
    assert lesson_graph.latest(db, att)["status"] == "ready"
    # opening the second book's entry gives the one lesson; from the second book, its place there
    v = lesson.view(db, att, b2)
    assert v["book"]["bookId"] == b2 and v["book"]["pages"] == [1, 3]
    assert [s["title"] for s in v["sources"]] == ["Inference Book", "Second Book"]
    assert bookstudy.lesson_book(db, att)["bookId"] == b1  # without a book: the lesson's own book


def test_the_home_moves_to_the_lesson_that_is_further_along(book):  # noqa: F811
    db, jobs, runner = book
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-1"})
    b1 = db.meta("last_book")
    att = lessons(db, b1)["Attention"]["conceptId"]
    add_second_book(db)
    runner.responses["Book map"] = lambda call: {"summary": "s", "lessons": [
        {"key": "a2", "title": "Attention as lookup", "covers": "c", "pages": "1-3", "ideas": [], "prereq_keys": [], "same_as": att}]} \
        if "Second Book" in call.prompt else map_reply(call)
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": "src-2"})
    other = lessons(db, db.meta("last_book"))["Attention as lookup"]["ownConceptId"]
    assert cells.home(db, other) == att
    db.x("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)", (other, 1, dumps({"sections": []}), "skipped", "x"))
    assert cells.home(db, att) == other  # the second book's lesson was written (before this change): it is further along
    assert db.one("SELECT concept_id FROM cell_homes")["concept_id"] == other
