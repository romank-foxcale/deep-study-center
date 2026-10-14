"""Workspace backups: a consistent copy of study.db (SQLite online backup API), daily, keeping the
newest 14. Restore = stop the server and copy a backup over study.db."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import DB, now, workspace

KEEP = 14
EVERY = timedelta(hours=24)


def folder() -> Path:
    f = workspace() / "backups"
    f.mkdir(parents=True, exist_ok=True)
    return f


def backup_now(db: DB) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = folder() / f"study-{stamp}.db"
    with db.lock:
        dst = sqlite3.connect(target)
        try:
            db.conn.backup(dst)
        finally:
            dst.close()
    db.set_meta("last_backup", now())
    for old in sorted(folder().glob("study-*.db"))[:-KEEP]:
        old.unlink()
    return target


def maybe_backup(db: DB) -> Path | None:
    last = db.meta("last_backup")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < EVERY:
        return None
    return backup_now(db)


def listing() -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size,
             "at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
            for p in sorted(folder().glob("study-*.db"), reverse=True)]
