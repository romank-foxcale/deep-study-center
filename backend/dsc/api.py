"""HTTP API. Local only (binds to 127.0.0.1): the app drives your own logged-in CLIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi.responses import Response

from . import actions, lesson, library, planner, progress, providers, runner, state
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
        maybe_refresh_cards(db, jobs)
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

    @app.post("/api/run")
    def run_code(body: dict = Body(...)) -> dict:
        """Run an exercise locally. Returns needs_setup | needs_approval (with the tests) | blocked | ran."""
        cid, item_id, code = body["conceptId"], body["itemId"], body.get("code", "")
        item = actions._card_item(db, cid, item_id)
        if not item or item["kind"] != "code" or item.get("runtime") != "local":
            raise HTTPException(400, "not a local exercise")
        if not runner.is_set_up():
            return {"status": "needs_setup"}
        if body.get("approve"):
            runner.approve(db, cid, item_id, item["tests"])
        if not runner.is_approved(db, cid, item_id, item["tests"]):
            return {"status": "needs_approval", "tests": item["tests"]}
        problems = runner.static_check(f'{code}\n{item["tests"]}')
        if problems:
            return {"status": "blocked", "problems": problems}
        result = runner.run(code, item["tests"], f"{cid}-{item_id}")
        progress.record_evidence(db, cid, item_id, 1.0 if result["passed"] else 0.0, angle=body.get("angle"))
        return {"status": "ran", **result}

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
    since = db.one("SELECT COUNT(*) AS n FROM feedback WHERE ts > ?", (last or "",))["n"]
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
