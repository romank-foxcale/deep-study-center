# TODO: the knowledge-graph rework and open items

This file lists all work that is not done yet, so that any session can pick up a task. Each task tells you:
why we need it, what to build, how to build it, how to check it, and when it is done.

Written 2026-11-20. Steps 1 and 2 of the rework are done (PR #13 merged, PR #15 open). Read "Before you start" first.

---

## Before you start

**The vision (from the user).** Deep Study Center (DSC) moves from "one goal, one roadmap" to **one knowledge graph
of everything the learner knows**. The learner can say "teach me X" with or without a goal. DSC then finds what they
already know (the graph), plans the shortest path to X, teaches it step by step, and adds the new knowledge to the
graph. The graph is shown as a skill tree (lit nodes = known, dim nodes = needed for a target). Understanding is not
enough: the learner must be able to **recall** and use it, so practice is a core part. Goals stay, but a goal becomes
a set of target nodes on the graph. In the end DSC becomes an **open-source desktop app**.
The inspiration is the video "Agent Harness for Learning Things" by Eero Alvar. Do not copy its look or code; use the
ideas: thinking fields, confidence, probe → plan → teach (predict → explain → check), reasoning chains in a graph,
adaptive practice with hints.

**How to run and test.**
- Workspace (the learner's data): `~/DeepStudy` (`DSC_WORKSPACE` overrides it). It holds `study.db` (SQLite) and
  `sources/*.pdf`. This is the user's real data: do not delete rows or files there without asking.
- Servers: `.claude/launch.json` has `web` (Vite, port 5173) and `api` (`python -m dsc.cli serve`, port 8000).
  Start them with the preview tools, not with Bash. Restart `api` after backend changes (no auto-reload).
  Never commit `.claude/launch.json` (local change).
- Backend tests: `cd backend && .venv/Scripts/python.exe -m pytest -q` (all must pass; about 150 tests).
- Frontend checks: `cd web && npx tsc -b && npx eslint src` (0 errors; the "Fast refresh" warnings are old and OK).
- Tests use `FakeRunner` (`backend/tests/conftest.py`): `runner.responses[<route role>]` is a value or a function of
  the call. The demo goal (`g-ai`, modules `m-la`, `m-calc`, …, concept `c-vectors`) is seeded in each test.

**How the code is built (short).**
- `backend/dsc/`: `db.py` (schema + `MIGRATIONS` list for new columns), `actions.py` (every UI action, registered
  in `ACTIONS`), `jobs.py` (background agent jobs, `HANDLERS` = kind → (run, fallback)), `state.py` (`snapshot()` is
  everything the UI gets), `engine.py` (BKT mastery, FSRS reviews, angles), `progress.py` (evidence, research ahead),
  `writer.py` (lesson writing: plan, assets, prose, review), `probe.py`, `sources.py`, `books.py`, `ohtani.py`.
- Prompts: `backend/dsc/prompts/*.md`, filled by `jobs.prompt(name, **fields)` with plain `{field}` replacement.
  `{rules}` and `{widgets}` are filled automatically.
- Agent calls: `jobs.call(jid, "<route role>", Call(prompt=..., schema=..., model=..., tools=...))`. Routes (which
  CLI and model per role) are in Settings and `providers.RECOMMENDED`. Providers are the `claude`, `codex` and
  `cursor` CLIs on the user's subscriptions.
- Frontend: `web/src/` (React 19, react-router HashRouter, react-markdown + KaTeX). `store.tsx` has the `Action`
  union and `dispatch`. Shared input for answers: `components/ThinkingInput.tsx`.
- The spec is `docs/SPEC.md` (one section per feature, newest is §20). Add a section for each new feature.

**Rules for working with this user.**
- Write to the user in ASD-STE100 Simplified Technical English (about 80 % strict): short sentences, active voice,
  lists for steps.
- For UI work, do not list what changed: the user checks it in the browser. Give the status only.
- Commit, push or open a PR only when the user asks. Branch from the newest `origin/main` (check `git fetch` first:
  other sessions merge PRs too). After a PR, bind it with the PR tools; the user usually asks for Auto-fix.
- Pitfall: Bash heredocs in this environment turn `\n` and `\\` inside code into real newlines and single
  backslashes. Write code with the Write/Edit tools, or put Python edit scripts in a file first.

---

## A. Open items from finished work

### A1. Merge PR #15 (the probe) and run one full probe with real answers
- **Why:** the probe was checked with tests and one real first round only. Its value depends on the quality of the
  agent's questions and assessment.
- **What:** the user answers a full probe for the book goal "Master Understanding Deep Learning…" at `/probe`
  (round 1 is ready). Then they click "Use this for my roadmap and lessons".
- **How to check:**
  1. Each round's questions follow from the earlier answers (look at `probe_items` in `study.db`: later rounds drill
     into the steps where answers were wrong, unsure or "I don't know").
  2. The assessment marks steps known / partly / new, and the edge text is specific.
  3. After "Use this": a pending roadmap diff exists for known steps, and `goals.profile` ends with
     "Where they stand (probe, <date>): …".
- **Possible fixes after the run:** tune `prompts/probe.md` (question length, how fast it drills in, when it stops).
- **Done when:** PR #15 is merged and one real probe ran to the end without errors.

### A2. Check dictation with a real microphone
- **Why:** dictation (`useDictation` in `ThinkingInput.tsx`) uses the browser's Web Speech API. It was not tested with
  a real microphone.
- **How to check:** in Chrome or Edge at `http://localhost:5173`, open a lesson check, click "Dictate", allow the
  microphone, speak two sentences. The text must appear at the end of the box; the interim text shows in italics.
  Click "Listening… stop". Check the "Microphone access was refused." message when access is blocked.
- **Note:** Chrome's Web Speech API sends audio to Google. That is acceptable for the web app, but not for the desktop
  app (see C2).
- **Done when:** dictation works in Chrome and Edge, or the bugs found are fixed.

### A3. ✅ DONE (2026-11-20, branch `claude/goal-sources`): Move the per-goal source choice out of the library (lost commit `2dedc29`)
Done as described below; "Learn" opens `/goal/book` with the source in the basket (router state `sourceIds`).
- **Why:** the user said the library column "Use for this goal" is unclear ("which goal?"). The per-goal choice must be
  on the goal page, as a check list or drag and drop. This was built in commit `2dedc29` on the old branch
  `claude/pdf-sources`, but that commit was pushed after PR #11 was merged, so it never reached `main`. Only its PDF
  text fix was ported (PR #14).
- **What:**
  1. Remove the "Use for this goal" column from `web/src/components/Sources.tsx` (`SourcesTable`). Add a column
     "Used in goals" with the goal titles (from `s.goals`).
  2. Add a "Sources for this goal" card to the goal page (`web/src/pages/Home.tsx`, under the goal hero): two lists,
     "Used for this goal" and "Not used", with tick boxes and drag and drop (HTML5 drag events), and an
     "Add PDF to this goal" button (`AddSources link`). The action `linkSource` already exists.
  3. Library uploads must not link to the active goal (`AddSources link={false}` in `Library.tsx`).
  4. Decide with the user how "Learn this book" relates to PR #12's book goals (`/goal/book`, "Understand books
     (80/20)"). Probably: a "Learn" button per source that opens `/goal/book` with that source already in the basket.
- **How:** take the code from `git show 2dedc29 -- web/src/components/Sources.tsx web/src/pages/Home.tsx
  web/src/styles.css` and adapt it to the current files. Do not port its `basis: "sources"` outline change: book goals
  replace it.
- **How to check:** browser: on Home, tick and untick a source, and drag one between the lists; `goal_sources` rows
  change. In the library, the goal names show. Tests: extend `tests/test_sources.py` if backend changes.
- **Done when:** no "Use for this goal" column remains, and the goal page controls which sources a goal uses.

### A4. Smaller items
Done 2026-11-22 (branch `claude/small-items`):
- "With your values" in the formula widget: a part that shows a parameter now gets its value through the part, so a
  name that differs from the symbol (`na` vs `N_A`) is filled in, also inside one function (`\cos\theta` with a
  slider `t` gives `\cos(1.0)`) (`byPart` in `viz/Formula.tsx`).
- Opening a goal lesson while a book goal is active failed ("Lesson not found"); `bookOpenLesson` now makes any
  lesson's goal active.
- Misconceptions in the remedial offer: a wrong answer given at 75 % or more counts 2, the offer names it ("given
  while sure: a likely misconception"), and the extra lesson's brief gives the confidence and the learner's thinking.
- The lesson reviewer gets the reasoning log and reports text that does not take on a misconception about its idea.
- Backups: two backups in one second no longer overwrite each other (`_2` suffix); this was why the backup test
  was flaky.
- Found on the way: an extra lesson in a book chapter was never written (book research skipped it); it now goes
  through normal research.

Still open:
- **Fix round with a real model:** `writer.check_viz` sends a broken formula widget back to an agent once
  (`fix_widget.md`). It was never run with a real model. Make a lesson with a broken widget and check that the fix is
  used.

---

## B. The knowledge-graph rework (steps 3–6)

Do the steps in this order. Each step works without the later ones. Steps 3 and 4 are the big ones.

### B3. ✅ DONE (2026-11-20, branch `claude/knowledge-graph`, SPEC §21): Step 3: one knowledge graph (data model)
Done with one change to the plan: instead of a `module_nodes` table and a `concepts.node_id` column, every concept
points to a node through `concept_nodes` (filled automatically by `graph.sync`), so the five places that insert
concepts did not change. Left for later: per-node review scheduling (reviews are still per concept).
- **Why:** now every concept belongs to one module of one goal (`concepts.module_id` → `modules` → `tracks.goal_id`).
  So knowledge learned for goal A is unknown in goal B, and DSC cannot study anything outside a goal. Everything else
  in the rework (teach me X, skill tree, recall practice) needs one global graph of ideas with a state per idea.
- **What:**
  - A **node** is one idea (now: one concept; later also smaller statements, "propositions"). A **link** says "this
    idea is used to reason toward that idea" (direction of reasoning, basic → advanced).
  - The learner's **state per node is global**: not seen / learning / understood / recallable (learned) / strong
    (mastered) / rusty, computed from all evidence for that node, from any goal or session.
  - A goal or module **refers** to nodes; several goals can share a node.
- **How (incremental, keep everything working):**
  1. Schema (`db.py`): `nodes(id, title, statement, kind, created_at, origin)`,
     `links(src, dst, why, origin, PRIMARY KEY(src, dst))`, `module_nodes(module_id, node_id, ord)`.
     Keep the `concepts` table for now; set node id = concept id for every existing concept (a one-time migration
     that also turns `concepts.prereqs` into links). New code reads nodes; old code keeps working on concepts.
  2. Dedupe at research time: `run_research_module` (`jobs.py`) already has `reuse_key` for the shared library.
     Extend it: before a new concept is written, find candidate nodes with the same idea (FTS5 over node title +
     statement, like `source_fts`), give the top candidates to the research prompt, and let the agent set
     `same_as: <node id>`. Then link the module to the existing node instead of making a new one.
  3. Global state: `engine.derive_concepts` works on one goal's concepts. Add `state.node_states(db)` that runs the
     same BKT/FSRS logic over all evidence per node id. `concept_states` then reads the node state for shared nodes.
  4. API: `GET /api/graph` → `{nodes: [{id, title, state, goals}], links: [{src, dst}]}`.
- **How to check:**
  - Test: migrate the demo workspace; every concept has a node; `concepts.prereqs` became links.
  - Test: two goals share a node; evidence in goal A makes the node learned in goal B.
  - Test: research for a second goal with an idea that exists gets `same_as` and makes no duplicate node.
  - Real data: run the migration on a copy of `~/DeepStudy/study.db` first (copy the file; never test on the
    original).
- **Risk:** this touches the center of the app. Keep the migration reversible (new tables only, no dropped columns)
  and make a backup (`backup.backup_now`) before it runs.
- **Done when:** `/api/graph` returns all nodes of all goals with a correct global state, and all old tests pass.

### B4. ✅ DONE (2026-11-20, branch `claude/knowledge-graph`, SPEC §22): Step 4: "Teach me X" study sessions
Done as planned, checked with a real session ("teach me the chain rule") on a copy of the workspace. Left for later:
graph widgets in explanations, prefetching the next step (each step waits for one model call), attaching a session
to a goal, and splitting nodes into smaller statements.
- **Why:** the user wants to say "teach me transformers" outside any goal frame. DSC should use the graph to see what
  they know, connect the new topic to it, and teach it so each step "feels obviously true".
- **What (the flow):**
  1. **Ask:** a "Study something" entry (sidebar + Home): one text field (with dictation): "What do you want to
     learn?", plus optional sources (PDFs) and an optional goal to attach to.
  2. **Probe:** reuse the probe (`probe.py`) with a topic scope: instead of roadmap steps, the agent first sketches
     the dependency tree of X (candidate nodes, matched to existing graph nodes), then probes only the nodes whose
     state is unknown. Answers have the thinking box and confidence.
  3. **Plan:** the agent builds the minimal dependency tree from lit (known) nodes to X. The page shows it as a
     small tree; the learner can accept it or remove nodes they know.
  4. **Teach, one step per node:** each step is **predict → explain → check**: a prediction question first ("what do
     you think comes next?", with thinking box), then a short explanation fitted to their prediction and thinking,
     then a check question. Keep each explanation short (no walls of text): the goal is a steady stream of the
     learner's thinking. Use the existing tools: graph widgets (`viz`), runnable Python, sources excerpts
     (`sources.excerpts`) for PDF pages, web research for fact checks.
  5. **Extract:** at the end (and every few steps) an agent distills the session into nodes and links (statements
     and reasoning chains), matched to existing nodes (B3 dedupe), and adds them to the graph with evidence from the
     checks.
- **How:**
  - Tables: `sessions(id, topic, goal_id NULL, status, plan JSON, created_at)`,
    `session_steps(id, session_id, node_id, ord, phase, item JSON, answer, thinking, confidence, ts)`.
  - Jobs: `session_probe`, `session_plan`, `session_step` (writes the next predict / explain / check from the whole
    session so far), `session_extract`. One agent call per step; the next step's call can start while the learner
    reads (prefetch) to hide the wait.
  - Prompts: `session_plan.md`, `session_step.md`, `session_extract.md`. Give them `state.reasoning_log`, the node
    states of the topic's neighbourhood, and the learner's playbook and guidelines.
  - Page: `web/src/pages/Study.tsx`, a step view like a chat but with structured cards (predict / explain / check),
    the plan tree on the side with "you are here".
- **How to check:** tests with `FakeRunner` for each phase (plan uses known nodes; step prompt contains the prediction
  thinking; extract adds nodes and links without duplicates). Browser: one short real session ("teach me the chain
  rule") from ask to extract; the new nodes appear in `/api/graph`.
- **Done when:** a learner can study a topic with no goal, and the result lands in the graph.

### B5. ✅ DONE (2026-11-20, branch `claude/knowledge-map`, SPEC §23): Step 5: the skill tree view
Done with an own layered layout (no d3). Left for later: "Practice" from a node (needs B6), remembering zoom and focus.
- **Why:** the user wants to see the knowledge as a growing tree: what they know (lit) and the building blocks still
  needed for a target (dim), like a progression tree in a game. Trees of several goals join into one big map.
  Use an original look; do not copy a specific game's art.
- **What:** a "Knowledge map" page.
  - Layout: basic ideas at the bottom, reasoning goes up (Y = depth = longest path from a root node). Inside a level,
    order nodes to reduce crossing links.
  - Colors by state: strong / learned (bright), learning / partly (half), needed for a selected target (dim outline),
    other unknown nodes hidden by default.
  - Select a goal or a session topic: its target nodes glow; the path from lit nodes to them is highlighted.
  - Click a node: its sessions, lessons, cards, last practice result, and "Practice" / "Teach me this".
  - Zoom and pan; a search box.
- **How:** read `/api/graph` (B3). No graph library is installed yet: use `d3-force` (small, npm) for the X spacing
  inside levels and draw with SVG, or write a simple layered layout yourself. Render with SVG for up to about 1000
  nodes; switch to canvas only if it is slow.
- **How to check:** browser with the real workspace: the map renders, colors match node states, selecting a goal
  highlights its path, and zoom/pan works. Check speed with about 1000 nodes (make a test graph).
- **Done when:** the map shows all goals' nodes in one tree, and a target shows what is still needed.

### B6. ✅ DONE (2026-11-21, branch `claude/recall-practice`, SPEC §24): Step 6: adaptive recall practice
Done as planned, checked with a real run on a copy of the workspace. Left for later: replace `Review.tsx` with
recall practice, prefetch the next problem, and watch whether the judge sometimes misreads a partial answer
(it said "no answer yet" once in the real run; the prompt was made stricter).
- **Why:** understanding is not the same as being able to use it. Recall works from cues; practice must make the set
  of cues wider and stronger. DSC now only re-asks one quiz question from a card (`Review.tsx`), which trains
  recognition, not recall.
- **What:** a practice session is a stream of problems that adapts:
  - Each problem targets 1–3 nodes. Difficulty changes in two ways: how many ideas a problem combines, and how
    familiar the cues are (the same setting as the lesson → a new setting).
  - The learner writes their thinking in chunks ("Submit thinking"), with dictation. No final answer form: the agent
    judges from the thinking whether it is solved.
  - When the learner is stuck, the agent gives the smallest hint that moves them on, never the solution.
  - The result per node becomes evidence (score 0–1) and updates the node's schedule (FSRS, `engine.review`).
  - Start points: "practice what is due", nodes picked on the map, or the learner's own problem (text or a PDF page:
    the agent rebuilds the problem from `source_pages`).
- **How:** tables `practice(id, created_at, node_ids, status)`, `practice_items(id, practice_id, problem JSON,
  node_ids, chunks JSON, hints JSON, score, ts)`; jobs `practice_next` (writes the next problem from the session so
  far and the node states) and `practice_judge` (reads a thinking chunk: solved / hint / keep going). Prompt files
  `practice_next.md`, `practice_judge.md`. Page `web/src/pages/Practice.tsx`. Later, replace `Review.tsx` with it.
- **How to check:** tests: a solved problem raises the nodes' evidence and moves their due date; a hint never contains
  the final answer (check with a test response); difficulty goes up after solved problems. Browser: one real session
  with 3 problems.
- **Done when:** due reviews run as recall practice, and results change node states on the map.

### B7. ✅ DONE (2026-11-22, branch `claude/probe-edge`, SPEC §26): A sharper probe (ideas from learnharness)
Done as planned, checked with a real study-session probe on a copy of the workspace. Left for later: free-recall
probe questions, and a "thinking while reading" field for teaching checks. Models sometimes still put a "because" in
every option; the options stay even, so it gives nothing away.
Idea source: the probe of [learnharness](https://github.com/amosblomqvist/learnharness) (AGPL-3.0). Copy the ideas
only, never its code or prompt text.
- **Why:** the probe asks rounds of 4 questions, so 3 of 4 questions cannot use the newest answer. It starts in the
  middle and moves one step at a time. The model sees which option it wrote first, and position bias can give the
  answer away. The guess line is 25% for every number of options. The result is only known / partial / unknown, so
  the teacher does not learn where the learner's reasoning stops.
- **What:**
  1. One question at a time: each question is chosen from the last answer and its thinking (both probes).
  2. Bracket the edge: start near the top of what the goal needs; a well-reasoned right answer allows a big jump; a
     miss narrows back. Stop when the lesson has enough evidence; do not keep going until a miss.
  3. Questions that split mental models: two different mental models give two different answers. One question can
     give evidence on more than one idea.
  4. Fair options: the model writes the explanation before it picks the answer; options are bare claims; each wrong
     option is the answer of one real misconception. The backend shuffles the options of every generated
     multiple-choice question and remaps the answer.
  5. Confidence compared with chance: a right answer counts as a guess when the confidence is at or below
     max(1/n, 30%) for n options. The slider snaps to 0 / 30 / 50 / 70 / 90 / 100 %, with plain labels. The probe
     prompt sees the chance level next to each confidence.
  6. A result per idea (strand): what the learner reasons from reliably (floor), where their reasoning stops
     (ceiling), the misconceptions, and "not tested" kept apart from "tested and missed". The study plan shows it,
     and the teaching turns of that idea get it.
- **How to check:** tests: the shuffle keeps the right option right; the guess rule follows the number of options;
  the probe asks one question per job and stores the per-idea result; a teaching turn prompt contains the result.
  Browser: one real study-session probe on a copy of the workspace.
- **Done when:** both probes ask one question at a time, options are shuffled, and the plan shows the per-idea result.

---

## C. Desktop app and open source (step 7)

### C1. ✅ DONE (2026-11-21, branch `claude/desktop-app`, SPEC §25): Package DSC as a desktop app
Done with Tauri 2 + a PyInstaller backend folder + an NSIS per-user installer, and an Anthropic API-key provider with
the key in the Windows Credential Manager. Left for later: bundle Pyodide for offline use, code signing, auto-update,
macOS/Linux builds, a single-instance guard (two app windows would start two backends on one workspace).
- **Why:** the user wants DSC to be a free, open-source desktop app that anyone can install.
- **What:** one installer per OS that starts the backend and shows the UI in a native window.
- **How:**
  - Shell: **Tauri v2** (small, uses the system webview) or **Electron** (bigger, same Chromium everywhere). Decide
    with the user. Tauri needs Rust; Electron is simpler for a web team.
  - Backend: bundle `backend/` as a sidecar binary with PyInstaller; the shell starts it on a free local port and
    stops it on exit. Workspace stays `~/DeepStudy`.
  - Providers: the app now needs the `claude` / `codex` / `cursor` CLIs and their subscriptions. Most users will not
    have them. Add API-key providers (Anthropic API first; keys stored in the OS keychain, never in the workspace) and
    a first-run screen to set them up.
  - Pyodide (runnable Python) loads from a CDN now; bundle it for offline use.
- **How to check:** build the installer on Windows; install on a clean Windows user account; create a goal with an
  API key; run a lesson; close and reopen (data kept).
- **Done when:** a fresh machine can install and use DSC without a terminal.

### C2. ✅ DONE (2026-11-22, branch `claude/probe-edge`, SPEC §27): Local dictation (Whisper)
Done with faster-whisper (base model by default, small as an option), a one-time download in Settings → Dictation,
and phrase-by-phrase recording in the page. Checked with a real model and a recorded test phrase, not yet with a real
microphone (A2). The desktop bundle includes it (installer 74 MiB instead of 19.7 MiB). Left for later: check the
microphone prompt of WebView2 in the installed desktop app.
- **Why:** the browser's speech API sends audio to Google, and desktop webviews may not support it.
- **How:** a local Whisper model (for example faster-whisper `small`, or whisper.cpp) in the backend:
  `POST /api/transcribe` takes short audio chunks recorded with `MediaRecorder`; `useDictation` uses it when the
  setting "Local dictation" is on or when the browser API is missing. One-time model download with a progress bar.
- **How to check:** dictate with the network off; text appears within about 2 s per phrase.

### C3. Open-source release (files done 2026-11-22, branch `claude/open-source`; repository steps open)
Done: MIT license (`LICENSE`, and the license fields in `pyproject.toml`, `package.json` and `Cargo.toml`); a README
for new users (what it is, install, providers, privacy); `CONTRIBUTING.md`, `SECURITY.md`, issue and pull-request
templates; the milestone history moved to `docs/CHANGELOG.md`. CI (pytest, tsc, eslint, build) already ran on every
pull request. Scan of files and history: no keys, tokens, file paths or e-mail addresses in any file; the roadmap data
named the author's study niches and region, now generic. The repository was already public before this step.
Open, for the user to decide or do:
- History: decided 2026-11-22 to keep it as it is (every commit carries the author's name and work e-mail, already
  public; a rewrite would change every hash and break old pull-request links). Future commits can use the GitHub
  no-reply e-mail.
- Repository settings: turn on private vulnerability reporting (SECURITY.md points to it), add a description and topics.
- First release: build the installer and attach it to a GitHub release (unsigned; code signing is a later step).
- **Why:** the user wants to publish DSC as open source.
- **What:**
  1. Choose a license with the user (MIT or Apache-2.0 are common).
  2. Remove personal data from the repository and its history: check `docs/ROADMAP.md` and its data files, the demo
     seed, test fixtures (`tests/fixtures/formula_widgets_real.json` came from the user's real lessons), and any
     names or e-mail addresses. Use `git log -p` / a secret scanner. Rewriting history needs the user's approval.
  3. README for strangers (what it is, install, providers, privacy: what is sent to which model), CONTRIBUTING,
     issue templates, and CI (pytest, tsc, eslint) on pull requests.
- **Done when:** the user approves the public repository and the release.

---

## D. Book study: "teach me this book" (the main flow from 2026-11-22)

The user's decision (2026-11-22): the main tool is "teach me X", and above all "teach me this book": one PDF at a
time. Big goals and the Ohtani table become an extra capability: **on hold, do not delete them**. The UI comes after
D1-D4 work; the user will discuss it then.

### D1-D5. ✅ DONE (2026-11-22, branch `claude/book-study`, SPEC §28) as a first working version
Checked with a real map of "Inference Engineering" on a copy of the workspace: 11 chapters, about 300 ideas and 500
links (200 across chapters) in 9 minutes; links to older graph ideas (matrix multiplication → linear layer as matmul,
dot product → scaled dot-product attention); a real study session of part 2.2 with ideas from other parts, idea links
in the explanation, and the hover card. Fixed during the check: big parts are split into sessions of at most 8 ideas;
the mapper sees all older graph ideas by title (word search missed synonyms); a re-mapped chapter no longer reuses or
links its own old ideas. Open: the UI design (with the user); a glossary appendix maps terms the book assumes (for
example softmax) as its own part; the "Study" order does not yet use the knowledge of earlier finished parts beyond
the graph state; a mapped chapter cannot be re-mapped from the UI (internal option `only`).

### D7. ✅ DONE (2026-11-22, branch `claude/ui-redesign`, SPEC §30): The redesign
Five main entries (Today, Books, Learn, Practice, Map) with goals on hold in their own group, the dark star-chart theme
by default (Light and System in Settings), a Today page, a book shelf, a new Book page, a reading layout for sessions,
and the map opening on Territories. Checked on the mock workspace in dark, light and phone width. Then (branch
`claude/page-polish`): Practice, Library, Me and Settings in the new style, and pinch zoom on the map. Open: the goal
pages keep their old layout while goals are on hold; pinch zoom is not yet tried on a real touch screen.

### D10. ✅ DONE (2026-11-22, branch `claude/formulas-3d`, SPEC §33): Formula hover notes and 3D surfaces
Hovering a formula shows its name, meaning, symbols and where you met it (checked on a copy with the real lesson "Loss
functions for multiple outputs": 16 notes in one call). A 3D surface widget with gradient descent, momentum, RMSProp
and Adam paths (checked on the mock). Open: existing lessons get 3D surfaces only when they are written again
(Refresh or "Explain differently"). Then (same branch, SPEC §34): formula lessons from the hover card, forms added to
them and a preferred form, and green / orange / gray frames on formulas. Checked on a copy with the real gradient
descent lesson: the formula lesson was written with its widget, and the other form of the update rule showed orange.

### D9. ✅ DONE (2026-11-22, branch `claude/reasoning-feedback`, SPEC §32): The tutor reads your reasoning
After a lesson check with thinking, the tutor marks the parts of the thinking as right or wrong with a reason, names
the wrong assumption, follows it until it breaks, and derives how it really works; saved per answer, with a history on
the Me page. Lessons and the tutor write in 80 % STE (a setting). Checked on the learner's real dictated answer (on a
copy of the workspace). The same reading for study-session answers and explain-backs: done 2026-11-22 (branch `claude/reasoning-everywhere`, SPEC §35). Also on this branch: a progress banner while a
lesson is written, and multi-line display formulas no longer turn red.

### D8. ✅ DONE (2026-11-22, branch `claude/page-polish`, SPEC §31): Book lessons
A book is chapters of saved lessons by topic: a chapter summary, lessons written from the book's pages on first open
(what the book says, what it means), idea links, feedback, a quiz at the end and a drawing board the grader reads.
Checked with tests, on the mock workspace, and with a real run on a copy of the workspace (2026-11-22): "Inference
Engineering" mapped into 11 chapters and 130 lessons in 7 minutes; the first open of "Attention and the KV cache"
wrote all 16 lesson plans of its chapter in one call and the lesson in about 10 minutes, with book summaries per
section and links to ideas from other goals; the grader read a drawing board and graded it. Fixed then: a writer's
`<details>` block now renders as a collapsible block. Then (branch `claude/book-chapters`): reference chapters (glossary, reading list)
get no lessons, and one chapter can be mapped again from the Book and Chapter pages.

### D6. ✅ DONE (2026-11-22, branch `claude/book-study`, SPEC §29): Map views and a mock workspace
Seven map views to choose from (Tree, Graph, Nebula, Skill wheel, Cells, Territories, Globe), saved per workspace, and
`dsc mock` for checking the UI with full data. Open: the UI talk (which view is the default; mobile touch zoom).

### D1. Map a book into its own idea graph
- **Why:** to teach a book, the agents must know what is in it, section by section, and which of its ideas the learner
  already has in the graph.
- **What:** "Study this book" on a ready PDF. A job reads the book one chapter at a time (the outline gives chapters,
  sections and pages; the page text gives the content). For every section it writes the ideas (title, statement,
  pages, prerequisites, kind) and maps each to an existing graph node when it is the same idea (`same_as`), else makes
  a new node (origin "book"). Prerequisites become links, also across chapters and to older nodes. A chapter that
  fails can be retried; the job continues where it stopped.
- **How:** tables `books(id, source_id, title, status, chapters_done, …)`, `book_parts(id, book_id, ord, chapter,
  title, page_from, page_to, session_id, status)`, `book_nodes(book_id, node_id, part_id, pages)`. Module `book.py`,
  prompt `book_map.md`, job `book_map`. A part is one section of the outline (level 2), or a whole chapter without
  sections. Front matter and parts without ideas are dropped.
- **Check:** tests with a fake model (parts and nodes made, `same_as` reuses a node, prerequisites become links,
  resume after a failed chapter). A real map of "Inference Engineering" on a copy of the workspace.

### D2. Study the book one part at a time
- **Why:** a part is the size of one study session (about 4-10 ideas).
- **What:** "Study" on a part starts a study session (SPEC §22) with the part's ideas already known (no sketch step).
  Ideas from earlier parts or other books that a part needs come in as prerequisites; the probe checks them, and an
  idea the learner lacks (for example softmax) is taught as its own idea. The teaching turns get the part's own pages
  and cite them. When the session is done, the part is done and the next part is suggested.
- **How:** `sessions.book_part`; `session.start_from_ideas`; `sources.excerpts` limited to a page range.

### D3. Homework and recall
- **What:** after a part, "Homework": a recall practice (SPEC §24) over the part's ideas. Every idea then has its own
  review schedule, so later recall practice includes it.

### D4. Idea links in lessons
- **Why:** when a lesson uses an idea the learner met before (softmax inside a transformer lesson), hovering over it
  should show where they learned it and how it connects.
- **What:** the teaching prompt gets the related graph ideas and links their first mention as `[text](#idea/<id>)`
  (unknown ids are removed). The page shows such links as a hover card: the statement, the state, the books (with
  pages), sessions and goals where it appears, and what it builds on and leads to. `GET /api/graph/node/{id}`.

### D5. A book's graph on the map (minimal; the UI is discussed later)
- **What:** the knowledge map can show one book's ideas, and the ideas it shares with other books.

---

## Suggested order

1. A1 (merge and test the probe), A3 (sources on the goal page), A2 (dictation check).
2. B3 (graph data model): the base for everything else.
3. B4 (teach me X), then B5 (skill tree), then B6 (recall practice).
   B7 (a sharper probe) after B6.
4. C1–C3 (desktop and open source), with A4 items whenever there is time.
