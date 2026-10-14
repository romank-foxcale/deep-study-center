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
- **Notes & highlights** (per lesson, anchored to text), searchable, readable by the tutor.
- **Feedback log**: every rating/comment with its target (lesson, section, example, angle),
  plus what the system changed in response ("playbook: geometric angle +", "roadmap: proposed
  inserting 'Dot product intuition'").
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
