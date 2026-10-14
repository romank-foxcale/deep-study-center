"""Deterministic engine: no LLM calls, no I/O. Everything here is derived by replaying logs.

- Playbook (knowledge center #2's "how to teach this person") from the signal log.
- Mastery per concept (BKT + gate) from the evidence log, plus spaced-review state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler

ANGLES = ("geometric", "algebraic", "computational")
ADJUST_KEYS = ("pace", "depth", "rigor")

# Learner-model thresholds (calibrated in study-center's learner_model_sim).
WORKS, AVOID, MIN_EVIDENCE = 0.68, 0.32, 1.5

# BKT and mastery gate (as in study-center's mentor_core.learner).
SLIP, GUESS, TRANSIT = 0.10, 0.25, 0.15
GATE_P, GATE_CORRECT = 0.95, 3
CONFIRM_AFTER = timedelta(hours=20)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- playbook

def verdict(score: float, evidence: float) -> str:
    if evidence < MIN_EVIDENCE:
        return "trying"
    if score >= WORKS:
        return "works"
    if score <= AVOID:
        return "avoid"
    return "trying"


def replay_playbook(signals: list[dict]) -> dict:
    """Signals (oldest first) -> {version, entries, adjust}.

    kinds: stated | reaction | outcome | explain (nudge score/evidence), correction (note = verdict
    override), remove (hide the entry until a later signal), adjust (delta added to a knob),
    adjust_set (delta is the new absolute value).
    """
    entries: dict[str, dict] = {}
    adjust = {k: 0 for k in ADJUST_KEYS}
    version = 1
    for s in signals:
        if s.get("voided"):
            continue
        version += 1 if s.get("bumps", 1) else 0
        kind, key = s["kind"], f'{s["dimension"]}:{s["value"]}'
        if kind in ("adjust", "adjust_set"):
            cur = adjust.get(s["dimension"], 0)
            adjust[s["dimension"]] = int(clamp((cur if kind == "adjust" else 0) + s["delta"], -3, 3))
            continue
        if kind == "remove":
            entries.pop(key, None)
            continue
        e = entries.setdefault(key, {
            "id": key, "dimension": s["dimension"], "value": s["value"], "score": 0.5, "evidence": 0.0,
            "note": "", "override": None,
        })
        if kind == "correction":
            e["override"] = s["note"]
            continue
        e["score"] = clamp(e["score"] + s["delta"], 0.02, 0.98)
        e["evidence"] += s["evidence"]
        if s.get("note") and kind in ("stated", "reaction"):
            e["note"] = s["note"]
    out = []
    for e in entries.values():
        v = e["override"] or verdict(e["score"], e["evidence"])
        note = e["note"] + (" Corrected by you." if e["override"] else "")
        out.append({**{k: e[k] for k in ("id", "dimension", "value", "evidence")},
                    "score": round(e["score"], 3), "verdict": v, "note": note.strip()})
    return {"version": version, "entries": out, "adjust": adjust}


def angle_ranking(playbook: dict) -> list[str]:
    """Best angle first; avoided angles last; ties go to the less-tested angle (exploration)."""
    by = {e["value"]: e for e in playbook["entries"] if e["dimension"] == "angle"}

    def key(a: str):
        e = by.get(a)
        score = -1.0 if e and e["verdict"] == "avoid" else (e["score"] if e else 0.5)
        return (-score, e["evidence"] if e else 0.0, ANGLES.index(a))

    return sorted(ANGLES, key=key)


def style_key(adjust: dict) -> str:
    return "p{pace}d{depth}r{rigor}".format(**{k: adjust.get(k, 0) for k in ADJUST_KEYS})


def choose_angles(sections: list[dict], playbook: dict, pinned: dict[str, str]) -> dict[str, str]:
    ranking = angle_ranking(playbook)
    out = {}
    for sec in sections:
        avail = sec.get("angles") or list(ANGLES)
        pin = pinned.get(sec["id"])
        out[sec["id"]] = pin if pin in avail else next((a for a in ranking if a in avail), avail[0])
    return out


# ---------------------------------------------------------------- mastery

def bkt(p: float, correct: bool) -> float:
    if correct:
        post = p * (1 - SLIP) / (p * (1 - SLIP) + (1 - p) * GUESS)
    else:
        post = p * SLIP / (p * SLIP + (1 - p) * (1 - GUESS))
    return min(1.0, post + (1 - post) * TRANSIT)


@dataclass
class ConceptState:
    state: str
    mastery: float
    correct_items: int
    learned_at: str | None


def derive_concepts(concepts: list[dict], evidence: list[dict]) -> dict[str, ConceptState]:
    """Replay evidence (oldest first) into per-concept state.

    learned: P(learned) >= 0.95 and >= 3 distinct items answered correctly.
    mastered: a correct spaced review at least 20 h after learning. rusty: the latest review failed.
    locked/ready from prerequisites; learning once the learner has started or answered anything.
    """
    by_concept: dict[str, list[dict]] = {}
    for ev in evidence:
        if not ev.get("voided"):
            by_concept.setdefault(ev["concept_id"], []).append(ev)

    base: dict[str, ConceptState] = {}
    for c in concepts:
        p, items, learned_at, status = c["p_init"], set(), None, None
        for ev in by_concept.get(c["id"], []):
            ok = bool(ev["correct"])
            if ev["kind"] == "review":
                if learned_at and not ok:
                    status = "rusty"
                elif learned_at:
                    confirmed = status == "mastered" or _ts(ev["ts"]) - _ts(learned_at) >= CONFIRM_AFTER
                    status = "mastered" if confirmed else "learned"
                continue
            p = bkt(p, ok)
            if ok:
                items.add(ev["item_id"])
            if learned_at is None and p >= GATE_P and len(items) >= GATE_CORRECT:
                learned_at, status = ev["ts"], "learned"
            if status == "rusty" and ok:
                status = "learned"
        if status is None:
            status = "learning" if (c.get("started") or by_concept.get(c["id"])) else "pending"
        base[c["id"]] = ConceptState(status, round(p, 3), len(items), learned_at)

    done = {"learned", "mastered", "rusty"}
    for c in concepts:
        st = base[c["id"]]
        if st.state == "pending":
            st.state = "ready" if all(base.get(p, ConceptState("ready", 0, 0, None)).state in done
                                      for p in c["prereqs"]) else "locked"
    return base


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- spaced reviews

SCHEDULER = Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)


def first_review(learned_at: str) -> tuple[str, str]:
    """(card json, due iso): the first review is one day after learning (the confirmation)."""
    card = Card(due=_ts(learned_at) + timedelta(days=1))
    return _card_json(card), card.due.isoformat()


def review(card_json: str, correct: bool, at: str) -> tuple[str, str]:
    import json
    card = Card.from_dict(json.loads(card_json))
    card, _ = SCHEDULER.review_card(card, Rating.Good if correct else Rating.Again, _ts(at))
    return _card_json(card), card.due.isoformat()


def _card_json(card: Card) -> str:
    import json
    return json.dumps(card.to_dict())
