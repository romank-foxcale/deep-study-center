"""Book study, "teach me this book" (SPEC §28): parts from the outline, the chapter-by-chapter map, studying a part,
homework, idea links and hover details."""

import json

import pytest

from dsc import actions, bookstudy, graph, session, state
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


def add_book(db, pages=12):
    db.x("""INSERT INTO sources(id, title, author, kind, filename, bytes, pages, status, outline, added_at)
            VALUES('src-1', 'Inference Book', 'A. Author', 'book', 'b.pdf', 1, ?, 'ready', ?, '2026-01-01')""",
         (pages, dumps(OUTLINE)))
    for p in range(1, pages + 1):
        text = f"page {p} text about attention softmax kv cache memory bandwidth serving"
        db.x("INSERT INTO source_pages(source_id, page, text) VALUES('src-1', ?, ?)", (p, text))
        db.x("INSERT INTO source_fts(source_id, page, text) VALUES('src-1', ?, ?)", (p, text))


def idea(key, title, prereqs=(), same_as=None, pages="4"):
    d = {"key": key, "title": title, "statement": f"{title} explained.", "kind": "concept", "pages": pages,
         "prereq_keys": list(prereqs)}
    if same_as:
        d["same_as"] = same_as
    return d


def map_reply(call):
    """Chapter 1: attention (reuses the graph's dot product), kv cache; chapter 2: batching (needs kv cache from chapter 1);
    chapter 3: bandwidth."""
    map_reply.prompts.append(call.prompt)
    if "Chapter: Chapter 1" in call.prompt:
        return {"parts": [
            {"part": 0, "summary": "How attention works.", "ideas": [idea("softmax", "Softmax"),
                                                                    idea("attention", "Attention", ["softmax", "c-dot"]),
                                                                    idea("dot", "Dot product", same_as="c-dot")]},
            {"part": 1, "summary": "Caching keys and values.", "ideas": [idea("kv-cache", "KV cache", ["attention"], pages="6-7")]},
            {"part": 9, "summary": "bad index", "ideas": [idea("x", "Dropped")]}]}
    if "Chapter: Chapter 2" in call.prompt:
        if map_reply.fail_chapter_2:
            raise RuntimeError("model hiccup")
        return {"parts": [{"part": 0, "summary": "Serving.", "ideas": [idea("batching", "Continuous batching", ["c1-kv-cache"])]}]}
    return {"parts": [{"part": 0, "summary": "Bandwidth.", "ideas": [idea("bw", "Memory bandwidth")]}]}


@pytest.fixture
def book(env):
    db, jobs, runner = env
    add_book(db)
    map_reply.prompts = []
    map_reply.fail_chapter_2 = False
    runner.responses["Book map"] = map_reply
    return db, jobs, runner


def test_parts_from_the_outline():
    ps = bookstudy.parts_from_outline(OUTLINE, 12)
    assert [(p["chapter"], p["title"], p["page_from"], p["page_to"]) for p in ps] == [
        (1, "1.1 Attention", 3, 5),        # the chapter's first pages go to its first section
        (1, "1.2 KV cache", 6, 7),
        (2, "Chapter 2: Serving", 8, 9),    # a chapter without sections is one part
        (3, "3.1 Memory bandwidth", 10, 12)]
    chunks = bookstudy.parts_from_outline([], 30)
    assert [(p["page_from"], p["page_to"]) for p in chunks] == [(1, 12), (13, 24), (25, 30)]


def test_map_makes_parts_ideas_and_links(book):
    db, jobs, runner = book
    s = act(db, jobs, type="studyBook", sourceId="src-1")
    b = s["studyBooks"][0]
    assert b["status"] == "ready" and b["chapters"] == 3 and b["chaptersDone"] == 3 and s["lastBook"] == b["id"]
    v = bookstudy.view(db, b["id"])
    parts = {p["title"]: p for p in v["parts"]}
    att = parts["1.1 Attention"]
    assert att["summary"] == "How attention works." and [i["title"] for i in att["ideas"]] == ["Softmax", "Attention", "Dot product & similarity"]
    dot = att["ideas"][2]  # the graph's node keeps its own title
    assert dot["id"] == "c-dot" and dot["fromGraph"]  # same_as reused the graph's node
    assert not any(i["title"] == "Dropped" for p in v["parts"] for i in p["ideas"])
    ids = {i["title"]: i["id"] for p in v["parts"] for i in p["ideas"]}
    pairs = {(lk["src"], lk["dst"]) for lk in graph.links(db)}
    assert (ids["Softmax"], ids["Attention"]) in pairs and ("c-dot", ids["Attention"]) in pairs
    assert (ids["KV cache"], ids["Continuous batching"]) in pairs  # across chapters, by key
    assert db.one("SELECT origin FROM nodes WHERE id=?", (ids["Softmax"],))["origin"] == "book"
    # the second chapter's prompt saw the first chapter's ideas, and the graph's matching ideas
    assert "c1-kv-cache: KV cache" in map_reply.prompts[1]
    assert v["next"] == att["id"]


def test_a_failed_chapter_is_retried_without_redoing_earlier_ones(book):
    db, jobs, runner = book
    map_reply.fail_chapter_2 = True
    s = act(db, jobs, type="studyBook", sourceId="src-1")
    b = s["studyBooks"][0]
    assert b["status"] == "failed" and b["chaptersDone"] == 1
    assert bookstudy.view(db, b["id"])["error"]
    map_reply.fail_chapter_2 = False
    calls = len(map_reply.prompts)
    s = act(db, jobs, type="bookRetry", bookId=b["id"])
    assert s["studyBooks"][0]["status"] == "ready"
    assert len(map_reply.prompts) == calls + 2 and "Chapter: Chapter 2" in map_reply.prompts[calls]


def test_study_a_part_then_homework(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    kv = next(p for p in bookstudy.view(db, bid)["parts"] if p["title"] == "1.2 KV cache")
    probe_prompts = []

    def tutor(call):
        if "Your task:" in call.prompt:
            return {"body": "x", "check": {"prompt": "q", "options": ["a", "b"], "explanation": "e", "answer": 0}}
        probe_prompts.append(call.prompt)
        return {"done": True, "result": {"start": "Start with attention.", "ideas": []}}
    runner.responses["Study tutor"] = tutor
    act(db, jobs, type="bookStudyPart", partId=kv["id"])
    sid = db.meta("last_session")
    v = session.view(db, sid)
    assert v["book"]["part"] == "1.2 KV cache" and v["book"]["pages"] == [6, 7]
    titles = [i["title"] for i in v["ideas"]]
    assert titles == ["Attention", "KV cache"]  # the outside prerequisite comes in first
    kv_idea = next(i for i in v["ideas"] if i["title"] == "KV cache")
    att_idea = next(i for i in v["ideas"] if i["title"] == "Attention")
    assert kv_idea["prereqs"] == [att_idea["key"]]
    assert v["status"] == "planning" and probe_prompts and "KV cache" in probe_prompts[0]
    # the teaching turns read the part's own pages only
    assert all(6 <= e["page"] <= 7 for e in __import__("dsc").sources.excerpts(db, None, "kv cache", ids=["src-1"], pages=(6, 7)))
    # opening the part again returns the same session
    act(db, jobs, type="bookStudyPart", partId=kv["id"])
    assert db.meta("last_session") == sid
    part = db.one("SELECT * FROM book_parts WHERE id=?", (kv["id"],))
    assert part["status"] == "studying" and part["session_id"] == sid
    bookstudy.on_session_done(db, sid)
    assert db.one("SELECT status FROM book_parts WHERE id=?", (kv["id"],))["status"] == "done"
    runner.responses["Practice"] = {"title": "t", "problem": "p", "solution": "s", "node_ids": [], "level": 1}
    act(db, jobs, type="bookHomework", partId=kv["id"])
    pr = db.one("SELECT * FROM practices WHERE id=?", (db.meta("last_practice"),))
    assert json.loads(pr["node_ids"]) == [kv_idea["node"]]


def test_hover_details_and_delete(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    ids = {i["title"]: i["id"] for p in bookstudy.view(db, bid)["parts"] for i in p["ideas"]}
    d = graph.node_detail(db, ids["Attention"])
    assert d["books"][0]["part"] == "1.1 Attention" and d["books"][0]["pages"] == "4"
    assert {x["title"] for x in d["buildsOn"]} == {"Softmax", "Dot product & similarity"} and [x["title"] for x in d["leadsTo"]] == ["KV cache"]
    assert graph.view(db)["books"][0]["id"] == bid
    db.x("""INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score) VALUES('2026-01-01', ?, 'x', 'practice', 1, 1.0)""",
         (ids["Softmax"],))
    act(db, jobs, type="deleteBook", bookId=bid)
    assert db.one("SELECT 1 FROM nodes WHERE id=?", (ids["Softmax"],))  # has evidence: kept
    assert not db.one("SELECT 1 FROM nodes WHERE id=?", (ids["KV cache"],))
    assert db.one("SELECT 1 FROM nodes WHERE id='c-dot'")  # a graph node the book reused stays
    assert not db.q("SELECT * FROM book_parts")


def test_turn_links_only_offered_ideas(book):
    db, jobs, runner = book
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    att = next(p for p in bookstudy.view(db, bid)["parts"] if p["title"] == "1.1 Attention")
    softmax = next(i["id"] for i in att["ideas"] if i["title"] == "Softmax")
    turn_prompts = []

    def tutor(call):
        if "Your task: **predict**" in call.prompt:
            return {"predict": {"prompt": "p", "options": ["a", "b"], "explanation": "e", "answer": 0}}
        if "Your task:" in call.prompt:
            turn_prompts.append(call.prompt)
            return {"body": f"Attention uses [softmax](#idea/{softmax}) and [magic](#idea/n-nope).",
                    "check": {"prompt": "q", "options": ["a", "b"], "explanation": "e", "answer": 0}}
        return {"done": True, "result": {"start": "", "ideas": []}}
    runner.responses["Study tutor"] = tutor
    act(db, jobs, type="bookStudyPart", partId=att["id"])
    sid = db.meta("last_session")
    act(db, jobs, type="sessionTeach", sessionId=sid)
    q = next(i for i in session.view(db, sid)["items"] if i["phase"] == "predict")
    act(db, jobs, type="sessionAnswer", sessionId=sid, itemId=q["id"], choice=0)
    body = next(i for i in session.view(db, sid)["items"] if i["phase"] == "explain")["body"]
    assert f"[softmax](#idea/{softmax})" in body and "magic" in body and "#idea/n-nope" not in body
    assert f"- {softmax}: Softmax" in turn_prompts[0]


def test_big_parts_are_split_and_a_chapter_can_be_mapped_again(book):
    db, jobs, runner = book
    many = [idea(f"s{n}", f"Serving idea {n}") for n in range(12)]
    base = map_reply

    def reply(call):
        if "Chapter: Chapter 2" in call.prompt:
            reply.prompts.append(call.prompt)
            return {"parts": [{"part": 0, "summary": "Serving.", "ideas": many}]}
        return base(call)
    reply.prompts = []
    runner.responses["Book map"] = reply
    bid = act(db, jobs, type="studyBook", sourceId="src-1")["studyBooks"][0]["id"]
    serving = [p for p in bookstudy.view(db, bid)["parts"] if p["title"].startswith("Chapter 2")]
    assert [(p["title"], len(p["ideas"])) for p in serving] == [("Chapter 2: Serving (1/2)", 8), ("Chapter 2: Serving (2/2)", 4)]
    assert [p["ord"] for p in bookstudy.view(db, bid)["parts"]] == list(range(5))
    # the mapper saw all older graph ideas by title, and the subsections of a part
    assert "c-dot: Dot product & similarity" in map_reply.prompts[0]  # chapter 1; chapter 2 sees it as a book idea
    assert "1.1 Attention" in map_reply.prompts[0]
    # mapping chapter 2 again joins and splits it again, with no duplicates; a model that points at the chapter's
    # own old ideas (same_as or a prerequisite id) gets new ideas, never a link to a deleted one
    old_id = serving[0]["ideas"][0]["id"]
    many[1] = {**many[1], "same_as": old_id, "prereq_keys": [old_id]}
    jobs.enqueue("book_map", "again", {"book_id": bid, "only": [1]})
    assert not db.q("SELECT node_id FROM book_nodes WHERE node_id NOT IN (SELECT id FROM nodes)")
    assert not db.q("SELECT src FROM links WHERE src NOT IN (SELECT id FROM nodes) OR dst NOT IN (SELECT id FROM nodes)")
    serving = [p for p in bookstudy.view(db, bid)["parts"] if p["title"].startswith("Chapter 2")]
    assert [(p["title"], len(p["ideas"])) for p in serving] == [("Chapter 2: Serving (1/2)", 8), ("Chapter 2: Serving (2/2)", 4)]
    assert db.one("SELECT COUNT(*) AS n FROM book_nodes WHERE book_id=?", (bid,))["n"] == 3 + 1 + 12 + 1
    made = db.one("SELECT COUNT(*) AS n FROM book_nodes WHERE book_id=? AND created=1", (bid,))["n"]
    assert db.one("SELECT COUNT(*) AS n FROM nodes WHERE origin='book'")["n"] == made  # no orphans from the first map
