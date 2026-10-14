"""Demo seed: the AI-researcher roadmap from the prototype, so the app works before any research runs.

"Vectors" ships with pre-written prose for all three angles (served without an LLM).
"Linear combinations" ships with a card and lesson plan but no prose, so opening it exercises
real rendering through the configured provider.
"""

from __future__ import annotations

import json
from importlib import resources

from . import engine
from .db import DB, dumps, now

TABLES = ("goals", "tracks", "modules", "concepts", "cards", "prose", "renditions", "signals", "evidence",
          "feedback", "notes", "diffs", "chats", "reviews", "routes", "jobs", "meta")

# Routes added after the demo data was exported; ensure_routes() adds them to older workspaces too.
EXTRA_ROUTES = [
    {"role": "Placement", "description": "Placement quiz for a new goal", "provider": "claude", "model": "sonnet"},
    {"role": "Reflection", "description": "Weekly reflection over your feedback", "provider": "claude", "model": "opus"},
]

VECTORS_EXPLAIN = {"s-ops": {
    "id": "e-ops", "prompt": "In your own words: why can you add two vectors by adding their coordinates separately? Use a picture or an example.",
    "rubric": ["Moving along one axis doesn't change the other coordinate (the axes are independent)",
               "So the total displacement in each coordinate is the sum of the parts",
               "A tip-to-tail picture or a concrete numeric example"]}}

VECTORS_VIZ = {"s-ops": {"type": "vectors2d", "showSum": True,
                          "caption": "Drag the arrow tips. The dashed arrow is u + v, drawn tip to tail.",
                          "vectors": [{"x": 1, "y": 2, "label": "u"}, {"x": 3, "y": -1, "label": "v"}]}}

LINCOMB_SECTIONS = [
    {"id": "s-why", "heading": "Why weighted sums matter", "angles": ["geometric", "computational"],
     "purpose": "Every neuron output and every linear layer is a weighted sum of inputs; linear combinations are the only thing a vector space lets you build."},
    {"id": "s-idea", "heading": "What a linear combination is", "angles": ["geometric", "algebraic", "computational"],
     "purpose": "Definition w = sum c_i v_i with scalar coefficients; scale each vector, then add; worked 2D example."},
    {"id": "s-reach", "heading": "Reaching a target", "angles": ["geometric", "algebraic"],
     "purpose": "Find coefficients that produce a given vector from two others; picture it as stretching and chaining arrows; solve the small linear system.",
     "check": {"id": "q-reach", "prompt": "Which coefficients give $a(1, 0) + b(1, 1) = (3, 2)$?",
               "options": ["$a = 1, b = 2$", "$a = 3, b = 2$", "$a = 2, b = 1$", "$a = 1, b = 1$"], "answer": 0,
               "explanation": "The second component only comes from $b$, so $b = 2$. Then $a + b = 3$ gives $a = 1$."},
     "explain": {"id": "e-reach", "prompt": "Explain why two non-parallel vectors in the plane can reach every point, and why two parallel ones cannot.",
                 "rubric": ["Scaling a vector moves along its own direction (a line through the origin)",
                            "Two different directions give two independent knobs, so both coordinates can be matched (two equations, two unknowns)",
                            "Parallel vectors share one direction, so every combination stays on that single line"]},
     "viz": {"type": "lincomb2d", "u": [1, 0], "v": [1, 1], "target": [3, 2],
             "caption": "Move the sliders for a and b until a·u + b·v lands on the target."}},
    {"id": "s-neuron", "heading": "A neuron is a linear combination", "angles": ["computational", "algebraic"],
     "purpose": "A linear layer output y = w1 x1 + ... + wn xn; weights are coefficients; matrix rows are many combinations at once.",
     "check": {"id": "q-neuron", "prompt": "A unit computes $y = 2x_1 - x_2$. What is $y$ for $x = (3, 4)$?",
               "options": ["$10$", "$2$", "$-2$", "$5$"], "answer": 1,
               "explanation": "$2 \\cdot 3 - 4 = 2$."},
     "code": {"id": "x-neuron", "runtime": "local",
              "prompt": "With PyTorch: build a `torch.nn.Linear(3, 1, bias=False)` layer, set its weights to `[2, -1, 0.5]`, and return its output for the input `x`. Check that it equals the linear combination $2x_1 - x_2 + 0.5x_3$.",
              "starter": "import torch\n\ndef neuron(x):\n    layer = torch.nn.Linear(3, 1, bias=False)\n    with torch.no_grad():\n        ...  # set layer.weight\n    return layer(x)\n",
              "tests": "x = torch.tensor([3.0, 4.0, 2.0])\n"
                       "y = neuron(x)\n"
                       "assert y.shape == (1,), \"output should have shape (1,)\"\n"
                       "assert abs(y.item() - (2*3 - 4 + 0.5*2)) < 1e-6, f\"expected 3.0, got {y.item()}\"\n"
                       "print(\"All tests passed\")"}},
    {"id": "s-misc", "heading": "A common trap", "angles": ["geometric", "algebraic"],
     "purpose": "Coefficients can be negative or zero; the zero vector is always a combination; negative weights flip arrows.",
     "check": {"id": "q-zero", "prompt": "Is $(0, 0)$ a linear combination of $(1, 2)$ and $(3, 4)$?",
               "options": ["Yes: take both coefficients 0", "No: neither vector points at the origin",
                           "Only if the vectors are parallel", "Only in three dimensions"], "answer": 0,
               "explanation": "$0 \\cdot (1, 2) + 0 \\cdot (3, 4) = (0, 0)$. The zero vector is a combination of any set of vectors."}},
    {"id": "s-code", "heading": "Build it yourself", "angles": ["computational"],
     "purpose": "Implement a linear combination of Python lists.",
     "code": {"id": "x-lincomb",
              "prompt": "Implement `lin_comb(coeffs, vectors)` returning $\\sum_i c_i v_i$ for vectors given as equal-length Python lists.",
              "starter": "def lin_comb(coeffs, vectors):\n    # scale each vector by its coefficient, then add them componentwise\n    ...\n",
              "tests": "assert lin_comb([1, 2], [[1, 0], [1, 1]]) == [3, 2], \"1*(1,0) + 2*(1,1) should be [3, 2]\"\n"
                       "assert lin_comb([0, 0], [[1, 2], [3, 4]]) == [0, 0], \"all-zero coefficients give the zero vector\"\n"
                       "assert lin_comb([2, -1, 1], [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) == [2, -1, 1]\n"
                       "print(\"All tests passed\")"}},
]


def load_demo() -> dict:
    return json.loads(resources.files("dsc").joinpath("seed/demo.json").read_text(encoding="utf-8"))


def seed_demo(db: DB) -> None:
    d = load_demo()
    ts = now()
    with db.tx():
        for t in TABLES:
            db.conn.execute(f"DELETE FROM {t}")
        g = d["goal"]
        db.conn.execute("INSERT INTO goals(id, title, why, done, hours, profile, created_at) VALUES(?,?,?,?,?,?,?)",
                        (g["id"], g["title"], g["why"], g["doneLooksLike"], g["hoursPerWeek"],
                         "Software engineer who codes daily; likes pictures before formulas; examples from ML.", ts))
        db.conn.execute("INSERT INTO meta(key, value) VALUES('active_goal', ?)", (g["id"],))
        db.conn.execute("INSERT INTO meta(key, value) VALUES(?, '1')", (f"placement_done:{g['id']}",))  # see diffs
        for i, t in enumerate(d["tracks"]):
            db.conn.execute("INSERT INTO tracks VALUES(?,?,?,?,?)", (t["id"], g["id"], i, t["title"], t["summary"]))
        for i, m in enumerate(d["modules"]):
            db.conn.execute("INSERT INTO modules(id, track_id, ord, title, research, planned) VALUES(?,?,?,?,?,?)",
                            (m["id"], m["trackId"], i, m["title"], "ready" if m["research"] == "ready" else "outline",
                             m.get("plannedConcepts") or len(m["conceptIds"])))
        for i, c in enumerate(d["concepts"]):
            db.conn.execute("INSERT INTO concepts VALUES(?,?,?,?,?,?,?,?,?)",
                            (c["id"], c["moduleId"], i, c["title"], c["objective"], c["minutes"], dumps(c["prereqs"]),
                             c["mastery"], 1 if c["state"] == "learning" else 0))

        vec_sections = []
        for s in d["vectorSections"]:
            sec = {"id": s["id"], "heading": s["heading"], "purpose": s["heading"], "angles": list(s["variants"])}
            if s.get("check"):
                sec["check"] = s["check"]
            if s.get("code"):
                sec["code"] = s["code"]
            if s["id"] in VECTORS_EXPLAIN:
                sec["explain"] = VECTORS_EXPLAIN[s["id"]]
            if s["id"] in VECTORS_VIZ:
                sec["viz"] = VECTORS_VIZ[s["id"]]
            vec_sections.append(sec)
        for card in d["cards"]:
            body = {k: v for k, v in card.items() if k not in ("conceptId", "version", "factCheck", "checkedAt")}
            body["sections"] = vec_sections if card["conceptId"] == "c-vectors" else LINCOMB_SECTIONS
            db.conn.execute("INSERT INTO cards VALUES(?,?,?,?,?)",
                            (card["conceptId"], card["version"], dumps(body), card["factCheck"], card["checkedAt"]))

        # Playbook: the prototype's starting entries become stated signals, replayed like any others.
        pb = d["playbook"]
        for e in pb["entries"]:
            db.conn.execute("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,?,?,1)",
                            (ts, "stated", e["dimension"], e["value"], e["score"] - 0.5, e["evidence"], e["note"]))
        for k, v in pb["adjust"].items():
            if v:
                db.conn.execute("INSERT INTO signals(ts, kind, dimension, value, delta, evidence, note, bumps) VALUES(?,?,?,?,?,0,'',1)",
                                (ts, "adjust_set", k, k, v))
        style = engine.style_key(pb["adjust"])
        for s in d["vectorSections"]:
            for angle, body in s["variants"].items():
                db.conn.execute("INSERT INTO prose VALUES(?,?,?,?,?,?,?,?)", ("c-vectors", 2, s["id"], angle, style, body, "seed", ts))

        signals = [dict(r) for r in db.conn.execute("SELECT * FROM signals ORDER BY id").fetchall()]
        playbook = engine.replay_playbook(signals)
        angles = engine.choose_angles(vec_sections, playbook, {})
        db.conn.execute("INSERT INTO renditions VALUES(?,?,?,?,?,?,0)",
                        ("c-vectors", 2, playbook["version"], style, dumps(angles), "{}"))

        for diff in d["diffs"]:
            db.conn.execute("INSERT INTO diffs(ts, goal_id, reason, changes, status) VALUES(?,?,?,?,?)",
                            (diff["ts"], g["id"], diff["reason"], dumps(diff["changes"]), diff["status"]))
        for i, r in enumerate(d["routes"] + EXTRA_ROUTES):
            db.conn.execute("INSERT INTO routes VALUES(?,?,?,?,?)", (r["role"], i, r["description"], r["provider"], r["model"]))


def ensure_routes(db: DB) -> None:
    """Add job routes introduced by newer versions to an existing workspace."""
    n = db.one("SELECT COUNT(*) AS n FROM routes")["n"]
    for r in EXTRA_ROUTES:
        if not db.one("SELECT 1 FROM routes WHERE role=?", (r["role"],)):
            db.x("INSERT INTO routes VALUES(?,?,?,?,?)", (r["role"], n, r["description"], r["provider"], r["model"]))
            n += 1
