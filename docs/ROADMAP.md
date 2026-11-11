# Daily roadmap

The daily roadmap gives you a short study plan for every day, for 6 to 12 months. It is for a
goal like "become an ML/AI engineer at a large AI company". It runs in the terminal, uses only
the Python standard library, and works without the web app.

Each day has:

1. **Coding interviews** from day 1: new LeetCode problems in pattern order, and spaced reviews
   of the problems you solved.
2. **One or more topic units** from the tracks you turned on, as many as fit your time budget.
3. **A weekly post** on one weekday, built from the units you finished that week.

Every unit has one goal, resources (free where possible), an exercise and a "done when" check.

## What is in it

| Track | Id | Content |
|---|---|---|
| Coding interviews | `dsa` | 155 free LeetCode problems in 18 patterns: arrays and hashing, two pointers, sliding window, stack, binary search, linked list, trees, tries, heaps, graphs, advanced graphs, backtracking, 1-D and 2-D DP, greedy, intervals, math, bits |
| ML and LLM fundamentals | `ml` | Math refresh, classic ML, deep learning, transformers and GPT from scratch, LLM training, LoRA and QLoRA, evaluation, inference and serving cost, RAG |
| ML for Earth and climate | `earth` | Gridded data, WeatherBench, ML weather models (FourCastNet, GraphCast, Pangu, GenCast, NeuralGCM), foundation models (ClimaX, Aurora), downscaling, satellite ML, geospatial foundation models, a capstone |
| LLM agents and agent collaboration | `agents` | Agent loops, tool use, MCP, context engineering, agent evals, multi-agent systems, handoffs, routing, switching models mid-trajectory, KV-cache and embedding communication, a research write-up |
| ML system design | `sysdesign` | An answer framework, data, experiments, recommendation, search, ads, fraud, serving and monitoring, LLM systems, agents, a weather service, mock interviews |
| Public output | `public` | Blog, GitHub profile, first post. Weekly posts come from `[posts]` in the config |

Run `dsc roadmap list` to see every unit, and `dsc roadmap show <id>` for one unit.

## Start

You need Python 3.11 or later. With the app installed (`start.ps1` or `start.sh`), use `dsc roadmap`.
Without it, run `python -m dsc.roadmap` from the `backend` folder.

1. Create your config:

   ```bash
   dsc roadmap init --start 2026-11-12
   ```

2. Edit the config that `init` printed (see [Personalize](#personalize)).
3. Preview the first week:

   ```bash
   dsc roadmap plan --days 7
   ```

4. Every day, show the plan and mark what you finished:

   ```bash
   dsc roadmap
   dsc roadmap done dsa-two-sum ml-linalg
   ```

## Commands

| Command | What it does |
|---|---|
| `dsc roadmap` or `dsc roadmap today` | The plan for today. `--date` shows another day |
| `dsc roadmap plan --days 7` | A preview of the next days. It assumes you finish each day. `--brief` shows titles only, `--out week.md` writes a file |
| `dsc roadmap done <id> ...` | Marks units done. For a review you could not solve without help, add `--fail`: it comes back the next day |
| `dsc roadmap skip <id> ...` | Takes units out of your plan (you know them already) |
| `dsc roadmap undo <id>` | Removes the last entry for a unit |
| `dsc roadmap status` | Progress per track, streak, and the projected end date |
| `dsc roadmap list [--track ml]` | Every unit with your marks: `x` done, `-` skipped, `!` failed |
| `dsc roadmap show <id>` | The full card of one unit |
| `dsc roadmap check` | Validates the curriculum data and your config |
| `dsc roadmap check-links` | Checks every resource URL and every LeetCode problem (title, difficulty, free). Needs network |

## How the plan is made

- The plan for a day comes from the progress you logged **before** that day. It does not change
  while you work through it.
- Work you did not do moves to the next study day. Nothing is lost.
- Coding: reviews that are due come first (at most `max_reviews_per_day`), then `new_per_day` new
  problems. A pattern intro comes before the first problem of each pattern. After a solve, the
  reviews come after 3, 7, 21 and 60 days (`review_intervals`). A failed review comes back the next day.
- Topics: the next unit comes from the track that is furthest behind its share (`weight`). Inside
  a track, units come in file order, but a unit waits until the units in its `requires` are done.
  A day always gets one topic unit, except a post day. A second unit comes only if it fits the budget.
- Posts: on `posts.weekday`, the plan adds a post about the units you finished in the last 7 days.
  An open post stays in the plan until the next post day.

## Personalize

Your personal data is the config and the progress log. Both live in your workspace, not in the
repository:

```
~/DeepStudy/roadmap/config.toml     your settings (DSC_WORKSPACE changes ~/DeepStudy)
~/DeepStudy/roadmap/progress.json   one entry per unit you finished, skipped or failed
```

The config has comments for every setting. The main ones:

| Setting | Use |
|---|---|
| `start_date` | Day 1 of the plan |
| `time.minutes_per_day`, `time.minutes_by_weekday` | Your time budget |
| `time.study_days` | Days with a plan. Other days are rest days |
| `dsa.new_per_day`, `dsa.max_reviews_per_day` | Coding load |
| `dsa.skip_patterns` | Patterns you already master |
| `tracks.<id>.enabled`, `.weight` | Which tracks you study, and their share of days |
| `tracks.<id>.skip_basics` | Skip units marked basic (setup, math refresh, intro classic ML) |
| `tracks.<id>.skip` | Unit ids you know already |
| `posts.enabled`, `.weekday` | The weekly post |

To keep your progress safe, back up the workspace folder, or point `DSC_WORKSPACE` at a folder
inside a **private** repository.

## Change the curriculum

The curriculum is data in `backend/dsc/roadmap/data/`:

- `resources.toml`: every resource, once, with a title and URL. Units refer to it by key, with an
  optional pointer: `"mml-book: chapter 2"`.
- `dsa.toml`: patterns with their problems (`[slug, title, difficulty]`).
- `ml.toml`, `earth.toml`, `agents.toml`, `sysdesign.toml`, `public.toml`: one track each. A unit
  has `id`, `title`, `minutes`, `goal`, `resources`, `exercise`, `done_when`, and optional
  `requires` and `basic`.

After a change, run `dsc roadmap check`, `dsc roadmap check-links` and the tests
(`python -m pytest tests/test_roadmap.py` in `backend`).

## Fork it for your own goal

1. Fork the repository.
2. Change the track files to your goal, or turn tracks off in your config.
3. Keep your config and progress in your workspace. The repository then stays free of personal data.
