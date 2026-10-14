"""HTTP API. Local only (binds to 127.0.0.1): the app drives your own logged-in CLIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import actions, lesson, providers, state
from .db import DB, workspace
from .jobs import Jobs
from .seed import ensure_routes, seed_demo


def create_app(db: DB | None = None, jobs: Jobs | None = None, static_dir: Path | None = None) -> FastAPI:
    db = db or DB(workspace() / "study.db")
    if not db.one("SELECT 1 FROM routes LIMIT 1"):
        seed_demo(db)  # first run: start from the demo roadmap
    ensure_routes(db)
    jobs = jobs or Jobs(db)
    app = FastAPI(title="Deep Study Center")
    app.state.db, app.state.jobs = db, jobs

    @app.get("/api/state")
    def get_state() -> dict:
        maybe_reflect(db, jobs)
        return state.snapshot(db)

    @app.post("/api/action")
    def post_action(action: dict = Body(...)) -> dict:
        try:
            actions.dispatch(db, jobs, action)
        except actions.ActionError as e:
            raise HTTPException(400, str(e)) from e
        return state.snapshot(db)

    @app.get("/api/lesson/{cid}")
    def get_lesson(cid: str) -> dict:
        _require_concept(db, cid)
        return lesson.view(db, cid)

    @app.post("/api/lesson/{cid}/open")
    def open_lesson(cid: str) -> dict:
        _require_concept(db, cid)
        return lesson.open_lesson(db, jobs, cid)

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
    since = db.one("SELECT COUNT(*) AS n FROM feedback WHERE ts > ?", (last or "",))["n"]
    if since >= REFLECT_MIN_FEEDBACK and not jobs.active("reflect"):
        jobs.enqueue("reflect", "Weekly reflection", {})


def _require_concept(db: DB, cid: str) -> None:
    if not db.one("SELECT 1 FROM concepts WHERE id=?", (cid,)):
        raise HTTPException(404, "no such lesson")
