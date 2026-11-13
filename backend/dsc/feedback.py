"""Feedback items: kinds, the playbook signals each item adds, edit and delete (SPEC §11).

Kinds:
- ``lesson``: about this lesson only. Changes this lesson when applied; adds no playbook signals.
- ``me``: about how I learn. Also changes the playbook (signals), so other lessons adapt.
- ``fact``: claims the material is wrong. Never applied to prose; goes to the card check (refresh + fact-check).

An item owns the signals it added (``signal_ids``). Edit voids them and adds new ones; delete voids them.
The playbook is replayed from the signal log, so both take effect at once.
"""

from __future__ import annotations

import re

from . import engine, state
from .db import DB, dumps, loads, now

KINDS = ("lesson", "me", "fact")

TAG_LABELS = {
    "framing-off": "The framing didn't work for me",
    "confused": "I got lost / missing background",
    "too-abstract": "Too abstract",
    "too-fast": "Too fast",
    "too-slow": "Too slow",
    "too-long": "Too long",
    "more-rigor": "I want more rigor",
    "loved-it": "This worked really well",
}
TAG_IDS = {v: k for k, v in TAG_LABELS.items()}

# Tags that describe the learner rather than one lesson (they were always playbook signals).
ME_TAGS = {"framing-off", "too-abstract", "too-fast", "too-slow", "too-long", "more-rigor", "loved-it"}
FACT_RE = re.compile(r"\b(is wrong|are wrong|incorrect|not true|is false|wrong (formula|answer|sign|definition|key)|"
                     r"(error|mistake|typo) in|should be|is actually)\b", re.I)
ME_RE = re.compile(r"\b(i (always|usually|generally|prefer|like|learn|need|am|'m)|in general|all (the )?lessons|"
                   r"every lesson|my background|for me)\b", re.I)


def propose_kind(tags: list[str], text: str) -> str:
    """Rule-based first guess, shown at once; an agent job may refine it, and the learner can correct it."""
    if FACT_RE.search(text or ""):
        return "fact"
    if ME_RE.search(text or "") or any(t in ME_TAGS for t in tags):
        return "me"
    return "lesson"


def tag_ids(labels: list[str]) -> list[str]:
    return [TAG_IDS.get(t, t) for t in labels]


def _signal(db: DB, kind: str, dimension: str, value: str, delta: float = 0, evidence: float = 0,
            note: str = "", bumps: bool = True) -> int:
    return db.x("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,?,?,?)",
                (now(), kind, dimension, value, delta, evidence, note, 1 if bumps else 0))


def add_signals(db: DB, tags: list[str], text: str, angle: str | None, kind: str) -> tuple[list[int], list[str]]:
    """The playbook signals for one item (only for kind "me") and the effect lines the learner sees."""
    if kind != "me":
        return [], []
    pb0 = state.playbook(db)
    ids: list[int] = []
    effects: list[str] = []

    def nudge(value: str, delta: float, why: str) -> None:
        e = next((x for x in pb0["entries"] if x["dimension"] == "angle" and x["value"] == value), None) or {"score": 0.5}
        ids.append(_signal(db, "reaction", "angle", value, delta, 1.0, note=text or why))
        effects.append(f'Playbook: "{value}" {"less" if delta < 0 else "more"} trusted '
                       f'({e["score"]:.2f} → {engine.clamp(e["score"] + delta, 0.02, 0.98):.2f}) {why}')

    def knob(key: str, step: int, what: str) -> None:
        ids.append(_signal(db, "adjust", key, key, step))
        effects.append(f"{key.capitalize()} {'+' if step > 0 else ''}{step}: {what}")

    for t in tags:
        if t == "framing-off" and angle:
            nudge(angle, -0.14, "because the framing missed")
        elif t == "loved-it" and angle:
            nudge(angle, +0.10, "because it landed")
        elif t == "too-abstract":
            nudge("computational", +0.08, "(more concrete, code-first)")
        elif t == "too-fast":
            knob("pace", -1, "smaller steps, more worked examples")
        elif t == "too-slow":
            knob("pace", +1, "fewer worked examples, skip what you show you know")
        elif t == "too-long":
            knob("depth", -1, 'shorter lessons, details moved to "go deeper"')
        elif t == "more-rigor":
            knob("rigor", +1, "formal statements and proofs earlier")
    if text and not ids:
        # A comment about me with no tag: kept as a stated preference the reflection and every writer read.
        ids.append(_signal(db, "stated", "comment", text[:80], 0, 0.3, note=text, bumps=False))
        effects.append("Playbook: kept as something you said about how you learn")
    return ids, effects


def kind_effect(kind: str) -> str:
    return {"lesson": "About this lesson: select it and click Apply to rewrite this lesson (the playbook is not changed)",
            "me": "About you: the playbook changed; select it and click Apply to rewrite this lesson now",
            "fact": "A possible error in the material: Apply sends it to the card check, not into your lesson"}[kind]


def void_signals(db: DB, row: dict) -> None:
    ids = loads(row["signal_ids"], [])
    if not ids:
        return
    marks = ','.join('?' * len(ids))
    bumped = db.one(f"SELECT MAX(bumps) AS b FROM signals WHERE voided=0 AND id IN ({marks})", ids)["b"]
    db.x(f"UPDATE signals SET voided=1 WHERE id IN ({marks})", ids)
    if bumped:  # voiding a real change is itself a change: bump the version so renditions go stale
        _signal(db, "void", "feedback", str(row["id"]))


def resignal(db: DB, fid: int, *, tags: list[str] | None = None, text: str | None = None, kind: str | None = None,
             kind_source: str | None = None) -> None:
    """Edit an item: void its signals, store the new values, add new signals. The playbook replays from the log."""
    row = db.one("SELECT * FROM feedback WHERE id=?", (fid,))
    if not row or row["deleted"]:
        raise ValueError("no such feedback")
    labels = loads(row["tags"], []) if tags is None else [TAG_LABELS.get(t, t) for t in tags]
    text = row["text"] if text is None else text.strip()
    kind = kind or row["kind"]
    if kind not in KINDS:
        raise ValueError("kind must be lesson, me or fact")
    if not labels and not text:
        raise ValueError("feedback needs a tag or some text")
    pb0 = state.playbook(db)["version"]
    void_signals(db, row)
    ids, effects = add_signals(db, tag_ids(labels), text, row["angle"], kind)
    pb1 = state.playbook(db)["version"]
    effects.append(kind_effect(kind))
    if pb1 != pb0:
        effects.append(f"Playbook replayed (v{pb1})")
    # updated_at marks the learner's own edits ("changed since applied"); an agent's kind proposal is not one.
    edited = now() if kind_source != "agent" else row["updated_at"]
    db.x("UPDATE feedback SET tags=?, text=?, kind=?, kind_source=?, signal_ids=?, effects=?, updated_at=? WHERE id=?",
         (dumps(labels), text, kind, kind_source or row["kind_source"], dumps(ids), dumps(effects), edited, fid))


def delete(db: DB, fid: int) -> None:
    row = db.one("SELECT * FROM feedback WHERE id=?", (fid,))
    if not row or row["deleted"]:
        raise ValueError("no such feedback")
    void_signals(db, row)
    db.x("UPDATE feedback SET deleted=1, signal_ids='[]', updated_at=? WHERE id=?", (now(), fid))
