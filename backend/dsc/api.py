"""HTTP API. Local only (binds to 127.0.0.1): the app drives your own logged-in CLIs."""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import actions, lesson, providers, state
from .db import DB, workspace
from .jobs import Jobs
from .seed import seed_demo


def create_app(db: DB | None = None, jobs: Jobs | None = None, static_dir: Path | None = None) -> FastAPI:
    db = db or DB(workspace() / "study.db")
    if not db.one("SELECT 1 FROM routes LIMIT 1"):
        seed_demo(db)  # first run: start from the demo roadmap
    jobs = jobs or Jobs(db)
    app = FastAPI(title="Deep Study Center")
    app.state.db, app.state.jobs = db, jobs

    @app.get("/api/state")
    def get_state() -> dict:
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


def _require_concept(db: DB, cid: str) -> None:
    if not db.one("SELECT 1 FROM concepts WHERE id=?", (cid,)):
        raise HTTPException(404, "no such lesson")
