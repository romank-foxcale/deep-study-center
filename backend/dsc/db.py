"""Workspace and SQLite store.

The workspace (default ``~/DeepStudy``, override with ``DSC_WORKSPACE``) holds ``study.db`` and
one folder per agent job. Logs (signals, evidence, feedback) are append-only; everything the UI
shows about the learner is derived from them by replay (see ``engine``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, why TEXT NOT NULL DEFAULT '', done TEXT NOT NULL DEFAULT '',
  hours REAL NOT NULL DEFAULT 5, profile TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tracks (
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, ord INTEGER NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS modules (
  id TEXT PRIMARY KEY, track_id TEXT NOT NULL, ord INTEGER NOT NULL, title TEXT NOT NULL,
  research TEXT NOT NULL DEFAULT 'outline', planned INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY, module_id TEXT NOT NULL, ord INTEGER NOT NULL, title TEXT NOT NULL,
  objective TEXT NOT NULL, minutes INTEGER NOT NULL DEFAULT 20, prereqs TEXT NOT NULL DEFAULT '[]',
  p_init REAL NOT NULL DEFAULT 0.1, started INTEGER NOT NULL DEFAULT 0);

-- Knowledge center #1: versioned, learner-independent cards. body = JSON (see SPEC §2.1).
CREATE TABLE IF NOT EXISTS cards (
  concept_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, fact_check TEXT NOT NULL,
  checked_at TEXT NOT NULL, PRIMARY KEY (concept_id, version));

-- Knowledge center #2: lesson prose per (card version, section, angle, style), reused across renders.
CREATE TABLE IF NOT EXISTS prose (
  concept_id TEXT NOT NULL, card_version INTEGER NOT NULL, section_id TEXT NOT NULL, angle TEXT NOT NULL,
  style TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (concept_id, card_version, section_id, angle, style));
CREATE TABLE IF NOT EXISTS renditions (
  concept_id TEXT PRIMARY KEY, card_version INTEGER NOT NULL, playbook_version INTEGER NOT NULL,
  style TEXT NOT NULL, section_angles TEXT NOT NULL DEFAULT '{}', pinned TEXT NOT NULL DEFAULT '{}',
  studied INTEGER NOT NULL DEFAULT 0);

-- Append-only learner logs.
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, dimension TEXT NOT NULL,
  value TEXT NOT NULL, delta REAL NOT NULL DEFAULT 0, evidence REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '', bumps INTEGER NOT NULL DEFAULT 1, voided INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, item_id TEXT NOT NULL,
  kind TEXT NOT NULL, choice INTEGER, correct INTEGER NOT NULL, angle TEXT, voided INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, section_id TEXT,
  tags TEXT NOT NULL, text TEXT NOT NULL, effects TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, quote TEXT, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS diffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, goal_id TEXT NOT NULL, reason TEXT NOT NULL,
  changes TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, role TEXT NOT NULL,
  text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (
  concept_id TEXT PRIMARY KEY, card TEXT NOT NULL, due TEXT NOT NULL, learned_at TEXT NOT NULL);

-- Explain-back answers and the grader's verdicts (graded evidence goes to `evidence`).
CREATE TABLE IF NOT EXISTS gradings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, item_id TEXT NOT NULL,
  answer TEXT NOT NULL, status TEXT NOT NULL, score REAL, feedback TEXT, missing TEXT, followup TEXT);

-- Placement diagnostic: a question bank per goal (one row per module) and the answers.
CREATE TABLE IF NOT EXISTS placement_items (
  goal_id TEXT NOT NULL, module_id TEXT NOT NULL, item TEXT NOT NULL, PRIMARY KEY (goal_id, module_id));
CREATE TABLE IF NOT EXISTS placement_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, goal_id TEXT NOT NULL, module_id TEXT NOT NULL,
  choice INTEGER, correct INTEGER NOT NULL);

-- Weekly reflections over the feedback log, with proposals the learner accepts or rejects.
CREATE TABLE IF NOT EXISTS reflections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, summary TEXT NOT NULL, proposals TEXT NOT NULL,
  source TEXT NOT NULL);

-- Local runner: the learner approved this exact test code (by hash) before it first ran.
CREATE TABLE IF NOT EXISTS runner_approvals (
  concept_id TEXT NOT NULL, item_id TEXT NOT NULL, tests_hash TEXT NOT NULL, approved_at TEXT NOT NULL,
  PRIMARY KEY (concept_id, item_id, tests_hash));

-- Shared card library: fact-checked cards promoted for reuse across goals (key = slug of the title).
CREATE TABLE IF NOT EXISTS library (
  key TEXT PRIMARY KEY, title TEXT NOT NULL, objective TEXT NOT NULL, body TEXT NOT NULL, version INTEGER NOT NULL,
  source_concept TEXT NOT NULL, source_goal TEXT NOT NULL, promoted_at TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS routes (
  role TEXT PRIMARY KEY, ord INTEGER NOT NULL, description TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, status TEXT NOT NULL, label TEXT NOT NULL,
  input TEXT NOT NULL, output TEXT, error TEXT, progress TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""

MIGRATIONS = [
    ("evidence", "score", "REAL"),                         # soft evidence (0..1), e.g. graded explain-back
    ("modules", "known", "INTEGER NOT NULL DEFAULT 0"),    # placement showed the learner knows it
]


def workspace() -> Path:
    path = Path(os.environ.get("DSC_WORKSPACE") or Path.home() / "DeepStudy").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def loads(s: str | None, default: Any = None) -> Any:
    return default if s is None else json.loads(s)


class DB:
    """Thin wrapper: one connection, serialized by a lock (API thread + job workers)."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Additive column migrations for workspaces created by older versions."""
        for table, column, ddl in MIGRATIONS:
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def q(self, sql: str, args: tuple | list = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple | list = ()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple | list = ()) -> int:
        with self.lock:
            return self.conn.execute(sql, args).lastrowid or 0

    def tx(self):
        """``with db.tx():`` runs the block in one transaction."""
        return _Tx(self)

    def meta(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.x("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


class _Tx:
    def __init__(self, db: DB):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        self.db.conn.execute("BEGIN")
        return self.db

    def __exit__(self, exc_type, *_):
        try:
            self.db.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db.lock.release()
