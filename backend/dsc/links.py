"""Teach from a link (SPEC §47): a web page's text or a video's transcript becomes a source with pages, so "Teach me
this" makes it a book of lessons, like a PDF.

- **Read** (job ``read_link``): a web page is fetched once and its main text is kept (scripts, menus, headers, footers
  and forms are left out; an <article> or <main> part wins when the page has one). A video's transcript comes from its
  captions (YouTube). A link to a PDF file is saved and read as a PDF.
- **Pages.** The text is cut into pages of about ``PAGE_CHARS`` at paragraph ends, so the book machinery (chapters by
  pages, citations "p. N") works unchanged. A web page's headings become its outline (chapters); a video's pages are
  stretches of about ``VIDEO_SECONDS``, and ``sources.marks`` keeps where each page starts, so a citation opens the
  video at that time.
- Nothing is sent to a model here. The fetch sends no data about the learner.
"""

from __future__ import annotations

import html
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from .db import DB, dumps, loads

PAGE_CHARS = 2_500
GROUP_PAGES = 4  # a chapter of a web page has at least this many pages (one model call maps one chapter)
VIDEO_SECONDS = 180
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 30
AGENT = "Mozilla/5.0 (compatible; DeepStudyCenter; +https://github.com/romank-foxcale/deep-study-center)"


class LinkError(Exception):
    pass


# ---------------------------------------------------------------- web pages

_SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "button", "select", "template",
         "iframe", "canvas", "figure"}
_BLOCK = {"p", "li", "pre", "blockquote", "td", "th", "dd", "dt", "div", "section", "article", "main", "br", "tr", "table",
          "ul", "ol", "figcaption", "caption"}
_HEAD = {"h1": 0, "h2": 1, "h3": 2, "h4": 3}
_VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "col", "embed", "param", "track"}


class _Page(HTMLParser):
    """Blocks of text ([level or None, text]) of the whole body, and of its <article>/<main> part."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.stack: list[str] = []
        self.buf: list[str] = []
        self.head: int | None = None
        self.blocks: list[tuple[int | None, str, bool]] = []  # (heading level, text, inside article/main)
        self.main = 0
        self.title = ""
        self.og = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("property") == "og:title" or a.get("name") == "og:title"):
            self.og = a.get("content") or ""
        if tag in _VOID:
            if tag == "br":
                self.buf.append("\n")
            return
        self.stack.append(tag)
        if tag == "title":
            self.in_title = True
        if self.skip or tag in _SKIP or a.get("aria-hidden") == "true" or "hidden" in a:
            self.skip += 1
            return
        if tag in ("article", "main"):
            self._flush()
            self.main += 1
        elif tag in _HEAD:
            self._flush()
            self.head = _HEAD[tag]
        elif tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _VOID or tag not in self.stack:
            return
        while self.stack:  # close unclosed tags inside this one
            t = self.stack.pop()
            if t == "title":
                self.in_title = False
            if self.skip:
                self.skip -= 1
                if t == tag:
                    return
                continue
            if t in ("article", "main"):
                self._flush()
                self.main = max(0, self.main - 1)
            elif t in _HEAD or t in _BLOCK:
                self._flush()
            if t == tag:
                return

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if not self.skip:
            self.buf.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if text:
            self.blocks.append((self.head, text, self.main > 0))
        self.head = None

    def close(self):
        super().close()
        self._flush()


def page_text(raw: str) -> tuple[str, list[tuple[int | None, str]]]:
    """The page's title and its main text as blocks: (heading level or None, text)."""
    p = _Page()
    p.feed(raw)
    p.close()
    main = [(h, t) for h, t, m in p.blocks if m]
    blocks = main if sum(len(t) for _, t in main) >= 500 else [(h, t) for h, t, _ in p.blocks]
    blocks = [(h, t) for h, t in blocks if h is not None or len(t) >= 25 or t.endswith((".", ":", "?", "!"))]  # menus, labels
    title = " ".join(html.unescape(p.og or p.title).split())
    return title, blocks


def paginate(blocks: list[tuple[int | None, str]]) -> tuple[list[str], list[dict]]:
    """Pages of about PAGE_CHARS (cut at block ends) and the outline from the headings."""
    pages: list[str] = []
    outline: list[dict] = []
    cur: list[str] = []
    size = 0

    def close():
        nonlocal cur, size
        if cur:
            pages.append("\n".join(cur))
        cur, size = [], 0
    levels = sorted({h for h, _ in blocks if h is not None})
    for h, t in blocks:
        if h is not None:
            if h == (levels[0] if levels else 0) and size > PAGE_CHARS // 3:
                close()  # a top heading starts a new page, unless the page is nearly empty
            outline.append({"title": t[:160], "page": len(pages) + 1, "level": levels.index(h)})
        while len(t) > PAGE_CHARS:  # a very long block: cut it at a sentence end
            cut = t.rfind(". ", 0, PAGE_CHARS) + 1 or PAGE_CHARS
            cur.append(t[:cut])
            close()
            t = t[cut:].strip()
        if size + len(t) > PAGE_CHARS:
            close()
        cur.append(t)
        size += len(t) + 1
    close()
    return pages, outline


def group(outline: list[dict]) -> list[dict]:
    """An outline for the book machinery: the page's headings grouped into chapters of at least GROUP_PAGES pages
    (level 0), each heading a section of its chapter (level 1). A short page with fewer than 3 chapters is cut by
    pages instead (bookstudy: one chapter for a short article), which is what it should be."""
    heads = sorted(outline, key=lambda o: o["page"])
    if heads and sum(1 for o in heads if o["level"] == 0) == 1 and heads[0]["level"] == 0:
        heads = heads[1:]  # the page's own title above its headings
    top = min((o["level"] for o in heads), default=0)
    heads = [o for o in heads if o["level"] == top]
    out: list[dict] = []
    start = None
    for h in heads:
        if start is None or h["page"] - start >= GROUP_PAGES:
            start = h["page"]
            out.append({"title": h["title"], "page": start, "level": 0})
        out.append({"title": h["title"], "page": h["page"], "level": 1})
    return out


def _fetch(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - http(s) only, checked when the link was added
            data = r.read(MAX_BYTES + 1)
            ctype = r.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001 - any network failure is one message for the learner
        raise LinkError(f"the page could not be fetched ({e})") from e
    if len(data) > MAX_BYTES:
        raise LinkError("the page is larger than 8 MB")
    return data, ctype


def _decode(data: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', data[:4000])
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    try:
        return data.decode(enc, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- videos

def video_id(url: str) -> str | None:
    """The YouTube video id of a link (watch, youtu.be, shorts, embed, live), or None."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host == "youtu.be" or host.endswith(".youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        vid = (parse_qs(u.query).get("v") or [""])[0]
        if not vid:
            m = re.match(r"/(shorts|embed|live|v)/([\w-]+)", u.path)
            vid = m.group(2) if m else ""
    else:
        return None
    return vid if re.fullmatch(r"[\w-]{6,20}", vid or "") else None


def transcript(vid: str) -> list[dict]:
    """The video's captions as [{text, start}] (seconds): English first, else the first language it has."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise LinkError("reading videos needs the package youtube-transcript-api") from e
    api = YouTubeTranscriptApi()
    try:
        listing = api.list(vid)
        try:
            tr = listing.find_transcript(["en", "en-US", "en-GB"])
        except Exception:  # noqa: BLE001 - no English: the first one it has
            tr = next(iter(listing))
        return [{"text": s.text, "start": float(s.start)} for s in tr.fetch()]
    except LinkError:
        raise
    except Exception as e:  # noqa: BLE001
        raise LinkError(f"the video has no captions that can be read ({type(e).__name__})") from e


def video_title(url: str) -> str:
    """The video's title from YouTube's public oEmbed address ("" when it cannot be read)."""
    import json
    from urllib.parse import quote
    try:
        data, _ = _fetch(f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}")
        return " ".join(str(json.loads(data.decode("utf-8")).get("title") or "").split())
    except Exception:  # noqa: BLE001 - the title is a nicety
        return ""


def video_pages(snips: list[dict]) -> tuple[list[str], list[int]]:
    """Pages of about VIDEO_SECONDS of transcript, and the second each page starts at."""
    pages, marks, cur, start = [], [], [], None
    for s in snips:
        t = " ".join(html.unescape(s["text"]).replace("\n", " ").split())
        if not t or t.startswith("[") and t.endswith("]"):  # [Music], [Applause]
            continue
        if start is None:
            start = int(s["start"])
        cur.append(t)
        if s["start"] - start >= VIDEO_SECONDS and t.endswith((".", "?", "!")) or s["start"] - start >= VIDEO_SECONDS * 1.5:
            pages.append(" ".join(cur))
            marks.append(start)
            cur, start = [], None
    if cur:
        pages.append(" ".join(cur))
        marks.append(start or 0)
    return pages, marks


def clock(seconds: int) -> str:
    h, rest = divmod(int(seconds), 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60}:{rest % 60:02d}"


# ---------------------------------------------------------------- the job

def read(jobs, jid: int, d: dict) -> dict:
    """Read a link source into pages; then, when asked, start teaching it."""
    from . import sources
    db: DB = jobs.db
    sid = d["source_id"]
    src = db.one("SELECT * FROM sources WHERE id=?", (sid,))
    if not src or not src["url"]:
        raise LinkError("unknown link")
    db.x("UPDATE sources SET status='reading' WHERE id=?", (sid,))
    url, title, marks = src["url"], "", []
    vid = video_id(url)
    if vid:
        jobs.progress(jid, "reading the video's captions")
        pages, marks = video_pages(transcript(vid))
        outline = []
        title = video_title(url)
    else:
        jobs.progress(jid, "fetching the page")
        data, ctype = _fetch(url)
        if "pdf" in ctype.lower() or data[:5] == b"%PDF-":
            sources.file_path(sid).write_bytes(data)  # a link to a PDF: read it as a PDF
            out = sources.ingest(db, sid, lambda m: jobs.progress(jid, m))
            return _then(db, jobs, d, out)
        title, blocks = page_text(_decode(data, ctype))
        pages, outline = paginate(blocks)
        outline = group(outline)
    words = sum(len(p.split()) for p in pages)
    status = "ready" if words >= 150 else "no_text"
    with db.tx():
        db.conn.execute("DELETE FROM source_pages WHERE source_id=?", (sid,))
        db.conn.execute("DELETE FROM source_fts WHERE source_id=?", (sid,))
        db.conn.executemany("INSERT INTO source_pages(source_id, page, text) VALUES(?,?,?)",
                            [(sid, n + 1, t) for n, t in enumerate(pages)])
        db.conn.executemany("INSERT INTO source_fts(source_id, page, text) VALUES(?,?,?)",
                            [(sid, n + 1, t) for n, t in enumerate(pages) if t])
        default = (urlparse(url).netloc + urlparse(url).path).rstrip("/")[:200]
        new_title = title[:200] if title and src["title"] == default else src["title"]  # a name the learner gave wins
        db.conn.execute("UPDATE sources SET pages=?, status=?, outline=?, title=?, marks=? WHERE id=?",
                        (len(pages), status, dumps(outline), new_title, dumps(marks), sid))
    return _then(db, jobs, d, {"pages": len(pages), "words": words, "status": status, "outline": len(outline)})


def _then(db: DB, jobs, d: dict, out: dict) -> dict:
    if d.get("teach") and out.get("status") == "ready":
        from . import bookstudy
        db.set_meta("last_book", bookstudy.start(db, jobs, d["source_id"]))
    return out


def failed(jobs, jid: int, d: dict) -> None:
    jobs.db.x("UPDATE sources SET status='error' WHERE id=?", (d["source_id"],))


def href(db: DB, sid: str, page: int | None) -> str | None:
    """Where a citation "source:<id>#page=N" of a link source opens: the page, or the video at that time."""
    src = db.one("SELECT url, marks FROM sources WHERE id=?", (sid,))
    if not src or not src["url"]:
        return None
    marks = loads(src["marks"], []) or []
    if page and video_id(src["url"]) and 0 < page <= len(marks):
        sep = "&" if "?" in src["url"] else "?"
        return f'{src["url"]}{sep}t={marks[page - 1]}s'
    return src["url"]
