"""Daily roadmap planner: curriculum data + your config + your progress -> the plan for a day.

Pure functions, standard library only. The plan for a day is computed from the progress logged
*before* that day, so it stays stable while you work through it, and missed work rolls forward
by itself. Nothing here writes files; see ``cli`` for that.
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
EXAMPLE_CONFIG = Path(__file__).parent / "config.example.toml"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TOPIC_FILES = ["ml", "earth", "agents", "sysdesign", "public"]
UNIT_FIELDS = ("title", "goal", "exercise", "done_when")


@dataclass(frozen=True)
class Resource:
    title: str
    url: str
    note: str = ""


@dataclass
class Unit:
    id: str
    track: str
    title: str
    minutes: int
    goal: str
    exercise: str
    done_when: str
    resources: list[Resource] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    basic: bool = False
    kind: str = "unit"          # unit | pattern | problem | post
    pattern: str = ""           # dsa pattern id for pattern and problem units
    difficulty: str = ""        # easy | medium | hard for problems


@dataclass
class Item:
    """One entry of a day's plan: a unit, and whether it is new work or a review."""
    unit: Unit
    review: bool = False
    minutes: int = 0


@dataclass
class Curriculum:
    units: dict[str, Unit]
    tracks: dict[str, list[str]]        # topic track id -> unit ids in file order
    track_titles: dict[str, str]
    dsa: list[str]                      # pattern intros and problems, in study order
    patterns: dict[str, str]            # pattern id -> title
    resources: dict[str, Resource]


# --- loading --------------------------------------------------------------------------------

def _resolve(ref: str, catalog: dict[str, Resource], where: str) -> Resource:
    key, _, note = ref.partition(":")
    key = key.strip()
    if key not in catalog:
        raise ValueError(f"{where}: unknown resource '{key}' (add it to resources.toml)")
    res = catalog[key]
    return Resource(res.title, res.url, note.strip())


def load_curriculum(data_dir: Path = DATA_DIR) -> Curriculum:
    with open(data_dir / "resources.toml", "rb") as f:
        raw_res = tomllib.load(f)
    catalog = {k: Resource(v["title"], v["url"]) for k, v in raw_res.items()}
    units: dict[str, Unit] = {}
    tracks: dict[str, list[str]] = {}
    titles: dict[str, str] = {}

    def add(u: Unit) -> None:
        if u.id in units:
            raise ValueError(f"duplicate unit id '{u.id}'")
        units[u.id] = u

    with open(data_dir / "dsa.toml", "rb") as f:
        dsa_raw = tomllib.load(f)
    dsa: list[str] = []
    patterns: dict[str, str] = {}
    for p in dsa_raw["pattern"]:
        pid, ptitle = p["id"], p["title"]
        patterns[pid] = ptitle
        res = [_resolve(r, catalog, f"pattern {pid}") for r in p["resources"]]
        intro = Unit(
            id=f"dsa-pattern-{pid}", track="dsa", title=f"Pattern: {ptitle}", minutes=20,
            goal=f"Learn the idea before the problems. {p['idea']}",
            exercise=(f"Read the resources. In `patterns/{pid}.py`, write the pattern's template from memory, "
                      "and list 3 phrases in a problem statement that point to this pattern."),
            done_when="Your template file exists, and you can say the idea in one sentence without notes.",
            resources=res, kind="pattern", pattern=pid,
        )
        add(intro)
        dsa.append(intro.id)
        for slug, ptitle_, diff in p["problems"]:
            u = Unit(
                id=f"dsa-{slug}", track="dsa", title=ptitle_, minutes=0,
                goal=f"Solve '{ptitle_}' with the {ptitle.lower()} pattern.",
                exercise=("Solve it in Python without hints, inside the time box. If you are stuck at the end of "
                          "the time box, read one hint or the NeetCode explanation, close it, and code it yourself. "
                          "Write the time and space complexity as a comment."),
                done_when="LeetCode accepts your solution, and you can say in two sentences why the pattern fits.",
                resources=[Resource(f"LeetCode: {ptitle_}", f"https://leetcode.com/problems/{slug}/"),
                           catalog["neetcode-roadmap"]],
                kind="problem", pattern=pid, difficulty=diff,
            )
            add(u)
            dsa.append(u.id)

    for name in TOPIC_FILES:
        with open(data_dir / f"{name}.toml", "rb") as f:
            raw = tomllib.load(f)
        tid = raw["track"]["id"]
        titles[tid] = raw["track"]["title"]
        tracks[tid] = []
        for r in raw["unit"]:
            for key in ("id", "minutes", "resources", *UNIT_FIELDS):
                if not r.get(key):
                    raise ValueError(f"unit {r.get('id', '?')} in {name}.toml: missing '{key}'")
            add(Unit(
                id=r["id"], track=tid, title=r["title"], minutes=int(r["minutes"]), goal=r["goal"],
                exercise=r["exercise"], done_when=r["done_when"],
                resources=[_resolve(x, catalog, f"unit {r['id']}") for x in r["resources"]],
                requires=list(r.get("requires", [])), basic=bool(r.get("basic", False)),
            ))
            tracks[tid].append(r["id"])

    for u in units.values():
        for req in u.requires:
            if req not in units:
                raise ValueError(f"unit {u.id}: requires unknown unit '{req}'")
    return Curriculum(units, tracks, titles, dsa, patterns, catalog)


DEFAULT_CONFIG: dict[str, Any] = {
    "start_date": None,
    "goal": "",
    "time": {"minutes_per_day": 90, "study_days": WEEKDAYS, "minutes_by_weekday": {}},
    "dsa": {"enabled": True, "new_per_day": 1, "max_reviews_per_day": 2, "review_intervals": [3, 7, 21, 60],
            "minutes_easy": 20, "minutes_medium": 35, "minutes_hard": 50, "minutes_review": 15,
            "skip_patterns": []},
    "tracks": {},
    "posts": {"enabled": True, "weekday": "sun", "minutes": 60},
}
DEFAULT_TRACK = {"enabled": True, "weight": 1.0, "skip_basics": False, "skip": []}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return normalize_config(tomllib.load(f))


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _merge(DEFAULT_CONFIG, raw)
    cfg["start_date"] = date.fromisoformat(str(cfg["start_date"])) if cfg["start_date"] else date.today()
    for day in cfg["time"]["study_days"]:
        if day not in WEEKDAYS:
            raise ValueError(f"config: unknown weekday '{day}' (use {', '.join(WEEKDAYS)})")
    if cfg["posts"]["weekday"] not in WEEKDAYS:
        raise ValueError(f"config: unknown posts.weekday '{cfg['posts']['weekday']}'")
    cfg["tracks"] = {tid: _merge(DEFAULT_TRACK, t) for tid, t in cfg["tracks"].items()}
    return cfg


def track_cfg(cfg: dict, track: str) -> dict:
    return cfg["tracks"].get(track, DEFAULT_TRACK)


# --- progress -------------------------------------------------------------------------------

def _events_before(events: list[dict], day: date) -> list[dict]:
    iso = day.isoformat()
    return [e for e in events if e["date"] < iso]


def is_skipped(cur: Curriculum, cfg: dict, uid: str, closed: set[str]) -> bool:
    """True when config or a 'skip' event takes a unit out of the plan."""
    u = cur.units.get(uid)
    if u is None:
        return False
    if u.track == "dsa":
        return u.pattern in cfg["dsa"]["skip_patterns"] or not cfg["dsa"]["enabled"]
    t = track_cfg(cfg, u.track)
    return (not t["enabled"]) or uid in t["skip"] or (u.basic and t["skip_basics"]) or uid in closed


def _problem_due(history: list[dict], intervals: list[int]) -> date | None:
    """Next review date of a problem from its events, or None when it is retired."""
    last = history[-1]
    last_day = date.fromisoformat(last["date"])
    if last["result"] == "fail":
        return last_day + timedelta(days=1)
    passes = 0
    for e in reversed(history):
        if e["result"] == "fail":
            break
        passes += 1
    step = passes - 1                     # the first solve schedules intervals[0]
    if step >= len(intervals):
        return None
    return last_day + timedelta(days=intervals[step])


def post_id(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"post-{year}-W{week:02d}"


def _post_unit(cur: Curriculum, cfg: dict, post_day: date, events: list[dict]) -> Unit:
    lo, hi = (post_day - timedelta(days=6)).isoformat(), post_day.isoformat()
    seen: list[str] = []
    for e in events:
        u = cur.units.get(e["id"])
        if lo <= e["date"] <= hi and e["result"] == "done" and u and u.kind == "unit" and u.title not in seen:
            seen.append(u.title)
    topics = "; ".join(seen) if seen else "the coding problems you solved this week"
    return Unit(
        id=post_id(post_day), track="posts", title=f"Weekly post ({post_id(post_day)[5:]})",
        minutes=int(cfg["posts"]["minutes"]),
        goal="Publish one short post about something you learned this week.",
        exercise=(f"This week you studied: {topics}. Pick one idea. Write 400-800 words: explain it in plain words, "
                  "show one result you made (a plot, code or a number), and say what surprised you."),
        done_when="The post is live at a public URL (or a dated draft, if your blog is not set up yet).",
        kind="post",
    )


def problem_minutes(cfg: dict, u: Unit) -> int:
    return int(cfg["dsa"][f"minutes_{u.difficulty}"])


# --- the planner ----------------------------------------------------------------------------

def is_study_day(cfg: dict, day: date) -> bool:
    return WEEKDAYS[day.weekday()] in cfg["time"]["study_days"]


def budget(cfg: dict, day: date) -> int:
    return int(cfg["time"]["minutes_by_weekday"].get(WEEKDAYS[day.weekday()], cfg["time"]["minutes_per_day"]))


def plan_day(cur: Curriculum, cfg: dict, events: list[dict], day: date) -> list[Item]:
    """The plan for `day`, from the events logged before it."""
    if not is_study_day(cfg, day):
        return []
    past = _events_before(events, day)
    history: dict[str, list[dict]] = {}
    for e in past:
        history.setdefault(e["id"], []).append(e)
    closed = {i for i, h in history.items() if h[-1]["result"] in ("done", "skip")}
    skipped = {i for i, h in history.items() if h[-1]["result"] == "skip"}

    def satisfied(uid: str) -> bool:
        return uid in closed or is_skipped(cur, cfg, uid, skipped)

    items: list[Item] = []
    used = 0

    # 1. Coding interviews: spaced reviews first, then new problems in pattern order.
    if cfg["dsa"]["enabled"]:
        intervals = cfg["dsa"]["review_intervals"]
        due: list[tuple[date, int, str]] = []
        for pos, uid in enumerate(cur.dsa):
            u = cur.units[uid]
            if u.kind != "problem" or uid not in history or is_skipped(cur, cfg, uid, skipped):
                continue
            if history[uid][-1]["result"] == "skip":
                continue
            when = _problem_due(history[uid], intervals)
            if when is not None and when <= day:
                due.append((when, pos, uid))
        for _, _, uid in sorted(due)[: int(cfg["dsa"]["max_reviews_per_day"])]:
            m = int(cfg["dsa"]["minutes_review"])
            items.append(Item(cur.units[uid], review=True, minutes=m))
            used += m
        new = 0
        for uid in cur.dsa:
            if new >= int(cfg["dsa"]["new_per_day"]):
                break
            u = cur.units[uid]
            if uid in history or is_skipped(cur, cfg, uid, skipped):
                continue
            m = u.minutes if u.kind == "pattern" else problem_minutes(cfg, u)
            items.append(Item(u, minutes=m))
            used += m
            if u.kind == "problem":
                new += 1

    # 2. The weekly post, on its weekday, or later in the week if it is still open.
    posting = False
    if cfg["posts"]["enabled"]:
        back = (day.weekday() - WEEKDAYS.index(cfg["posts"]["weekday"])) % 7
        post_day = day - timedelta(days=back)
        if post_day >= cfg["start_date"] and post_id(post_day) not in closed:
            pu = _post_unit(cur, cfg, post_day, events)
            items.append(Item(pu, minutes=pu.minutes))
            used += pu.minutes
            posting = back == 0

    # 3. Topic units: the enabled track furthest behind its weight share goes next.
    spent: dict[str, float] = {t: 0.0 for t in cur.tracks}
    for uid in closed:
        u = cur.units.get(uid)
        if u and u.kind == "unit" and uid not in skipped:
            spent[u.track] += u.minutes
    planned: set[str] = set()
    remaining = budget(cfg, day) - used
    topics_today = 0
    while True:
        best: tuple[float, int, Unit] | None = None
        for order, (tid, ids) in enumerate(cur.tracks.items()):
            t = track_cfg(cfg, tid)
            if not t["enabled"] or float(t["weight"]) <= 0:
                continue
            nxt = next((cur.units[i] for i in ids if i not in closed and i not in planned
                        and not is_skipped(cur, cfg, i, skipped)
                        and all(satisfied(r) for r in cur.units[i].requires)), None)
            if nxt is None:
                continue
            key = (spent[tid] / float(t["weight"]), order, nxt)
            if best is None or key[:2] < best[:2]:
                best = key
        if best is None:
            break
        u = best[2]
        if u.minutes > remaining and (topics_today > 0 or posting):
            break
        items.append(Item(u, minutes=u.minutes))
        planned.add(u.id)
        spent[u.track] += u.minutes
        remaining -= u.minutes
        topics_today += 1
        if remaining <= 0:
            break
    return items


def simulate(cur: Curriculum, cfg: dict, events: list[dict], start: date, days: int
             ) -> tuple[list[tuple[date, list[Item]]], list[dict]]:
    """Plan `days` days from `start`, assuming each day's plan is done on that day."""
    events = list(events)
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        items = plan_day(cur, cfg, events, day)
        out.append((day, items))
        done_today = {e["id"] for e in events if e["date"] == day.isoformat()}
        for it in items:
            if it.unit.id not in done_today:
                events.append({"id": it.unit.id, "date": day.isoformat(), "result": "done"})
    return out, events


def finish_date(cur: Curriculum, cfg: dict, events: list[dict], start: date, horizon: int = 1500) -> date | None:
    """The day the last new unit or problem is planned, if all done as planned."""
    events = list(events)
    last = None
    for i in range(horizon):
        day = start + timedelta(days=i)
        items = plan_day(cur, cfg, events, day)
        if any(not it.review and it.unit.kind in ("unit", "problem", "pattern") for it in items):
            last = day
        elif (day - (last or start)).days > 30:
            break
        for it in items:
            events.append({"id": it.unit.id, "date": day.isoformat(), "result": "done"})
    return last


def day_number(cfg: dict, day: date) -> int:
    return (day - cfg["start_date"]).days + 1
