# Deep Study Center

A personal study platform for big, multi-step goals, like "become a world-class AI researcher
and engineer". You state the goal in a conversation; agents research it into a concise source
knowledge base; every lesson is rendered *for you*, and every piece of feedback reshapes the lessons
after it (and offers to refresh the ones before it).

Two knowledge centers:

1. **Source KB**: canonical, fact-checked, versioned concept cards (the same for everyone).
2. **Learner lens**: your profile, teaching playbook, notes, feedback log, mastery evidence, and
   your personal *renditions* of each lesson, which go stale and get re-rendered when your playbook changes.

It runs locally and uses your own Claude / ChatGPT / Cursor subscriptions through their CLIs.
See [docs/SPEC.md](docs/SPEC.md) for the full design and the decisions behind it.

## Status

**Milestone 5** (current):

- **This week**: one plan across all your goals. Your weekly hours are split by goal; each study day starts with the
  spaced reviews due, then lessons in roadmap order from the goal furthest behind its share, with a confirmation
  review the day after each lesson. Set hours, study days and a start time; export the week to your calendar (.ics).
  Today's plan is on Home.
- **Card refresh**: cards not reviewed in 30 days are re-checked against the web (a few a day, or on demand per card)
  for errors, outdated claims and better sources. A proposed update is shown as a diff; approving it creates the
  next card version, which is fact-checked again, and your lessons re-render. Nothing changes without approval.

**Milestone 4** added:

- **Interactive visuals**: built-in widgets (draggable vectors with tip-to-tail sums, linear-combination sliders,
  a 2x2 matrix transforming the plane, function plots with parameter sliders). Agents place them in lessons as a
  JSON spec that the backend validates; no agent-written code runs in your browser.
- **Local Python runner** for exercises that need PyTorch: a separate environment in your workspace (set up once from
  Settings), and you review each exercise's test code before it first runs. A static check blocks networking,
  process, file-system and introspection code. It is not a sandbox; see `backend/dsc/runner.py`.
- **Shared card library**: promote fact-checked cards; research for any goal reuses them instead of rewriting.
- **Search** across your notes, lessons and source cards (SQLite FTS5).
- **Anki export** of the questions and explain-back prompts of the concepts you've learned.

**Milestone 3** added, on top of the milestone-2 backend:

- **Explain-back**: lessons ask you to explain an idea in your own words; an independent grader agent scores it
  against a hidden rubric (1 / 0.5 / 0, with what's missing and a follow-up question). Passing it is part of the
  mastery gate, and partial credit counts as soft evidence.
- **Placement**: a quiz over the roadmap outline (one question per module, binary search per track, "I don't know"
  welcome) proposes compressing the modules you already know; you approve it on the roadmap.
- **Research ahead**: the next module is researched automatically while you work on the current one
  (Settings → Research to turn it off).
- **Weekly reflection**: once a week, after a few pieces of feedback, an agent reviews your feedback log, practice
  results and notes, writes a short summary, and proposes playbook changes you accept or reject.
- **Codex and Cursor adapters**: `codex exec` (structured output via `--output-schema`) and the Cursor CLI
  (`cursor-agent` / `agent`, JSON parsed from the result). Both strip API-key variables so your plan is used.
  Not yet tested against the real CLIs.
- **CI**: backend tests and the frontend type-check, lint and build run on every push and pull request.

Milestone 2 built the backend: the deterministic engine (BKT, FSRS, playbook replay), the SQLite workspace
(`~/DeepStudy`, override with `DSC_WORKSPACE`), and agent jobs on your own subscription for research, roadmap
outlines, lesson rendering, tutor chat, roadmap reviews and fact-checks, each with an offline fallback.

The app starts from a demo roadmap (AI researcher & engineer). "Vectors" has pre-written prose; every other lesson is
written for you on first open. *+ New goal* runs the real interview → outline → placement → research pipeline.

## Run

Requires Python 3.11+, Node 20+, and the [Claude Code](https://code.claude.com) CLI logged in with your subscription
(`claude` on PATH). Optional: `codex` and the Cursor CLI, logged in, if you route jobs to them in Settings.

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # macOS/Linux: .venv/bin/pip
.venv/Scripts/dsc serve                   # API on http://127.0.0.1:8000
```

In a second terminal:

```bash
cd web
npm install
npm run dev                               # http://localhost:5173 (proxies /api to the backend)
```

Or build the frontend once (`npm run build` in `web/`) and `dsc serve` serves the whole app on port 8000.
Tests: `.venv/Scripts/python -m pytest` in `backend/`.

## Layout

```
docs/SPEC.md            product spec and decisions
backend/dsc/
  engine.py             BKT, mastery gate, FSRS, playbook replay, angle choice (pure, no I/O)
  db.py                 workspace + SQLite schema (append-only logs)
  state.py              read side: snapshots for the UI
  actions.py            write side: every UI action
  lesson.py             renditions: open, refresh, prose cache, render scheduling
  jobs.py               agent jobs (research, outline, render, tutor, roadmap review, fact-check,
                        grading, placement quiz, reflection) + offline fallbacks
  progress.py           evidence recording, research one module ahead
  runner.py             local Python runner: approval by test hash, static check, isolated run
  viz.py                interactive-visual specs and their validation
  library.py            shared card library, full-text search, Anki export
  planner.py            weekly plan across goals and its calendar (.ics) export
  providers.py          agent-CLI adapters (claude -p, codex exec, Cursor CLI), routing and fallback
  prompts/              one prompt per job
  seed/demo.json        demo roadmap
backend/tests/          engine and end-to-end flow tests (fake provider)
web/src/
  store.tsx             API client: snapshot + actions, polling while jobs run
  pages/                Home, This week, Goal setup, Placement, Roadmap, Lesson, Reviews, Search, Me, Library,
                        Settings
  components/           inline checks, explain-back, Pyodide and local exercises, side panel (tutor, notes,
                        source card), feedback dialog
  components/viz/       interactive widgets and a safe expression evaluator for plots
```

## Next

Ideas: phone reviews over the home network (deliberately skipped for now: the app has no login), a Docker option for
the local runner, per-goal time settings on the week page, and suggestions for which cards to share.
