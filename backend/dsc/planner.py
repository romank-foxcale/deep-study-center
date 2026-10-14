"""Weekly plan across all goals (deterministic, no LLM calls).

Each goal gets a share of the weekly study time proportional to its hours/week. Every study day
gets an equal slice of the week. Within a day: spaced reviews due that day come first (across all
goals), then lessons, always taken from the goal furthest behind its share. Lessons follow each
goal's roadmap order; a lesson whose prerequisites are planned earlier in the week can follow
them. A learned lesson's confirmation review is projected for the next study day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import state
from .db import DB

REVIEW_MINUTES = 3
DEFAULTS = {"weekly_hours": None, "study_days": "0,1,2,3,4,5", "start_time": "19:00"}  # Mon=0 ... Sun=6


@dataclass
class Item:
    kind: str            # review | lesson
    goal_id: str
    concept_id: str
    title: str
    minutes: int
    note: str = ""


@dataclass
class Day:
    date: date
    budget: int
    items: list[Item] = field(default_factory=list)

    @property
    def used(self) -> int:
        return sum(i.minutes for i in self.items)


def settings(db: DB) -> dict:
    out = {k: db.meta(f"plan_{k}", v) for k, v in DEFAULTS.items()}
    days = sorted({int(d) for d in str(out["study_days"]).split(",") if d.strip().isdigit() and 0 <= int(d) <= 6})
    goals = db.q("SELECT hours FROM goals")
    default_hours = sum(g["hours"] for g in goals) or 5
    try:
        hours = float(out["weekly_hours"]) if out["weekly_hours"] else default_hours
    except ValueError:
        hours = default_hours
    return {"weekly_hours": hours, "study_days": days or [0, 1, 2, 3, 4], "start_time": out["start_time"] or "19:00"}


def _goal_queue(db: DB, goal_id: str) -> tuple[list[dict], dict[str, str], list[dict], set[str]]:
    """(lesson candidates in roadmap order, state per concept, reviews with due dates,
    concepts in modules placement marked as known)."""
    concepts, states = state.concept_states(db, goal_id)
    known_modules = {m["id"] for m in db.q(
        "SELECT m.id FROM modules m JOIN tracks t ON t.id = m.track_id WHERE t.goal_id = ? AND m.known = 1", (goal_id,))}
    has_card = {r["concept_id"] for r in db.q("SELECT DISTINCT concept_id FROM cards")}
    queue = [{**c, "has_card": c["id"] in has_card} for c in concepts if c["module_id"] not in known_modules
             and states[c["id"]].state in ("ready", "learning", "locked", "rusty")]
    ids = [c["id"] for c in concepts]
    reviews = db.q(f"SELECT concept_id, due FROM reviews WHERE concept_id IN ({','.join('?' * len(ids))})", ids) if ids else []
    known = {c["id"] for c in concepts if c["module_id"] in known_modules}
    return queue, {cid: s.state for cid, s in states.items()}, reviews, known


def plan_week(db: DB, start: date | None = None) -> dict:
    cfg = settings(db)
    start = start or date.today()
    days = [Day(start + timedelta(d), 0) for d in range(7)]
    study = [d for d in days if d.date.weekday() in cfg["study_days"]]
    week_minutes = int(cfg["weekly_hours"] * 60)
    for d in study:
        d.budget = week_minutes // max(1, len(study))

    goals = db.q("SELECT id, title, hours FROM goals ORDER BY created_at")
    total_hours = sum(g["hours"] for g in goals) or 1
    share = {g["id"]: g["hours"] / total_hours for g in goals}
    titles: dict[str, str] = {}
    queues, states, done_or_planned = {}, {}, set()
    pending_reviews: list[tuple[date, Item]] = []
    for g in goals:
        queue, st, reviews, known = _goal_queue(db, g["id"])
        queues[g["id"]] = queue
        states.update(st)
        done_or_planned |= known
        for c in state.concepts_raw(db, g["id"]):
            titles[c["id"]] = c["title"]
        for r in reviews:
            due = datetime.fromisoformat(r["due"]).date()
            pending_reviews.append((max(due, start), Item("review", g["id"], r["concept_id"], titles.get(r["concept_id"], ""), REVIEW_MINUTES,
                                                          "overdue" if due < start else "")))
    done_or_planned |= {cid for cid, s in states.items() if s in ("learned", "mastered")}
    used = {g["id"]: 0 for g in goals}

    def next_lesson(goal_id: str) -> dict | None:
        for c in queues[goal_id]:
            if c["id"] not in done_or_planned and all(p in done_or_planned for p in c["prereqs"]):
                return c
        return None

    for i, d in enumerate(days):
        if d not in study:
            continue
        # 1. reviews due by today (projected ones included), across goals
        for due, item in sorted(pending_reviews, key=lambda x: x[0]):
            if due <= d.date:
                d.items.append(item)
                used[item.goal_id] += item.minutes
        pending_reviews = [(due, it) for due, it in pending_reviews if due > d.date]
        # 2. lessons from the goal furthest behind its share, until the day is full
        while d.used < d.budget:
            ranked = sorted(goals, key=lambda g: used[g["id"]] / max(1, share[g["id"]] * week_minutes))
            pick = next(((g, c) for g in ranked if (c := next_lesson(g["id"]))), None)
            if not pick:
                break
            g, c = pick
            minutes = int(c["minutes"])
            if d.items and d.used + minutes > d.budget * 1.15:
                break  # don't overfill a day that already has something in it
            note = "continue" if states[c["id"]] == "learning" else ("" if c["has_card"] else "needs research")
            d.items.append(Item("lesson", g["id"], c["id"], c["title"], minutes, note))
            used[g["id"]] += minutes
            done_or_planned.add(c["id"])
            nxt = next((x.date for x in study if x.date > d.date), d.date + timedelta(1))
            pending_reviews.append((nxt, Item("review", g["id"], c["id"], c["title"], REVIEW_MINUTES, "confirm")))

    # Modules still to be researched before their lessons can be planned (research runs ahead on its own).
    upcoming = []
    for g in goals:
        m = db.one("""SELECT m.id, m.title, m.research FROM modules m JOIN tracks t ON t.id = m.track_id
                      WHERE t.goal_id = ? AND m.known = 0 AND m.research != 'ready' ORDER BY t.ord, m.ord LIMIT 1""", (g["id"],))
        if m:
            upcoming.append({"goalId": g["id"], "moduleId": m["id"], "title": m["title"], "research": m["research"]})

    return {
        "start": start.isoformat(), "settings": cfg, "upcomingResearch": upcoming,
        "days": [{"date": d.date.isoformat(), "weekday": d.date.strftime("%a"), "study": d in study, "budget": d.budget,
                  "minutes": d.used, "items": [{"kind": i.kind, "goalId": i.goal_id, "conceptId": i.concept_id, "title": i.title,
                                                "minutes": i.minutes, "note": i.note} for i in d.items]} for d in days],
        "goals": [{"id": g["id"], "title": g["title"], "share": round(share[g["id"]], 3),
                   "plannedMinutes": used[g["id"]], "targetMinutes": int(share[g["id"]] * week_minutes)} for g in goals],
    }


def to_ics(plan: dict) -> str:
    """One calendar event per study day that has items, at the configured start time (floating local time)."""
    hh, mm = (int(x) for x in plan["settings"]["start_time"].split(":"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Deep Study Center//Weekly plan//EN", "CALSCALE:GREGORIAN"]
    for d in plan["days"]:
        if not d["items"]:
            continue
        day = date.fromisoformat(d["date"])
        begin = datetime(day.year, day.month, day.day, hh, mm)
        end = begin + timedelta(minutes=max(15, d["minutes"]))
        lessons = [i for i in d["items"] if i["kind"] == "lesson"]
        reviews = [i for i in d["items"] if i["kind"] == "review"]
        summary = "Study: " + (", ".join(i["title"] for i in lessons[:3]) or f"{len(reviews)} review(s)")
        desc = [f"- {i['title']} ({i['minutes']} min{', ' + i['note'] if i['note'] else ''})" for i in lessons]
        if reviews:
            desc.append(f"- {len(reviews)} spaced review(s): " + ", ".join(i["title"] for i in reviews))
        lines += ["BEGIN:VEVENT", f"UID:dsc-{d['date']}@deep-study-center", f"DTSTAMP:{stamp}",
                  f"DTSTART:{begin:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}",
                  _fold(f"SUMMARY:{_ics_escape(summary)}"), _fold(f"DESCRIPTION:{_ics_escape(chr(10).join(desc))}"), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)
