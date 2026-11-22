"""HTTP API. Local only (binds to 127.0.0.1): the app drives your own logged-in CLIs."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi.responses import Response

from . import actions, backup, bookstudy, dictation, today, graph, lesson, library, planner, practice, progress, providers, runner, session, sources, state, versions
from .db import DB, workspace
from .jobs import Jobs
from .seed import ensure_routes, init_empty


def create_app(db: DB | None = None, jobs: Jobs | None = None, static_dir: Path | None = None) -> FastAPI:
    db = db or DB(workspace() / "study.db")
    if not db.one("SELECT 1 FROM routes LIMIT 1"):
        init_empty(db)  # first run: the learner chooses their own goal or the demo
    ensure_routes(db)
    jobs = jobs or Jobs(db)
    app = FastAPI(title="Deep Study Center")
    app.state.db, app.state.jobs = db, jobs

    @app.get("/api/session/{sid}")
    def get_session(sid: str) -> dict:
        """One study session as the page shows it (SPEC §22)."""
        v = session.view(db, sid)
        if not v:
            raise HTTPException(404, "no such session")
        return v

    @app.get("/api/today")
    def get_today() -> dict:
        """The Today page (SPEC §30): where to continue, what is due, this week."""
        return today.view(db)

    @app.get("/api/book/{bid}")
    def get_book(bid: str) -> dict:
        """One book study: its parts with their ideas and state (SPEC §28)."""
        v = bookstudy.view(db, bid)
        if not v:
            raise HTTPException(404, "no such book")
        return v

    @app.get("/api/drawing/{name}")
    def get_drawing(name: str):
        """A drawing the learner made on the drawing board (SPEC §31)."""
        path = workspace() / "drawings" / name
        if not re.fullmatch(r"[0-9a-f]{16}\.png", name) or not path.exists():
            raise HTTPException(404, "no such drawing")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/graph/node/{nid}")
    def get_node(nid: str) -> dict:
        """One idea for a hover card: where it was learned and how it connects (SPEC §28)."""
        v = graph.node_detail(db, nid)
        if not v:
            raise HTTPException(404, "no such idea")
        return v

    @app.get("/api/practice/{pid}")
    def get_practice(pid: str) -> dict:
        """One practice run as the page shows it (solutions only for closed problems; SPEC §24)."""
        v = practice.view(db, pid)
        if not v:
            raise HTTPException(404, "no such practice")
        return v

    @app.get("/api/practice-due")
    def get_practice_due() -> dict:
        return practice.schedule(db)

    @app.get("/api/graph")
    def get_graph() -> dict:
        """The knowledge graph: every node with the learner's state and goals, and the links (SPEC §21)."""
        return graph.view(db)

    @app.get("/api/state")
    def get_state() -> dict:
        maybe_reflect(db, jobs)
        maybe_refresh_cards(db, jobs)
        backup.maybe_backup(db)
        return state.snapshot(db)

    @app.post("/api/action")
    def post_action(action: dict = Body(...)) -> dict:
        try:
            actions.dispatch(db, jobs, action)
        except actions.ActionError as e:
            raise HTTPException(400, str(e)) from e
        return state.snapshot(db)

    @app.get("/api/lesson/{cid}/diff")
    def lesson_diff(cid: str, a: int, b: int) -> dict:
        """Compare two versions of a lesson: a word-level diff per section with each change's reason."""
        _require_concept(db, cid)
        try:
            return versions.diff(db, cid, a, b)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/api/lesson/{cid}")
    def get_lesson(cid: str) -> dict:
        _require_concept(db, cid)
        return lesson.view(db, cid)

    @app.post("/api/lesson/{cid}/open")
    def open_lesson(cid: str) -> dict:
        _require_concept(db, cid)
        return lesson.open_lesson(db, jobs, cid)

    @app.post("/api/run")
    def run_code(body: dict = Body(...)) -> dict:
        """Run an exercise locally. Returns needs_setup | needs_approval (with the tests) | blocked | ran."""
        cid, item_id, code = body["conceptId"], body["itemId"], body.get("code", "")
        item = actions._card_item(db, cid, item_id)
        if not item or item["kind"] != "code" or item.get("runtime") != "local":
            raise HTTPException(400, "not a local exercise")
        use_docker = runner.mode(db) == "docker"
        if not (runner.docker_ready() if use_docker else runner.is_set_up()):
            return {"status": "needs_setup", "mode": "docker" if use_docker else "local"}
        if body.get("approve"):
            runner.approve(db, cid, item_id, item["tests"])
        if not runner.is_approved(db, cid, item_id, item["tests"]):
            return {"status": "needs_approval", "tests": item["tests"]}
        problems = runner.static_check(f'{code}\n{item["tests"]}')
        if problems:
            return {"status": "blocked", "problems": problems}
        result = runner.run(code, item["tests"], f"{cid}-{item_id}", use_docker=use_docker)
        if progress.record_evidence(db, cid, item_id, 1.0 if result["passed"] else 0.0, angle=body.get("angle")):
            progress.on_finished(db, jobs, cid)
        return {"status": "ran", **result}

    @app.post("/api/activity")
    def activity(body: dict = Body(...)) -> dict:
        """Heartbeat from an open, visible lesson the learner is interacting with (seconds since the last one)."""
        cid, secs = body.get("conceptId", ""), int(body.get("seconds", 0))
        if not 0 < secs <= 120 or not db.one("SELECT 1 FROM concepts WHERE id=?", (cid,)):
            raise HTTPException(400, "bad heartbeat")
        day = datetime.now().date().isoformat()  # local day, to match the plan
        db.x("""INSERT INTO activity VALUES(?,?,?) ON CONFLICT(day, concept_id) DO UPDATE SET seconds = seconds + excluded.seconds""",
             (day, cid, secs))
        return {"ok": True}

    @app.get("/api/plan")
    def get_plan() -> dict:
        return planner.plan_week(db)

    @app.get("/api/plan.ics")
    def get_plan_ics() -> Response:
        return Response(planner.to_ics(planner.plan_week(db)), media_type="text/calendar",
                        headers={"Content-Disposition": 'attachment; filename="study-plan.ics"'})

    @app.get("/api/search")
    def search(q: str = "") -> list[dict]:
        return library.search(db, q)

    @app.post("/api/sources")
    async def upload_source(request: Request, filename: str = "source.pdf", kind: str = "book") -> dict:
        """Upload a PDF (the raw file as the body). Its text is read by a background job."""
        data = await request.body()
        try:
            sid = sources.add(db, data, filename, kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if request.query_params.get("link") == "1" and state.active_goal(db):
            sources.link(db, state.active_goal(db), sid, True)
        jobs.enqueue("ingest_source", f"Read {filename}", {"source_id": sid})
        return state.snapshot(db)

    @app.post("/api/transcribe")
    async def transcribe(request: Request) -> dict:
        """Local dictation (SPEC §27): one recorded phrase as the raw body → its text. The audio is not stored."""
        data = await request.body()
        try:
            return await asyncio.to_thread(dictation.transcribe, db, data, request.query_params.get("lang"))
        except dictation.DictationError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/sources/{sid}/file")
    def source_file(sid: str):
        """The PDF itself, so a citation link can open it at a page (…/file#page=42)."""
        if not db.one("SELECT 1 FROM sources WHERE id=?", (sid,)) or not sources.file_path(sid).exists():
            raise HTTPException(404, "no such source")
        return FileResponse(sources.file_path(sid), media_type="application/pdf",
                            headers={"Content-Disposition": "inline"})

    @app.get("/api/export/anki")
    def anki() -> FileResponse:
        path = library.export_anki(db)
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    @app.get("/api/providers")
    def get_providers() -> list[dict]:
        return providers.status()

    if static_dir and static_dir.exists():  # serve the built frontend (dsc serve)
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app


REFLECT_EVERY = timedelta(days=7)
REFLECT_MIN_FEEDBACK = 3


def maybe_reflect(db: DB, jobs: Jobs) -> None:
    """Weekly reflection: once a week, if there's been enough feedback since the last one."""
    last = db.meta("last_reflection")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < REFLECT_EVERY:
        return
    since = db.one("SELECT COUNT(*) AS n FROM feedback WHERE deleted = 0 AND ts > ?", (last or "",))["n"]
    if since >= REFLECT_MIN_FEEDBACK and not jobs.active("reflect"):
        jobs.enqueue("reflect", "Weekly reflection", {})


REFRESH_AFTER = timedelta(days=30)
REFRESH_PER_DAY = 3


def maybe_refresh_cards(db: DB, jobs: Jobs) -> None:
    """Card refresh: at most a few cards a day, oldest first, only cards not reviewed in 30 days."""
    if db.meta("auto_refresh", "1") != "1" or jobs.active("refresh_card") or jobs.active("research_module"):
        return
    today = datetime.now(timezone.utc).date().isoformat()
    if db.one("SELECT COUNT(*) AS n FROM jobs WHERE kind='refresh_card' AND created_at >= ?", (today,))["n"] >= REFRESH_PER_DAY:
        return
    cutoff = (datetime.now(timezone.utc) - REFRESH_AFTER).isoformat()
    row = db.one("""SELECT c.concept_id, k.title FROM cards c JOIN concepts k ON k.id = c.concept_id
                    WHERE c.version = (SELECT MAX(version) FROM cards WHERE concept_id = c.concept_id)
                      AND COALESCE(c.refreshed_at, c.checked_at) < ?
                      AND NOT EXISTS (SELECT 1 FROM card_proposals p WHERE p.concept_id = c.concept_id AND p.status = 'pending')
                    ORDER BY COALESCE(c.refreshed_at, c.checked_at) LIMIT 1""", (cutoff,))
    if row:
        jobs.enqueue("refresh_card", f"Check {row['title']} for updates", {"concept_id": row["concept_id"]})


def _require_concept(db: DB, cid: str) -> None:
    if not db.one("SELECT 1 FROM concepts WHERE id=?", (cid,)):
        raise HTTPException(404, "no such lesson")
