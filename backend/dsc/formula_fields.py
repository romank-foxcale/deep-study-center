"""The fields of mathematics a formula belongs to (SPEC §41), for the Formulas country of the map.

A model tags each formula once with 1 to 4 fields from a fixed list, most important first. The tags are kept per formula
form (``formulas.key``), so the same formula in two lessons has one set of fields. On the map, the Formulas country has
a province per field; a formula in 2 or 3 fields sits where those provinces meet, a formula in 4 or more is "Essential".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import DB, dumps, loads, now

# The fixed list, in ring order: neighbours on the ring are related fields, so their provinces touch on the map.
FIELDS: list[tuple[str, str]] = [
    ("algebra", "Algebra & functions"),
    ("probability", "Probability & statistics"),
    ("information", "Information theory"),
    ("ml", "Machine learning"),
    ("calculus", "Calculus & optimization"),
    ("linalg", "Linear algebra"),
    ("geometry", "Geometry & trigonometry"),
    ("physics", "Physics"),
    ("algorithms", "Algorithms & complexity"),
    ("discrete", "Discrete math & logic"),
]
IDS = [f for f, _ in FIELDS]
BATCH = 60

SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "required": ["n", "fields"], "properties": {
        "n": {"type": "integer"}, "fields": {"type": "array", "items": {"enum": IDS}, "maxItems": 4}}}}}}


def all_formulas(db: DB) -> dict[str, dict]:
    """Every formula on the map, by its key: formulas met in lessons (not derivation steps) and formula pages."""
    out: dict[str, dict] = {}
    for r in db.q("SELECT key, tex, body FROM formula_notes WHERE kind != 'step' ORDER BY created_at"):
        out.setdefault(r["key"], {"tex": r["tex"], "name": loads(r["body"], {}).get("name") or ""})
    for r in db.q("""SELECT f.key, f.tex, l.name FROM formula_forms f JOIN formula_lessons l ON l.id = f.formula_id
                     ORDER BY f.added_at"""):
        out.setdefault(r["key"], {"tex": r["tex"], "name": r["name"]})
    return out


def tags(db: DB) -> dict[str, list[str]]:
    """formula key -> its fields, most important first."""
    return {r["key"]: [f for f in loads(r["fields"], []) if f in IDS] for r in db.q("SELECT key, fields FROM formula_fields")}


def untagged(db: DB) -> list[str]:
    have = {r["key"] for r in db.q("SELECT key FROM formula_fields")}
    return [k for k in all_formulas(db) if k not in have]


def ensure(db: DB, jobs) -> None:
    """Start the tagging job when some formula has no fields yet (not again within 10 minutes after a failure)."""
    if not untagged(db) or jobs.active("formula_fields"):
        return
    last = db.one("SELECT status, updated_at FROM jobs WHERE kind='formula_fields' ORDER BY id DESC LIMIT 1")
    if last and last["status"] == "failed":
        at = datetime.fromisoformat(last["updated_at"])
        if datetime.now(timezone.utc) - at < timedelta(minutes=10):
            return
    jobs.enqueue("formula_fields", "Sort formulas into fields", {})


def run(jobs, jid: int, d: dict) -> dict:
    from .jobs import prompt
    from .providers import Call
    db = jobs.db
    every = all_formulas(db)
    saved = 0
    for _ in range(20):  # batches until every formula has its fields
        todo = untagged(db)[:BATCH]
        if not todo:
            break
        jobs.progress(jid, f"sorting {len(todo)} formula(s) into fields")
        out = jobs.call(jid, "Formula notes", Call(
            prompt=prompt("formula_fields", fields="\n".join(f"- {i}: {t}" for i, t in FIELDS),
                          formulas="\n".join(f'{n + 1}. {every[k]["name"]}: ${every[k]["tex"]}$' for n, k in enumerate(todo))),
            schema=SCHEMA, model="sonnet", timeout=300))
        got: dict[int, list[str]] = {}
        for it in out.get("items") or []:
            n = it.get("n")
            if isinstance(n, int) and 1 <= n <= len(todo):
                got[n] = [f for f in dict.fromkeys(it.get("fields") or []) if f in IDS][:4]
        ts = now()
        with db.tx():
            for n, k in enumerate(todo, 1):  # a formula the model left out is kept with no fields ("Not sorted")
                db.conn.execute("INSERT OR REPLACE INTO formula_fields(key, fields, at) VALUES(?,?,?)", (k, dumps(got.get(n, [])), ts))
                saved += 1
    return {"formulas": saved}


def fields_of(db: DB, key: str) -> list[str]:
    row = db.one("SELECT fields FROM formula_fields WHERE key=?", (key,))
    return [f for f in loads(row["fields"], []) if f in IDS] if row else []
