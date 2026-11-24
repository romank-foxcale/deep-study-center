"""The learner's own PDF sources (SPEC §17): upload, reading, search, and use in the outline and research."""

from fastapi.testclient import TestClient

from dsc import actions, sources, state
from dsc.api import create_app


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def make_pdf(pages: list[str], title: str = "Deep RL Book", outline: list[tuple[str, int]] = ()) -> bytes:
    """A small, valid PDF with one line of text per page and an optional outline (bookmarks)."""
    objs: list[bytes] = []
    n = len(pages)
    font = 3 + 2 * n
    first_ol = font + 1
    objs.append(b"<< /Type /Catalog /Pages 2 0 R" + (f" /Outlines {first_ol} 0 R".encode() if outline else b"") + b" >>")
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    if outline:
        items = [first_ol + 1 + i for i in range(len(outline))]
        objs.append(f"<< /Type /Outlines /First {items[0]} 0 R /Last {items[-1]} 0 R /Count {len(items)} >>".encode())
        for i, (label, page) in enumerate(outline):
            prev = f" /Prev {items[i - 1]} 0 R" if i else ""
            nxt = f" /Next {items[i + 1]} 0 R" if i + 1 < len(items) else ""
            objs.append(f"<< /Title ({label}) /Parent {first_ol} 0 R{prev}{nxt} "
                        f"/Dest [{3 + 2 * (page - 1)} 0 R /Fit] >>".encode())
    info = len(objs) + 1
    objs.append(f"<< /Title ({title}) /Author (A. Writer) >>".encode())
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs):
        offsets.append(len(out))
        out += f"{i + 1} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


PAGES = ["Markov decision processes describe states, actions and rewards for an agent in an environment.",
         "The Bellman equation writes the value of a state as reward plus the discounted value of the next state.",
         "Policy gradient methods change the policy parameters in the direction that raises expected return."]
PDF = make_pdf(PAGES, outline=[("Chapter 1 MDPs", 1), ("Chapter 2 Bellman", 2), ("Chapter 3 Policy gradients", 3)])


def test_upload_reads_pages_outline_and_metadata(env):
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    r = client.post("/api/sources?filename=deep_rl-book.pdf&kind=book&link=1", content=PDF)
    assert r.status_code == 200
    [src] = r.json()["sources"]
    assert src["status"] == "ready" and src["pages"] == 3 and src["outline"] == 3
    assert src["title"] == "Deep RL Book" and src["author"] == "A. Writer"
    assert src["goalIds"] == ["g-ai"]  # link=1 adds it to the current goal
    f = client.get(f"/api/sources/{src['id']}/file")
    assert f.status_code == 200 and f.content == PDF and f.headers["content-type"] == "application/pdf"
    assert client.get("/api/sources/src-missing/file").status_code == 404
    assert client.post("/api/sources?filename=x.pdf", content=b"hello").status_code == 400


def test_search_finds_the_best_page_and_formats_citations(env):
    db, jobs, _ = env
    sid = sources.add(db, PDF, "rl.pdf")
    sources.ingest(db, sid)
    assert sources.excerpts(db, "g-ai", "Bellman equation") == []  # not linked to the goal yet
    sources.link(db, "g-ai", sid, True)
    hits = sources.excerpts(db, "g-ai", "The Bellman equation and value")
    assert hits[0]["page"] == 2 and hits[0]["sourceId"] == sid
    text = sources.excerpts_text(hits)
    assert f'source:{sid}#page=2' in text and "[Deep RL Book, p. 2]" in text
    toc = sources.contents_text(db, "g-ai")
    assert "Chapter 2 Bellman (p. 2)" in toc and "A. Writer" in toc


def test_scanned_pdf_is_marked_no_text(env):
    db, _, _ = env
    sid = sources.add(db, make_pdf(["", "", ""]), "scan.pdf")
    assert sources.ingest(db, sid)["status"] == "no_text"


def test_actions_edit_link_and_delete(env):
    db, jobs, _ = env
    sid = sources.add(db, PDF, "rl.pdf")
    sources.ingest(db, sid)
    act(db, jobs, type="editSource", id=sid, title="My RL notes", kind="article")
    s = act(db, jobs, type="linkSource", sourceId=sid, on=True)
    src = s["sources"][0]
    assert src["title"] == "My RL notes" and src["kind"] == "article" and src["goalIds"] == ["g-ai"]
    s = act(db, jobs, type="linkSource", sourceId=sid, on=False)
    assert s["sources"][0]["goalIds"] == []
    s = act(db, jobs, type="deleteSource", id=sid)
    assert s["sources"] == [] and not sources.file_path(sid).exists()
    assert db.q("SELECT * FROM source_fts WHERE source_id=?", (sid,)) == []


def test_new_goal_uses_its_sources_in_outline_and_research(env):
    db, jobs, runner = env
    sid = sources.add(db, PDF, "rl.pdf")
    sources.ingest(db, sid)
    runner.responses["Curriculum"] = {"title": "Learn RL", "why": "w", "done": "d", "tracks": [
        {"title": "Basics", "summary": "s", "modules": [{"title": "Bellman equation", "summary": "value of a state", "planned": 1}]}]}
    runner.responses["Research"] = {"concepts": [
        {"key": "bellman", "title": "Bellman", "objective": "o", "minutes": 20, "prereq_keys": [],
         "card": {"bloom": "understand", "core": "c", "formal": "f", "why": "w", "angles": [], "examples": [],
                  "misconceptions": [], "sections": [{"id": "s-1", "heading": "H", "purpose": "p", "angles": ["algebraic"]}],
                  "sources": [{"title": "Deep RL Book, p. 2", "url": f"source:{sid}#page=2", "kind": "book", "why": "w"}]}}]}
    runner.responses["Fact-check"] = {"results": []}
    s = act(db, jobs, type="createGoal", layout="list", sourceIds=[sid, "src-unknown"],
            answers=[{"q": "goal", "a": "learn RL"}, {"q": "know", "a": "python"}, {"q": "why", "a": "job"}, {"q": "time", "a": "6 hours"}])
    gid = s["goal"]["id"]
    assert next(x for x in s["sources"] if x["id"] == sid)["goalIds"] == [gid]
    outline_prompt = next(c.prompt for role, c in runner.calls if role == "Curriculum")
    assert "Chapter 2 Bellman (p. 2)" in outline_prompt
    research_prompt = next(c.prompt for role, c in runner.calls if role == "Research")
    assert f"source:{sid}#page=2" in research_prompt and "[Deep RL Book, p. 2]" in research_prompt
    # deleting the goal drops its links but keeps the source
    s = act(db, jobs, type="deleteGoal", id=gid)
    assert next(x for x in s["sources"] if x["id"] == sid)["goalIds"] == []


def test_clean_joins_split_surrogates_and_drops_lone_ones():
    pair = "\ud835\udc65"  # U+1D465 (math italic x) as two separate surrogates, as some PDFs give it
    assert sources.clean(f"a  {pair}\n b \ud835 c") == "a \U0001d465 b \ufffd c"
    sources.clean(pair).encode("utf-8")  # storable


def test_read_again_after_an_error(env):
    db, jobs, _ = env
    sid = sources.add(db, PDF, "rl.pdf")
    db.x("UPDATE sources SET status='error' WHERE id=?", (sid,))
    s = act(db, jobs, type="rereadSource", id=sid)
    assert next(x for x in s["sources"] if x["id"] == sid)["status"] == "ready"


def test_the_same_file_or_link_twice_is_refused(env):
    """SPEC §40: a duplicate is found by the file's SHA-256 (any name) or by the link."""
    db, jobs, _ = env
    client = TestClient(create_app(db=db, jobs=jobs))
    r = client.post("/api/sources?filename=a.pdf&kind=article&title=My%20paper", content=PDF)
    src = r.json()["sources"][0]
    assert src["title"] == "My paper" and src["kind"] == "article" and len(src["sha256"]) == 64
    r = client.post("/api/sources?filename=other-name.pdf", content=PDF)
    assert r.status_code == 409 and "My paper" in r.json()["detail"]
    r = client.post("/api/sources/link", json={"url": "https://www.youtube.com/watch?v=abc", "title": ""})
    link = next(x for x in r.json()["sources"] if x["url"])
    assert link["kind"] == "video" and link["status"] == "error" and not link["mapped"]  # read at once (no network in tests) and link["title"].startswith("www.youtube.com")
    assert client.post("/api/sources/link", json={"url": "https://www.youtube.com/watch?v=abc"}).status_code == 409
    assert client.post("/api/sources/link", json={"url": "ftp://x"}).status_code == 400
    s = act(db, jobs, type="editSource", id=link["id"], kind="web")
    assert next(x for x in s["sources"] if x["id"] == link["id"])["kind"] == "web"
    act(db, jobs, type="deleteSource", id=link["id"])
    assert all(x["id"] != link["id"] for x in state.snapshot(db)["sources"])


def test_old_kinds_and_files_get_the_new_types_and_a_hash(env):
    db, jobs, _ = env
    sid = sources.add(db, PDF, "x.pdf", "book")
    db.x("UPDATE sources SET kind='post', sha256='' WHERE id=?", (sid,))
    sources.upgrade(db)
    row = db.one("SELECT kind, sha256 FROM sources WHERE id=?", (sid,))
    assert row["kind"] == "web" and len(row["sha256"]) == 64
