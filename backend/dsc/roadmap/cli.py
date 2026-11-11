"""`dsc roadmap ...`: the daily study plan and your progress.

Your config and progress live in <workspace>/roadmap/ (default workspace ~/DeepStudy, override
with DSC_WORKSPACE), never in the repository. Run `dsc roadmap --help` for the commands.
Also runs without installing the app: `python -m dsc.roadmap` from the `backend` folder.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from . import plan as P


def workspace() -> Path:
    return Path(os.environ.get("DSC_WORKSPACE") or Path.home() / "DeepStudy").expanduser()


def paths(args) -> tuple[Path, Path]:
    base = workspace() / "roadmap"
    return (Path(args.config) if args.config else base / "config.toml",
            Path(args.progress) if args.progress else base / "progress.json")


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["events"]


def write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "events": events}, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# --- rendering ------------------------------------------------------------------------------

def render_item(cur: P.Curriculum, it: P.Item, done: bool, full: bool = True) -> str:
    u = it.unit
    box = "[x]" if done else "[ ]"
    if u.kind == "problem":
        label = f"{'Review' if it.review else 'Code'} - {cur.patterns[u.pattern]}: {u.title} ({u.difficulty})"
    elif u.kind == "pattern":
        label = f"Code - {u.title}"
    elif u.kind == "post":
        label = f"Post - {u.title}"
    else:
        label = f"{cur.track_titles[u.track]} - {u.title}"
    lines = [f"### {box} {label}, {it.minutes} min  `{u.id}`"]
    if not full:
        return lines[0]
    if it.review:
        lines += [
            "- Goal: Keep the pattern fresh with spaced repetition.",
            f"- Resources: LeetCode {u.resources[0].url}",
            f"- Exercise: Solve it again from a blank editor in {it.minutes} min, without notes. Say the pattern and the complexity aloud.",
            f"- Done when: LeetCode accepts it without hints. If you needed help: `dsc roadmap done {u.id} --fail`.",
        ]
        return "\n".join(lines)
    lines.append(f"- Goal: {u.goal}")
    if u.resources:
        lines.append("- Resources:")
        for r in u.resources:
            note = f" ({r.note})" if r.note else ""
            lines.append(f"  - {r.title}{note}: {r.url}")
    lines.append(f"- Exercise: {u.exercise}")
    lines.append(f"- Done when: {u.done_when}")
    return "\n".join(lines)


def render_day(cur: P.Curriculum, cfg: dict, day: date, items: list[P.Item], events: list[dict],
               full: bool = True) -> str:
    head = f"## Day {P.day_number(cfg, day)} - {day.strftime('%a')} {day.isoformat()}"
    if not items:
        return f"{head} - rest day\n"
    total = sum(it.minutes for it in items)
    done_ids = {e["id"] for e in events if e["date"] == day.isoformat() and e["result"] in ("done", "fail", "skip")}
    body = [render_item(cur, it, it.unit.id in done_ids, full) for it in items]
    return f"{head} - {total} min (budget {P.budget(cfg, day)})\n\n" + "\n\n".join(body) + "\n"


# --- commands -------------------------------------------------------------------------------

def load(args):
    cfg_path, prog_path = paths(args)
    if not cfg_path.exists():
        raise SystemExit(f"No config at {cfg_path}. Run `dsc roadmap init` first.")
    cur = P.load_curriculum()
    cfg = P.load_config(cfg_path)
    return cur, cfg, read_events(prog_path), prog_path


def parse_day(s: str | None) -> date:
    return date.fromisoformat(s) if s else date.today()


def cmd_init(args) -> None:
    cfg_path, prog_path = paths(args)
    if cfg_path.exists() and not args.force:
        print(f"Config already exists: {cfg_path}\nEdit it, or run again with --force to replace it.")
        return
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    text = P.EXAMPLE_CONFIG.read_text(encoding="utf-8")
    start = parse_day(args.start)
    text = text.replace('start_date = "2026-11-12"', f'start_date = "{start.isoformat()}"', 1)
    cfg_path.write_text(text, encoding="utf-8")
    print(f"Wrote {cfg_path} (start date {start.isoformat()}).")
    print(f"Progress will be saved to {prog_path}.")
    print("Next: edit the config, then run `dsc roadmap today`.")


def cmd_today(args) -> None:
    cur, cfg, events, _ = load(args)
    day = parse_day(args.date)
    print(render_day(cur, cfg, day, P.plan_day(cur, cfg, events, day), events))
    print("Mark a unit: dsc roadmap done <id>   (a failed review: --fail)")


def cmd_plan(args) -> None:
    cur, cfg, events, _ = load(args)
    start = parse_day(args.start) if args.start else max(date.today(), cfg["start_date"])
    days, _ = P.simulate(cur, cfg, events, start, args.days)
    out = [f"# Plan for {args.days} days from {start.isoformat()}",
           "Assumes you finish each day's plan on that day.", ""]
    for day, items in days:
        out.append(render_day(cur, cfg, day, items, [], full=not args.brief))
    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


def _known_id(cur: P.Curriculum, uid: str) -> bool:
    return uid in cur.units or (uid.startswith("post-") and len(uid) == len("post-2026-W01"))


def cmd_mark(args, result: str) -> None:
    cur, cfg, events, prog_path = load(args)
    day = parse_day(args.date).isoformat()
    for uid in args.ids:
        if not _known_id(cur, uid):
            raise SystemExit(f"Unknown id '{uid}'. Find ids with `dsc roadmap today` or `dsc roadmap list`.")
    for uid in args.ids:
        e = {"id": uid, "date": day, "result": result}
        if getattr(args, "note", None):
            e["note"] = args.note
        events.append(e)
        print(f"{result}: {uid} ({day})")
    write_events(prog_path, events)


def cmd_undo(args) -> None:
    cur, cfg, events, prog_path = load(args)
    for i in range(len(events) - 1, -1, -1):
        if events[i]["id"] == args.id:
            e = events.pop(i)
            write_events(prog_path, events)
            print(f"Removed: {e['result']} {e['id']} ({e['date']})")
            return
    raise SystemExit(f"No progress entry for '{args.id}'.")


def cmd_status(args) -> None:
    cur, cfg, events, _ = load(args)
    today = date.today()
    last = {}
    for e in events:
        last[e["id"]] = e["result"]
    closed = {i for i, r in last.items() if r in ("done", "skip")}
    skipped = {i for i, r in last.items() if r == "skip"}
    print(f"Goal: {cfg['goal']}" if cfg["goal"] else "Goal: (set `goal` in your config)")
    print(f"Started {cfg['start_date'].isoformat()}, today is day {P.day_number(cfg, today)}.\n")
    probs = [u for u in cur.units.values() if u.kind == "problem" and not P.is_skipped(cur, cfg, u.id, skipped)]
    solved = sum(1 for u in probs if u.id in last)
    print(f"- Coding problems: {solved}/{len(probs)} attempted")
    for tid, ids in cur.tracks.items():
        t = P.track_cfg(cfg, tid)
        if not t["enabled"]:
            print(f"- {cur.track_titles[tid]}: off")
            continue
        active = [i for i in ids if not P.is_skipped(cur, cfg, i, skipped)]
        print(f"- {cur.track_titles[tid]}: {sum(1 for i in active if i in closed)}/{len(active)} units")
    posts = sorted(i for i, r in last.items() if i.startswith("post-") and r == "done")
    print(f"- Weekly posts: {len(posts)} published")
    streak, day = 0, today
    days_with_work = {e["date"] for e in events}
    if today.isoformat() not in days_with_work:
        day = today - timedelta(days=1)
    while day.isoformat() in days_with_work or (not P.is_study_day(cfg, day) and day >= cfg["start_date"]):
        streak += day.isoformat() in days_with_work
        day -= timedelta(days=1)
    print(f"- Streak: {streak} study days")
    end = P.finish_date(cur, cfg, events, max(today, cfg["start_date"]))
    if end:
        months = (end - cfg["start_date"]).days / 30.4
        print(f"- At this pace, the last new unit is on {end.isoformat()} (about {months:.0f} months from the start).")


def cmd_list(args) -> None:
    cur = P.load_curriculum()
    cfg_path, prog_path = paths(args)
    last = {e["id"]: e["result"] for e in read_events(prog_path)}
    groups = [("dsa", "Coding interviews", cur.dsa)] + [(t, cur.track_titles[t], ids) for t, ids in cur.tracks.items()]
    for tid, title, ids in groups:
        if args.track and args.track != tid:
            continue
        mins = sum(cur.units[i].minutes for i in ids)
        print(f"\n## {title} ({tid}, {len(ids)} units{'' if tid == 'dsa' else f', {mins / 60:.0f} h'})")
        for i in ids:
            u = cur.units[i]
            mark = {"done": "x", "skip": "-", "fail": "!"}.get(last.get(i, ""), " ")
            extra = f" ({u.difficulty})" if u.difficulty else ""
            req = f"  after: {', '.join(u.requires)}" if u.requires else ""
            print(f"[{mark}] {i}: {u.title}{extra}{req}")


def cmd_show(args) -> None:
    cur = P.load_curriculum()
    if args.id not in cur.units:
        raise SystemExit(f"Unknown id '{args.id}'.")
    u = cur.units[args.id]
    print(render_item(cur, P.Item(u, minutes=u.minutes), False))


def cmd_check(args) -> None:
    cur = P.load_curriculum()
    n_prob = sum(1 for u in cur.units.values() if u.kind == "problem")
    n_unit = sum(len(v) for v in cur.tracks.values())
    print(f"Curriculum OK: {n_prob} coding problems in {len(cur.patterns)} patterns, "
          f"{n_unit} topic units in {len(cur.tracks)} tracks, {len(cur.resources)} resources.")
    cfg_path, _ = paths(args)
    if cfg_path.exists():
        P.load_config(cfg_path)
        print(f"Config OK: {cfg_path}")


def cmd_check_links(args) -> None:
    from .links import check_all
    sys.exit(check_all(P.load_curriculum(), leetcode=not args.no_leetcode))


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(prog="dsc roadmap", description="Daily study roadmap: plan and progress.")
    p.add_argument("--config", help="config file (default: <workspace>/roadmap/config.toml)")
    p.add_argument("--progress", help="progress file (default: <workspace>/roadmap/progress.json)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("init", help="create your config in the workspace")
    s.add_argument("--start", help="start date YYYY-MM-DD (default: today)")
    s.add_argument("--force", action="store_true", help="replace an existing config")
    s = sub.add_parser("today", help="show the plan for today (the default command)")
    s.add_argument("--date", help="another day, YYYY-MM-DD")
    s = sub.add_parser("plan", help="preview the next days, assuming each day is done")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--start", help="first day YYYY-MM-DD (default: today or the start date)")
    s.add_argument("--brief", action="store_true", help="titles only")
    s.add_argument("--out", help="write Markdown to this file")
    for name, help_ in (("done", "mark units done (or a review passed)"), ("skip", "take units out of your plan")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("ids", nargs="+")
        s.add_argument("--date", help="the day you did it, YYYY-MM-DD (default: today)")
        s.add_argument("--note", help="a short note to keep with the entry")
        if name == "done":
            s.add_argument("--fail", action="store_true", help="you could not solve it without help")
    s = sub.add_parser("undo", help="remove the last progress entry for a unit")
    s.add_argument("id")
    sub.add_parser("status", help="progress per track, streak and projected finish")
    s = sub.add_parser("list", help="every unit, with your marks")
    s.add_argument("--track", help="only this track: dsa, ml, earth, agents, sysdesign, public")
    s = sub.add_parser("show", help="the full card of one unit")
    s.add_argument("id")
    sub.add_parser("check", help="validate the curriculum data and your config")
    s = sub.add_parser("check-links", help="check every resource URL and LeetCode problem (needs network)")
    s.add_argument("--no-leetcode", action="store_true")

    args = p.parse_args(argv)
    cmd = args.cmd or "today"
    if cmd == "today" and not hasattr(args, "date"):
        args.date = None
    {
        "init": cmd_init, "today": cmd_today, "plan": cmd_plan,
        "done": lambda a: cmd_mark(a, "fail" if a.fail else "done"),
        "skip": lambda a: cmd_mark(a, "skip"),
        "undo": cmd_undo, "status": cmd_status, "list": cmd_list, "show": cmd_show,
        "check": cmd_check, "check-links": cmd_check_links,
    }[cmd](args)
