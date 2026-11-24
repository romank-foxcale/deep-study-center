"""Teach from a link (SPEC §47): a web page's text or a video's captions become pages, then a book of lessons."""

import json

import pytest

from dsc import actions, bookstudy, links, sources, state
from test_bookstudy import map_reply, cards_reply, prose_reply

PARA = "Attention weighs every value by how well its key matches the query, and the weights sum to one. "
PAGE = f"""<!doctype html><html><head><title>Ignored title</title><meta property="og:title" content="Attention &amp; you">
<script>var x = "{'never shown ' * 50}";</script><style>p {{ color: red }}</style></head>
<body><nav><a href="/">Home</a> <a href="/blog">Blog</a></nav>
<header><h1>Site name</h1></header>
<main>
<h1>Attention, explained</h1><p>{PARA * 3}</p>
<h2>Scores</h2><p>{PARA * 12}</p><ul><li>{PARA}</li><li>Short</li></ul>
<h2>Softmax</h2><p>{PARA * 12}<br>{PARA}</p><div class="ad" hidden>Buy now, a long hidden advert that must not appear at all.</div>
<h3>Why it sums to one</h3><p>{PARA * 2}</p>
</main>
<footer><p>Copyright, all rights reserved, and a long footer line that is not part of the text.</p></footer></body></html>"""


def test_a_web_page_becomes_its_main_text_in_pages_with_its_headings_as_outline():
    title, blocks = links.page_text(PAGE)
    assert title == "Attention & you"
    text = " ".join(t for _, t in blocks)
    for gone in ("never shown", "color: red", "Home", "Site name", "hidden advert", "Copyright", "Short"):
        assert gone not in text
    assert blocks[0] == (0, "Attention, explained") and (1, "Scores") in blocks and (2, "Why it sums to one") in blocks
    pages, outline = links.paginate(blocks)
    assert all(len(p) <= links.PAGE_CHARS + 200 for p in pages) and len(pages) >= 2
    assert [(o["title"], o["level"]) for o in outline] == [("Attention, explained", 0), ("Scores", 1), ("Softmax", 1),
                                                           ("Why it sums to one", 2)]
    assert [o["page"] for o in outline] == sorted(o["page"] for o in outline)
    assert "Softmax" in pages[outline[2]["page"] - 1]


def test_a_video_link_gives_its_id_and_its_captions_become_timed_pages():
    assert links.video_id("https://www.youtube.com/watch?v=abcDEF12345&t=3") == "abcDEF12345"
    assert links.video_id("https://youtu.be/abcDEF12345?si=x") == "abcDEF12345"
    assert links.video_id("https://youtube.com/shorts/abcDEF12345") == "abcDEF12345"
    assert links.video_id("https://example.com/watch?v=abcDEF12345") is None
    snips = [{"text": "[Music]", "start": 0.0}] + [{"text": f"sentence {i} about attention.", "start": 1.0 + i * 10} for i in range(60)]
    pages, marks = links.video_pages(snips)
    assert len(pages) == len(marks) >= 3 and marks[0] == 1 and all(b - a >= links.VIDEO_SECONDS for a, b in zip(marks, marks[1:]))
    assert "[Music]" not in pages[0] and pages[0].startswith("sentence 0")
    assert links.clock(75) == "1:15" and links.clock(3725) == "1:02:05"


@pytest.fixture
def linked(env, monkeypatch):
    db, jobs, runner = env
    map_reply.prompts, map_reply.fail_chapter_2 = [], False
    cards_reply.prompts, prose_reply.prompts = [], []
    runner.responses["Book map"] = lambda call: {"summary": "About attention.", "lessons": [
        {"key": "att", "title": "Attention", "covers": "Attention.", "pages": "1-2", "ideas": ["weights"], "prereq_keys": []}]}
    runner.responses["Research"] = cards_reply
    runner.responses["Renditions"] = prose_reply
    fetched = []
    monkeypatch.setattr(links, "_fetch", lambda url: fetched.append(url) or (PAGE.encode(), "text/html; charset=utf-8"))
    return db, jobs, runner, fetched


def test_adding_a_link_reads_it_and_teach_me_this_makes_it_a_book(linked):
    db, jobs, runner, fetched = linked
    sid = sources.add_link(db, "https://example.com/attention")
    assert db.one("SELECT status FROM sources WHERE id=?", (sid,))["status"] == "reading"
    jobs.enqueue("read_link", "Read a link", {"source_id": sid})
    src = db.one("SELECT * FROM sources WHERE id=?", (sid,))
    assert src["status"] == "ready" and src["pages"] >= 2 and src["title"] == "Attention & you"
    assert [(o["title"], o["level"]) for o in json.loads(src["outline"])][:2] == [("Scores", 0), ("Scores", 1)]
    assert db.one("SELECT text FROM source_pages WHERE source_id=? AND page=1", (sid,))["text"].startswith("Attention, explained")
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": sid})
    bid = db.meta("last_book")
    assert bookstudy.view(db, bid)["chapters"] and fetched == ["https://example.com/attention"]


def test_teach_me_this_on_an_unread_link_reads_it_first_then_teaches_it(linked):
    db, jobs, runner, fetched = linked
    sid = sources.add_link(db, "https://example.com/attention", title="My name for it")
    actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": sid})  # one click: read, then teach
    src = db.one("SELECT * FROM sources WHERE id=?", (sid,))
    assert src["status"] == "ready" and src["title"] == "My name for it"  # a name the learner gave wins
    assert any(b["sourceId"] == sid for b in state.snapshot(db)["studyBooks"])


def test_a_link_without_text_or_that_fails_is_marked_and_can_be_read_again(linked, monkeypatch):
    db, jobs, runner, fetched = linked
    monkeypatch.setattr(links, "_fetch", lambda url: (b"<html><body><p>Too short.</p></body></html>", "text/html"))
    sid = sources.add_link(db, "https://example.com/empty")
    jobs.enqueue("read_link", "Read a link", {"source_id": sid})
    assert db.one("SELECT status FROM sources WHERE id=?", (sid,))["status"] == "no_text"
    with pytest.raises(actions.ActionError, match="No text"):
        actions.dispatch(db, jobs, {"type": "studyBook", "sourceId": sid})

    def boom(url):
        raise links.LinkError("the page could not be fetched (timed out)")
    monkeypatch.setattr(links, "_fetch", boom)
    actions.dispatch(db, jobs, {"type": "rereadSource", "id": sid})
    assert db.one("SELECT status FROM sources WHERE id=?", (sid,))["status"] == "error"
    monkeypatch.setattr(links, "_fetch", lambda url: (PAGE.encode(), "text/html"))
    actions.dispatch(db, jobs, {"type": "rereadSource", "id": sid})
    assert db.one("SELECT status FROM sources WHERE id=?", (sid,))["status"] == "ready"


def test_a_video_is_read_from_its_captions_and_a_citation_opens_it_at_the_page_time(linked, monkeypatch):
    db, jobs, runner, fetched = linked
    snips = [{"text": f"sentence {i} about attention weights and keys.", "start": i * 10.0} for i in range(80)]
    monkeypatch.setattr(links, "transcript", lambda vid: snips if vid == "abcDEF12345" else [])
    monkeypatch.setattr(links, "_fetch", lambda url: fetched.append(url) or (b'{"title": "Attention in   transformers"}', "application/json"))
    sid = sources.add_link(db, "https://www.youtube.com/watch?v=abcDEF12345")
    jobs.enqueue("read_link", "Read a link", {"source_id": sid})
    src = db.one("SELECT * FROM sources WHERE id=?", (sid,))
    marks = json.loads(src["marks"])
    assert src["status"] == "ready" and src["pages"] == len(marks) >= 3 and src["title"] == "Attention in transformers"
    assert fetched == ["https://www.youtube.com/oembed?format=json&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DabcDEF12345"]
    assert links.href(db, sid, 2) == f"https://www.youtube.com/watch?v=abcDEF12345&t={marks[1]}s"
    assert links.href(db, sid, None) == "https://www.youtube.com/watch?v=abcDEF12345"
    db.x("""INSERT INTO sources(id, title, kind, filename, status, outline, added_at) VALUES('src-pdf','P','book','p.pdf','ready','[]','x')""")
    assert links.href(db, "src-pdf", 3) is None  # a PDF opens in the app's own file view


def test_a_link_to_a_pdf_file_is_read_as_a_pdf(linked, monkeypatch):
    db, jobs, runner, fetched = linked
    monkeypatch.setattr(links, "_fetch", lambda url: (b"%PDF-1.4 fake", "application/pdf"))
    read = []
    monkeypatch.setattr(sources, "ingest", lambda db, sid, progress: read.append(sid) or {"status": "ready", "pages": 3})
    sid = sources.add_link(db, "https://example.com/paper.pdf")
    jobs.enqueue("read_link", "Read a link", {"source_id": sid})
    assert read == [sid] and sources.file_path(sid).read_bytes().startswith(b"%PDF")


def test_a_long_pages_headings_become_chapters_of_several_pages_and_a_short_page_is_one_chapter():
    heads = [{"title": "Title", "page": 1, "level": 0}] + [{"title": f"H{i}", "page": 1 + i // 2, "level": 1} for i in range(20)]
    out = links.group(heads)
    chapters = [o for o in out if o["level"] == 0]
    assert [c["page"] for c in chapters] == [1, 5, 9] and len([o for o in out if o["level"] == 1]) == 20
    ch = bookstudy.chapters_from_outline(out, 10)
    assert [(c["page_from"], c["page_to"]) for c in ch] == [(1, 4), (5, 8), (9, 10)] and len(ch[0]["sections"]) >= 7
    short = links.group([{"title": "A", "page": 1, "level": 1}, {"title": "B", "page": 2, "level": 1}])
    assert [(c["page_from"], c["page_to"]) for c in bookstudy.chapters_from_outline(short, 3)] == [(1, 3)]
