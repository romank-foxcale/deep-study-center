# Deep Study Center: product spec

A personal, local study platform for long, multi-step goals ("become a top AI researcher"). You
state a goal in a conversation; agents research it into a concise source knowledge base; every
lesson is rendered *for you* and keeps adapting as you give feedback. Successor to
[study-center](https://github.com/romank-foxcale/study-center) (the Mentor Claude Code plugin),
rewritten from scratch as a web app.

## 1. Decisions (from the requirements interview, 2026-10-14)

| Topic | Decision |
|---|---|
| Audience | Single user, runs locally. Multi-user is not designed out, but not built. |
| Where learning happens | In the browser. The web app is the product; no Claude Code session needed. |
| Model access | **The user's own subscriptions** (Claude, ChatGPT, Cursor), via their locally installed, logged-in agent CLIs (`claude -p`, `codex exec`, `cursor-agent -p`). No API keys, no per-token billing. Plan rate limits apply. |
| Provider routing | Each job (research, curriculum, source cards, rendition, tutor chat, grading, code review) has a provider + model chosen in Settings. Default: Claude for everything; others as alternatives or fallback when a plan is rate-limited. |
| Goal & scope | Chosen by the learner in a goal-setting chat. No fixed curriculum. |
| Source of truth | Hybrid: per-goal research by subagents; good cards can be promoted into a reusable library across goals. |
| Research timing | Progressive: whole roadmap outline + light source list up front; deep source cards researched about one module ahead of the learner. |
| Content principle | 80/20: concise, but fully covering each concept. Link the canonical source instead of paraphrasing it. |
| Adaptation | Everything adapts: future lessons, past lessons (refresh), the roadmap (as an approved diff), and the global teaching playbook. |
| Feedback | Available on every lesson and section at any time, even without chat or answers; every item is logged and reflected on. |
| Mastery | Rigorous and engine-decided: placement diagnostic, practice + mastery gate (BKT), spaced reviews (FSRS), confirmation at a delayed review. Reading is not completing. |
| Lesson page | Rendition + tutor chat panel + notes & highlights + inline checks + Pyodide code exercises + feedback + "explain differently". |
| Code exercises | In-browser Python via Pyodide (NumPy yes, PyTorch no). A local runner for real training may come later. |
| Stack | FastAPI + SQLite + agent-CLI adapters (Python); React + TypeScript (Vite) frontend. |
| Data | Workspace `~/DeepStudy` (configurable), outside the repo. The repo is public and code-only. |
| Milestone 1 | **UI prototype first**: clickable frontend on mock data to nail the experience, then wire the backend. |

## 2. The two knowledge centers

### 2.1 Source KB (learner-independent)
```
Goal ─┬─ Track (Linear Algebra, Probability, Deep Learning, ...)
      │    └─ Module (Vectors & spaces, ...)
      │         └─ Concept ── Concept card (versioned)
      └─ prerequisite edges between concepts (a DAG, across tracks)
```
A **concept card** is the canonical, fact-checked material for one small, testable concept:
- objective (what you can do after), Bloom level, est. minutes, prerequisites
- core idea, formal statement, *why it works*
- several **angles** (geometric, algebraic, computational, physical analogy, ...)
- worked-example bank (tagged by domain), misconceptions (with diagnostic questions)
- exercises with hidden keys: mcq, numeric, short, explain-back, code (Pyodide + tests)
- canonical sources (the 1-3 best existing explanations: paper, chapter, video, visualization)
- `version`, `sources_checked_at`, `fact_check` status

Cards change only when the *content* should change (an error, a better source), never because of
a learner's taste.

### 2.2 Learner Lens (yours)
- **Profile**: background, goal, time budget, interests (domains for examples).
- **Teaching playbook**: what works for you, derived by replay from signals
  (stated preferences, feedback, outcomes). Versioned: every change bumps `playbook_version`.
  Example entries: "geometry before algebra (works, 0.81)", "avoid sports analogies",
  "pace +1", "show code alongside formulas".
- **Renditions**: your version of a lesson = f(card@version, playbook@version, your history).
  Each records the versions it was built from. A rendition is **stale** when either changed.
  - not yet studied → regenerated on open (or ahead of time in the background)
  - already studied → "Refresh for current me" (keeps old one for comparison)
  - Each lesson keeps immutable **versions** (v1, v2, …) with a "current" pointer; revert moves the pointer
    (see §11).
- **Notes & highlights** (per lesson, anchored to text), searchable, readable by the tutor.
- **Feedback log**: every rating/comment with its target (lesson, section, example, angle),
  plus what the system changed in response ("playbook: geometric angle +", "roadmap: proposed
  inserting 'Dot product intuition'"). Items can be added, edited and deleted, have a kind
  (about this lesson / about me / possible error) and a status (pending, applied in vN, reverted),
  and can be applied to their lesson (§11).
- **Evidence**: graded answers → BKT mastery, FSRS reviews (port of Mentor's engine ideas).

### 2.3 How feedback propagates
```
feedback / outcome ──▶ signal log ──▶ playbook replay ──▶ playbook_version++
                                          │
                     ┌────────────────────┼──────────────────────┐
                     ▼                    ▼                      ▼
        renditions marked stale   roadmap reviewer agent    tutor chat context
        (future: regen on open;   proposes a diff (insert   updated immediately
         past: refresh offered)   prereq, compress, deepen)
                                  → learner approves
```
Feedback can also be **applied** to the lesson at hand: one agent job writes the lesson's next version,
and a word-level diff shows what changed and why. Reverting that version is itself a signal (§11).

## 3. Pages (prototype)
1. **Home**: active goal, next activity, due reviews, streak, recent feedback effects.
2. **Goal setup**: chat with the planner → ultimate goal, constraints, profile; produces the roadmap outline.
3. **Roadmap**: tracks → modules → concepts with state (locked/ready/learning/learned/mastered/rusty), stale badges, research status per module, pending roadmap diffs to approve.
4. **Lesson**: rendition in sections; per-section "explain differently" and feedback; inline checks; code exercise; right panel tabs: Tutor / Notes / Source card; lesson feedback any time.
5. **Me**: profile, playbook (with evidence and the ability to correct), feedback log with effects.
6. **Library**: source KB browser (cards, versions, sources).
7. **Settings**: workspace, provider routing per role, CLI status.

## 4. Backend (built in milestone 2)
- `providers/`: one adapter per CLI (Claude Code headless, Codex, Cursor), common interface:
  `run(job, prompt, schema?, stream) -> events`, rate-limit detection, fallback.
- `jobs/`: research, curate, outline, card-write, fact-check, render, tutor, grade, roadmap-review.
  Long jobs run in a queue with progress streamed to the UI (SSE).
- `engine/`: graph, BKT, mastery gate, FSRS, planner, playbook replay (deterministic, tested, no LLM calls).
- `store/`: SQLite (append-only evidence + signals, versioned cards, renditions) + markdown files.

### 4.1 Provider policy and flags (checked 2026-10-14)
- Anthropic's [legal page](https://code.claude.com/docs/en/legal-and-compliance) forbids third-party
  apps from offering Claude.ai login or routing requests through Pro/Max credentials *on behalf of
  their users*, and explicitly allows an end user to sign in to the unmodified Claude Code binary
  with their own subscription. Our design (one user, their own login, unmodified `claude` binary)
  stays on that side. **If this ever becomes multi-user, Claude access must switch to API keys.**
- The Agent SDK documents API-key auth only, so the adapter shells out to `claude -p` instead.
- Flags: `--output-format stream-json --verbose --include-partial-messages`, `--json-schema` (with
  `--output-format json`, result in `structured_output`), `--model`, `--append-system-prompt-file`,
  `--tools` (restricts built-ins; `--allowedTools` only pre-approves), `--strict-mcp-config`,
  `--setting-sources`, `--max-turns`, `--session-id`/`--resume`, `--permission-prompts none`.
  Do **not** use `--bare` (it skips subscription credentials). Run each job with cwd set to a
  trusted job folder inside the workspace, because `-p` runs that folder's project hooks.
- Unverified: reports that subscription `-p`/SDK usage draws from a separate monthly allowance.

## 5. Open questions
- Card promotion to the shared library: manual for now (milestone 4); automatic suggestions later?
- Codex and Cursor adapters are written against their docs (2026-10-14) but untested against the real CLIs.

## 6. Milestone 2 notes (2026-10-14)
- State lives in the backend; the UI renders snapshots (`GET /api/state`) and posts actions (`POST /api/action`).
- The playbook is replayed from `signals` (stated, reaction, outcome, explain, correction, remove, adjust).
  Weak signals (practice outcomes, "explain differently") don't bump the playbook version, so they never
  trigger re-renders on their own; explicit feedback and settings do.
- Lesson prose is cached per (concept, card version, section, angle, style); `style` encodes pace/depth/rigor.
  While a new rendition is written, the closest cached prose is shown, marked as approximate.
- The card holds the lesson plan (sections, checks with hidden keys, exercises); renditions only write prose.
  Code-exercise tests run in the browser, so they are visible to the learner by design.
- Jobs run on a 3-thread pool; jobs interrupted by a restart are marked failed on startup.


## 7. Milestone 3 notes (2026-10-14)
- **Explain-back**: cards may give one section an `explain` item (`prompt`, hidden `rubric`). The grader job sees
  the rubric and the learner's answer (inside `<learner>` tags, treated as data) but not the lesson chat. Its score
  (0 / 0.5 / 1) is soft evidence for BKT; the mastery gate requires a passed explain-back when the card has one.
- **Placement**: one MCQ per module, written once per goal (`placement_items`). The engine runs a binary search per
  track: knowing a module implies knowing the earlier ones in its track, a gap implies gaps later. At most 20
  questions. Finishing proposes a roadmap diff that compresses known modules; approval sets `modules.known`.
- **Research ahead**: after opening a lesson, answering, approving a diff or finishing a research job, the module
  after the learner's current one is researched if it is still an outline (one research job at a time).
- **Reflection**: triggered on state reads when 7 days have passed since the last one and there have been at least
  3 pieces of feedback since (or via "Reflect now"). Proposals change the playbook only when accepted, as
  `stated` + `correction` signals or an `adjust` signal.
- **Codex**: `codex exec --skip-git-repo-check --ephemeral --sandbox read-only --cd <job> --output-last-message <file>
  [--output-schema <file>] [--search] -`, prompt on stdin, `CODEX_API_KEY`/`OPENAI_API_KEY` removed. Schemas are
  converted to OpenAI strict mode (all properties required, optional ones nullable, nulls dropped afterwards).
- **Cursor**: `cursor-agent` (or `agent`) `-p --output-format json --trust --mode ask --workspace <job>`; no
  structured-output flag, so the schema is appended to the prompt and JSON is parsed from `result`.
  `CURSOR_API_KEY` removed. The prompt is passed as an argument, so very long prompts may hit command-line limits
  on Windows.


## 8. Milestone 4 notes (2026-10-14)
- **Local runner** (decision: review, then run locally). `runner-venv` in the workspace with numpy + torch, set up
  from Settings. `/api/run` returns needs_setup | needs_approval (with the full test code) | blocked (static check)
  | ran. Approvals are stored per (concept, item, sha256 of the tests), so changed tests need a new approval. Runs use
  `python -I -X utf8 -B`, an empty folder, a minimal environment (no tokens or API keys), and a 90 s timeout.
  The server records the evidence. This is not a sandbox; Docker could be offered later as a stricter option.
- **Visuals**: `viz` on a card section is one of vectors2d, lincomb2d, matrix2d or plot. `viz.validate` clamps
  numbers and whitelists plot expressions (numbers, x, up to 3 one-letter parameters, + - * / ^, a fixed function
  list). It runs when cards are written and again whenever a lesson is read. The frontend evaluates plot
  expressions with its own small parser (no eval).
- **Shared library**: `library` keyed by the slug of the concept title. Only fact-checked cards can be promoted.
  The research prompt lists the library; a concept may set `reuse_key` to take a library card (marked passed, not
  re-checked, use counted).
- **Search**: an FTS5 index over notes, the current rendition's prose and cards, rebuilt per query (small data).
- **Anki**: genanki deck per goal with stable ids; MCQ checks and explain-back prompts of learned, mastered or
  rusty concepts; `$...$` math converted to MathJax delimiters.


## 9. Milestone 5 notes (2026-10-14)
Scope chosen: weekly plan and card refresh. Phone access was skipped: the server binds to 127.0.0.1 and has no
authentication, so exposing it on a network needs its own design (pairing token, read-only review scope).
- **Plan** (`planner.py`, deterministic): weekly minutes = settings (default: sum of goals' hours/week), split equally
  over study days. Each goal's share follows its hours/week. Day order: reviews due by that day (including confirmation
  reviews projected one study day after a planned lesson), then lessons from the goal with the lowest used/target ratio.
  Lessons follow roadmap order; a locked lesson is plannable once its prerequisites are learned or planned earlier
  in the week. Modules placement marked known are skipped. A day can overrun by up to 15% to keep a lesson whole.
  Concepts without a card are planned with "needs research"; the next unresearched module per goal is listed.
- **Calendar**: one VEVENT per study day with items, at the start time in floating local time, RFC 5545 escaping and
  75-octet folding. Stable UIDs per date so re-importing updates the events.
- **Card refresh**: `refresh_card` job (route "Card refresh", Opus with web search) reviews the latest version. No
  change → `cards.refreshed_at` is set. A change → a `card_proposals` row (earlier pending ones are superseded). Item
  ids are restored from the previous version so past answers still line up; visuals are re-validated. Approval
  inserts version + 1 (fact-check pending, then the fact-check job runs), which makes renditions stale. Approval is
  refused if the card changed since the proposal. Automatic: on state reads, if enabled, at most 3 jobs a day, oldest
  `COALESCE(refreshed_at, checked_at)` older than 30 days, skipping cards with a pending proposal and never while a
  research job runs.
- The diff the learner sees is field-level (objective, core, formal, why, misconceptions, sources added/removed,
  sections added/removed/changed, with defaults filled in so normalisation alone isn't a change).


## 10. Milestone 6 notes (2026-10-14)
Scope chosen: daily-use readiness, small planner and library items, and the Docker runner option.
- **Launch**: `dsc start` rebuilds `web/dist` when any source file is newer, serves it from FastAPI, and opens the
  browser. `start.ps1` and `start.sh` also create the backend venv on first run.
- **First run**: an empty workspace gets job routes only (`first_run` meta). The demo can be loaded only into a
  workspace without goals, because loading it resets everything, the playbook included.
- **Goal removal**: deletes the goal and all per-concept rows; the playbook (signals) stays. A backup is written first.
- **Backups**: SQLite online backup API to `backups/study-<timestamp>.db`, at most once per 24 h on state reads,
  plus on demand; the newest 14 are kept.
- **Undo**: voids the latest practice evidence for an item (and its grading); if the concept is no longer learned,
  its review is removed. Replay recomputes everything else.
- **Live progress**: research and refresh calls use `--output-format stream-json --verbose`; tool_use events for
  WebSearch/WebFetch become job progress lines (the last 60 are kept). The `result` event is found by type, since
  other events can follow it.
- **Time tracking**: the lesson page sends a 30 s heartbeat while visible and with input in the last 2 minutes;
  `activity(day, concept_id, seconds)`. The week page shows today's actual minutes and the last 7 days.
- **Share suggestions**: fact-checked cards for learned or mastered concepts that aren't shared yet.
- **Docker runner**: `runner_mode` local | docker. Image `deep-study-center-runner:1` (python:3.12-slim, CPU
  PyTorch, unprivileged user). Runs with `--network none --read-only --tmpfs /tmp --memory 2g --cpus 2
  --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges` and the code mounted read-only. Test approval
  and the static check still apply. Untested here: Docker isn't installed.


## 11. Applying feedback to a lesson (2026-11-14)
The learner applies their own feedback to the current lesson, sees exactly what changed and why, and can go back.
- **Lesson versions** (`versions.py`, tables `lesson_versions`, `lesson_heads`). A version is an immutable snapshot of
  every section's prose plus the fingerprint it was written for: card version, style key, angle per section, and the
  playbook version. It records its parent, source (`render` | `apply`), summary, the feedback ids it applied and, per
  change, section, feedback ids, why, how and a short `technique` label. The rendered lesson becomes v1. A complete
  re-render (new card, new style, another angle) adds a `render` version; sections whose fingerprint did not change
  keep the head's text, so "explain differently" in one section keeps feedback applied to the others. The page shows
  the head. While a re-render is incomplete, sections fall back to the prose cache as before.
- **Chosen lessons.** Applying feedback or restoring a version sets `chosen`: the lesson is then treated like a
  studied one and is never re-rendered silently on open; the stale banner offers "Refresh for current me", which
  clears `chosen`.
- **Kinds.** `lesson` (only this lesson; no playbook signals), `me` (also adds playbook signals: the tag rules from
  §6, or a weak non-bumping `stated` signal for a comment), `fact` (claims the material is wrong). A rule-based guess
  is shown at once; for items with text a `classify_feedback` job (route "Feedback") proposes the kind; the learner can
  set it, and an agent never overrides the learner's choice.
- **Edit and delete.** An item owns its signals (`signal_ids`). Edit voids them and adds new ones; delete voids them and
  hides the item. Replay counts voided bumping signals toward the version, and a void that withdraws a bumping
  signal adds a `void` marker that only bumps, so `playbook_version` never goes down and staleness stays correct.
- **Status** (derived): `pending`; `applied` in vN when a version on the head's line contains the item; `reverted` when
  only versions off that line contain it; `routed` (sent to the card check); `done` (handled at once, e.g. a section
  switched angle). An applied item edited later is marked "changed since applied".
- **Apply** (`applyFeedback` → job `apply_feedback`, route "Feedback"). Requires the head to match the rendition (the
  lesson is fully written). One call gets the card, the current lesson, the selected items, the playbook and recent
  reverts, and returns per item a kind, the changed sections, and per change feedback ids, why, how and technique.
  `fact` items are never applied: they set `routed_at` and start a `refresh_card` job with the learner's claims (the
  existing proposal → approval → fact-check flow). The agent may flag an item as fact unless the learner set its kind.
  The new version keeps the base fingerprint and updates the rendition's playbook version, so "me" feedback it
  answered does not make it stale. Offline fallback: each targeted section switches to the next angle that already
  has cached prose for the same card and style (and pins it).
- **Fact guard** (`versions.fact_guard`). The job can only return section prose: checks with hidden keys, exercises
  and the card are not part of its output. A revision is rejected when it names an unknown section, reveals a check
  explanation or explain-back rubric (normalized substring, ≥ 25 characters), is more than 3× the section (min 2,500
  characters), or adds a display formula that is a new claim: not in the card or lesson, and not a numeric worked
  example (digits outside exponents and indices, and only symbols the card's or lesson's math already uses). A change
  without a reason is dropped. Rejections are shown as job progress.
- **Revert** (`revertLesson`). Moves the head to any version of the current card (versions of an older card version
  are refused: the card may have been corrected) and updates the rendition's fingerprint. When applied versions are
  left behind, a `lesson_reverts` row is written and each of their techniques gets a weak, non-bumping `reaction`
  signal (dimension `technique`, −0.1, evidence 0.5), so the playbook shows it, three reverts make it "avoid", and it
  re-renders nothing. Later applies and the weekly reflection get the recent reverts.
- **Diff** (`GET /api/lesson/{id}/diff?a=&b=`). Per section, a word-level diff (difflib over word, space and punctuation
  tokens) as `eq | del | ins` runs with inserted/deleted word counts and the angle on each side. Annotations are the
  changes of versions on b's line but not a's; changes only on a's line are marked `undone`. The UI shows the raw
  Markdown with deleted text red and struck through, inserted text green, using the theme tokens.


## 12. Feedback on a chosen part, lesson guidelines, extra lessons (2026-11-14)
- **References.** Selecting text in a lesson offers "Add note", "Feedback on this" and "Ask tutor". Hovering a formula
  offers "Feedback on formula" and "Note"; each interactive graph has "Feedback on this graph" and "Note". A feedback
  item stores `ref` = {kind: text | formula | viz, quote, sectionId}. Formulas are quoted as their LaTeX source (from
  KaTeX's annotation); text with formulas inside keeps them as `$LaTeX$`; a graph is quoted by its caption. Notes keep
  the same quote.
- **Scope on apply.** Feedback without a section is about the whole lesson and may change any section. Feedback about a
  section or a quoted part changes that part; another section may change only when the agent gives
  `related_because` (directly relevant, or the same issue). A change outside the target without a reason is dropped
  (job progress says so). The diff shows the reason as "Also changed here because". Graphs are card widgets: the agent
  can change the text around them, not the graph.
- **Lesson guidelines** (`guidelines.py`, table `guidelines`, one row per version). Up to 10 concrete instructions to a
  lesson writer, each with why and the feedback ids it comes from. The `distill_guidelines` job (route "Feedback") reads
  recent feedback with kinds, targets and statuses, kept revisions, reverts, the playbook and the current guidelines.
  It writes a point only for a pattern: the same request in two or more items, a general statement by the learner, or a
  kept revision. Lines the learner wrote or kept (`byLearner`) are never dropped. The learner edits them on the Me page
  (one per line). Render and apply prompts include them. They do not make written lessons stale.
- **Next lesson on finish.** A lesson is finished when the learner clicks "I've read it" (first time) or an answer makes
  the concept learned. Then `distill_guidelines` runs and afterwards prewrites the next lesson in roadmap order that is
  not learned and has a lesson plan (render with the new guidelines; never rewrites a studied or shaped lesson).
  Offline, the guidelines stay and the next lesson is still written. Later lessons can still be opened early; they are
  written on open.
- **Extra (remedial) lessons** (`remedial.py`). Struggle score per lesson = wrong answers + 1.5 × failed explain-backs
  + 0.5 × tutor questions + 2 × "I got lost" feedback. At 4 or more, with at least one wrong answer, failed
  explain-back or "I got lost", and while the lesson is not learned and has no open extra lesson, the lesson page offers
  "Vectors (b)" with the reasons. "Not now" stores the score; the offer returns after 3 more points. Adding it inserts
  concept `<id>-rb` (then `-rc`, …) after the lesson and its earlier extra lessons, and runs the single-concept research
  job with a brief of what went wrong (wrong answers with the chosen and right options, explain-back gaps, tutor
  questions, feedback and its quotes, all as learner data). The card is fact-checked as usual.
- Fix: when a single inserted lesson fails to research, the module returns to its earlier research status instead of
  "outline" (which made the whole module research again).

## 13. Ohtani table roadmaps (2026-11-18)
A goal has a `layout`: `list` (the classic roadmap above) or `ohtani` (the default for new goals), chosen on the goal
setup page. An Ohtani table (Mandala Chart) is a 9x9 grid of nine 3x3 blocks:

- **Goal**: the center cell of the center block.
- **Areas**: 8 tracks, one per outer block. `tracks.pos` is the block (TL, TM, TR, MR, BR, BM, BL, ML: clockwise from the
  top left). The area name is the block's center cell; its 8 modules ("steps") fill the cells around it, clockwise from
  the top-left cell. A step's concepts are its sub-steps, as many as the step needs.
- **Merges**: a ninth track with `pos` C. Its 8 modules fill the cells around the goal; merge i joins area i with its
  clockwise neighbour (the cell at C.TL joins TL and TM). `modules.requires` lists the steps of those two areas it
  builds on. The outline prompt (`outline_ohtani.md`) orders the areas so that ring neighbours have real synergy.
- Every step has `modules.done_when`, a concrete check. Research gets it in the module brief; a merge's brief also
  names the steps it merges.
- **Order**: the outline gives each step a wave (1-12). `modules.seq` = steps sorted by wave and interleaved across
  areas, each merge right after the last step it requires (`ohtani.build`). Every "roadmap order" query (research
  ahead, next lesson, weekly plan, placement) sorts by `m.seq, t.ord, m.ord`; classic goals have seq 0 everywhere, so
  their order is unchanged.
- **Locks**: the concepts of a module with `requires` get every concept of the required modules as extra prerequisites
  (a required module that is not researched yet adds a placeholder, so the merge stays locked; one placement marked as
  known adds nothing). Placeholders never appear in the snapshot.
- Placement asks only about area steps, not merges.
- **Grid** (Roadmap page): a cell fills bottom-up by learned/total concepts (known = full); an area cell and the goal
  show the average of their steps. Locked merges are dimmed, the step of the next lesson has a ring, and the cells a
  picked merge builds on are outlined. The detail panel shows the step's "done when", progress, requirements and a
  link to its lessons in the list below the grid.


## 14. Angle mix and writing a lesson in steps (2026-11-18)
**Angle mix** (`engine.choose_angles`). Each section gets one angle, chosen from the angles its card section allows.
The card lists the best fit for the section's purpose first (research prompt). Value of an angle for a section =
playbook score + fit bonus (0.12 first, 0.04 second) - 0.15 for every earlier section of the lesson that already uses
it. So a liked angle gets more sections, but not all of them. "Avoid" angles are used only when a section offers nothing
else; pinned sections keep their angle; a lesson of two or more sections uses at least two angles when its sections
allow it. Before, the single best angle was used in every section.

**Writing a lesson** (`writer.py`). A whole lesson (first write, refresh, new style) is one `render` job with
`full: true`, in steps, each by its own agent (routes in Settings):
1. **Lesson planner**: per section the angle (it may change the suggested mix, never a pinned section), a 1-3 line brief
   for the writer, and whether the card's graph and quiz question fit this learner (`keep` / `new` / `none` for a graph,
   `keep` / `new` for a question). It reads the playbook, the lesson guidelines and the recent feedback.
2. **Lesson assets**: the graphs (built-in widgets only, `viz.validate`) and quiz questions the planner asked for, made
   from the card with the guidelines. A question made for the learner has its own id `p-<section>` and key.
3. **Renditions** (prose writer): the text of each section, with its brief and the graph it shows.
4. **Lesson review**: checks the lesson against the guidelines, playbook and recent feedback, and checks the new graphs
   and questions against the card. Sections with a text problem are rewritten once with the fix; a new graph or question
   with a problem is dropped (the card's one is shown).
Only the prose writer is required: without a model for another step, the lesson is written without it. Single-section
renders ("explain differently", a pin) run only the prose writer, with the stored brief. The plan, the learner's assets
and the review are stored per (lesson, card version) in `lesson_plans`; the card never changes. The lesson view, grading
(`actions._card_item`), revealed answers and the extra-lesson brief use the learner's questions; spaced reviews and the
Anki deck keep the card's questions. While a writing job runs, only that job snapshots a lesson version, so a draft
before the reviewer's fixes never becomes a version. The lesson page shows "How this lesson was written for you" (plan,
review, fixes) and "made for you" on graphs and questions. Not yet: code exercises are not remade per learner, and the
Change log shows text changes only (not graph or question changes).

## 15. Runnable code, IDE-style code, annotated formulas (2026-11-18)
- **Runnable code**: every ```python block in lesson text is an editor with Run (Pyodide in the browser, standard library
  and NumPy; packages a block imports are loaded first). The blocks of one lesson share one namespace, like notebook cells:
  running a block first runs the earlier blocks that have not run yet. "Restart" clears the namespace. The text writer
  and the apply-feedback agent are told this, so they write blocks that run as they are.
- **IDE look**: code (blocks, runnable blocks, exercises) uses a dark editor theme with line numbers and a small Python
  highlighter (`highlight.ts`, no dependency): a transparent text field over the colored code. Run buttons are green.
- **Explorable formula** (`viz` type `formula`, `Formula.tsx`): `tex` with `{{id}}` per part; each part has its own TeX
  (it may contain other parts), a label in plain words and a color. Hovering a part shows its label (no arrows); a legend
  under the formula lists every part in its color, with a slider for each parameter (parameter parts can also be dragged
  in the formula). Every change is explained: the formula again with the learner's values (parentheses where a value
  follows a number or is negative) and `resultExpr` as its result; a line "σ went from 1.0 to 1.6 (when it grows: …)"
  from the parameter's `effect`, with the result before and after; and a plot of `plotExpr` over x or over one parameter
  (`plotVar`, with a dot at its value), the starting curve dashed. `viz.validate` accepts only safe TeX (no `\html…`,
  `\href`, `\url`, macros), known parts and safe expressions; KaTeX trusts only the `\htmlClass` the widget adds itself.
  Research, the planner and the asset writer are told to give every key formula such a widget, with a result or a plot.
- **"What if" in a formula**: the learner clicks a colored part in the legend and types another form for it (shown as
  TeX by `expr.toTex`); every valid change shows at once. A part can have `expr` (its calculator form; a parameter part
  uses its name, and an edit replaces that name everywhere) and 2-4 `variants` (`tex`, `expr`, `why`): suggested forms
  shown as hints, whose `why` appears when the learner types one. `plotExpr`/`resultExpr` refer to a part as `[id]`, so
  an edit changes the plot and the result. When something is edited, the real formula ("real") and the learner's
  ("yours") are shown side by side with a separator, or one above the other when they do not fit; the plot shows both
  curves with a real/yours legend. `checks` (`area` = integral of the plot over its range, `peak`, `at`,
  `result`; optional `expect`) are measured live for the real formula and the changed one (✓/✗), the variant's `why`
  says what breaks, the real curve is dashed, and "Ask the tutor why" puts the question, with the check numbers, into
  the tutor chat. The reviewer checks that every `why` agrees with the checks.

## 16. Widgets are computed before they are shown (2026-11-18)
- `vizcheck.py` computes a formula widget exactly as `Formula.tsx` does (same expression language, no `eval`): the
  result, the plot (400 points), every check and every "what if" variant, at the start values. `viz.validate` removes
  what cannot work: a result or plot that cannot be computed, a check the real formula fails, a variant that changes
  nothing visible. Validation is stable: validating a validated widget changes nothing (tested on every real widget).
- Each value is tied to the part that shows its symbol (y in "y^2"); x becomes a value when a plot runs over x and a
  part shows x. A value inside a larger part gets its own slider row. Each simple part gets its calculator form from
  its TeX (`texexpr.py`: x² → `x^2`, σ√2π → `sigma*sqrt(2*pi)`), so the learner edits the whole colored part.
- `viz.inspect` lists the problems in plain words. `writer.check_viz` sends a widget with problems back to an agent
  once ("Lesson assets" route, `fix_widget.md`) and keeps the better version; this runs for research, card refresh and
  graphs made for the learner. Remaining notes are stored with the graph (`vizNotes`) and shown under it ("The app
  checked this graph and adjusted it").
- The lesson reviewer gets "Graph numbers" (`vizcheck.describe`): the start values, the result, each check and each
  variant's numbers, so it can check every "why" against them.
- `tests/fixtures/formula_widgets_real.json` holds the widgets the real model wrote; `test_vizcheck.py` checks each one
  (stable, computable, passes its own checks, every variant changes something, every value is shown).

## 17. The learner's own sources: books, articles and posts as PDF (2026-11-19)
- Purpose: the learner can base a goal on books, articles or posts they choose. The roadmap follows their chapters, and
  cards cite their pages ("Title, p. 42"), with a link that opens the PDF at that page.
- Upload: Source library → "My sources" → "Add PDF", or "Your own sources" in the new-goal setup. The file goes to
  `POST /api/sources?filename=&kind=&link=` as the raw body (no multipart). It is saved as `<workspace>/sources/<id>.pdf`
  (200 MB at most). `GET /api/sources/<id>/file` serves it, so `…/file#page=N` opens a page in the browser.
- Reading (`sources.py`, job `ingest_source`, pypdf): the text of each page (`source_pages`), a full-text index
  (`source_fts`, SQLite FTS5), the PDF outline as the table of contents, and the title and author from the metadata
  (a title the learner set wins). A PDF with text on fewer than 1 in 5 pages is "no text" (a scan); there is no OCR.
- Use per goal (`goal_sources`): chosen on the goal's home page, "Sources for this goal": two lists (used, not used);
  tick a box or drag a source between them. "Add PDF to this goal" there uploads and links at once. A PDF added in the
  library is not linked to any goal; the library shows which goals use each source ("Used in goals") and has "Learn",
  which opens the book-goal page with that source in the basket. Sources chosen in the goal setup are linked to the
  new goal. The library tab is in the URL (`/library?tab=mine`).
- Roadmap: the outline prompts (`outline.md`, `outline_ohtani.md`) get the tables of contents and build the roadmap
  around them, with the chapters named in module summaries.
- Research: `research_module` gets the 8 pages of the goal's sources that match the module best (bm25 over title,
  summary and "done when"; at most 900 characters each). Cards based on them cite the url `source:<id>#page=<n>`;
  the app opens it as the PDF at that page (`sourceHref`).
- Actions: `linkSource`, `editSource` (title, kind), `deleteSource` (removes the file, pages and links; cards that cite
  it keep their text). Deleting a goal removes its links, not the sources.

## 18. Book goals: the 80/20 core of chosen sources (2026-11-19)
- Purpose: a lighter goal for a learner with no time to read whole books. Its scope is one or more of their own sources
  (PDF books, articles, posts). They get the ~20% of each source that carries ~80% of its value: the key concepts,
  arguments and frameworks, in the order that builds understanding, with lessons that cite the pages.
- Start: Source library → "My sources" → "Understand books (80/20)" (`/goal/book`). The learner ticks sources, or drags
  them from the list on the left into the "Goal basket" on the right. Only sources with status `ready` can be used: the
  page waits for sources still being read and refuses scans without text. Two questions only: why these sources, and
  the hours a week (with a deadline). Background and teaching style come from the profile of the newest earlier goal.
  The shape is an Ohtani table (default) or a classic roadmap.
- Outline (`createGoal` with `kind: "book"` → job `outline`, `goals.kind = 'book'`). The outline prompt gets the numbered
  sources with their tables of contents (levels 0-2); a source without one gets the first words of up to 60 sampled pages
  (`books.structure_text`). `_book.md` is added as `{focus}`: rank every chapter as core, supporting or skip (core and
  supporting about 20-30% of the pages), build the roadmap only from core and supporting chapters, name chapters and
  pages in step summaries, and return every ranked chapter in `selection` (source number, chapter, pages, rank, why,
  step). The schema is the layout's schema plus `selection`.
- The cut (`book_cuts`, `books.save`): one row per ranked chapter; status `kept` (core, supporting) or `cut` (skip).
  Its step is the step the agent named (exact title, case-insensitive), else the area step with most words in common;
  never a merge step. Unknown sources and ranks are dropped.
- Roadmap page: "The 80/20 cut" lists what was left out (per source, with why and pages) and what was kept (with rank
  and step). "Bring back" (`restoreCut`) adds a left-out chapter: to a step that is still an outline, as "Also covers
  (brought back by the learner): …" in its summary with one more planned lesson; to a researched step, as a new lesson at
  its end, researched on its own from the pages (single-concept `research_module`). The row becomes `restored`.
- Research for a book goal gets 12 matching pages instead of 8 and `_book_research.md` as `{focus}`: teach what the
  sources say, cite the pages, use the web only to check, to explain the same idea better, or for a prerequisite.
- Not yet: films and videos (only PDF sources exist), and undoing a "Bring back".

## 19. Thinking box, confidence and dictation on every answer (2026-11-20)
- Purpose: the agents see how the learner reasons, not only whether an answer is right. Two people can give the same
  wrong answer for different reasons. (Step 1 of the knowledge-graph rework.)
- Every quiz question (lessons, reviews, placement) has an optional "Think out loud" box and a "How sure are you?"
  slider (0-100 %, "not set" until moved). Explain-back has the slider too; its answer is already the thinking.
- Dictation: a "Dictate" button on each box uses the browser's speech recognition (Chromium); spoken phrases are added
  at the end of the text. It is hidden where the browser has none. A local Whisper model is a later option.
- Stored with the answer: `evidence.thinking`, `evidence.confidence`, `gradings.confidence`,
  `placement_answers.thinking/confidence`. The answer shows them back after checking.
- Scoring: a right answer at 25 % or less ("Guess") is half evidence (score 0.5). It is shown as right, moves
  P(learned), but does not count as a known item. In a review, a right guess is not recall (the card goes rusty).
  In placement, a right guess does not mark the module known.
- Agents: `state.reasoning_log` lists recent answers with thinking or confidence ("wrong while sure" = likely
  misconception, "right, but a guess"), plus graded explain-backs. The lesson planner, the prose writer and the tutor
  (for that lesson) get it.

## 20. The probe: where you stand (2026-11-20)
- Purpose: find the edge of what the learner knows for a goal, the way a good tutor would: short questions, each chosen
  from the earlier answers and the learner's thinking. It replaces the placement quiz (one fixed, hard question per
  step). Step 2 of the knowledge-graph rework.
- Page `/probe` ("Where you stand"; `/placement` opens it too). The outline job starts the first round, so it is ready
  when the roadmap is. The roadmap shows a banner until the result is used ("Not now" hides it: `dismissProbe`).
- Rounds (`probe.run_round`, job `probe_round`, route "Placement"): the agent (`probe.md`) gets the goal and profile,
  the steps in order without merge steps, what the learner learned in other goals (concepts with a review, known steps),
  and every answer with its thinking and confidence. Since §26 a round is one question, chosen from all earlier
  answers; the agent brackets the edge of each area (it starts high, see §26). Questions are short (under 30 s each,
  "I don't know" added by the page) and their options are shuffled. Limit: 15 questions; at the
  limit, or on "Stop and see where I stand" (`probeAssessNow`), the agent must assess. A reply without usable
  questions fails the job (the page offers "Try again"); it never ends the probe.
- Each answer (`probeAnswer`: item, choice or null, thinking, confidence) shows right / wrong and a one-line why at
  once. When a round is complete, the next round is asked for.
- Assessment (`probe_results`): a one-line summary, the edge in words, the ideas to fix (misconceptions), and per
  step known / partial / unknown with a note. "Use this for my roadmap and lessons" (`applyProbe`): known steps become a
  roadmap proposal (compress, as before), and the edge and misconceptions are added to the goal profile, which
  research, the lesson writer and the tutor read. "Retake" (`resetProbe`) clears it; known steps stay known.
- Tables: `probe_items` (one row per question, with the answer, thinking and confidence), `probe_results`. The old
  `placement_items` / `placement_answers` stay for old data; `engine.placement` and the `placement_bank` job are gone.

## 21. One knowledge graph (2026-11-20)
- Purpose: knowledge belongs to the learner, not to one goal. An idea learned for one goal is known in every goal,
  and later steps ("Teach me X", the skill-tree map, recall practice) work on one graph. Step 3 of the rework.
- Model (`graph.py`): a node is one idea (`nodes`: id, title, statement, kind, origin). Every concept (a lesson in a
  goal's module) points to one node (`concept_nodes`); concepts in different goals can share a node. A link means
  "this idea is used to reason toward that idea": links come from the concepts' prerequisites (mapped to nodes) and
  from the `links` table (for later steps). `node_fts` indexes node titles and statements.
- Automatic: `graph.sync` gives every concept without a node its own node (node id = concept id). It runs before
  any read (state, graph view), also inside an open transaction, so code that inserts concepts needs no change.
  Existing workspaces get their nodes on first use; states stay the same until ideas are shared.
- Shared state: `state.concept_states` uses the evidence of every concept on the same node
  (`graph.evidence_for`); an explain-back passed on a sibling counts for this concept. `graph.states` gives the
  learner's state per node from all evidence (same rules as a concept).
- Research dedupe: `research_module` gets up to 15 existing nodes that match the module (`graph.candidates`,
  full-text search, not the module's own) and may set `same_as: <node id>` for a concept that is the same idea at
  the same depth. That concept points to the existing node, and without its own card it reuses the node's newest card
  (fact-check status carried over). An unknown id is ignored.
- Deleting a goal removes its concepts' mappings and nodes that no concept uses any more; shared nodes stay.
- API: `GET /api/graph` → `{nodes: [{id, title, statement, kind, state, mastery, goals, concepts}], links: [{src, dst,
  origin}]}`. The map that shows it is step 5.
- Not yet: reviews are still scheduled per concept (a shared node learned in goal A has no review row in goal B);
  nodes smaller than a concept (statements from sessions) come with step 4.

## 22. Study sessions: "teach me X" (2026-11-20)
- Purpose: learn anything, with or without a goal. DSC maps the topic, connects it to the knowledge graph (§21),
  checks what the learner holds, and teaches one small reasoning step at a time, so each step "feels obviously true".
  What they learn goes into the graph. Step 4 of the rework.
- Page `/study` ("Study" in the sidebar): one text field with dictation, optional own sources (ready PDFs), the list
  of past sessions. A session is `/study/<id>`, with a phase bar: Map the topic → What you know → Plan → Learn →
  Add to your graph → Done. "Delete session" removes it.
- Phases (`session.py`, `sessions.status`; jobs `session_sketch`, `session_probe`, `session_turn`, `session_extract`):
  1. Sketch ("Study plan" route, `session_sketch.md`): 4-12 ideas with `prereq_keys`, one `target_key`, and
     `same_as` for ideas already in the graph (the prompt lists the graph ideas that match the topic, plus learned
     ones, with their state). Each idea becomes a node at once: the existing node, or a new one (origin "session",
     `session_nodes.created = 1`), with reasoning links between the ideas. Ideas the graph holds as learned or
     mastered are marked known.
  2. Probe ("Study tutor" route, `session_probe.md`): quick questions on the ideas not known yet, one at a time,
     at most 10 (§26); "Stop asking and show the plan" ends it and still writes the result. The result per idea:
     known / partial / unknown / untested, what the learner reasons from, where their reasoning stopped, and the
     misconceptions; plus where to start.
  3. Plan: the ideas to teach, prerequisites first (topological order), the target last. The learner can untick ideas
     they hold (`sessionKnown`; not the target), then "Start learning" (`sessionTeach`).
  4. Teach (`session_turn.md`): per idea **predict** (a question before any explanation, answered with thinking and
     confidence; "I don't know" allowed) → **explain** (60-200 words, fitted to the prediction and thinking, Markdown
     with math and runnable Python) + **check** (a new setting). A wrong check gets one **repair** (another angle +
     a new check); after a second miss the session moves on.
  5. Extract ("Study plan" route, `session_extract.md`): a statement per taught idea (what the learner now holds,
     written into new nodes), reasoning links between the ideas and other graph ideas (`links`, origin "session"),
     and a summary for the learner with what to practise next.
- Evidence: probe and check answers are evidence on the idea's node (`evidence.concept_id` = node id, item
  `<session>-<item>`, guess rule as in §19); predictions are not evidence. The graph counts evidence on a node id
  directly (`graph.states`, `graph.evidence_for`), so a lesson later mapped to the same node (research `same_as`)
  sees it. Understanding alone does not make a node "learned" (3 right items + recall practice, step 6): taught
  ideas show as "learning".
- A failed step shows "Try again" (`sessionRetry`), which re-runs the step of the current phase.
- API: `GET /api/session/<id>` (the session as the page shows it; answer keys only after answering). Snapshot:
  `sessions` (list) and `lastSession`.
- Not yet: graphs (viz widgets) inside explanations, prefetching the next step, attaching a session to a goal.

## 23. The knowledge map (2026-11-20)
- Purpose: see everything you know and everything you still need as one skill tree, so progress is visible and a
  goal's missing building blocks are obvious. Step 5 of the rework. Original look; no game art is copied.
- Page `/map` ("Knowledge map" in the sidebar). It reads `GET /api/graph` (§21), which now also returns, per node,
  `lessons` ([{id, title, goalId}]), and the lists of `goals` and `sessions`.
- Layout (`components/graphLayout.ts`, no library): depth = longest path from a root idea; basics at the bottom,
  reasoning goes up; nodes inside a layer are ordered by barycenter sweeps (6 rounds up and down) to reduce crossing
  links, with ideas of the same goal or session kept together at the start. 1000 nodes take about 5 ms.
- Show: "Everything" (option "Hide ideas not started"), one goal, or one study session. For a goal or session, the
  map shows its ideas plus everything they build on (other ideas are dimmed); its target ideas (no next idea inside
  it) have a dashed halo; the bar says "N of M known · K still needed". Opens on the active goal.
- Node look: strong (glow) and known = green; learning / rusty = amber with a ring for mastery; ready = blue outline;
  needs others first / not started = dashed. Links between two known ideas are green; arrows point to the idea a
  link helps you reason toward.
- Interaction: wheel to zoom at the cursor, drag to pan, +/−/Fit; "Find an idea" marks matches, Enter selects and
  centers the first. Click an idea: a panel with its state, statement, "Builds on" / "Leads to" (click to jump),
  its lessons (opening one switches to its goal first), its study sessions, and "Teach me this" (opens Study with the
  idea as the topic).
- Not yet: practice from the map (step 6), saving the zoom and focus per user.

## 24. Recall practice (2026-11-21)
- Purpose: understanding an idea is not the same as recalling it when a problem calls for it. Recall works from cues,
  so practice widens and strengthens them: problems that make the learner find and use the idea themselves. Step 6
  of the rework.
- Page `/practice` ("Practice" in the sidebar, with the number of ideas due): "Due now" lists due ideas and ideas
  learned recently but never practised, with "Practise 5 problems"; "My own problem" takes a pasted or dictated
  problem, or a page of a ready PDF source (one problem). On the map, "Practise" on an idea starts a run on it.
- What is due (`practice.due`): ideas whose own review is due (`node_reviews`), lesson reviews that are due (mapped
  to their ideas), then ideas in state "learning" (mastery ≥ 0.2) that were never practised. A run takes up to 6.
- A run (`practices`, `practice_items`; jobs `practice_next`, `practice_judge`; route "Practice", Sonnet):
  - Problem (`practice_next.md`): 1-3 ideas, self-contained, never naming the idea or method (finding it is part of
    recall), with a hidden worked solution and key steps. Level 1-4 (`practice.LEVELS`): one idea in a familiar
    setting → one idea in a new setting → two ideas → two or three ideas in an unfamiliar setting. A clean solve
    raises the level; giving up or 2+ hints lowers it.
  - The learner sends thinking in chunks (typed or dictated). The judge (`practice_judge.md`) sees the hidden
    solution and returns solved / progress / stuck / wrong with short feedback, and the smallest hint when asked
    for or when stuck or wrong; never the solution. "Give up" ends the problem and shows the solution; "Stop" ends
    the run.
- Result per problem: score 1.0 solved without hints, 0.7 with one, 0.4 with more, 0 given up. It is evidence on each
  target idea (`evidence.concept_id` = node id; kind "practice", or "review" once the idea is learned, so it can
  become strong or go rusty) and updates the idea's FSRS card in `node_reviews` (`engine.new_card`, `engine.review`).
- API: `GET /api/practice/<id>` (solutions only for closed problems), `GET /api/practice-due`. Snapshot:
  `practices`, `lastPractice`, `practiceDue`.
- Prompt rule for every job: write money as `\$35k` or "35k USD", because a bare `$` starts math.
- Not yet: replacing the old Reviews page (one quiz question per lesson) with recall practice; prefetching problems.

## 25. Desktop app and the Claude API with your own key (2026-11-21)
- Purpose: anyone can install DSC and use it without a terminal, Python, Node or the agent CLIs. Step C1 of the TODO.
- Shell (`desktop/`, Tauri 2): a native window shows a small "Starting…" page (`desktop/ui/index.html`), starts the
  bundled backend `dsc-backend.exe serve --port <free port>` (no console window), waits until the port answers (90 s
  at most), then loads `http://127.0.0.1:<port>/`. On exit it stops the backend. If the backend does not start, the
  page shows the error and the log path. The backend log is `%LOCALAPPDATA%\app.deepstudycenter.desktop\logs\backend.log`.
- Backend bundle (`desktop/backend/dsc-backend.spec`, PyInstaller, one folder of about 37 MB): the `dsc` package with
  its prompts and data, uvicorn, keyring, and the built UI (`web/dist`, found through `sys._MEIPASS` in `cli.py`).
- Data: the same workspace as the web app (`~/DeepStudy`, or `DSC_WORKSPACE`), so the web app and the desktop app share
  one learner's data. Run only one of them at a time.
- Build: `cd desktop && npm install && npm run build` → `desktop/src-tauri/target/release/bundle/nsis/Deep Study
  Center_<version>_x64-setup.exe` (NSIS, per-user install, no admin rights). Icons come from `desktop/app-icon.png`
  (`desktop/make_icon.py`, then `npm run icons`).
- Claude API provider (`providers.AnthropicAPI`, provider id "anthropic", official `anthropic` SDK):
  - Models: opus → `claude-opus-5-5` (effort `high`), sonnet → `claude-sonnet-5-5`, haiku → `claude-haiku-5-5`.
    Thinking is adaptive (always on for these models).
  - Streaming with `max_tokens` 64000; research jobs get server-side `web_search_20260209` and `web_fetch_20260209`
    (20 uses each), and a `pause_turn` is resumed (6 rounds at most); their searches show as job progress.
  - Structured output through `output_config.format` (the schema made strict by `api_schema`: no numeric or length
    limits, `minItems` 0 or 1). With web tools the JSON is asked for in the prompt instead (web citations and a JSON
    output format do not mix).
  - Server-side refusal fallbacks are on (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`); a refusal
    or a cut-off answer fails the job with a clear message.
  - Order of providers for every job: the routed one, then the Claude CLI, then the Claude API when a key is set.
    "Use the API for all jobs" routes every job to it (a Codex job goes to Opus).
- The key (`apikey.py`): `ANTHROPIC_API_KEY` from the environment, else the system credential store through `keyring`
  (Windows Credential Manager, service "Deep Study Center"). `setApiKey` checks it first with the Models API (no
  tokens used); a rejected key is not stored. The key is never sent to the UI, written to the database, logs or job
  folders. Settings → "Anthropic API key", and a "Connect a model" card on the welcome page when no provider is found.
- Not yet: Pyodide (runnable Python) still loads from a CDN (needs the network), code signing
  (Windows SmartScreen warns on the first run of an unsigned installer), automatic updates, macOS and Linux builds.

## 26. A sharper probe (2026-11-22)
- Purpose: find the edge of the learner's understanding with fewer, better questions, and give the teacher a clear
  picture: what the learner reasons from, where their reasoning stops, and which wrong beliefs to repair. TODO B7.
  The ideas come from the probe of learnharness (AGPL-3.0); DSC copies no code or prompt text from it.
- One question at a time (both probes): each probe job returns one question (`session_probe`: `question`;
  `probe_round`: a list of at most 1), chosen from every earlier answer and its thinking. Limits: 10 questions in a
  study session (`session.PROBE_MAX`), 15 in the goal probe (`probe.MAX_QUESTIONS`).
- Bracketing the edge (prompts `session_probe.md`, `probe.md`): start near the top of what the target needs; a right
  answer with sound reasoning allows a big jump; weak reasoning or confidence at or below chance allows a small step at
  most; a miss or "I don't know" moves toward the prerequisites. Drill into a detail only when it would change what
  gets taught. Stop when the teacher has enough; do not raise the level until a miss.
- Questions that split mental models: a prediction, a comparison or a short case where two mental models give two
  answers. One question can give evidence on several ideas.
- Fair options (`mcq.py`, every generated multiple-choice question: both probes, study-session predict and check,
  lesson checks):
  - `mcq.SCHEMA` puts `explanation` before `answer`, so the model reasons out the right option first, then commits.
  - The prompts ask for bare claims of the same form, wrong options built from real misconceptions, and no
    "all/none of the above".
  - `mcq.shuffle` puts the options in a random order when the question is stored and remaps `answer`. A refreshed
    lesson card keeps the order of a check it already had, so past answers still line up. Tests turn the shuffle off
    (`mcq.SHUFFLE`, autouse fixture in `conftest.py`).
- Confidence compared with chance: confidence is the learner's estimate that the pick is right. A right answer counts
  as a guess (half evidence; no recall in reviews) when the confidence is at or below max(1/n, 30%) for n options
  (`mcq.guess_line`, `progress.guessed`). The prompts show "confidence 70% (chance: 25%)". The slider snaps to
  0 / 30 / 50 / 70 / 90 / 100 % ("I think it is wrong", "Doubtful", "Coin flip", "Fairly sure", "Sure", "Certain");
  it stays "not set" until the learner touches it.
- The study-session result (`session.apply_result`): per idea `probe = {level, reasonsFrom, runsOut, misconceptions}`
  in the session's `ideas` JSON, with level known / partial / unknown / untested ("untested" never sets a level, so the
  idea is taught), and `sessions.probe_start` (where to start). A new result replaces an earlier one. The text is
  written to the learner as "you". The plan page shows "Where to start" and, under each idea, "You reason from",
  "Your reasoning stopped at" and "To fix". Every teaching turn of an idea gets its result and the start advice
  (`session_turn.md`: `{probe}`, `{start}`).
- Checked with a real run on a copy of the workspace (Bayes' theorem, 5 questions): the probe started at the target,
  moved to a prerequisite after a miss with low confidence, re-tested the missed idea, and stopped; the first teaching
  question built on what the result said the learner already uses.
- Not yet: free-recall probe questions (the learner writes the answer; better fit for practice), and a separate
  "thinking while reading" field for teaching checks.

## 27. Local dictation with Whisper (2026-11-22)
- Purpose: dictation without sending the learner's voice to a cloud service, also in desktop webviews that have no
  speech API. TODO C2.
- Backend (`dictation.py`, faster-whisper 1.2.1 on the CPU, int8; `av` pinned to 15.1.0 because av 16+ breaks
  faster-whisper 1.2.1):
  - Settings in `meta`: `dictation_mode` "browser" (default) or "local"; `dictation_model` "base" (default, 142 MB,
    about 1.2-1.8 s for a 4 s phrase on a laptop CPU) or "small" (464 MB, more accurate, 5-6 s per phrase).
  - Download: action `downloadDictationModel` → job `dictation_model` → `huggingface_hub.snapshot_download` of
    `Systran/faster-whisper-<size>` (only the files the model needs) into `<workspace>/models/whisper`. The "xet"
    transfer is turned off for it, so the folder grows while it downloads and the job reports "downloaded N%" (the
    folder size, also for paths longer than 260 characters). An incomplete download fails the job.
    `removeDictationModel` deletes a model.
  - `POST /api/transcribe` (raw audio body: webm/opus from the page, or ogg/wav; at most 8 MB) → `{text, language,
    seconds}`. The model loads from the local folder (no network) on the first phrase and stays in memory (one model
    at a time). The audio goes to a temporary file that is deleted at once; it is never stored. Language is detected
    per phrase. Voice-activity filtering drops silence.
  - The state snapshot has `dictation: {mode, model, available, ready, models: [{id, label, mb, installed}]}`.
- Page (`components/localDictation.ts`, used by `useDictation` in `ThinkingInput.tsx`):
  - The local engine is used when the mode is "local" and the chosen model is downloaded, or when the browser has no
    speech API and a model is downloaded. Otherwise the browser's speech API is used. The Dictate button's tooltip
    says "(on this computer)" for the local engine.
  - One `MediaRecorder` per phrase on the microphone stream. A level meter (RMS against a running noise floor) ends
    a phrase after 0.7 s of silence, or after 20 s. A phrase with less than 0.25 s of speech is dropped. Each phrase
    is posted on its own; results are added in order. While a phrase is written down the hint says "Writing down what
    you said…".
  - Settings → Dictation: the engine, the model (download with progress, delete), and a box to try it.
- Checked: unit tests (settings, download job with progress, incomplete download, transcription, errors); a real
  download of the base model; a real transcription of a spoken test phrase as WebM and WAV with Hugging Face network
  access turned off; and the full page path (the test phrase played into a stand-in microphone in the Settings box:
  two phrases came out right and in order).
- Desktop bundle (`desktop/backend/dsc-backend.spec`): collects faster-whisper (with its voice-activity ONNX file),
  CTranslate2's DLLs, onnxruntime and av; `hf_xet` is left out. The backend folder grows from about 37 MB to 266 MB
  (av 81 MB, CTranslate2 61 MB, onnxruntime 44 MB), the installer from 19.7 to 74.2 MiB. Checked: the bundled backend
  downloaded the base model with progress and wrote down a test phrase in 1.2-1.8 s.
- Not yet: a test with a real microphone (TODO A2), and a check that WebView2 in the desktop app allows the
  microphone (it asks the learner once).
- Model downloads write no progress bars or Windows symlink warnings to the backend log.

## 28. Book study: "teach me this book" (2026-11-22)
- Purpose: the main flow from now on. The learner picks one PDF and says "teach me this book"; DSC maps the book into
  its own idea graph, joined to what the learner already knows, and teaches it one part at a time with the book's own
  pages, then makes them practise it. Big goals and the Ohtani table stay, as an extra capability on hold (TODO D).
- Parts (`bookstudy.parts_from_outline`): the chapter level is the shallowest outline level with at least 3 entries; a
  chapter's sections (next level) are its parts, and pages before the first section go to the first one. A chapter
  without sections is one part. Front matter (contents, index, acknowledgements, …) is left out. A PDF without an
  outline is cut into parts of 12 pages. Example: "Inference Engineering" (259 pages) gives 11 chapters and 45 parts.
- Map (action `studyBook` → job `book_map`, route "Book map", Claude Opus, prompt `book_map.md`): one call per chapter,
  with the chapter's parts and page ranges, the chapter's page text (at most 3,000 characters a page and 80,000 a
  chapter), the ideas of earlier chapters (their keys), and up to 40 graph ideas that may be the same. Per part: a
  summary and its ideas (key, title, statement, kind: concept / formula / method / fact / term, pages, prerequisite
  keys, `same_as`). A `same_as` idea reuses the graph node (its title stays); other ideas become nodes with origin
  "book". Prerequisites become links (origin "book"), also to earlier chapters (`c<N>-<key>`) and to older graph ideas.
  `books.chapters_done` counts finished chapters: a failed map stops with status "failed", and "Continue mapping"
  (`bookRetry`) starts at the next chapter. A retried chapter replaces its own earlier result.
- Tables: `books(id, source_id, title, status, chapters_done, chapters, …)`, `book_parts(id, book_id, ord, chapter,
  chapter_title, title, page_from, page_to, summary, session_id, practice_id, status)`, `book_nodes(book_id, node_id,
  part_id, key, pages, created, ord)`; `sessions.book_part`.
- Study a part (`bookStudyPart` → `session.start_from_ideas`): a study session (§22) with the part's ideas and, before
  them, the ideas from outside the part that they build on (another part, another book, a goal). No sketch step; ideas
  the graph holds as learned are known, the rest go through the probe (§26), the plan, predict → explain → check, and
  the extract step. The teaching turns get only the part's pages (`sources.excerpts(..., pages=(from, to))`; when no
  page matches the words, the range's first pages). When the session is done, the part is done (`on_session_done`).
  Opening a part again opens its session.
- Homework (`bookHomework`): a recall practice (§24) over the part's ideas; it reopens while it is active. Each idea
  then has its own review schedule, so later "practise what is due" includes it.
- Idea links (D4): every teaching turn gets up to 40 graph ideas it may link (the session's ideas, their neighbours,
  and ideas whose words match the current idea). The tutor links the first mention as `[words](#idea/<id>)`;
  `session.idea_links` turns a link to any other id into plain text. The page (`Markdown` → `IdeaLink`) shows such a
  link with a dotted underline; hover or click opens a card from `GET /api/graph/node/{id}`: the statement, the state,
  the books with part and pages, the sessions and goal lessons where it appears, what it builds on and leads to, and
  "Show on the map".
- Map view (D5): `graph.view` has `books` and each node's `books`; the knowledge map can show one book ("This book on
  the map" on the book page), and a node's panel lists its books.
- Pages (minimal; the UI will be redesigned with the user): Study → "Study a book" (pick a ready PDF → "Teach me this
  book"), and `/book/:id`: progress while mapping, the next part, chapters with their parts (pages, number of ideas,
  status, "Study" / "Open", "Homework"), and each part's ideas with their state, "in your graph", "also in other books".
  A study session of a book part shows the book and pages above its title, and "Homework" and "Back to the book" when
  it is done.
- Removing a book study (`deleteBook`) keeps ideas that have evidence or that another book, session or goal uses.

## 29. Map views and the mock workspace (2026-11-22)
- Purpose: the learner chooses how to see the knowledge map; and the UI can be checked with full data (every state,
  several books, sessions, lessons with formulas and graphs) without studying first.
- Views (Knowledge map → "View", saved in `meta.map_view` by `setMapView`, in the snapshot as `mapView`):
  - Tree: the layered skill tree (§23), basics at the bottom.
  - Graph: an Obsidian-style force graph; every idea colored by its state, size by its number of links; names appear
    when zoomed in, or for the idea in focus and its neighbours.
  - Nebula: a force layout pulled into one soft cloud per book or goal (its cluster color); shared ideas sit between
    their clouds.
  - Skill wheel: the goal's basics in the core; each book a sector sized by its ideas; each chapter a spoke from its
    basics (inside) to its most advanced ideas (rim); links across sectors only show for the idea in focus.
  - Cells: circle packing, book > chapter > idea; arcs for links across books.
  - Territories: a hex map; every idea a hex, every book a country with the goal in the middle; basics at a country's
    heart; learned hexes light up, gold for "know strongly"; shared ideas on the borders.
  - Globe: ideas on a sphere you turn by dragging; each book a region; the far side fades.
  All views share the page's focus filter, search (Enter selects and centers), the side panel, hover tooltips and a
  highlight of the idea in focus with its neighbours. The canvas views (`components/MapCanvas.tsx`, d3-force and
  d3-hierarchy) pan by dragging and zoom with the wheel or the +/− buttons.
- States and colors (theme tokens `--st-*`, light and dark): know strongly (mastered, gold with a glow), learned,
  learning (a pie of its mastery), due for review (rusty), ready to learn, needs others first (locked). An idea in a
  second book has a second ring in that book's cluster color.
- Clusters (`graph._clusters`, in `graph.view`): each idea's `cluster` is the book that made it (else its first book,
  goal or session, else "loose"); `also` lists the other books and goals; `chapter`, `chapterTitle` and `order`
  (0..1, the reading order inside the cluster) place it. `clusters` lists them, largest first.
- Mock workspace (`dsc mock [folder]`, default `~/DeepStudy-mock`, module `mock.py`): the demo goal (the "Vectors"
  lesson), plus a full "Dot product & similarity" lesson with two formula widgets and a check; four mapped books with
  sample chapters and ideas (no PDF files), shared ideas and links across books and to the goal; every idea state made
  from real evidence rows (and review schedules); three book-part study sessions (done with formulas and idea links,
  teaching, probing). It refuses a folder that holds anything but an earlier mock (file `MOCK`), so it never touches
  a real workspace. Run it with `DSC_WORKSPACE=<folder> dsc serve --port 8001`.
- The five concepts were first shown as a separate page (`docs/mockups/graph-concepts.html`).

## 30. The redesign: five entries, Today, the book shelf (2026-11-22)
- Purpose: the app is built around "teach me this book" and "teach me X". Big goals stay, on hold.
- Navigation (`App.tsx`): Today (`/`), Books (`/books`), Learn (`/study`), Practice (`/practice`, with a badge for what is
  due), Map (`/map`). A collapsed group "Goals (on hold)" holds Goal overview (`/goal`, the former Home), Roadmap,
  This week, Reviews and "+ New goal" (and the goal switcher); it opens by itself on a goal page. Source library, Me and
  Settings sit at the bottom. On a phone (under 760 px) the five entries are a tab bar at the bottom.
- Theme: the dark "star chart" is the default (night blue, gold for "know strongly"). Settings → Appearance: Dark,
  Light or Follow the system, kept in the browser (`localStorage["dsc-theme"]`, set on `<html data-theme>` before
  the page draws). Fonts: Space Grotesk (headings), Inter (text), Source Serif 4 (session explanations),
  JetBrains Mono (labels); each with a system fallback.
- Today (`pages/Today.tsx`, `GET /api/today`, `today.py`): "Continue" (the newest unfinished study session with its
  next idea and progress, else the next part of the newest book), "Due for recall" (count and the first ideas), "This
  week" (ideas learned since Monday, ideas known strongly, sessions done, answers), a small Territories map (click an
  idea to open it on the map), the book shelf and recent sessions. Without books or sessions: a start card; without a
  model provider: the API-key card.
- Books (`pages/Books.tsx`, `components/BookShelf.tsx`): a card per book study with a colored spine, a ring of known
  (green) and strong (gold) ideas, parts and ideas done; ready PDFs not studied yet get "Teach me this book".
  `bookstudy.listing` now gives `author`, `ideas`, `known`, `strong`.
- Book page: parts done, ideas known and strong, a stacked progress bar, the next part ("Continue" for the part in
  progress first, else the first part not done), parts by chapter with a dot per idea in its state, and the book's own
  Territories map (shared ideas show their other book as a second ring). "Remove" asks inside the page.
- Session: explanations in the reading face, the plan with a state dot per idea.
- Map: opens on everything, in Territories (`mapView` default "territory").
- The clickable mockup is `docs/mockups/ui-redesign.html`.
- Older pages in the new style (2026-11-22): Practice has two columns (the due ideas with state dots and "first time"
  for never-practised ideas; your own problem and earlier runs) and, during a run, the problem in the reading face with
  a side panel (problem steps, the level as 4 bars, the ideas in the problem). Settings is grouped into Appearance,
  Models, Learning and Data, with a contents list on wide screens. Me is a two-column grid. Source library opens on
  "My PDFs" (`?tab=goal` and `?tab=shared` for the card tabs). The map views zoom with two fingers (pinch).
- The mock workspace also has a recall-practice run in progress (one problem solved, one open with a hint).
- Known ideas can be learned again (2026-11-22): in a session's plan, a known idea can be ticked back in (`again`), and
  "Learn it again" (`sessionLearnAgain`) puts every idea back, so a part you already know can still be read and
  practised. "Start learning" is hidden, and refused by the backend, while the plan is empty. A finished session in
  which nothing was taught shows its ideas and "Learn it again", which reopens it at the plan. On the book page, a part
  whose ideas you all know offers "Review" instead of "Study".


## 31. Book lessons: chapters of saved lessons (2026-11-22)
- Purpose: a book is studied as lessons that follow the book closely, are written once and saved, and stay open
  whatever the learner already knows. It replaces the parts-as-study-sessions of §28 (`books.version` 2; a version 1
  book offers "Map it as lessons", which maps it again; sessions and evidence stay).
- Data: a book study has a hidden goal (`goals.kind = 'bookstudy'`, `books.goal_id`) so the normal lesson machinery
  works: one track (the book), one module per chapter, one concept per lesson. `book_chapters` holds each chapter's
  title, pages, outline sections, summary, module and `mapped`. `book_parts` rows are the lessons (`concept_id`,
  `ideas`); `book_nodes` links each lesson's graph node to the book. Hidden goals are left out of the goal lists, the
  planner hours, the map's goal clusters and the hover card's goal lessons.
- Map (job `book_map`, prompt `book_map.md`, one Opus call per chapter): a 2-4 sentence chapter summary and the
  chapter's lessons **by topic** (a long section can become several lessons; short ones join): key, title, covers,
  pages, key ideas, `prereq_keys` (lessons of this chapter, lessons of earlier chapters by id, or older graph ideas)
  and `same_as` (the lesson is exactly an older graph idea). Concepts are made without cards.
- Write on first open (`bookstudy.ensure_written`, called by `lesson.open_lesson`): `research_module` for a book goal
  runs `bookstudy.write_cards` (prompt `book_cards.md`, the chapter's page text only, no web): one call writes the
  cards of all the chapter's unwritten lessons. Each section has `book: {summary, pages}`, a close summary of what the
  book says there (short quotes only), plus a check, one explain-back (`work: true` for a calculation) and graphs. The
  card's source is the book with `source:<id>#page=N`. Then the opened lesson is written by the normal writer for this
  learner (playbook, guidelines, feedback), which sees the book summaries and is told its text is "what it means".
  The writer may link ideas the learner met elsewhere (`[words](#idea/<id>)`, only offered ids; `writer.book_links`).
  The lesson is saved (prose cache and lesson versions) and opens at once next time. Research-ahead writes the
  current and next chapter in the background (only mapped chapters).
- Pages: Book (`/book/:id`): the lesson to continue, chapters that open and close with their summary and lessons
  (what each covers, pages, state, "also in" other books, Open / Continue / Open again), homework per chapter, the
  book's map. Chapter (`/book/:id/chapter/:n`): the summary, the lessons with their key ideas, homework, previous and
  next chapter. Lesson: crumbs to book and chapter, each section a collapsible chunk with "What the book says" (pages)
  and "What it means", feedback on any part as before, and "Check yourself" at the end with every check and the
  explain-back (thinking, dictation, confidence). Opening a book lesson makes its hidden goal active
  (`bookOpenLesson`).
- Drawing board (`components/DrawingBoard.tsx`): pen colors, eraser, undo, clear; mouse, pen or finger. The PNG is
  sent with an explain-back (`explain.drawing`), saved under `workspace/drawings/` (`gradings.drawing`, served at
  `/api/drawing/<name>`), and the grader gets it as an image (`Call.images`: image blocks for the API, `--image` for
  Codex, a copied file plus the Read tool for the Claude CLI, a copied file for Cursor).
- Today's "Continue" is the newest of an unfinished session and the next book lesson.
- Homework is per chapter (`bookHomework {bookId, chapter}`).
- The mock workspace has the four books as chapters of lessons and one saved lesson ("Scaled dot-product attention")
  with book chunks, idea links, checks and a worked explain-back; auto-research and auto-refresh are off there.
- Reference chapters (2026-11-22): a chapter whose title (without its number) is a glossary, a reading list, a
  bibliography, references, an index, notes or answers is `book_chapters.kind = 'reference'`: it keeps its pages and
  gets no lessons and no model call. The map prompt also returns no lessons for reference material; a chapter mapped with no lessons becomes a reference chapter. Chapter ends use
  every outline entry, also the left-out ones (index, acknowledgements), so a chapter never runs into back matter.
- Map one chapter again (`bookRemapChapter {bookId, chapter, asLessons?}`, `bookstudy.remap_chapter`): the chapter's
  lessons, cards and saved text go, and the map job maps only that chapter. Answers, notes, feedback and gradings stay
  by lesson id; a new lesson with the same key gets the same id and so its history back. `asLessons` cuts a
  reference chapter into lessons after all. The Book and Chapter pages offer it, with a confirm step.
- Markdown: a writer's `<details><summary>…</summary>…</details>` is drawn as a collapsible block (raw HTML stays off).
- The clickable mockup is `docs/mockups/book-lessons.html`.

## 32. The tutor reads your reasoning (2026-11-22)
- Purpose: a wrong answer is best fixed from the learner's own reasoning. "No, it is B" adds new information next to the
  wrong idea; following the wrong idea until it breaks connects the two, so the right idea sticks.
- When a lesson check is answered with thinking (typed or dictated, at least 20 characters), `reasoning.queue` saves a
  pending row in `reasoning_reviews` and queues the job `reasoning_review` (route "Reasoning review", Sonnet, prompt
  `reason_review.md`). The job reads the question, the options, the key and its explanation, the lesson's idea and the
  section (with what the book says), the choice, the confidence and the thinking, and returns:
  - `verdict`: right, right_with_gaps, wrong or unclear; a `summary`;
  - `parts`: 2-6 exact quotes from the thinking, each marked right, partly or wrong, with a 1-2 sentence note (quotes
    that are not in the thinking are dropped; the rest are sorted by where they stand);
  - `assumption`: the wrong idea behind a wrong answer or step; `follow`: 2-4 steps that take it as true until it breaks
    ("If it worked your way …"); `truth`: how it really works, derived from where it broke; `takeaway`.
- Page: under the answer, the thinking with the quoted parts marked in place (green, amber, red, numbered), the notes,
  "Your assumption", "If it worked your way", "How it really works" and "Remember". While the job runs: "The tutor is
  reading your reasoning…". An earlier answer with thinking (or a failed review) offers "Let the tutor read my
  reasoning" (`reviewReasoning`).
- History: `GET /api/reasoning` (`reasoning.history`) lists every reviewed answer with its thinking, confidence and
  findings; the Me page shows "Your reasoning" (newest first, with the assumption found), so the learner sees how
  their understanding changes.
- Writing style (Settings → Learning → Writing style, `writing_style`, default "ste"): every job's rules get
  `_ste.md`, so lessons, book summaries and the tutor write in ASD-STE100 Simplified Technical English, about 80 %
  strict. "Free" turns the rule off. It applies to text written from then on.
- Lesson progress (2026-11-22): while a lesson is written (book research for its chapter, the render job, or applying
  feedback), `lesson.view` gives `writing`: the steps ("Plan the chapter's lessons from the book", "Plan the lesson for
  you", "Make graphs and questions", "Write the text", "Review and fix"; one step when lessons are written in one
  call), the step it is on (from the job's progress lines) and the newest line. The lesson page shows a sticky banner
  with a moving bar, the steps and how many sections are ready, and says that text, formulas and graphs can still
  change.
- Display formulas: a multi-line `$$` block with text on its fence lines (`$$\begin{aligned}` … `\end{aligned}$$`) is
  rewritten with the fences on their own lines before rendering; before, the formula broke and the text after it
  showed as one red KaTeX error.

## 33. Formula hover notes and 3D surfaces (2026-11-22)
- Formula notes (`formulas.py`, job `formula_notes`, route "Formula notes", prompt `formula_notes.md`): a lesson's
  display formulas and its inline formulas that say something (an equation, a sum, a fraction; not plain arithmetic)
  are collected from the text the page shows and the book summaries, at most 25. One call writes a note for each:
  a name, its meaning in 1-2 sentences, its symbols (TeX and meaning) and 0-3 graph ideas it is, uses or comes from
  (only ids offered: this lesson's idea, the ideas it builds on or leads to, word matches). Notes are saved in
  `formula_notes` by the formula's TeX without spaces. The job runs after a lesson is written or revised, and on open
  for a lesson that has formulas without notes (switch: meta `formula_notes`, default on).
- Page (`components/FormulaHover.tsx`): hovering a formula reads KaTeX's TeX annotation, finds the note and shows a
  card: name, meaning, symbols, and "Where you met it" with each idea's state and a link to its lesson (or the map).
  Formula widgets keep their own part labels.
- 3D surface widget (`surface3d`, `components/viz/Surface3D.tsx`): z = f(x, y) from the plot syntax over a box,
  drawn on a canvas with our own projection (drag to turn, top view), with optimizer paths from one start point:
  gradient descent, momentum (β 0.9), RMSProp (ρ 0.9) and Adam (0.9, 0.999). The learner changes the learning rate
  (log slider) and the start point, plays the steps and reads each method's loss. The writers may use it for loss
  landscapes, descent and its variants, saddle points and valleys (`_widgets.md`); `viz.validate` checks the
  expression (x and y only), the box, the start, the optimizers, the learning rate (up to 2) and the steps (5-300).
- The mock workspace has a saved "Gradient descent" lesson (Understanding Deep Learning) with two surfaces: a narrow
  valley (gradient descent zigzags, momentum does not) and the Rosenbrock valley (all four methods).

## 34. Formula lessons and colored formula frames (2026-11-22)
- Purpose: a formula met for the first time can become its own short lesson; a formula met in another form is joined
  to that lesson, which then compares the forms; the frame color says at a glance what you know.
- Notes get a `kind` (idea, or step: a line of a derivation or a calculation) and a `formula_id` (the formula lesson
  that is this formula, in any form). The notes job sees the learner's formula lessons with their forms and matches;
  a lesson's notes are matched again (job `formula_notes`, prompt `formula_match.md`, which also sets the kind) when a
  formula lesson was made after they were matched, or when they were written before kinds existed.
- Frames (`FormulaHover.tsx`): every display formula, and every inline formula that has a note and is an idea:
  green = you learned its formula lesson and this form is one of its forms; orange = a formula lesson exists but this
  form is new to it; gray = no formula lesson yet (or not learned yet); a faint dashed frame = a step.
- Hover card actions: gray → "Make a lesson about this formula" (`makeFormulaLesson`); orange → "Add this form to that
  lesson" (`addFormulaForm`); green → a link to the formula lesson.
- A formula lesson (`formula_lessons.py`, tables `formula_lessons`, `formula_forms`) is a concept right after the
  lesson it came from (and a lesson of the same book chapter), linked to it in the graph. The job `formula_lesson`
  (prompt `formula_lesson.md`, route "Research", no web) writes its card from the formula, its note, the text around
  it, the book's pages and the ideas the learner knows: "What each part means" with the explorable formula widget
  (required), "Where it comes from" (derived from known ideas, with the explain-back), "Use it" (worked example and a
  check) and "Its forms" (two or more forms: side by side, symbol by symbol, why each, when each is handy). Adding a
  form or preferring one (`preferFormulaForm`) writes the card again (a new version) and the lesson again. The lesson
  page shows "Forms of this formula" with "I prefer this form".
- Normal lessons use at most one formula widget, for their central formula (`_widgets.md`); formula lessons use it
  fully. Widget captions and lesson objectives now render math.

## 35. The tutor reads your reasoning everywhere (2026-11-22)
- Explain-backs: the grader (`grade.md`, `GRADE_SCHEMA`) also returns the reading of the answer: parts quoted from it
  and marked right, partly or wrong with a reason, the wrong assumption, steps that follow it until it breaks, how it
  really works, and a takeaway. It is saved in `gradings.review` (quotes not in the answer are dropped) and shown under
  the score in place of the plain answer ("Where your reasoning went off"), with the drawing board image.
- Study sessions: a prediction or a check answered with thinking (20+ characters) gets a `reasoning_review` row
  (`session_item_id`; `concept_id` is then the session id) and the same review job; the prompt says whether it was a
  prediction before the explanation or a check after it, and includes what the tutor explained. The probe stays quick
  (no review). The session's explain and repair turns now also name the wrong idea and follow it until it breaks.
- History (`reasoning.history`, Me → "Your reasoning"): lesson checks, study-session answers and explain-backs, newest
  first, each with a link to where it was answered.

## 36. Your preferred formula forms in every lesson (2026-11-22)
- When the learner chooses a form in a formula lesson ("I prefer this form") and the formula has two or more forms,
  `guidelines.text` (read by the lesson planner, the graph and question writer, the text writer, the reviewer, applying
  feedback, the study-session tutor and practice) gets a line per formula: write it in that form; when the source
  (a book) writes it another way, show the source's form once, map it symbol by symbol, then use the preferred form.
  "What the book says" keeps the book's own notation.
- It applies to text written from then on. On the formula lesson, "Forms of this formula" offers "Rewrite it with your
  form" for each lesson that uses another form (a "Refresh for current me" of that lesson).

## 37. Building blocks: the formula tree and shared book lessons (2026-11-22)
- Purpose: knowledge accumulates in blocks. A complex formula or topic is understood only when the blocks under it are
  held, so the app teaches from the bottom up, and a topic several sources teach is one block, not several lessons.
  Grounded in knowledge space theory (ALEKS: prerequisite graphs and the "outer fringe" of what a learner is ready
  for), research on symbol sense (reading through a formula, notation conventions), concreteness fading, faded worked
  examples, and equation sensemaking (special cases).
- Formula tree (`formula_lessons.decompose`, prompt `formula_blocks.md`, table `formula_blocks`): before a formula
  lesson is written, its 2-6 direct blocks are found: notations (∏, Σ, the bar in Pr(y | x), argmin, subscripts),
  simpler formulas it is built from, and ideas, each in general form and general words, matched to the learner's
  formula lesson or graph idea when it is the same thing, or marked basic (school level). A block is known (green) when
  its lesson or idea is learned, or basic; else new.
- "Learn these first" (`learnBlocksFirst`): every new block becomes a short formula lesson (or a notation lesson,
  prompt `notation_lesson.md`) placed right before the formula in its module and book chapter, linked to it in the
  graph; each one finds its own blocks when written, so the tree grows down to what the learner holds.
- Formula-lesson structure (`formula_lesson.md`), not a chapter lesson: read it aloud with every symbol in general
  terms; build it from the blocks, one small step each (with the explain-back); tiny numbers in a neutral setting and
  a faded worked example, with the explorable formula widget and a check; special cases and a common misreading;
  only then where it is used, with every domain word explained; and its forms.
- Page: "Built from" (each block, green or gray, with its lesson or idea) and "Used in" (formulas built from it and
  lessons that use it); the hover card says how many blocks are new. Hover notes now give the general meaning first and
  the lesson's example after "Here:".
- Shared book lessons: the map sets `same_as` when a book teaches a topic another book or goal already has (even
  explained a bit differently): one block, one mastery. Writing a chapter skips such a block when another version is
  written; the book page shows "Shared block: you have this topic in …", opens the written version, and offers
  "This book's version" (written from this book's pages when asked). The lesson page shows "One block, N versions".
- Readiness: each book lesson lists what it builds on that the learner does not hold yet (this book's earlier
  lessons and older ideas the map linked to it); "Next" is a lesson whose parts the learner holds (the one in
  progress first), so the book is read in an order that builds.

## 38. The whole formula tree (2026-11-22)

- A page "Formula tree" (`#/formulas`, linked from the Map page and from each formula lesson: "See the whole formula
  tree") shows every formula lesson and every building block as one graph. Basics are at the bottom. An arrow goes
  from a block to the formula built from it.
- Nodes: a formula or notation lesson (square), a graph idea that is a block (it lists the block names it teaches
  here), or a block with no lesson yet (the same name under two formulas is one node). A block named like a formula
  lesson is that lesson. A block that is the formula itself is left out.
- Colors: green = you hold it (or basic arithmetic), orange = learning, dashed blue = its lesson is being written,
  dashed gray = new to you. A notation is never basic, also in rows saved before that rule.
- Selecting a node shows its form, meaning, state, the lesson to open, what it is built from and what uses it, and
  for a formula with blocks that have no lesson, "Learn them first". The rest of the tree dims, except the
  selected node's whole subtree. API: `GET /api/formulas` (`formula_lessons.tree`).

## 39. Desktop app updates (2026-11-23)

- **What it is for:** a learner with the installed app gets new versions without a visit to GitHub.
- **When:** after each start of the installed app (not in a debug build), when the backend answers. One request goes
  to `https://github.com/romank-foxcale/deep-study-center/releases/latest/download/latest.json` (the Tauri updater
  plugin). No data about the learner is sent.
- **The offer:** a native dialog "A new version": the new and the current version, and that the workspace is not
  changed. "Later" closes it until the next start. "Install and restart" downloads the installer, checks its
  signature, stops the backend (the installer replaces its files), and runs the installer in passive mode (a progress
  bar, no questions). The installer opens the new version.
- **Signing:** the public key is in `tauri.conf.json` (`plugins.updater.pubkey`). The private key stays with the
  maintainer, outside the repository; a release build reads it from `TAURI_SIGNING_PRIVATE_KEY`. An update with no
  correct signature is not installed. A lost key means installed apps cannot update again.
- **Errors:** every step goes to `update.log` in the app's log folder. A failed check is silent (offline is normal);
  a failed download or install shows a dialog that points to the Releases page.
- **Switches:** `DSC_NO_UPDATE_CHECK=1` turns the check off; `DSC_UPDATE_URL` replaces the server (for a test).
- **Release files:** `desktop/release.py` copies the installer under the name GitHub gives it and writes
  `latest.json` (version, signature, download URL). Steps: `docs/RELEASING.md`. `npm run build:local` builds with no
  signing key and no update files.
- 0.4.0 has no updater; its users install 0.4.1 by hand once.

## 40. Sources, the shelf, and the review fixes (2026-11-23)

What it is for: the learner's review of 0.4 (navigation, the source library, the map, lessons, the formula tree).

- **Back.** Every page but Today has "Back" at the top: the previous page in this tab, else the page above (a chapter →
  its book, a book → Books, a lesson → Books, the formula tree → Map).
- **Sources** (was "Source library", "My PDFs"): one table of every source. Removed: the tabs "This goal's cards" and
  "Shared cards", the Anki export, the book goal (80/20, SPEC §18: page, actions, `books.py`, the outline branch and
  its prompt). Shared cards from before still feed goal research.
  - Types: Book, Article, Internet source (`web`), Video, Custom (made by the learner: a roadmap, or a "teach me" topic).
    Old `post` → `web`, `other` → `custom`. The learner changes the type at any time.
  - Status: error (red: unreadable or no text), uploading (gray: being read), uploaded (yellow), ready (green: "Teach me
    this book" made its lessons).
  - A click on the title opens the source: the PDF, or the link (a web page, a video).
  - "Add source" is a dialog: a PDF file or a link; a name (default: the file name; it wins over the PDF's own title);
    a type; the upload progress; Cancel. Duplicates: the same file (SHA-256, any name) or the same link is refused; the
    same name asks first. Links are kept and opened; reading a web page or a video transcript comes later.
  - A search box (title, author, file name, link, type) and type chips, on Sources and on Books.
- **Books.** Every card has a trash can (it deletes the source and its book study; learned ideas stay on the map). The
  shelf also shows links and Custom study topics ("teach me X"). A book has one color: the map area's color
  (`graph.area_colors`: books in the order they were added, then goals, then sessions), on its card and on every map view.
- **On hold:** Practice joins goals in the sidebar group "On hold"; Today hides "Due for recall".
- **Map:** the views Graph, Nebula and Globe are removed (a saved one shows Territories). The Tree view zooms with the
  mouse wheel (the listener was attached before the map had loaded, so the wheel did nothing).
- **Lessons:**
  - A Python block keeps the learner's edits when the page refreshes (the code block's component was made again at
    each render, so React remounted it).
  - Formula hover: "Where you met it" lists other lessons only. A formula you met in other lessons is orange; new is
    gray. A step of a derivation (a formula on the way to the final form) has no frame and no hover card.
  - A board task ("Work it out") is only for a calculation that is hard in the head, and states its inputs, what to
    compute and the form of the answer. Its slider asks "How sure are you of your answer?".
  - Book lessons: one lesson is one idea, each built on what the learner already knows (the map prompt). Books mapped
    before (`books.plan` 1) show "Re-plan lessons": every chapter is mapped again; answers, notes and learned ideas stay.
- **Formula tree = the derivation graph.** Pick a formula: it is at the top, and under it what it is derived from, each
  node with its own formula (rendered math). "What is it built from?" finds a node's parts one level down (job
  `formula_open`; a formula lesson gets its blocks, a formula with no page gets `formula_parts`). "Make a formula page"
  makes a page for any formula node (placed before the nearest formula page above it; its parts become its blocks).
  Formula and notation pages look different (a tinted background, "Formula page") and have no multiple-choice quiz.

## 41. Formulas on the map, and the Territories legend (2026-11-23)

What it is for: formulas are knowledge too, so the map shows them next to the ideas they belong to.

- **Formulas on the map.** Every formula met in a lesson (a formula note that is not a derivation step) is on the map.
  - A formula with a formula page is that page's node, marked as a formula with its form.
  - Any other formula is a map item made for each map (not stored): id `fx:<hash of its form>`. It is linked to each
    lesson that uses it. The same formula in two lessons is one item.
  - All formulas (pages too) are one country of their own, "Formulas", with its own color (not a book color): most
    lessons have formulas, so inside the books they would cover the land (`_formula_country`).
  - **Provinces by field.** A model job (`formula_fields`) tags each formula once with 1 to 4 fields of mathematics from
    a fixed list, most important first, judged on the formula itself (not the book it came from). The tags are kept per
    form in `formula_fields` (key = `formulas.key`), so a formula in two lessons has one set of fields. The job starts
    after new formula notes or a new formula page, and when the map loads with untagged formulas (not again within 10
    minutes after a failure).
    - Fields, in ring order (neighbours are related, so their provinces touch): Algebra & functions, Probability &
      statistics, Information theory, Machine learning, Calculus & optimization, Linear algebra, Geometry &
      trigonometry, Physics, Algorithms & complexity, Discrete math & logic.
    - Territories: each field present is a province of the Formulas country, seeded on a ring around its middle. A
      formula in 1 field is in its province; in 2 or 3 fields it sits where those provinces meet, and its hex is split
      into 2 or 3 slices (the same split form for every hex); in 4 or more fields it is gray ("Essential"), in the middle.
      A formula with no fields yet is "Not sorted yet" (dark gray). Its learning state is a smaller hex inside, so the
      field colors stay visible. Thin dashed lines separate the provinces.
    - The legend lists the provinces under Formulas: each field with its formulas (a formula in two fields counts in
      both; "shared" says how many), then Essential and Not sorted. Cells and Wheel group formulas by province
      (``chapter``); the tooltip names the fields.
  - Its state is the best state of those lessons: a formula is learned with its lesson.
  - A formula has no special mark: its country shows what it is. The tooltip says "Formula"; the panel shows its rendered
    math and meaning.
    A formula with no page has no "Practise".
  - `graph.view` adds them (`_formula_items`); the map's "Everything" counts ideas and formulas apart.
- **Territories** is the default view, also in the UI when no view is saved.
- **Country names** are no longer drawn on the land. They are in a legend under the map ("Countries"): each book or
  goal with its color and its known/all count. The legend can be collapsed; the choice is kept in this browser.
- The map page fits the window under "Back" (no page scroll).

## 42. Lessons you approve before they are written: the plan graph (2026-11-23)

What it is for: the learner sees and changes how a lesson will teach before it is written, also while the plan is
being made. Phase 1 of the lessons rework (the study of LearnHarness and the mock screens are in the proposal of
2026-11-23; LearnHarness is AGPL-3.0, so its ideas are used, not its text).

- **When.** Opening a book lesson that is not written yet makes its plan (job `lesson_graph`, prompt `lesson_plan.md`)
  instead of writing the chapter's lessons. "Write it now without a plan" keeps the old way (`/open?noplan=true`): the
  chapter's lessons without a plan are written together. A lesson that has a plan is never written in that batch; it
  waits for its approval. Lessons written before stay as they are.
- **The plan** is a small graph from what the learner holds to the lesson's one idea. Node kinds: `held` (the learner
  holds it: built on, not taught again; `linksTo` its map idea), `foundation` (needed, not derivable from what is held,
  true with no "but"), `step` (one new fact by one move of reasoning), `formula`, `goal` (exactly one). Each node
  except held ones has a form: example, interactive, figure, text (at most three short sentences), derivation, and why.
  Edges mean "hold this first". With the plan: `approach` (2-4 sentences) and `goal` (one sentence).
  - Input: the lesson (title, what it covers, key ideas, pages), the book's pages, what the learner may hold (its
    prerequisites and the closest map ideas with their states, and the formulas met in lessons), the version before,
    and the learner's notes.
  - Code checks the model's plan: unique keys, known kinds and forms, edges only between nodes, an edge that would
    close a cycle is dropped, one goal (`lesson_graph.clean`).
- **Versions and notes.** `lesson_graphs` keeps one row per version (status planning, ready, approved, failed).
  `lesson_graph_notes` keeps the learner's notes: on a node "I know this" (`cut`, pressed again to take back), "Show it
  another way" (`other`), a node note, a note on the whole plan, or a note sent while planning (`steer`). "Re-plan with
  my notes" makes the next version from the notes not used yet; the planner changes only what they ask for and keeps
  the node keys, so the screen marks new and changed nodes and lists the ones left out.
- **Steering.** A note sent while a version is being made is used by the next version, which starts by itself when
  the running one ends.
- **Approve and write** marks the version approved and writes only this lesson (`research_module` with `only`); the
  book-cards prompt gets the plan: one section per step, foundation and formula, in the plan's order, in each node's
  form, and nothing the plan says the learner holds. The written lesson shows "The plan you approved".
- **Screen.** The plan is drawn with the goal at the top and what you hold at the bottom; click a node for what it
  adds, its form and the note buttons. While planning: the job's steps and the steer box. The book page shows a plan
  pill per lesson (Planning…, Plan ready · review it, Writing from your plan, Plan failed).
- **Robust.** Two opens at once make one version (one transaction). A version left "planning" when the app stopped
  shows as failed ("interrupted") with "Try again".
- API: `GET /api/lesson/{cid}/plan`; actions `planLesson`, `lessonPlanNote`, `approveLessonPlan`.
- Next phases: steps written one at a time (predict, step, check, repair) with the plan beside the lesson; practice
  from a lesson, chapter, field or the weakest items; later, generated interactive demos.

## 43. Step lessons: one step at a time, written just ahead (2026-11-24)

What it is for: an approved plan is taught one reasoning step at a time, so the learner never waits for a whole lesson
and every step is checked before the next one builds on it. Phase 2 of the lessons rework.

- **On approval** (§42) the lesson gets a card with `steps: true` and one section per plan node that is not held, in the
  plan's order (each with `node`, `kind`, `form`, and an angle from the form). The card lists the held nodes. No
  chapter batch, no full-lesson writer: `lesson.ensure_prose` hands a step lesson to `lesson_steps.ensure`.
- **Written just ahead.** Job `lesson_step` (prompt `lesson_step.md`) writes one section: the step it is on and the next
  one are written; the rest waits. After each answer, and after each written step, the next ones are queued.
- **A step:**
  - `predict` (optional): a question before the step, about what it will show. Answered with `predictStep` into
    `step_predictions`; not graded evidence (guessing is the point). The step's text stays veiled until the learner
    predicts or skips. The key is shown once predicted.
  - the text: one new fact, at most about 80 words, in the plan's form (example, interactive with a widget, figure,
    text, derivation), in STE; it builds on the learner's prediction and last check. Stored as the section's prose.
  - `check`: closed behind "Check your understanding" until the learner opens it; answered like any check (evidence on
    the map, the tutor reads the thinking).
  - `repair`: shown only after a wrong check: the wrong idea named, then the right one with a new small example.
  - the goal step also has an explain-back.
- **Progress.** A step is done when its check (for a goal with no check, its explain-back) has an answer; the step
  after it then opens. The writer of a step sees each earlier step's text and how the learner did on its prediction
  and check, with their thinking.
- **Explain differently** on a step writes it again with the learner's note (`rewriteStep`); its answers stay.
- **Screen.** A sticky bar with the plan's steps (done, current, to come) and what the lesson builds on; the steps so far,
  each a card; "You finished the lesson" at the end.
- The steps are also ideas on the map (§46).

## 44. Practice, back from hold: pick what to practise, a hint ladder, a pause, retests (2026-11-24)

What it is for: make held knowledge come to mind in new situations, on exactly what the learner chooses. Phase 3 of
the lessons rework; it builds on recall practice (§24), which already sends every result to the map (evidence per idea
and its own spaced review).

- **Practice is back in the main menu** (Today, Books, Learn, Practice, Map), with the number of ideas due.
- **The picker** (`GET /api/practice-targets`, `practice.targets`):
  - By book: books → chapters → lessons (each an idea of the map, with its state; "not studied yet" is shown) → the
    lesson's steps or sections. Ticking parts makes them the run's focus for that idea.
  - By field: the provinces of the Formulas country with their formulas (§41). A picked formula brings in the lessons
    it comes from and becomes part of the focus.
  - My weakest: worked-on ideas that hold least (low mastery, recent misses, rusty).
  - My own problem: text or a page of a source, as before.
  - The session: 5, 10 or 20 problems; style applied, formal or mixed. The selection from all tabs is one run.
  - Entry points: "Practise this chapter" on the book page; "Practise this lesson" at the end of a step lesson; "Practise"
    on a map idea; "practise them" for what is due. A lesson id stands for its idea.
- **The problem writer** (prompt `practice_next.md`): the weakest idea first; never the same idea as the last problem
  (switching is what makes recall happen); a mode per problem: `recall` first, then `tell_apart` (one detail decides),
  then `combine`; a miss goes back to recall; the idea is never named; it solves the problem first and changes it if a
  shortcut skips the idea; it follows the focus, the formulas and the style.
- **The hint ladder** (prompt `practice_judge.md`): look again at a given → name the kind of pattern → name the area →
  name the idea → outline the first move → show the worked step. One rung per request, for the first wrong or missing
  point; a wrong direction gets "check the assumption", not the correction; explaining what the problem asks is free.
  The rung is kept with each hint and shown as a bar.
- **The pause.** After a solve or "give up", the learner reads the verdict and the worked solution. The next problem is
  written meanwhile (status `waiting`, hidden) and opens with "Next problem" (`practiceNext`); pressed early, it opens
  as soon as it is written.
- **Retests.** When the run's problems are done, each given-up or hint-heavy problem (score below 0.7) comes back once in
  a new setting, at most 3; then the run ends.

## 45. Generated interactive demos, sandboxed and tested (2026-11-24)

What it is for: when a step should be operated (a process over time, linked views, draggable geometry, a simulation)
and no built-in widget can show it, the learner still gets something to move. Phase 4 of the lessons rework.

- **When.** The step writer (§43) gives `demo_brief` instead of a widget, only for an interactive or figure step and
  only when no built-in widget fits: a precise specification (what it shows, each control with its range and start,
  what to watch, the formulas and numbers in the book's notation). The step's text is shown at once; the demo follows.
- **Build** (job `lesson_demo`, prompt `demo_build.md`, role "Lesson assets"): one self-contained HTML file. Code checks
  it (`demos.check`): inline script and style only; no outside files or addresses (the SVG namespace is allowed); no
  network, storage, eval, dialogs, iframes or access to the page around it; at least one control; at most 200 kB. A
  demo with problems goes back once with the exact problems.
- **Sandbox.** The page runs it in an iframe with `sandbox="allow-scripts"` (no same origin: no cookies, no app API)
  and a Content-Security-Policy that blocks every request. A small bridge reports errors and the demo's height.
- **Test before the learner sees it.** A new demo is loaded hidden and operated: every slider and number input to its
  minimum, maximum and start; every select option; up to 8 buttons. No error: the demo shows and is marked tested
  (`demoResult`), and shows at once from then on. Errors: the server fixes it once with those errors (at most 2 builds
  in all); if it fails again it is left out, and the step's text stands alone. A result for an old version is ignored.
- Stored in the step's section: `demo = {status, brief, html, title, watch, version, tries, errors, tested}`.

## 46. The steps of a planned lesson as ideas on the map (2026-11-24)

What it is for: a step lesson teaches several small ideas (foundations and reasoning steps). The map shows each one,
so the learner sees what the lesson is built from, what holds, and can practise one step on its own.

- **Which.** Each taught foundation and step of a step lesson (§43) becomes an idea of the map: id
  `pn-<lesson>-<key>`, kind "step", origin "plan", with the step's title and what it adds. Held nodes, formula nodes
  and the goal are not new ideas: a held node is its map idea, a formula is in the Formulas country, and the goal is
  the lesson's own idea.
- **A step that is already on the map.** When the plan links a step to an idea already on the map (`linksTo`), the
  step is that idea: no copy is made.
- **Place.** A step idea is in its lesson's book and chapter, just before the lesson.
- **Links** come from the plan's edges ("hold this first", origin "plan"). A formula node is joined across: a -> formula
  -> b becomes a -> b.
- **State.** A step's check and explain-back count on the step's idea (or on the linked idea), and on the lesson. One
  check alone does not make an idea learned, so a step whose last answer was right shares its lesson's state when the
  lesson is learned or mastered. A step idea starts with its first answer. "Practise" works on a step idea.
- **Kept in step.** `plan_nodes.sync` (from `graph.sync`) maps each step lesson's newest card once
  (`plan_nodes`, `plan_maps`). A new card replaces the lesson's step ideas: after a re-plan, or without steps after
  "Write it now without a plan". Step ideas that no lesson owns are removed.
- **Screen.** The hover card says "Step of <lesson>". The side panel says "A step of a lesson" and links the lesson
  under "Taught in".

## 47. Teach from a link: a web page or a video (2026-11-24)

What it is for: an article or a lecture video is taught like a book. "Teach me this" on a link makes chapters of
lessons from its text.

- **Read** (job `read_link`, `links.py`). The job starts when the link is added, or on "Teach me this" (then the book
  starts by itself when the text is read).
  - A web page is fetched once. Its main text is kept: scripts, menus, headers, footers, forms, hidden parts and short
    labels are left out, and an `<article>` or `<main>` part wins when it has enough text.
  - A YouTube video gives its captions: English first, else the first language it has. Reading videos needs the
    package `youtube-transcript-api`.
  - A link to a PDF file is saved and read as a PDF.
- **Pages.** The text is cut into pages of about 2,500 characters at paragraph ends, so chapters, lessons and citations
  ("p. N") work as for a PDF.
  - A web page's headings become chapters of at least 4 pages, with the headings as their sections. A short page is
    one chapter.
  - A video's pages are about 3 minutes of captions. `sources.marks` keeps the second each page starts at.
- **Citations** open through `GET /api/sources/{id}/open?page=N`: a PDF at its page, a web page, or a video at the time
  its page starts (`&t=<s>s`).
- **Status.** reading, then read (ready), "error: no text" (too little text, or no captions), or error (the fetch
  failed). "Read again" reads it again.
- **Privacy.** The fetch sends no data about the learner. Nothing is sent to a model until the book is mapped.

## 48. No schedule: study and see the progress (2026-11-24)

What it is for: the learner decides what to study and when. The app shows what is learned; it does not plan reviews.
Phase 1 of the one-map redesign (one cell per idea, no countries; later phases follow).

- **Removed:** the review schedule (FSRS cards in `reviews` and `node_reviews`), the "due" lists (Today, Practice,
  the navigation badges), the Reviews page and its `review` action, and the states "mastered" (a confirmed review)
  and "rusty" (a failed review). The `fsrs` package is no longer a dependency.
- **States now:** locked, ready, learning, learned. Once an idea is learned (the BKT gate: P >= 0.95, 3 distinct right
  items, and the explain-back when the lesson has one), it stays learned.
- **Old data:** the `reviews` and `node_reviews` tables stay in the schema so old workspaces open, but nothing reads
  or writes them. Old answers of kind "review" count as ordinary answers. Nothing is deleted.
- **Practice** is only what the learner picks (book, chapter, lesson and steps, field of formulas, the weakest ideas,
  or their own problem). With nothing picked, it practises the weakest ideas. Results are evidence of kind "practice".
- **Today:** where to continue, and this week (ideas learned, sessions, answers). Book cards show learned ideas only.
- **Still open:** the weekly plan of goals (on hold: lessons only, no reviews) and the roadmap's coding-problem
  intervals (`roadmap/plan.py`, on hold) are left as they are, for a later decision.

## 49. One cell per idea: one lesson, many sources (2026-11-24)

What it is for: one idea is one understanding. When two books (or a book and a video) explain the same idea, the
learner gets one lesson of it, written from both, not two lessons. Phase 2 of the one-map redesign.

- **Joining.** Book mapping already joins a lesson to the same idea from another source (`same_as`, §31). The idea is
  one node of the map and one cell.
- **Home lesson** (`cells.home`): every cell has one lesson. When an idea has lessons from several sources, the one
  furthest along wins (a plan, then a written card, then answers, then opened); on a tie the kept one stays
  (`cell_homes`), then the oldest. Every book row of the idea opens that lesson. Opening another lesson of the idea
  (an old link, the map) returns `redirect` to it.
- **Sources** (`cells.sources`): every book part of the idea's lessons, the home's first. The lesson page lists them
  ("One lesson from N sources"). A lesson opened from a book (`?book=`) shows its place in that book.
- **Written from all sources** (`cells.source_text`): the planner (§42) and the step writer (§43) get the pages of
  every source, each block labeled by source and page, with the budget shared between sources. The planner names the
  source each step follows in the node's `pages`; one notation for the whole lesson. The learner's answers and notes
  change how the lesson is built, not what it is about.
- **Writing a chapter** (the older batch): a lesson whose idea has its one lesson elsewhere is not written again.
- **Old data:** nothing is deleted or moved. Lessons of one idea written before this stay as earlier versions on the
  lesson page. Evidence was already counted per idea (§21).
- Next phases: the hex map without countries (§29 replaced), gaps between cells, and goals as a direction on the map.

## 50. The hex map of ideas: one hex per idea, no countries (2026-11-24)

What it is for: the map shows one mind, not a shelf of books. Every idea is one hex (one cell per idea, §49), whatever
its sources; ideas that build on each other sit side by side. Phase 3 of the one-map redesign (the mock "A · Hex
cells" was chosen).

- **Views:** "Map" (the hex map, the default) and "Tree". The country views (Territories, Skill wheel, Cells) are
  removed; `map_view` is `hex` or `tree`, and an old value opens the hex map.
- **Layout** (`HexMap.layoutCells`, in the page, deterministic): a small force layout (links pull two ideas one hex
  apart; near cells push apart; a weak pull to the middle keeps one piece of land), then every idea snaps to the
  nearest free hex, the most linked first.
- **Colors:** learned (green), known but not learned yet (blue-gray: the learner started it), not explored (dark).
  Formulas and lesson steps are cells too.
- **Point at a cell:** its name, what it is (a formula, a step of a lesson), its state, one line on what it says, and
  how many sources it has. Its links are drawn to its neighbours; other cells dim.
- **Click a cell:** the panel shows what it builds on and leads to, its sources (`node_detail.sources`: every book,
  article, web page or video part with pages, and the study sessions that taught it), and "Start / Continue / Open the
  lesson" for the idea's one lesson (`node_detail.lesson`).
- **Also:** "Show names", search, zoom (wheel, buttons, Fit), drag to pan. Today and the book page show the same hex
  map, small. The book page shows only that book's ideas.
- Next: gaps (open space where an idea is missing), then goals as a direction on the map.

## 51. Gaps: open space where an idea is missing (2026-11-24)

What it is for: the map shows not only what the learner holds, but where something is missing between two ideas,
so they can "conquer the territory" step by step. Phase 4 of the one-map redesign.

- **A gap** sits on an arrow A -> B of the map when B needs 1-3 ideas that are on no cell (`gaps` table: status open,
  filled or dismissed; the ideas with title, what each says, and whether it was added).
- **Finding gaps** (job `find_gaps`, prompt `gap_find.md`, role "Research"): after a book finishes mapping (meta
  `auto_gaps`, on by default), and with "Find gaps" on the map. The agent sees the arrows near ideas the learner has
  started or learned (at most 160) and the ideas of the map, and returns at most 6 gaps.
- **Code checks** every gap: both ends are ideas of the map and differ; no proposed idea has the title of an idea
  already on the map; an arrow the learner said is not missing is never proposed again; an open gap on the same arrow
  gets the new ideas instead of a second gap; at most 3 ideas per gap.
- **On the map:** a gap takes one empty, dashed hex per missing idea, between its two cells. Point at it: what is
  missing and between what. Click it: the gap panel.
- **The learner's choices** (actions `acceptGap`, `findGaps` with `gapId`, `dismissGap`):
  - "Add to map": the idea becomes a cell (not explored yet), linked A -> new -> B; what is still missing moves to
    sit between the new cell and B; the gap closes when nothing is left. The panel then opens the new cell
    ("Teach me this").
  - "Find more": the agent looks at that arrow again; the gap grows (at most 3 ideas).
  - "Not missing": the gap closes and that arrow is not proposed again.

## 52. The formula flow of a formula page; no formula widget in normal lessons (2026-11-24)

What it is for: on a formula's page, the learner sees exactly where each part comes from, changes one value or one
part, and sees what happens to every part below it. The design is the approved mock "A"
(`web/public/_mocks/formula-graph-a.html`).

- **The flow** (`formula_flow.py`; table `formula_flows`): inputs (values to drag, with ranges; a constant is
  `fixed`), input boxes (the inputs they hold), and formula boxes in order. Each formula box: its symbol, a label,
  `uses` (earlier boxes), `tex` (naming inputs and boxes as `{id}`), `expr` (the calculator form of the widgets; a list
  for a small vector, whose parts are `id_1`, `id_2`, ...), `say` (what it is and why it is needed), and on 1-3 main
  boxes 1-3 `whatif` forms (`tex`, `expr`, `why`, `ok`).
- **Built** by an agent (job `formula_flow`, prompt `formula_flow.md`, role "Lesson assets") when a formula page is
  written (meta `auto_flow`), or with "Build it" / "Build it again" on the page (action `makeFormulaFlow`).
- **Checked by code** (`formula_flow.check`), the way the page computes it: short lowercase ids that are not function
  names; every input in one input box; a box uses only inputs and earlier boxes; every `{ref}` is known; every box
  computes at the start values and at each input's minimum and maximum; every what-if computes and has the box's
  shape; at most 10 inputs and 14 boxes. A flow with problems goes back to the agent once with them; then it fails,
  and the page shows why with "Try again".
- **On the page** (`FormulaFlow.tsx`): rows from the inputs down, arrows in the color of the value they carry; drag a
  dotted value (in a formula or a pill) and every formula that really uses it shows numbers in place of letters;
  "Numbers in every formula"; point at a box to keep only what it comes from and feeds; click a box for its card: the
  formula, what it is, its value now, "Built from" and "Used by" (click to move), and "What if this part were
  different?": pick another form, and every box below shows the real value and yours, with why it works or breaks.
  "Back to the real formula" undoes every what-if.
- **Normal lessons** no longer show the explorable formula widget: writers are told it is only for formula pages, and
  a widget in an existing lesson is hidden, with "Explore this formula on its own page" (a link when the formula has a
  page). Formula pages keep it.

## 53. Goals on the map: each goal a star at its own edge (2026-11-24)

What it is for: a goal shows which way to move. Setting a goal places it at an edge of the learner's land; every cell
sits closer to the goals it serves and away from the ones it does not. The chosen mock "C · Several goals"
(`web/public/_mocks/goal-map.html`). The old roadmap goals (`goals`, the "On hold: goals" pages) are not touched.

- **A goal** (`map_goals.py`; tables `map_goals`, `goal_blocks`, `goal_scores`): a title in one line, its direction,
  a color and an edge (angle; each new goal gets the next edge), its building blocks, and a score 0..1 per idea of the
  map (how much it moves the learner toward the goal; an idea with no score counts as 0.1).
- **The goal agent** (job `goal_research`, prompt `goal_research.md`, role "Research"): when a goal is added or
  renamed, it writes the direction, 6-12 building blocks (a block that is already a cell — by `same_as` or the same
  title — is "on the map" with score 1; the others are missing), and scores for the ideas that help (1 core, 0.7 on the
  way, 0.4 a side step). Code clamps scores to 0..1 and drops unknown ids.
- **New cells** (job `goal_score`, prompt `goal_score.md`): when the map is read, every goal with ideas it has no score
  for gets them scored (at most 200 at a time, one job per goal). An idea the agent leaves out is scored 0.1, so it is
  not asked again. A new cell that is a missing block (`block`) fills it.
- **The map** (`HexMap.layoutCells`): for each goal, every cell gets a strong pull to a place along the goal's
  direction set by its score (forward for a building block, backward for a side road); links still keep neighbours
  together. The goal's star sits just past the land's edge in its direction, with a soft glow; its missing blocks are
  dashed hexes in its color on the way to it; a cell with a score of 0.6 or more has a thin inner ring in the color of
  the goal it serves most.
- **The goal panel** (click a star): the direction; building blocks learned / started / on the map / missing; the
  next moves (cells of the goal next to what is learned); the missing blocks with "Add to map" (a new cell, score 1)
  and "Teach me this"; Rename (researched again) and Remove (the cells stay). "★ Add a goal" is in the map's legend.
