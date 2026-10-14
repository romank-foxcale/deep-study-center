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

**Milestone 2: backend** (current). The app is real end to end:

- **Engine** (deterministic, tested): BKT mastery gate, FSRS spaced reviews, playbook replay from an append-only
  signal log, angle choice with per-section pins. No LLM calls.
- **Store**: SQLite in your workspace (`~/DeepStudy`, override with `DSC_WORKSPACE`). Cards are versioned; lesson prose
  is cached per (card version, section, angle, style), so a playbook change re-renders only what changed.
- **Agent jobs** on your own subscription via the `claude` CLI (headless): module research with web search,
  roadmap outline for a new goal, lesson rendering, tutor chat, roadmap review after feedback, independent fact-check.
  Each job is routed per Settings; missing providers fall back to Claude, and every job has an offline fallback.
- **Frontend** talks to the API; answers are graded on the server (keys never reach the browser before you answer).

The app starts from a demo roadmap (AI researcher & engineer). "Vectors" has pre-written prose; every other lesson is
written for you on first open. *+ New goal* runs the real interview → outline → research pipeline.

## Run

Requires Python 3.11+, Node 20+, and the [Claude Code](https://code.claude.com) CLI logged in with your subscription
(`claude` on PATH). Codex and Cursor adapters come in milestone 3.

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
  jobs.py               agent jobs (research, outline, render, tutor, roadmap review, fact-check) + fallbacks
  providers.py          agent-CLI adapters (claude -p), routing and fallback
  prompts/              one prompt per job
  seed/demo.json        demo roadmap
backend/tests/          engine and end-to-end flow tests (fake provider)
web/src/
  store.tsx             API client: snapshot + actions, polling while jobs run
  pages/                Home, Goal setup, Roadmap, Lesson, Reviews, Me, Library, Settings
  components/           inline checks, Pyodide exercise, side panel (tutor, notes, source card), feedback dialog
```

## Next

Milestone 3: Codex and Cursor adapters, placement diagnostic for new goals, explain-back answers graded by an
agent, "research the next module" running automatically one module ahead, weekly reflection over the feedback log.
