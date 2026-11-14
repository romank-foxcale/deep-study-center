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
