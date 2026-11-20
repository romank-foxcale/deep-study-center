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
  and every answer with its thinking and confidence. It searches each area from the middle (toward the basics after a
  miss, "I don't know" or a guess; toward advanced steps after a sure hit), then drills into the edge. A round has at
  most 4 short questions (under 30 s each, "I don't know" added by the page). Limits: 5 rounds, 20 questions; at the
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
  2. Probe ("Study tutor" route, `session_probe.md`): rounds of up to 4 quick questions on the ideas not known yet,
     middle of the tree first; at most 3 rounds / 12 questions; "Stop asking and show the plan" ends it. Levels:
     known / partial / unknown.
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
