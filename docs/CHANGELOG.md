# Changelog

The history of Deep Study Center, newest first. The full design and the decisions are in [SPEC.md](SPEC.md); the
work still open is in [TODO.md](TODO.md).

## Unreleased: formulas on the map, lesson plans, step lessons (SPEC §41-§43)

- **Step lessons** (SPEC §43): an approved plan is taught one step at a time. Each step: a prediction first, the step in
  its form (at most about 80 words, an example, a widget, a derivation), then "Check your understanding". A wrong check
  shows a short repair. The next step is written while you read this one. "Explain differently" writes one step again
  with your note.
- **Plan a lesson before it is written** (SPEC §42): opening a book lesson that is not written yet first makes its plan,
  a small graph from what you hold to the lesson's idea, with the form of each step (example, interactive, figure,
  short text, derivation). Watch it being made and send notes; cut what you know, ask for another form, add notes,
  re-plan, and approve. Only then is the lesson written, from the plan. "Write it now without a plan" keeps the old way.
- **Formulas on the map:** every formula from your lessons is on the knowledge map, in a "Formulas" country of its own,
  linked to the idea that uses it. Click it to see the math.
- **Formula provinces:** a model sorts each formula into fields of mathematics (probability, linear algebra, ...). Each
  field is a province of the Formulas country. A formula in 2 or 3 fields sits where those provinces meet, split in
  their colors; one in 4 or more is gray ("Essential"). The legend lists the provinces with their counts.
- **Territories** is the default map view. Country names moved from the land into a legend under the map, which can be
  collapsed.

## 0.4.1 (2026-11-23): the app updates itself, and the review fixes (SPEC §39, §40)

- **Auto-update** (SPEC §39): after the start, the desktop app asks the newest GitHub release for a newer version and
  offers "Install and restart". Updates are signed; the app installs only an update with a correct signature.
  `DSC_NO_UPDATE_CHECK=1` turns the check off. Version 0.4.0 has no updater: install 0.4.1 once by hand.
- Release files: `desktop/release.py` writes `latest.json`; the steps are in [RELEASING.md](RELEASING.md).
- **Back** at the top of every page.
- **Sources:** types (Book, Article, Internet source, Video, Custom), clear status colors, a click opens the source,
  an "Add source" dialog (file or link, name, type, progress, duplicate check by SHA-256), search and type filters.
  Removed: the goal and shared card tabs, the Anki export, and the book goal (80/20).
- **Books:** a trash can on every card, search and filters, links and Custom topics on the shelf, one color per book
  on its card and on the map.
- **Practice** is on hold. **Map:** Graph, Nebula and Globe removed; the Tree zooms with the mouse wheel.
- **Lessons:** Python edits survive a refresh; cleaner formula hover cards; clear board tasks; one idea per book
  lesson, with "Re-plan lessons" for books mapped before.
- **Formula tree** is a derivation graph with the math in each node, one level at a time, and formula pages on request.
  Formula pages look different and have no quiz.

## 0.4.0 (2026-11-23): book study, the first public release

- **Teach me this book** (SPEC §28, §31): a PDF becomes chapters of lessons by topic. Lessons are written from the
  book's pages when you open them, with idea links, a quiz and a drawing board the grader reads.
- **Map views and the redesign** (§29, §30): seven map views; Today, Books, Learn, Practice and Map; dark theme.
- **The tutor reads your reasoning** (§32, §35): it marks each part of your thinking right or wrong, names the wrong
  assumption, follows it until it breaks, and derives how it really works. In checks, study sessions and
  explain-backs. Lessons are written in Simplified Technical English by default.
- **Formulas** (§33, §34, §36): hover notes, formula lessons with interactive widgets, green / orange / gray frames,
  your preferred form in every lesson, and 3D surfaces for gradient descent.
- **Building blocks** (§37, §38): formula lessons are built bottom-up from a formula tree; one topic is one shared
  block across books; "Next" picks a lesson whose parts you hold; the whole formula tree on one page.

## 2026-11: knowledge graph, study sessions, desktop app

- **Knowledge graph** (SPEC §21): every idea you learn is one node, with reasoning links between nodes.
- **Study sessions, "teach me X"** (§22): a probe finds what you already know, then predict → explain → check, one idea at a time.
- **Knowledge map** (§23): all ideas as one skill tree.
- **Recall practice** (§24): adaptive problems with hints and a schedule per idea.
- **Desktop app and the Claude API with your own key** (§25).
- **A sharper probe** (§26): one question at a time, shuffled options, a result per idea.
- **Local dictation with Whisper** (§27).

## Earlier milestones

**Book goals** (current): no time to read whole books? In the Source library, "Understand books (80/20)" builds a goal
from one or more of your PDFs. Tick them or drag them into the goal basket, answer two questions, and an agent ranks every
chapter as core, supporting or left out. The roadmap (Ohtani table or classic) teaches only the core, with lessons that
cite the pages; the Roadmap page lists what was left out, and "Bring back" adds a chapter again. See SPEC §18.

**Lessons written in steps**: a whole lesson is planned, its graphs and quiz questions are made for you,
its text is written, and a reviewer checks it against your lesson guidelines and feedback before you see it (one round
of fixes). Each section's angle is a mix that follows the section's purpose and your playbook, not one angle everywhere.
The lesson page shows how it was written; graphs and questions made for you are marked.

**Ohtani table** added: a new goal can be built as an Ohtani table (a Mandala Chart), the default shape.

- The goal is in the middle of a 9x9 grid. 8 areas (for example Linear Algebra, Statistics) sit around it, each with
  8 steps; every step has as many lessons as it needs.
- The 8 cells around the goal are merge steps: each joins two neighbouring areas in one task toward the goal (top-left
  merges the top-left and top-middle areas). The outline orders the areas so that neighbours combine well.
- A merge step unlocks when the steps it builds on are learned. Steps are learned wave by wave across the areas.
- The Roadmap page shows the grid. A cell fills as you pass its lessons' checks; the current step has a ring. Pick a
  cell for its "done when" check, what it builds on, and its lessons.
- The classic roadmap (3-7 tracks) is still available on the goal setup page.

**Personal lessons** added: feedback on any part of a lesson, lessons that learn from your feedback, and extra
lessons when you are stuck.

- Select text, or point at a formula or an interactive graph, to give feedback on exactly that part (or add a note).
  Applying it changes that part, and other parts only where they are directly relevant or have the same issue.
- Lesson guidelines: when you finish a lesson, the main points and patterns of your feedback are distilled into a
  short list (Me page, editable). The next lesson is then written with them, and so is every later lesson.
- Extra lessons: when wrong answers, failed explain-backs, tutor questions or "I got lost" pile up, the lesson offers
  an extra lesson ("Vectors (b)") aimed at exactly what got in the way. One click adds it; it is researched and
  fact-checked like any lesson.

**Feedback you can apply** added:

- Apply one or more pieces of feedback to the lesson you are on (from the lesson's Feedback log or Me → Feedback log).
  One agent job writes the next version of the lesson and says, per change, which feedback caused it, why and how.
- Lesson versions: every version is kept. Compare any two in a GitHub-style prose diff (deleted text red, inserted
  green, each change with its reason and feedback), and go back to any version of the current card.
- Add, edit and delete feedback. Each item has a kind (about this lesson / about me / possible error) that an agent
  proposes and you can correct, and a status: pending, applied in vN, reverted, or sent to the card check.
- Fact guard: a revision changes only explanations, examples, angle and pace. Facts, checks and exercises stay as
  fact-checked; a report that the material is wrong goes to the card check instead.
- Going back from applied feedback teaches the playbook which way of applying it did not work for you.

**Milestone 6** added daily-use readiness:

- One command to set up and start (`start.ps1` / `start.sh`, or `dsc start`); the frontend is rebuilt only when it changed.
- First run starts empty and lets you pick your own goal or the demo; goals can be removed in Settings (after a backup).
- Daily backups of the workspace database (newest 14 kept), plus "Back up now".
- Undo an answer (mis-click) or remove a grade you disagree with; mastery is recomputed from what remains.
- Live research progress: each web search and page the research agent reads shows up as it happens.
- This week: per-goal hours, and time actually spent (counted while a lesson is open and you're active).
- Library: suggestions for which cards to share (fact-checked, and you've learned the concept).
- Docker option for exercises (no network, read-only, resource limits, unprivileged user). Untested until Docker is installed.

**Milestone 5** added:

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
