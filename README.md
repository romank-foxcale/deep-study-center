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

**Milestone 1: UI prototype** (this commit). A clickable React app on mock data. The feedback loop is real:
the playbook, renditions, mastery and roadmap changes all run in a browser-side mock engine, and the code
exercise runs real Python in the browser via Pyodide. No backend yet.

Try this: open *Vectors*, give "The framing didn't work for me" feedback on a section (only that section changes),
do it again on another section, then reopen the lesson (everything switches), and check the roadmap and
*Me & playbook*.

## Run

Requires Node 20+.

```bash
cd web
npm install
npm run dev
```

Then open http://localhost:5173. Data is kept in your browser's localStorage; *Settings → Reset demo data*
starts over.

## Layout

```
docs/SPEC.md          product spec and decisions
web/                  React + TypeScript (Vite) frontend
  src/data/mock.ts    demo roadmap, source cards, the full "Vectors" lesson
  src/store.tsx       state + mock engine (feedback → playbook → renditions, BKT, roadmap diffs)
  src/pages/          Home, Goal setup, Roadmap, Lesson, Me, Library, Settings
  src/components/     lesson parts: inline checks, Pyodide exercise, side panel, feedback dialog
```

## Next

Milestone 2: FastAPI backend with the deterministic engine (BKT, mastery gate, FSRS, playbook replay),
SQLite workspace in `~/DeepStudy`, and agent-CLI adapters (Claude Code headless first) for research,
cards, renditions, tutor chat and grading.
