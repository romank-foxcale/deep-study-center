"""Book study v2 (SPEC §31): a book is chapters, a chapter is lessons by topic. Lessons are written from the book's
pages on first open and saved; every lesson stays open whatever the learner knows."""

import json
import re

import pytest

from dsc import actions, bookstudy, graph, lesson, state, today
from dsc.db import dumps

OUTLINE = [
    {"title": "Book root", "page": 1, "level": 0},
    {"title": "Table of Contents", "page": 2, "level": 1},
    {"title": "Chapter 1: Models", "page": 3, "level": 1},
    {"title": "1.1 Attention", "page": 4, "level": 2},
    {"title": "1.2 KV cache", "page": 6, "level": 2},
    {"title": "Chapter 2: Serving", "page": 8, "level": 1},
    {"title": "Chapter 3: Hardware", "page": 10, "level": 1},
    {"title": "3.1 Memory bandwidth", "page": 10, "level": 2},
]


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def add_book(db, pages=12, outline=None):
    db.x("""INSERT INTO sources(id, title, author, kind, filename, bytes, pages, status, outline, added_at)
            VALUES('src-1', 'Inference Book', 'A. Author', 'book', 'b.pdf', 1, ?, 'ready', ?, '2026-01-01')""",
         (pages, dumps(outline or OUTLINE)))
    for p in range(1, pages + 1):
        text = f"page {p} text about attention softmax kv cache memory bandwidth serving"
        db.x("INSERT INTO source_pages(source_id, page, text) VALUES('src-1', ?, ?)", (p, text))
        db.x("INSERT INTO source_fts(source_id, page, text) VALUES('src-1', ?, ?)", (p, text))


def lesson_(key, title, prereqs=(), same_as=None, pages="4"):
    d = {"key": key, "title": title, "covers": f"{title} explained.", "pages": pages, "ideas": [f"{title} idea"],
         "prereq_keys": list(prereqs)}
    if same_as:
        d["same_as"] = same_as
    return d


def map_reply(call):
    """Chapter 1: softmax, attention (builds on softmax and the graph's dot product), kv cache; chapter 2: batching
    (builds on the kv cache lesson of chapter 1); chapter 3: bandwidth."""
    map_reply.prompts.append(call.prompt)
    if "Chapter: Chapter 1" in call.prompt:
        return {"summary": "How a model attends.", "lessons": [
            lesson_("softmax", "Softmax"), lesson_("attention", "Attention", ["softmax", "c-dot"]),
            lesson_("kv-cache", "KV cache", ["attention"], pages="6-7")]}
    if "Chapter: Chapter 2" in call.prompt:
        if map_reply.fail_chapter_2:
            raise RuntimeError("model hiccup")
        kv = re.search(r"- (\S+-kv-cache): KV cache", call.prompt).group(1)
        return {"summary": "Serving many users.", "lessons": [lesson_("batching", "Continuous batching", [kv], pages="8-9")]}
    return {"summary": "Bandwidth.", "lessons": [lesson_("bw", "Memory bandwidth", pages="10-12")]}


def cards_reply(call):
    cards_reply.prompts.append(call.prompt)
    ids = re.findall(r"^- id (\S+): ", call.prompt, re.M)
    return {"cards": [{"id": i, "card": {
        "bloom": "understand", "core": f"core of {i}", "formal": "", "why": "why", "examples": [{"label": "e", "domain": "ml"}],
        "misconceptions": ["m"], "sections": [
            {"id": "s-what", "heading": "What it is", "purpose": "the idea", "angles": ["geometric"],
             "book": {"summary": "The book says it is a weighted sum.", "pages": "4"},
             "check": {"prompt": "q?", "options": ["a", "b", "c", "d"], "explanation": "e", "answer": 0}},
            {"id": "s-why", "heading": "Why it works", "purpose": "the reason", "angles": ["algebraic"],
             "book": {"summary": "The book derives it.", "pages": "5"},
             "explain": {"prompt": "Work it out.", "work": True, "rubric": ["the sum"]}}]}} for i in ids]}


def prose_reply(call):
    prose_reply.prompts.append(call.prompt)
    ids = [line.split()[1] for line in call.prompt.splitlines() if line.startswith("- s-")]
    softmax = re.search(r"^- (\S+-softmax): Softmax", call.prompt, re.M)
    link = f" Uses [softmax](#idea/{softmax.group(1)}) and [magic](#idea/n-nope)." if softmax else ""
    return {"sections": [{"id": i, "body": f"meaning of {i}.{link}"} for i in ids]}


@pytest.fixture
def book(env):
    db, jobs, runner = env
    add_book(db)
    map_reply.prompts = []
    map_reply.fail_chapter_2 = False
    cards_reply.prompts = []
    prose_reply.prompts = []
    runner.responses["Book map"] = map_reply
    runner.responses["Research"] = cards_reply
    runner.responses["Renditions"] = prose_reply
    return db, jobs, runner


def lessons(db, bid):
    return {x["title"]: x for ch in bookstudy.view(db, bid)["chapters"] for x in ch["lessons"]}


def test_chapters_from_the_outline():
    ch = bookstudy.chapters_from_outline(OUTLINE, 12)
    assert [(c["chapter"], c["title"], c["page_from"], c["page_to"], len(c["sections"])) for c in ch] == [
        (1, "Chapter 1: Models", 3, 7, 2), (2, "Chapter 2: Serving", 8, 9, 0), (3, "Chapter 3: Hardware", 10, 12, 1)]
    assert [(c["page_from"], c["page_to"]) for c in bookstudy.chapters_from_outline([], 30)] == [(1, 12), (13, 24), (25, 30)]


def test_map_makes_chapters_of_lessons_in_a_hidden_goal(book):
    db, jobs, runner = book
    s = act(db, jobs, type="studyBook", sourceId="src-1")
    b = s["studyBooks"][0]
    assert b["status"] == "ready" and b["chapters"] == 3 and b["chaptersDone"] == 3 and s["lastBook"] == b["id"]
    assert b["goalId"] not in {g["id"] for g in s["goals"]}  # the book's goal is hidden from the goal lists
    v = bookstudy.view(db, b["id"])
    assert [c["summary"] for c in v["chapters"]] == ["How a model attends.", "Serving many users.", "Bandwidth."]
    ls = lessons(db, b["id"])
    assert list(ls) == ["Softmax", "Attention", "KV cache", "Continuous batching", "Memory bandwidth"]
    kv = ls["KV cache"]
    assert kv["pages"] == [6, 7] and kv["covers"] == "KV cache explained." and kv["ideas"] == ["KV cache idea"]
    assert not kv["carded"] and not kv["written"] and kv["state"] in ("pending", "locked")
    # each lesson is a concept of the hidden goal, with its prerequisites, and a node of the graph
    c = db.one("SELECT * FROM concepts WHERE id=?", (ls["Continuous batching"]["conceptId"],))
    assert json.loads(c["prereqs"]) == [kv["conceptId"]]
    pairs = {(lk["src"], lk["dst"]) for lk in graph.links(db)}
    assert (ls["Softmax"]["nodeId"], ls["Attention"]["nodeId"]) in pairs and ("c-dot", ls["Attention"]["nodeId"]) in pairs
    assert (kv["nodeId"], ls["Continuous batching"]["nodeId"]) in pairs
    assert graph.view(db)["books"][0]["id"] == b["id"]
    assert v["next"] == ls["Softmax"]["conceptId"]
    assert "c-dot: Dot product & similarity" in map_reply.prompts[0]  # the mapper sees the older graph ideas


def test_a_failed_chapter_is_retried_without_redoing_earlier_ones(book):
    db, jobs, runner = book
    map_reply.fail_chapter_2 = True
    b = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]
    assert b["status"] == "failed" and b["chaptersDone"] == 1 and bookstudy.view(db, b["id"])["error"]
    map_reply.fail_chapter_2 = False
    calls = len(map_reply.prompts)
    assert act(db, jobs, type="bookRetry", bookId=b["id"])["studyBooks"][0]["status"] == "ready"
    assert len(map_reply.prompts) == calls + 2 and "Chapter: Chapter 2" in map_reply.prompts[calls]
    assert len(lessons(db, b["id"])) == 5


def test_first_open_writes_the_chapter_from_the_book_then_the_lesson_is_saved(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    att = lessons(db, bid)["Attention"]
    act(db, jobs, type="bookOpenLesson", conceptId=att["conceptId"])
    assert state.active_goal(db) == bookstudy.get(db, bid)["goal_id"]
    v = lesson.open_lesson(db, jobs, att["conceptId"], plan=False)
    # one call wrote the cards of all three lessons of chapter 1, from the chapter's pages, without web tools
    research = [c for r, c in runner.calls if r == "Research"]
    assert len(research) == 1 and not research[0].tools and "[p. 4]" in research[0].prompt
    assert all(lessons(db, bid)[t]["carded"] for t in ("Softmax", "Attention", "KV cache"))
    assert not lessons(db, bid)["Continuous batching"]["carded"]
    sec = v["sections"][0]
    assert sec["book"] == {"summary": "The book says it is a weighted sum.", "pages": "4"}
    assert sec["body"].startswith("meaning of s-what") and sec["check"]["id"] == "q-s-what"
    assert v["sections"][1]["explain"]["work"] is True and "rubric" not in v["sections"][1]["explain"]
    assert v["book"]["chapter"] == 1 and v["book"]["pages"] == [4, 4] and v["book"]["prev"]["title"] == "Softmax"
    assert v["card"]["sources"][0]["url"] == "source:src-1#page=4"
    # the writer saw the book summaries; idea links survive only for offered ideas
    assert "The book says it is a weighted sum." in prose_reply.prompts[0]
    softmax = lessons(db, bid)["Softmax"]["nodeId"]
    assert f"[softmax](#idea/{softmax})" in sec["body"] and "#idea/n-nope" not in sec["body"] and "magic" in sec["body"]
    # opening again changes nothing: the lesson is saved
    n = len(runner.calls)
    lesson.open_lesson(db, jobs, att["conceptId"], plan=False)
    assert len(runner.calls) == n and lessons(db, bid)["Attention"]["written"]


def test_homework_per_chapter_and_today_continues_the_book(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    ls = lessons(db, bid)
    c = today.view(db)["continue"]
    assert c["kind"] == "lesson" and c["conceptId"] == ls["Softmax"]["conceptId"] and c["chapter"] == 1 and c["total"] == 3
    runner.responses["Practice"] = {"title": "t", "problem": "p", "solution": "s", "node_ids": [], "level": 1}
    act(db, jobs, type="bookHomework", bookId=bid, chapter=1)
    pr = db.one("SELECT * FROM practices WHERE id=?", (db.meta("last_practice"),))
    assert json.loads(pr["node_ids"]) == [ls[t]["nodeId"] for t in ("Softmax", "Attention", "KV cache")]


def test_delete_removes_the_hidden_goal_and_keeps_used_ideas(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    gid = bookstudy.get(db, bid)["goal_id"]
    ls = lessons(db, bid)
    act(db, jobs, type="deleteBook", bookId=bid)
    assert not db.one("SELECT 1 FROM goals WHERE id=?", (gid,))
    assert not db.q("SELECT 1 FROM concepts WHERE id=?", (ls["Softmax"]["conceptId"],))
    assert not db.q("SELECT * FROM book_parts") and not db.q("SELECT * FROM book_chapters")
    assert db.one("SELECT 1 FROM nodes WHERE id='c-dot'")  # an older graph idea the book built on stays


def test_a_version_1_book_is_mapped_again_as_lessons(book):
    db, jobs, runner = book
    db.x("""INSERT INTO books(id, source_id, title, status, chapters_done, chapters, created_at, updated_at)
            VALUES('b-old', 'src-1', 'Inference Book', 'ready', 3, 3, 't', 't')""")
    db.x("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to)
            VALUES('b-old', 0, 1, 'Chapter 1', 'Old part', 3, 5)""")
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    assert bid != "b-old" and not bookstudy.get(db, "b-old") and bookstudy.get(db, bid)["version"] == 2
    assert len(lessons(db, bid)) == 5


PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_the_grader_sees_the_drawing_board(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    cid = lessons(db, bid)["Attention"]["conceptId"]
    act(db, jobs, type="bookOpenLesson", conceptId=cid)
    lesson.open_lesson(db, jobs, cid, plan=False)
    runner.responses["Grading"] = {"score": 1, "feedback": "ok", "missing": [], "followup": ""}
    act(db, jobs, type="explain", conceptId=cid, itemId="e-s-why", answer="see board", drawing=PNG)
    call = [c for r, c in runner.calls if r == "Grading"][-1]
    assert len(call.images) == 1 and call.images[0].read_bytes().startswith(b"\x89PNG") and "drawing board" in call.prompt
    g = state.gradings(db, [cid])[f"{cid}:e-s-why"]
    assert g["status"] == "graded" and g["drawing"].endswith(".png")
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="explain", conceptId=cid, itemId="e-s-why", answer="short")  # no drawing: words needed


def test_reference_chapters_get_no_lessons_and_left_out_entries_still_end_chapters(env):
    db, jobs, runner = env
    outline = OUTLINE + [{"title": "Appendix A: Inference Glossary", "page": 11, "level": 1},
                         {"title": "Index", "page": 12, "level": 1}]
    ch = bookstudy.chapters_from_outline(outline, 12)
    assert [(c["title"], c["page_from"], c["page_to"], c["kind"]) for c in ch][-2:] == [
        ("Chapter 3: Hardware", 10, 10, "chapter"), ("Appendix A: Inference Glossary", 11, 11, "reference")]  # the index ends it
    add_book(db, outline=outline)
    map_reply.prompts, map_reply.fail_chapter_2 = [], False
    runner.responses["Book map"] = map_reply
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    v = bookstudy.view(db, bid)
    assert v["status"] == "ready" and len(map_reply.prompts) == 3  # no call for the glossary
    ref = v["chapters"][-1]
    assert ref["kind"] == "reference" and ref["mapped"] and ref["lessons"] == []
    # the learner can still cut it into lessons
    act(db, jobs, type="bookRemapChapter", bookId=bid, chapter=ref["chapter"], asLessons=True)
    ref = bookstudy.view(db, bid)["chapters"][-1]
    assert ref["kind"] == "chapter" and [x["title"] for x in ref["lessons"]] == ["Memory bandwidth"]


def test_a_chapter_is_mapped_again_and_keeps_what_the_learner_did(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    att = lessons(db, bid)["Attention"]
    lesson.open_lesson(db, jobs, att["conceptId"], plan=False)  # writes the chapter's cards and this lesson
    db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score) VALUES('2026-01-01', ?, 'x', 'check', 1, 1.0)""",
         (att["conceptId"],))
    db.x("INSERT INTO notes(ts, concept_id, quote, text) VALUES('t', ?, '', 'my note')", (att["conceptId"],))
    calls = len(map_reply.prompts)
    act(db, jobs, type="bookRemapChapter", bookId=bid, chapter=1)
    assert len(map_reply.prompts) == calls + 1 and "Chapter: Chapter 1" in map_reply.prompts[-1]  # only this chapter
    again = lessons(db, bid)["Attention"]
    assert again["conceptId"] == att["conceptId"] and not again["carded"] and not again["written"]  # same key: same lesson
    assert db.one("SELECT 1 FROM evidence WHERE concept_id=?", (att["conceptId"],))
    assert db.one("SELECT 1 FROM notes WHERE concept_id=?", (att["conceptId"],))
    assert len(lessons(db, bid)) == 5 and bookstudy.view(db, bid)["status"] == "ready"
    # a chapter the mapper finds is only reference material (no lessons) becomes a reference chapter
    runner.responses["Book map"] = {"summary": "A glossary.", "lessons": []}
    act(db, jobs, type="bookRemapChapter", bookId=bid, chapter=3)
    assert bookstudy.view(db, bid)["chapters"][2]["kind"] == "reference"
    with pytest.raises(actions.ActionError):
        act(db, jobs, type="bookRemapChapter", bookId=bid, chapter=99)


def test_an_extra_lesson_in_a_book_chapter_is_researched_and_sure_wrong_answers_count_double(book):
    from dsc import remedial
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    cid = lessons(db, bid)["Attention"]["conceptId"]
    act(db, jobs, type="bookOpenLesson", conceptId=cid)
    lesson.open_lesson(db, jobs, cid, plan=False)
    for i, conf in enumerate((0.9, 0.3, None)):
        db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, choice, correct, score, confidence, thinking)
                VALUES('2026-01-01', ?, 'q-s-what', 'practice', 1, 0, 0, ?, ?)""", (cid, conf, "longer keys win" if i == 0 else ""))
    s = remedial.signals(db, cid)
    assert len(s["sureWrong"]) == 1 and s["score"] == 4  # 3 wrong + 1 extra for the sure one
    assert "while sure (90 %): likely a misconception" in remedial.brief(db, cid) and 'Their thinking: "longer keys win"' in remedial.brief(db, cid)
    # the extra lesson goes through normal research, not the book-chapter writer
    runner.responses["Research"] = lambda call: {"concepts": [{"key": "x", "title": "Attention (b)", "objective": "o", "bloom": "understand",
        "minutes": 10, "prereq_keys": [], "card": {"core": "c", "formal": "", "why": "w", "angles": [], "examples": [], "misconceptions": [],
        "sources": [], "sections": [{"id": "s-a", "heading": "A", "purpose": "p", "angles": ["geometric"]},
                                    {"id": "s-b", "heading": "B", "purpose": "p", "angles": ["geometric"]}]}}]}
    new_id = remedial.add(db, jobs, cid)
    assert state.latest_card(db, new_id) is not None


def test_a_goal_lesson_opens_while_a_book_goal_is_active(book):
    db, jobs, runner = book
    goal = state.active_goal(db)
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    act(db, jobs, type="bookOpenLesson", conceptId=lessons(db, bid)["Softmax"]["conceptId"])
    assert state.active_goal(db) != goal
    act(db, jobs, type="bookOpenLesson", conceptId="c-dot")
    assert state.active_goal(db) == goal


def test_a_topic_another_lesson_already_teaches_is_one_cell_with_one_lesson(book):
    """SPEC §49: the book's softmax lesson is the goal's linear-combination idea: one cell, one lesson, two sources."""
    from dsc import cells
    db, jobs, runner = book
    base = map_reply

    def reply(call):
        out = base(call)
        if "Chapter: Chapter 1" in call.prompt:
            out["lessons"][0]["same_as"] = "c-lincomb"
        return out
    runner.responses["Book map"] = reply
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    ls = lessons(db, bid)
    sm = ls["Softmax"]
    assert sm["nodeId"] == "c-lincomb" and sm["conceptId"] == "c-lincomb" and sm["ownConceptId"] != "c-lincomb"
    assert cells.home(db, sm["ownConceptId"]) == "c-lincomb"  # the written goal lesson is the idea's one lesson
    # writing the chapter never writes a second lesson of the idea
    act(db, jobs, type="bookOpenLesson", conceptId=ls["Attention"]["conceptId"])
    lesson.open_lesson(db, jobs, ls["Attention"]["conceptId"], plan=False)
    assert not db.one("SELECT 1 FROM cards WHERE concept_id=?", (sm["ownConceptId"],)) and lessons(db, bid)["KV cache"]["carded"]
    v = lesson.view(db, "c-lincomb", bid)
    assert v["blockVersions"] == [] and [x["title"] for x in v["sources"]] == ["Inference Book"]
    assert v["book"]["bookId"] == bid and v["book"]["pages"] == [sm["pages"][0], sm["pages"][1]]  # its place in this book
    text, listing = cells.source_text(db, "c-lincomb")
    assert "=== Source 1: Inference Book" in text and "[Inference Book, p. 4]" in text and listing.startswith("Inference Book")


def test_next_is_a_lesson_whose_parts_you_hold(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    ls = lessons(db, bid)
    assert ls["Softmax"]["ready"] and not ls["Attention"]["ready"]
    assert {n["title"] for n in ls["Attention"]["needs"]} >= {"Softmax"}
    assert bookstudy.view(db, bid)["next"] == ls["Softmax"]["conceptId"]


def test_an_old_book_is_planned_again_with_one_idea_per_lesson(book):
    """SPEC §40: a book mapped by topic (plan 1) offers "Re-plan lessons"; it maps every chapter again and keeps
    what the learner did."""
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    assert not bookstudy.view(db, bid)["oldPlan"] and "**One lesson is one idea.**" in map_reply.prompts[0]
    db.x("UPDATE books SET plan=1 WHERE id=?", (bid,))
    assert bookstudy.view(db, bid)["oldPlan"]
    att = lessons(db, bid)["Attention"]
    db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score) VALUES('2026-01-01', ?, 'x', 'check', 1, 1.0)""",
         (att["conceptId"],))
    calls = len(map_reply.prompts)
    act(db, jobs, type="bookReplan", bookId=bid)
    assert len(map_reply.prompts) == calls + 3  # every chapter again
    v = bookstudy.view(db, bid)
    assert v["status"] == "ready" and not v["oldPlan"] and len(lessons(db, bid)) == 5
    assert lessons(db, bid)["Attention"]["conceptId"] == att["conceptId"]
    assert db.one("SELECT 1 FROM evidence WHERE concept_id=?", (att["conceptId"],))


def test_a_book_card_and_its_map_area_have_one_color(book):
    from dsc import graph
    db, jobs, runner = book
    s = act(db, jobs, type="studyBook", sourceId="src-1")
    b = s["studyBooks"][0]
    clusters = {c["id"]: c for c in graph.view(db)["clusters"]}
    assert clusters[f"book:{b['id']}"]["color"] == b["color"] == 0 and b["kind"] == "book"
    assert next(x for x in s["sources"] if x["id"] == "src-1")["mapped"]
