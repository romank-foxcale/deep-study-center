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
  hours REAL NOT NULL DEFAULT 5, profile TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  layout TEXT NOT NULL DEFAULT 'list');
CREATE TABLE IF NOT EXISTS tracks (
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, ord INTEGER NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  pos TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS modules (
  id TEXT PRIMARY KEY, track_id TEXT NOT NULL, ord INTEGER NOT NULL, title TEXT NOT NULL,
  research TEXT NOT NULL DEFAULT 'outline', planned INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
  known INTEGER NOT NULL DEFAULT 0, seq INTEGER NOT NULL DEFAULT 0, requires TEXT NOT NULL DEFAULT '[]',
  done_when TEXT NOT NULL DEFAULT '');
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
-- reviews and node_reviews: the old review schedule. Kept so old workspaces open; not used (SPEC §48: no schedule).
CREATE TABLE IF NOT EXISTS reviews (
  concept_id TEXT PRIMARY KEY, card TEXT NOT NULL, due TEXT NOT NULL, learned_at TEXT NOT NULL);

-- Explain-back answers and the grader's verdicts (graded evidence goes to `evidence`).
CREATE TABLE IF NOT EXISTS gradings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, item_id TEXT NOT NULL,
  answer TEXT NOT NULL, status TEXT NOT NULL, score REAL, feedback TEXT, missing TEXT, followup TEXT);

-- Placement diagnostic: a question bank per goal (one row per module) and the answers.
-- The knowledge graph (SPEC §21): one node per idea; concepts (lessons in a goal) point to nodes; links = reasoning.
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, statement TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'concept',
  created_at TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'concept');
CREATE TABLE IF NOT EXISTS concept_nodes (concept_id TEXT PRIMARY KEY, node_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS concept_nodes_node ON concept_nodes(node_id);
CREATE TABLE IF NOT EXISTS links (
  src TEXT NOT NULL, dst TEXT NOT NULL, why TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT '', PRIMARY KEY (src, dst));
CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(node_id UNINDEXED, text);
-- Recall practice (SPEC §24): problems over ideas, judged from the learner's thinking.
CREATE TABLE IF NOT EXISTS practices (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, node_ids TEXT NOT NULL DEFAULT '[]', own TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 1, count INTEGER NOT NULL DEFAULT 5,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS practice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, practice_id TEXT NOT NULL, problem TEXT NOT NULL, status TEXT NOT NULL,
  hints INTEGER NOT NULL DEFAULT 0, chunks TEXT NOT NULL DEFAULT '[]', score REAL, created_at TEXT NOT NULL, ended_at TEXT);
CREATE TABLE IF NOT EXISTS node_reviews (node_id TEXT PRIMARY KEY, card TEXT NOT NULL, due TEXT NOT NULL, last_at TEXT NOT NULL);
-- Study sessions (SPEC §22): "teach me X" with or without a goal.
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, ideas TEXT NOT NULL DEFAULT '[]',
  plan TEXT NOT NULL DEFAULT '[]', current INTEGER NOT NULL DEFAULT 0, source_ids TEXT NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, idea_key TEXT NOT NULL, phase TEXT NOT NULL,
  round INTEGER NOT NULL DEFAULT 0, ord INTEGER NOT NULL DEFAULT 0, item TEXT NOT NULL, choice INTEGER,
  answered INTEGER NOT NULL DEFAULT 0, correct INTEGER, thinking TEXT NOT NULL DEFAULT '', confidence REAL,
  answered_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session_nodes (
  session_id TEXT NOT NULL, node_id TEXT NOT NULL, created INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (session_id, node_id));
-- The probe (SPEC §20): rounds of quick questions an agent picks from earlier answers, then an assessment.
CREATE TABLE IF NOT EXISTS probe_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, round INTEGER NOT NULL, ord INTEGER NOT NULL,
  module_id TEXT NOT NULL, item TEXT NOT NULL, choice INTEGER, answered INTEGER NOT NULL DEFAULT 0, correct INTEGER,
  thinking TEXT NOT NULL DEFAULT '', confidence REAL, answered_at TEXT);
CREATE TABLE IF NOT EXISTS probe_results (
  goal_id TEXT PRIMARY KEY, ts TEXT NOT NULL, assessment TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0);
-- The old placement quiz (before the probe); kept so old data stays readable.
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

-- Card refresh: proposed new versions of a card, shown as a diff for the learner to approve.
CREATE TABLE IF NOT EXISTS card_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, base_version INTEGER NOT NULL,
  body TEXT NOT NULL, summary TEXT NOT NULL, changes TEXT NOT NULL, status TEXT NOT NULL);

-- Time actually spent per day and concept (from page activity heartbeats), for plan vs. actual.
CREATE TABLE IF NOT EXISTS activity (
  day TEXT NOT NULL, concept_id TEXT NOT NULL, seconds INTEGER NOT NULL, PRIMARY KEY (day, concept_id));

-- Lesson versions: immutable snapshots of one lesson's prose. The head is the version the page shows;
-- revert moves the head and loses nothing. fingerprint = (card_version, style, angles) it was written for.
CREATE TABLE IF NOT EXISTS lesson_versions (
  concept_id TEXT NOT NULL, version INTEGER NOT NULL, ts TEXT NOT NULL, parent INTEGER,
  card_version INTEGER NOT NULL, playbook_version INTEGER NOT NULL, style TEXT NOT NULL, angles TEXT NOT NULL,
  sections TEXT NOT NULL, source TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', feedback_ids TEXT NOT NULL DEFAULT '[]',
  changes TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (concept_id, version));
-- chosen = the learner applied feedback or restored a version: never re-rendered silently on open.
CREATE TABLE IF NOT EXISTS lesson_heads (
  concept_id TEXT PRIMARY KEY, version INTEGER NOT NULL, chosen INTEGER NOT NULL DEFAULT 0);
-- A revert away from applied feedback: "the way this feedback was applied did not work".
CREATE TABLE IF NOT EXISTS lesson_reverts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, concept_id TEXT NOT NULL, from_version INTEGER NOT NULL,
  to_version INTEGER NOT NULL, feedback_ids TEXT NOT NULL, changes TEXT NOT NULL);

-- Lesson guidelines distilled from the learner's feedback (SPEC §12); one row per version.
CREATE TABLE IF NOT EXISTS guidelines (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, items TEXT NOT NULL, source TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '');

-- Writing one learner's lesson in steps (SPEC §14): the planner's plan, the graphs and quiz questions made for this
-- learner, and the reviewer's findings, per (lesson, card version). The card itself never changes.
CREATE TABLE IF NOT EXISTS lesson_plans (
  concept_id TEXT NOT NULL, card_version INTEGER NOT NULL, ts TEXT NOT NULL, plan TEXT NOT NULL DEFAULT '{}',
  assets TEXT NOT NULL DEFAULT '{}', review TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (concept_id, card_version));

-- The learner's own sources (SPEC §17): PDFs in workspace/sources/<id>.pdf, their text per page and a full-text
-- index over it, and which goals use which source.
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'book',
  filename TEXT NOT NULL DEFAULT '', bytes INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'reading', outline TEXT NOT NULL DEFAULT '[]', added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_pages (
  source_id TEXT NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY (source_id, page));
CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(source_id UNINDEXED, page UNINDEXED, text);
CREATE TABLE IF NOT EXISTS goal_sources (goal_id TEXT NOT NULL, source_id TEXT NOT NULL, PRIMARY KEY (goal_id, source_id));
-- Book goals (SPEC §18): the 80/20 cut of the chosen sources. rank core | supporting | skip; status kept | cut | restored.
-- Book study (SPEC §28): one PDF mapped into its own idea graph, then studied one part (section) at a time.
CREATE TABLE IF NOT EXISTS books (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL, status TEXT NOT NULL,
  chapters_done INTEGER NOT NULL DEFAULT 0, chapters INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS book_parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, ord INTEGER NOT NULL, chapter INTEGER NOT NULL,
  chapter_title TEXT NOT NULL, title TEXT NOT NULL, page_from INTEGER NOT NULL, page_to INTEGER NOT NULL,
  summary TEXT NOT NULL DEFAULT '', session_id TEXT, practice_id TEXT, status TEXT NOT NULL DEFAULT 'todo');
CREATE TABLE IF NOT EXISTS book_nodes (
  book_id TEXT NOT NULL, node_id TEXT NOT NULL, part_id INTEGER NOT NULL, key TEXT NOT NULL,
  pages TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL DEFAULT 0, ord INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (book_id, node_id));
-- Book study v2 (SPEC §31): a chapter's summary and its module in the book's hidden goal (lessons = book_parts rows).
CREATE TABLE IF NOT EXISTS book_chapters (
  book_id TEXT NOT NULL, chapter INTEGER NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  page_from INTEGER NOT NULL, page_to INTEGER NOT NULL, sections TEXT NOT NULL DEFAULT '[]', module_id TEXT,
  mapped INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'chapter', PRIMARY KEY (book_id, chapter));
-- The tutor's reading of a learner's reasoning on one answer (SPEC §32): body = parts marked right/partly/wrong,
-- the wrong assumption, where following it breaks, and how it really works.
CREATE TABLE IF NOT EXISTS reasoning_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, evidence_id INTEGER NOT NULL, concept_id TEXT NOT NULL,
  item_id TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL DEFAULT '{}');
-- Formula notes (SPEC §33): per lesson and formula (TeX without spaces): name, meaning, symbols, graph ideas.
CREATE TABLE IF NOT EXISTS formula_notes (
  concept_id TEXT NOT NULL, key TEXT NOT NULL, tex TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (concept_id, key));
-- Formula lessons (SPEC §34): a lesson about one formula, made from a hover card; its forms (the ways lessons write it).
CREATE TABLE IF NOT EXISTS formula_lessons (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, source_concept TEXT NOT NULL, preferred TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS formula_forms (
  formula_id TEXT NOT NULL, key TEXT NOT NULL, tex TEXT NOT NULL, concept_id TEXT NOT NULL, added_at TEXT NOT NULL,
  PRIMARY KEY (formula_id, key));
-- The formula tree (SPEC §37): a formula's building blocks (notations, simpler formulas, ideas), each matched to a
-- formula lesson or graph idea of the learner (ref), or basic.
CREATE TABLE IF NOT EXISTS formula_blocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, formula_id TEXT NOT NULL, ord INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  tex TEXT NOT NULL DEFAULT '', meaning TEXT NOT NULL DEFAULT '', ref_kind TEXT, ref TEXT, basic INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
-- The derivation graph (SPEC §40): what a formula with no lesson is built from, one level down, found when the learner
-- opens it ("block:<name>" node). Formula lessons keep their blocks in formula_blocks.
CREATE TABLE IF NOT EXISTS formula_parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL, ord INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  tex TEXT NOT NULL DEFAULT '', meaning TEXT NOT NULL DEFAULT '', basic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS formula_opened (node TEXT PRIMARY KEY, at TEXT NOT NULL);
-- The fields of mathematics of each formula, by its form (SPEC §41): a JSON list of field ids, most important first.
CREATE TABLE IF NOT EXISTS formula_fields (key TEXT PRIMARY KEY, fields TEXT NOT NULL, at TEXT NOT NULL);
-- The lesson plan graph (SPEC §42): a book lesson is planned and approved before it is written. One row per version;
-- status planning | ready | approved | failed. nodes/edges are JSON. The learner's notes on a plan are kept apart;
-- used_in is the version that used them (NULL: not used yet).
CREATE TABLE IF NOT EXISTS lesson_graphs (
  concept_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, approach TEXT NOT NULL DEFAULT '',
  goal TEXT NOT NULL DEFAULT '', nodes TEXT NOT NULL DEFAULT '[]', edges TEXT NOT NULL DEFAULT '[]',
  error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, approved_at TEXT, PRIMARY KEY (concept_id, version));
-- The steps of a planned lesson as ideas on the map (SPEC §46): one node per taught foundation or step;
-- plan_maps keeps which card version of each step lesson is mapped.
-- own = 0: the step is an idea already on the map (the plan linked it), so no node was made for it.
CREATE TABLE IF NOT EXISTS plan_nodes (
  concept_id TEXT NOT NULL, node_key TEXT NOT NULL, node_id TEXT NOT NULL, section_id TEXT NOT NULL, ord INTEGER NOT NULL,
  own INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (concept_id, node_key));
CREATE TABLE IF NOT EXISTS plan_maps (concept_id TEXT PRIMARY KEY, card_version INTEGER NOT NULL);
-- The formula flow of a formula page (SPEC §52): status building | ready | failed; spec is JSON (formula_flow.py).
CREATE TABLE IF NOT EXISTS formula_flows (
  concept_id TEXT PRIMARY KEY, status TEXT NOT NULL, spec TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
-- Gaps on the map (SPEC §51): ideas missing on the arrow a -> b. status open | filled | dismissed; ideas is JSON
-- [{title, says, status open|added, nodeId}]; busy = 1 while the agent looks at this gap again.
CREATE TABLE IF NOT EXISTS gaps (
  id TEXT PRIMARY KEY, a TEXT NOT NULL, b TEXT NOT NULL, status TEXT NOT NULL, ideas TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, busy INTEGER NOT NULL DEFAULT 0);
-- One cell per idea (SPEC §49): the one lesson of an idea that has lessons from several sources.
CREATE TABLE IF NOT EXISTS cell_homes (node_id TEXT PRIMARY KEY, concept_id TEXT NOT NULL, at TEXT NOT NULL);
-- Step lessons (SPEC §43): the learner's prediction before a step (not graded evidence: guessing is the point).
CREATE TABLE IF NOT EXISTS step_predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, concept_id TEXT NOT NULL, section_id TEXT NOT NULL, choice INTEGER NOT NULL,
  correct INTEGER NOT NULL, thinking TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lesson_graph_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, concept_id TEXT NOT NULL, version INTEGER NOT NULL, node TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', at TEXT NOT NULL, used_in INTEGER);
CREATE TABLE IF NOT EXISTS book_cuts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, ord INTEGER NOT NULL, source_id TEXT NOT NULL,
  chapter TEXT NOT NULL, pages TEXT NOT NULL DEFAULT '', rank TEXT NOT NULL, why TEXT NOT NULL DEFAULT '',
  module_id TEXT, status TEXT NOT NULL, restored_at TEXT, concept_id TEXT);

CREATE TABLE IF NOT EXISTS routes (
  role TEXT PRIMARY KEY, ord INTEGER NOT NULL, description TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, status TEXT NOT NULL, label TEXT NOT NULL,
  input TEXT NOT NULL, output TEXT, error TEXT, progress TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""

MIGRATIONS = [
    ("evidence", "score", "REAL"),                         # soft evidence (0..1), e.g. graded explain-back
    ("evidence", "thinking", "TEXT NOT NULL DEFAULT ''"),  # the learner's raw thinking on this answer (typed or dictated)
    ("evidence", "confidence", "REAL"),                    # how sure the learner was (0..1); None = not given
    ("gradings", "confidence", "REAL"),
    ("placement_answers", "thinking", "TEXT NOT NULL DEFAULT ''"),
    ("placement_answers", "confidence", "REAL"),
    ("modules", "known", "INTEGER NOT NULL DEFAULT 0"),    # placement showed the learner knows it
    ("goals", "layout", "TEXT NOT NULL DEFAULT 'list'"),   # list (classic roadmap) | ohtani (9x9 Mandala grid)
    ("goals", "kind", "TEXT NOT NULL DEFAULT 'goal'"),     # goal | book (the 80/20 core of chosen sources, SPEC §18)
    ("tracks", "pos", "TEXT NOT NULL DEFAULT ''"),         # ohtani: grid block of this area (TL..ML) or C (merges)
    ("modules", "seq", "INTEGER NOT NULL DEFAULT 0"),      # global learning order across tracks (0 = track order)
    ("modules", "requires", "TEXT NOT NULL DEFAULT '[]'"), # module ids that must be learned first (ohtani merges)
    ("modules", "done_when", "TEXT NOT NULL DEFAULT ''"),  # the step's concrete completion check
    ("cards", "refreshed_at", "TEXT"),                     # last time a refresh job reviewed this version
    ("feedback", "kind", "TEXT NOT NULL DEFAULT 'me'"),    # lesson | me | fact (SPEC §11)
    ("feedback", "kind_source", "TEXT NOT NULL DEFAULT 'auto'"),  # auto (rules) | agent | learner
    ("feedback", "signal_ids", "TEXT NOT NULL DEFAULT '[]'"),     # playbook signals this item added (voided on edit/delete)
    ("feedback", "updated_at", "TEXT"),                    # last edit
    ("feedback", "deleted", "INTEGER NOT NULL DEFAULT 0"),
    ("feedback", "done_note", "TEXT"),                     # handled at once (e.g. section switched), nothing to apply
    ("feedback", "routed_at", "TEXT"),
    ("feedback", "angle", "TEXT"),
    ("feedback", "ref", "TEXT"),                           # the part it is about: {kind: text|formula|viz, quote, sectionId}                         # the section's angle when the feedback was given                     # a fact claim sent to the card check
    ("sessions", "probe_start", "TEXT NOT NULL DEFAULT ''"),  # the probe's advice where teaching starts (SPEC §26)
    ("sessions", "book_part", "INTEGER"),                  # the book part this session studies (SPEC §28)
    ("gradings", "drawing", "TEXT"),                       # the learner's drawing board (a PNG under workspace/drawings)
    ("books", "goal_id", "TEXT"),                          # v2: the book's hidden goal (goals.kind = 'bookstudy')
    ("books", "version", "INTEGER NOT NULL DEFAULT 1"),    # 1 = parts taught as study sessions; 2 = chapters of saved lessons
    ("book_parts", "concept_id", "TEXT"),                  # v2: the lesson (concept) this part is
    ("book_parts", "ideas", "TEXT NOT NULL DEFAULT '[]'"), # v2: the lesson's key ideas
    ("book_chapters", "kind", "TEXT NOT NULL DEFAULT 'chapter'"),
    ("reasoning_reviews", "session_item_id", "INTEGER"),   # a study-session answer (then concept_id is the session id)
    ("gradings", "review", "TEXT"),                         # the grader's reading of the explain-back (parts, assumption, …)
    ("formula_lessons", "meaning", "TEXT NOT NULL DEFAULT ''"),  # what the formula says (from its note or block)
    ("formula_lessons", "kind", "TEXT NOT NULL DEFAULT 'formula'"),  # formula | notation (a short notation lesson)
    ("formula_lessons", "blocks_at", "TEXT"),              # when its building blocks were found
    ("formula_notes", "kind", "TEXT NOT NULL DEFAULT 'idea'"),  # idea | step (a step of a derivation: neutral frame)
    ("formula_notes", "formula_id", "TEXT"),               # the formula lesson this formula is (any form)
    ("formula_notes", "matched_at", "TEXT"),
    ("sources", "sha256", "TEXT NOT NULL DEFAULT ''"),        # the file's hash, to find a duplicate upload
    ("sources", "url", "TEXT NOT NULL DEFAULT ''"),           # a link source (web page, video): no file
    ("sources", "marks", "TEXT NOT NULL DEFAULT '[]'"),       # a video: the second each page starts at (SPEC §47)
    ("books", "plan", "INTEGER NOT NULL DEFAULT 1"),         # the lesson plan rule the book was mapped with (2: one idea per lesson)               # last match against the formula lessons  # chapter | reference (glossary, reading list: no lessons)
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
