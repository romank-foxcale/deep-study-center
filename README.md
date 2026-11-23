# Deep Study Center

A local study app for big goals and deep understanding. You say what you want to learn. AI agents find what you
already know, teach the next idea one reasoning step at a time, and make you practise it until you can use it. All
your progress lives in one knowledge graph on your own computer.

It runs on your machine and uses the AI models you already have: the Claude Code, Codex or Cursor command-line tools
with your subscription, or an Anthropic API key. There is no account, no server of ours and no telemetry.

## What it does

- **"Teach me this book."** Pick one of your PDFs. Agents read it chapter by chapter and map its ideas into your
  knowledge graph, joined to what you already know. Then you study it one section at a time, with the book's own pages,
  and practise each section as homework. When a lesson uses an idea you met before, hover it to see where you learned
  it and what it connects to.
- **"Teach me X" study sessions.** A short probe asks one question at a time to find the edge of what you know. Then
  each idea is taught as predict → explain → check, fitted to your answers and to the thinking you type or dictate.
- **Knowledge map.** Everything you learn becomes a node in one graph, with the reasoning links between ideas. Choose
  how to see it: a tree, a skill wheel, nested cells or a hex map. Each book has one color, on its card and on the map.
- **Recall practice.** Problems that need the right idea without naming it. Hints, never answers. Each idea gets its
  own review schedule (FSRS).
- **Goals and roadmaps.** A big goal becomes a roadmap (an Ohtani 9x9 table or classic tracks) of researched,
  fact-checked lessons (on hold for now).
- **Lessons that adapt to you.** Give feedback on any part of a lesson; later lessons follow it. Interactive graphs,
  explain-back grading, runnable Python, a weekly plan across goals.
- **Think out loud.** Every question has a thinking box and a confidence slider. Dictation works through the browser
  or, privately, with a Whisper model on your computer.

The design and the reasons behind it are in [docs/SPEC.md](docs/SPEC.md). What changed when:
[docs/CHANGELOG.md](docs/CHANGELOG.md).

## Install

### From source (Windows, macOS, Linux)

You need Python 3.11+, Node 20+, and at least one model provider (see below).

```powershell
.\start.ps1        # Windows
```

```bash
./start.sh         # macOS / Linux
```

The first run creates the Python environment, builds the web UI, starts the app on http://127.0.0.1:8000 and opens
your browser. Start with your own goal or explore the demo.

### Desktop app (Windows)

A [Tauri](https://tauri.app) window around the same app; it needs no Python, Node or terminal. Download the installer
from the [Releases](https://github.com/romank-foxcale/deep-study-center/releases) page, or build it yourself (needs
Rust, Node 20+ and the backend environment with the dev extras):

```bash
cd desktop
npm install
npm run build     # the UI, the bundled backend and the installer
```

The installer is `desktop/src-tauri/target/release/bundle/nsis/Deep Study Center_<version>_x64-setup.exe` (per-user,
no admin rights). It is not code-signed, so Windows SmartScreen warns on the first run. See SPEC §25.

From 0.4.1, the installed app finds new versions itself: after the start it asks the Releases page for a newer
version and offers "Install and restart". Each update is signed, and the app installs only an update with a correct
signature (SPEC §39). Set `DSC_NO_UPDATE_CHECK=1` to turn the check off. A build of your own needs no signing key:
use `npm run build:local`. How to publish a release: [docs/RELEASING.md](docs/RELEASING.md).

## Model providers

Deep Study Center sends each agent job to a provider. Choose which job goes where in Settings → "Who does what".

| Provider | What you need | Billing |
|---|---|---|
| Claude Code CLI | `claude` on PATH, logged in | your Claude subscription |
| Codex CLI | `codex` on PATH, logged in | your ChatGPT subscription |
| Cursor CLI | `cursor-agent` on PATH, logged in | your Cursor subscription |
| Claude API | an Anthropic API key (Settings → Anthropic API key) | your API account |

The CLI adapters remove API-key variables from their environment, so your subscription is used, not an API account.
When no CLI works, jobs fall back to the Claude API if a key is set.

## Privacy: what stays on your computer and what does not

Stays local:

- Your workspace: `~/DeepStudy` (or `DSC_WORKSPACE`), a SQLite database, daily backups, your PDFs and downloaded models.
- Your API key: in the system credential store (Windows Credential Manager, macOS Keychain). Never in the database,
  logs or the UI.
- Local dictation: the audio goes to the Whisper model on your computer and is never stored.

Sent to other services:

- **To the model provider you chose:** the text each job needs. This includes your goal, your answers, your typed or
  dictated thinking, your notes and feedback, and pages of your PDFs when a lesson uses them. Research jobs also let
  the provider search and read the web.
- **To Google**, only if you use the browser's dictation (Chrome and Edge send the audio to Google). Choose "On this
  computer (Whisper)" in Settings → Dictation to avoid this.
- **To jsDelivr (a CDN):** the page loads Pyodide from it the first time you run Python in a lesson.
- **To Hugging Face:** the one-time download of a dictation model, only when you click "Download".
- **To GitHub (desktop app only):** one request for `latest.json` of the newest release at each start, to find an
  update. It sends no data about you or your workspace. `DSC_NO_UPDATE_CHECK=1` turns it off.

## Daily roadmap (terminal)

A separate, fixed 6-12 month plan to become an ML/AI engineer, a little every day. It works without the web app and
uses only the Python standard library: coding-interview problems with spaced reviews, topic tracks (ML and LLM
fundamentals, ML system design, ML for Earth and climate, LLM agents, public output) and a weekly post.

```bash
dsc roadmap init --start 2026-11-12   # writes ~/DeepStudy/roadmap/config.toml: edit it
dsc roadmap                           # today's plan
dsc roadmap done dsa-two-sum          # log progress (kept in your workspace, never in the repository)
```

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Development

Run the parts by hand (this is what the start scripts do):

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
npm run dev                               # http://localhost:5173 (sends /api to the backend)
```

Checks (CI runs the same on every pull request):

```bash
cd backend && .venv/Scripts/python -m pytest -q
cd web && npx tsc -b && npm run lint && npx vite build
```

To look at every screen with full data (books, all idea states, sessions, lessons with formulas and graphs)
without studying first, make a mock workspace. It never touches your real one:

```bash
dsc mock                                               # writes ~/DeepStudy-mock
DSC_WORKSPACE=~/DeepStudy-mock dsc serve --port 8001   # then open http://localhost:8001
```

The tests use a fake provider, so they need no model and no network. See [CONTRIBUTING.md](CONTRIBUTING.md) before
you open a pull request.

## Layout

```
docs/SPEC.md            product spec and decisions (one section per feature)
docs/TODO.md            open work, in order
backend/dsc/
  engine.py             BKT, mastery gate, FSRS, playbook replay (pure, no I/O)
  db.py                 workspace + SQLite schema
  state.py / actions.py read side (UI snapshots) / write side (every UI action)
  jobs.py               agent jobs and their offline fallbacks
  providers.py          Claude Code, Codex and Cursor CLI adapters, the Claude API, routing and fallback
  graph.py              the knowledge graph
  session.py            "teach me X" study sessions (sketch, probe, plan, teach, extract)
  practice.py           recall practice
  probe.py, mcq.py      the goal probe; shared multiple-choice helpers
  dictation.py          local Whisper dictation
  lesson.py, writer.py  lessons: planning, writing, review, versions
  prompts/              one prompt per job
  roadmap/              the daily roadmap (terminal)
backend/tests/          unit and end-to-end tests (fake provider)
web/src/                React UI: pages/, components/, store.tsx (API client)
desktop/                the Tauri desktop app and the PyInstaller backend bundle
```

## License

[MIT](LICENSE).
