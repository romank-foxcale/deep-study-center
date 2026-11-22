"""A mock workspace for checking the UI without studying first (SPEC §29): `dsc mock [folder]`.

It starts from the demo goal (``seed_demo``: the AI-researcher roadmap, the "Vectors" lesson with formulas, a draggable
vector graph, a check and an explain-back) and adds:

- a second complete lesson, "Dot product & similarity", with two interactive formula widgets and a check;
- four mapped books (sample chapters and ideas, no PDF files) with their own idea graphs, ideas shared between books,
  and prerequisite links inside and across books and to the goal;
- every idea state, made from real evidence rows the normal way: know strongly (a passed review), learned, learning,
  due for review (a failed review), ready and locked;
- three study sessions of book parts: one done (explanations with formulas and idea links), one in the middle of
  teaching, one in the probe;
- review schedules, so "practise what is due" has ideas.

It never touches the real workspace: the folder must be new or already a mock (it has the file ``MOCK``).
"""

from __future__ import annotations

import json
import random
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import bookstudy, engine, graph, viz
from .db import DB, dumps, now
from .seed import seed_demo

BOOKS = [
    ("Inference Engineering", "Philip Kiely", 0.38, 0.04, [
        ("Inference", ["Inference engineering", "Closed vs open models", "Nines of availability", "Three layers of inference",
                       "Six performance techniques"]),
        ("Prerequisites", ["Online vs offline apps", "Model evaluation", "Distillation", "Fine-tuning for a domain",
                           "Latency percentiles", "Time to first token", "Tokens per second"]),
        ("Models", ["Linear layer as matmul", "Activation functions", "Tokens and vocabulary", "Chat template", "Prefill and decode",
                    "Logits and token selection", "Temperature, top-k, top-p", "Scaled dot-product attention",
                    "Multi-head attention", "KV cache", "Mixture of Experts", "Arithmetic intensity", "Memory-bound decode"]),
        ("Hardware", ["Streaming multiprocessors", "Tensor cores", "HBM bandwidth", "Hopper H100", "Blackwell B200", "NVLink",
                      "Multi-instance GPU", "Local inference"]),
        ("Software", ["CUDA kernels", "Kernel fusion", "FlashAttention", "PyTorch compile", "TensorRT-LLM", "vLLM", "SGLang"]),
        ("Techniques", ["Continuous batching", "PagedAttention", "Prefix caching", "Quantization", "FP8 inference",
                        "Speculative decoding", "EAGLE drafts", "Tensor parallelism", "Expert parallelism",
                        "Prefill/decode disaggregation"]),
        ("Modalities", ["Embedding models", "Speech recognition", "Speech synthesis", "Diffusion steps", "Video generation"]),
        ("Production", ["Autoscaling replicas", "Cold starts", "Load balancing", "Multi-cloud capacity", "Observability"])]),
    ("Understanding Deep Learning", "Simon J. D. Prince", 0.14, 0.0, [
        ("Supervised learning", ["Supervised learning", "Loss function", "Linear regression", "Least squares"]),
        ("Shallow networks", ["Shallow network", "ReLU", "Universal approximation", "Hidden units as regions"]),
        ("Deep networks", ["Composing networks", "Depth efficiency", "Matrix notation for layers"]),
        ("Loss functions", ["Maximum likelihood", "Softmax", "Cross-entropy", "Negative log-likelihood", "KL divergence"]),
        ("Fitting models", ["Gradient descent", "Stochastic gradient descent", "Momentum", "Adam", "Learning rate schedule",
                            "Loss landscape", "Saddle points"]),
        ("Gradients", ["Backpropagation", "Computational graph", "Jacobian", "Vanishing gradients", "He initialization"]),
        ("Performance", ["Test error", "Bias and variance", "Double descent", "Curse of dimensionality"]),
        ("Regularization", ["L2 regularization", "Weight decay", "Dropout", "Early stopping", "Data augmentation",
                            "Label smoothing", "Ensembling", "Transfer learning"]),
        ("Convolutional networks", ["Convolution", "Stride and padding", "Pooling", "Receptive field", "Channels"]),
        ("Residual networks", ["Residual connection", "Batch normalization", "Layer normalization", "U-Net"]),
        ("Transformers", ["Self-attention", "Positional encoding", "Encoder-decoder", "Tokenization (BPE)", "Vision transformer",
                          "Sparse attention", "Language model pretraining"]),
        ("Graph networks", ["Graphs as data", "Message passing", "Graph convolution"]),
        ("Generative models", ["GANs", "Generator and discriminator", "Normalizing flows", "Change of variables", "VAEs", "ELBO",
                               "Reparameterization trick", "Diffusion: forward noising", "Diffusion: reverse process",
                               "Score matching"]),
        ("Reinforcement learning", ["Markov decision process", "Return and value", "Q-learning", "Policy gradient",
                                    "Actor-critic", "RLHF"]),
        ("Why it works", ["Why deep nets generalize", "Lottery tickets", "Overparameterization"])]),
    ("AI Engineering", "Chip Huyen", 0.56, 0.12, [
        ("Foundation models", ["Foundation models", "Sampling", "Structured output", "Hallucination"]),
        ("Evaluation", ["Evaluation methodology", "AI as a judge", "Pairwise comparison", "Benchmark contamination"]),
        ("Prompt engineering", ["Few-shot prompts", "Chain of thought", "Prompt injection", "Long context"]),
        ("RAG and agents", ["Retrieval", "Chunking", "Hybrid search", "Reranking", "Agents", "Tool use", "Planning", "Agent memory"]),
        ("Finetuning", ["When to finetune", "LoRA", "Model merging"]),
        ("Dataset engineering", ["Data quality", "Synthetic data", "Deduplication"]),
        ("Inference optimization", ["Latency vs cost", "Batching for throughput"]),
        ("Architecture", ["Guardrails", "Model router", "User feedback loop"])]),
    ("Designing Data-Intensive Applications", "Martin Kleppmann", 0.5, 0.3, [
        ("Foundations", ["Reliability", "Scalability", "Maintainability", "Data models", "Document vs relational"]),
        ("Storage", ["LSM trees", "B-trees", "Column storage", "Encoding and schemas"]),
        ("Replication", ["Leader-follower", "Replication lag", "Multi-leader", "Leaderless quorums"]),
        ("Partitioning", ["Partitioning by key", "Rebalancing", "Secondary indexes"]),
        ("Transactions", ["ACID", "Isolation levels", "Snapshot isolation", "Serializability"]),
        ("Distributed systems", ["Unreliable networks", "Clocks", "Linearizability", "Consensus"]),
        ("Derived data", ["Batch processing", "Stream processing", "Change data capture", "Event sourcing"])]),
]
# The same idea in a second book (book index, title in the first book, other book index).
SHARED = [(0, "KV cache", 2), (0, "Quantization", 2), (0, "Speculative decoding", 2), (0, "Model evaluation", 2),
          (1, "Softmax", 0), (1, "Self-attention", 0), (1, "LoRA", 2), (0, "Load balancing", 3)]
# Prerequisites across books and from the demo goal (older idea -> newer idea; "c-..." are goal concepts).
CROSS = [("c-matmul", "Linear layer as matmul"), ("c-dot", "Scaled dot-product attention"), ("Softmax", "Logits and token selection"),
         ("Self-attention", "Scaled dot-product attention"), ("c-vectors", "Supervised learning"),
         ("KV cache", "Latency vs cost"), ("c-dot", "Retrieval"), ("Load balancing", "Partitioning by key"),
         ("Quantization", "Latency vs cost"), ("c-eigen", "Jacobian")]

STATEMENT = "{title}: an idea of “{chapter}” in {book}. (Mock data for checking the app.)"


class MockError(Exception):
    pass


def _ts(base: datetime, days: float) -> str:
    return (base + timedelta(days=days)).isoformat(timespec="seconds")


def build(folder: Path) -> Path:
    folder = Path(folder).expanduser()
    marker = folder / "MOCK"
    if folder.exists() and any(folder.iterdir()) and not marker.exists():
        raise MockError(f"{folder} is not empty and is not a mock workspace; choose a new folder")
    folder.mkdir(parents=True, exist_ok=True)
    marker.write_text("A mock Deep Study Center workspace made by `dsc mock`. Safe to delete.\n", encoding="utf-8")
    for f in ("study.db", "study.db-wal", "study.db-shm"):
        (folder / f).unlink(missing_ok=True)
    db = DB(folder / "study.db")
    seed_demo(db)
    graph.sync(db)
    rnd = random.Random(7)
    base = datetime.now(timezone.utc) - timedelta(days=40)
    _dot_lesson(db)
    titles = _books(db, rnd)
    _states(db, rnd, base, titles)
    _sessions(db, titles)
    db.set_meta("map_view", "nebula")
    return folder / "study.db"


# ---------------------------------------------------------------- a second full lesson

DOT_SECTIONS = [
    ("s-sum", "Sum of products", {
        "geometric": "Line the two vectors up and multiply matching parts, then add:\n\n$$a\\cdot b = a_1 b_1 + a_2 b_2 + \\dots + a_n b_n$$\n\n"
                     "For $a = (1, 2)$ and $b = (3, -1)$: $a\\cdot b = 1\\cdot 3 + 2\\cdot(-1) = 1$. One number comes out, not a vector.",
        "algebraic": "The dot product is $a\\cdot b = \\sum_{i=1}^{n} a_i b_i$. It is linear in each argument: "
                     "$(\\lambda a + c)\\cdot b = \\lambda\\,(a\\cdot b) + c\\cdot b$, and symmetric: $a\\cdot b = b\\cdot a$."}),
    ("s-formula", "Length times length times cosine", {
        "geometric": "The same number has a picture: $a\\cdot b = \\lVert a\\rVert\\,\\lVert b\\rVert\\cos\\theta$. "
                     "Move the sliders: the result is largest when the arrows point the same way, zero at a right angle, "
                     "and negative when they point apart.",
        "algebraic": "From the law of cosines, $\\lVert a-b\\rVert^2 = \\lVert a\\rVert^2 + \\lVert b\\rVert^2 - 2\\lVert a\\rVert\\lVert b\\rVert\\cos\\theta$, "
                     "and expanding the left side gives $a\\cdot b = \\lVert a\\rVert\\lVert b\\rVert\\cos\\theta$."}),
    ("s-cos", "Cosine similarity", {
        "geometric": "Divide out the lengths and only the direction is left:\n\n$$\\cos\\theta = \\frac{a\\cdot b}{\\lVert a\\rVert\\,\\lVert b\\rVert}$$\n\n"
                     "This is how search and RAG compare two embeddings: $1$ means the same direction, $0$ unrelated, $-1$ opposite.",
        "algebraic": "Cosine similarity is the dot product of the unit vectors: $\\hat a\\cdot\\hat b$ with $\\hat a = a / \\lVert a\\rVert$. "
                     "It ignores scale, so a long document and a short one about the same topic score high."}),
]


def _dot_lesson(db: DB) -> None:
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "formula_widgets_real.json"
    widgets = {}
    if fixture.exists():
        for w in json.loads(fixture.read_text(encoding="utf-8")):
            widgets[w["source"]] = viz.validate(w["widget"])
    style = db.one("SELECT style FROM renditions WHERE concept_id='c-vectors'")["style"]
    pb_version = db.one("SELECT playbook_version FROM renditions WHERE concept_id='c-vectors'")["playbook_version"]
    sections = []
    for sid, heading, variants in DOT_SECTIONS:
        sec = {"id": sid, "heading": heading, "purpose": heading, "angles": list(variants)}
        w = widgets.get("0-m0-la-dot-product/s-formula") if sid == "s-formula" else widgets.get("0-m0-la-cosine-similarity/s-definition") if sid == "s-cos" else None
        if w:
            sec["viz"] = w
        if sid == "s-cos":
            sec["check"] = {"id": "q-s-cos", "prompt": "Two embeddings point in exactly opposite directions. What is their cosine similarity?",
                            "options": ["$1$", "$0$", "$-1$", "It depends on their lengths"], "answer": 2,
                            "explanation": "Opposite directions give $\\theta = \\pi$, and $\\cos\\pi = -1$; lengths cancel out."}
        sections.append(sec)
    body = {"objective": "Compute a dot product and read it as alignment; use cosine similarity to compare embeddings.",
            "bloom": "apply", "core": "The dot product multiplies matching parts and adds them; it measures how much two vectors point the same way.",
            "formal": "$a\\cdot b = \\sum_i a_i b_i = \\lVert a\\rVert\\lVert b\\rVert\\cos\\theta$", "why": "Every neuron and every attention score is a dot product.",
            "angles": ["geometric", "algebraic"], "examples": [], "misconceptions": [], "sources": [], "sections": sections}
    ts = now()
    with db.tx():
        db.conn.execute("DELETE FROM cards WHERE concept_id='c-dot'")
        db.conn.execute("INSERT INTO cards(concept_id, version, body, fact_check, checked_at) VALUES(?,?,?,?,?)",
                        ("c-dot", 1, dumps(body), "passed", ts[:10]))
        for sid, _, variants in DOT_SECTIONS:
            for angle, text in variants.items():
                db.conn.execute("INSERT OR REPLACE INTO prose VALUES(?,?,?,?,?,?,?,?)", ("c-dot", 1, sid, angle, style, text, "mock", ts))
        db.conn.execute("INSERT OR REPLACE INTO renditions VALUES(?,?,?,?,?,?,0)",
                        ("c-dot", 1, pb_version, style, dumps({s[0]: "geometric" for s in DOT_SECTIONS}), "{}"))
        db.conn.execute("UPDATE concepts SET started=1 WHERE id='c-dot'")


# ---------------------------------------------------------------- books

def _books(db: DB, rnd: random.Random) -> dict[str, str]:
    """Insert the books as already mapped: sources (outline and page text), parts, ideas and links. Returns title -> node id."""
    by_title: dict[str, str] = {}
    ts = now()
    for bi, (title, author, *_rest, chapters) in enumerate(BOOKS):
        sid, bid = f"src-mock{bi}", f"b-mock{bi}"
        page, outline, pages_text = 1, [], []
        part_rows = []
        for ci, (ch, ideas) in enumerate(chapters):
            n_pages = max(4, len(ideas))
            outline.append({"title": ch, "page": page, "level": 0})
            part_rows.append((ci, ch, page, page + n_pages - 1, ideas))
            for k in range(n_pages):
                pages_text.append((page + k, f"{ch}. " + " ".join(ideas[k::n_pages])))
            page += n_pages
        with db.tx():
            db.conn.execute("""INSERT INTO sources(id, title, author, kind, filename, bytes, pages, status, outline, added_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""", (sid, title, author, "book", f"{title}.pdf", 0, page - 1, "ready", dumps(outline), ts))
            for p, text in pages_text:
                db.conn.execute("INSERT INTO source_pages(source_id, page, text) VALUES(?,?,?)", (sid, p, text))
                db.conn.execute("INSERT INTO source_fts(source_id, page, text) VALUES(?,?,?)", (sid, p, text))
            db.conn.execute("""INSERT INTO books(id, source_id, title, status, chapters_done, chapters, created_at, updated_at)
                               VALUES(?,?,?,?,?,?,?,?)""", (bid, sid, title, "ready", len(chapters), len(chapters), ts, ts))
            prev: list[str] = []
            for ord_, (ci, ch, p0, p1, ideas) in enumerate(part_rows):
                cur = db.conn.execute("""INSERT INTO book_parts(book_id, ord, chapter, chapter_title, title, page_from, page_to, summary)
                                         VALUES(?,?,?,?,?,?,?,?)""", (bid, ord_, ci + 1, ch, ch, p0, p1,
                                                                      f"What {title} says about {ch.lower()}. (Mock data.)"))
                part_id = cur.lastrowid
                for k, idea in enumerate(ideas):
                    nid = f"n-{secrets.token_hex(5)}"
                    db.conn.execute("INSERT INTO nodes(id, title, statement, kind, created_at, origin) VALUES(?,?,?,?,?,?)",
                                    (nid, idea, STATEMENT.format(title=idea, chapter=ch, book=title), "concept", ts, "book"))
                    db.conn.execute("INSERT INTO node_fts(node_id, text) VALUES(?,?)", (nid, idea))
                    db.conn.execute("""INSERT INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                                       VALUES(?,?,?,?,?,1,?)""", (bid, nid, part_id, f"c{ci + 1}-{k}", str(p0 + k % (p1 - p0 + 1)), k))
                    by_title[idea] = nid
                    pool = prev[-5:]  # local prerequisites: 1-2 of the ideas just before
                    for src in rnd.sample(pool, min(len(pool), 1 + (rnd.random() < 0.45))):
                        db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (src, nid, "", "book"))
                    prev.append(nid)
        bookstudy._split_big_parts(db, {"id": bid}, [dict(r) for r in db.q("SELECT * FROM book_parts WHERE book_id=?", (bid,))])
    with db.tx():
        for bi, idea, other in SHARED:  # the second book uses the first book's node
            nid = by_title[idea]
            part = db.conn.execute("SELECT id FROM book_parts WHERE book_id=? ORDER BY ord DESC LIMIT 1", (f"b-mock{other}",)).fetchone()[0]
            db.conn.execute("""INSERT OR IGNORE INTO book_nodes(book_id, node_id, part_id, key, pages, created, ord)
                               VALUES(?,?,?,?,?,0,99)""", (f"b-mock{other}", nid, part, f"shared-{idea}", ""))
        for a, b in CROSS:
            src = a if a.startswith("c-") else by_title.get(a)
            dst = by_title.get(b)
            if src and dst:
                db.conn.execute("INSERT OR IGNORE INTO links(src, dst, why, origin) VALUES(?,?,?,?)", (src, dst, "", "book"))
    return by_title


# ---------------------------------------------------------------- idea states from evidence

def _evidence(db: DB, nid: str, state: str, day: float, base: datetime) -> None:
    rows = []
    if state in ("learned", "mastered", "rusty"):
        for k in range(5):
            rows.append((_ts(base, day + k * 0.05), nid, f"mock-{nid}-{k}", "practice", 1, 1.0))
        if state == "mastered":
            rows.append((_ts(base, day + 2), nid, f"mock-{nid}-r", "review", 1, 1.0))
        if state == "rusty":
            rows.append((_ts(base, day + 3), nid, f"mock-{nid}-r", "review", 0, 0.0))
    elif state == "learning":
        rows += [(_ts(base, day), nid, f"mock-{nid}-0", "practice", 1, 1.0), (_ts(base, day + 0.1), nid, f"mock-{nid}-1", "practice", 0, 0.4)]
    for r in rows:
        db.x("INSERT INTO evidence(ts, concept_id, item_id, kind, correct, score) VALUES(?,?,?,?,?,?)", r)
    if state in ("learned", "mastered", "rusty"):
        due = base + timedelta(days=day + (36 if state == "mastered" else 41 if state == "learned" else 38))
        card = engine.new_card(_ts(base, day))
        db.x("INSERT OR REPLACE INTO node_reviews(node_id, card, due, last_at) VALUES(?,?,?,?)",
             (nid, card, due.isoformat(timespec="seconds"), _ts(base, day)))


def _states(db: DB, rnd: random.Random, base: datetime, by_title: dict[str, str]) -> None:
    goal_nodes = [r["id"] for r in db.q("SELECT id FROM nodes WHERE origin='concept' ORDER BY id")]
    for i, nid in enumerate(goal_nodes):  # the goal's basics: mostly known strongly
        _evidence(db, nid, "mastered" if i < 5 else "learned" if i < 7 else "learning" if i < 8 else "none", 1 + i, base)
    for bi, (_title, _a, progress, rusty, chapters) in enumerate(BOOKS):
        ideas = [t for _, list_ in chapters for t in list_]
        for k, t in enumerate(ideas):
            nid, f, r = by_title[t], k / max(1, len(ideas) - 1), rnd.random()
            if f < progress * 0.55:
                state = "rusty" if r < rusty else ("mastered" if r < 0.62 else "learned")
            elif f < progress:
                state = "rusty" if r < rusty else ("mastered" if r < 0.3 else "learned")
            elif f < progress + 0.09:
                state = "learning"
            else:
                state = "none"  # ready or locked, from the prerequisites
            _evidence(db, nid, state, 5 + bi * 2 + f * 20, base)


# ---------------------------------------------------------------- study sessions of book parts

def _sessions(db: DB, by_title: dict[str, str]) -> None:
    from . import session
    parts = {r["title"]: r for r in db.q("SELECT * FROM book_parts WHERE book_id='b-mock0'")}

    def start(title: str) -> str:
        p = parts[title]
        ideas = [{"key": f"i{n + 1}", "title": r["title"], "statement": r["statement"], "node": r["node_id"], "prereqs": [f"i{n}"] if n else [],
                  "fromGraph": False}
                 for n, r in enumerate(db.q("""SELECT bn.node_id, n.title, n.statement FROM book_nodes bn JOIN nodes n ON n.id = bn.node_id
                                               WHERE bn.part_id=? ORDER BY bn.ord""", (p["id"],)))]
        sid = session.start_from_ideas(db, _NoJobs(), f'{p["title"]} (Inference Engineering)', p["title"], ideas, ["src-mock0"],
                                       book_part=p["id"])
        db.x("UPDATE book_parts SET session_id=?, status='studying' WHERE id=?", (sid, p["id"]))
        return sid

    softmax, attn = by_title["Softmax"], by_title["Scaled dot-product attention"]
    mcq = lambda q, opts, ans, why: {"prompt": q, "options": opts, "explanation": why, "answer": ans}  # noqa: E731
    # 1. a finished session: predict -> explain (formulas, idea links) -> check, for three ideas
    sid = start("Models (1/2)")
    s = session.get(db, sid)
    plan = [i["key"] for i in s["ideas"]][:3]
    steps = [
        (mcq("A layer has weights $W \\in \\mathbb{R}^{4\\times 3}$. Its input $x$ has 3 numbers. How many numbers come out?",
             ["3", "4", "12", "7"], 1, "$Wx$ has one entry per row of $W$: 4 rows, so 4 outputs."),
         "A linear layer is one matrix product plus a bias:\n\n$$y = Wx + b$$\n\nEach output is a [dot product](#idea/c-dot) of one row "
         "of $W$ with $x$, so a layer with 4 rows gives 4 numbers. On a GPU, inference is mostly these products, which is why "
         "[matrix multiplication](#idea/c-matmul) speed sets the cost.",
         mcq("Which part of $y = Wx + b$ holds what the model learned?", ["$x$", "$W$ and $b$", "$y$", "Only $b$"], 1,
             "The weights and the bias are the parameters; $x$ is the input.")),
        (mcq("Logits $3, 1, -2$. What do you expect softmax to do with them?", ["Sort them", "Turn them into probabilities that sum to 1",
             "Make them all equal", "Keep only the largest"], 1, "Softmax makes positive weights that sum to 1 and keeps the order."),
         f"[Softmax](#idea/{softmax})" + " turns scores into probabilities:\n\n$$p_i = \\frac{e^{z_i}}{\\sum_j e^{z_j}}$$\n\n"
         "For $3, 1, -2$: $e^3 \\approx 20.1$, $e^1 \\approx 2.7$, $e^{-2} \\approx 0.14$; the total is about $22.9$, so "
         "$p \\approx (0.88, 0.12, 0.006)$.",
         mcq("Logits $-1$ and $-3$. After softmax?", ["Two negative numbers", "Two positive numbers that sum to 1",
             "$-1$ gets a smaller probability", "Both get 0.5"], 1, "$e^x$ is always positive, and the larger logit wins.")),
        (mcq("Attention compares a query with every key. Which operation measures how well they match?",
             ["A sum", "A dot product", "A maximum", "A sort"], 1, "A large dot product means the vectors point the same way."),
         f"[Scaled dot-product attention](#idea/{attn}) scores every key against the query, then mixes the values:\n\n"
         "$$\\mathrm{Attention}(Q,K,V) = \\mathrm{softmax}\\!\\left(\\frac{QK^\\top}{\\sqrt{d_k}}\\right)V$$\n\n"
         "Dividing by $\\sqrt{d_k}$ keeps the scores in a range where softmax is not almost one-hot.",
         mcq("Why divide by $\\sqrt{d_k}$?", ["To save memory", "To keep softmax from saturating", "To normalise V",
             "To make it causal"], 1, "Large dot products would make softmax almost one-hot and slow learning.")),
    ]
    ts = now()
    for n, (pred, body, check) in enumerate(steps):
        key = plan[n]
        db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, choice, answered, correct, thinking, confidence, created_at, answered_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (sid, key, "predict", 0, 0, dumps(pred), pred["answer"] if n != 1 else 0, 1,
                                                        int(n != 1), "I think it multiplies by each row" if n == 0 else "", 0.7, ts, ts))
        db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, answered, created_at)
                VALUES(?,?,?,?,?,?,1,?)""", (sid, key, "explain", 0, 1, dumps({"body": body, "kind": "explain"}), ts))
        db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, choice, answered, correct, thinking, confidence, created_at, answered_at)
                VALUES(?,?,?,?,?,?,?,1,1,?,?,?,?)""", (sid, key, "check", 0, 2, dumps(check), check["answer"], "", 0.9, ts, ts))
    db.x("UPDATE sessions SET status='done', plan=?, current=?, summary=? WHERE id=?",
         (dumps(plan), len(plan), "You can now read a linear layer as $y = Wx + b$, turn logits into probabilities with softmax, "
          "and explain why attention scales its scores by $\\sqrt{d_k}$.", sid))
    db.x("UPDATE book_parts SET status='done' WHERE session_id=?", (sid,))
    # 2. a session in the middle of teaching: the first idea done, an open prediction on the second
    sid2 = start("Models (2/2)")
    s2 = session.get(db, sid2)
    keys = [i["key"] for i in s2["ideas"]]
    db.x("UPDATE sessions SET status='teaching', plan=?, current=1 WHERE id=?", (dumps(keys), sid2))
    db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)""",
         (sid2, keys[1], "predict", 0, 0, dumps(mcq("During decode, the model makes one new token. What must it read from memory each time?",
                                                       ["Only the new token", "All weights and the KV cache", "Only the KV cache", "Nothing"], 1,
                                                       "Decode is memory-bound: every step streams the weights and the cache.")), ts))
    # 3. a session in the probe: one answered question, one open
    sid3 = start("Hardware")
    db.x("UPDATE sessions SET status='probing' WHERE id=?", (sid3,))
    k3 = session.get(db, sid3)["ideas"][0]["key"]
    db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, choice, answered, correct, thinking, confidence, created_at, answered_at)
            VALUES(?,?,?,?,?,?,?,1,1,?,?,?,?)""", (sid3, k3, "probe", 1, 0, dumps(mcq("What does an H100 have more of than a CPU?",
            ["Cores for parallel math", "Cache per core", "Clock speed", "Disk"], 0, "Thousands of simple cores for parallel math.")), 0,
            "lots of small cores", 0.9, ts, ts))
    db.x("""INSERT INTO session_items(session_id, idea_key, phase, round, ord, item, created_at) VALUES(?,?,?,?,?,?,?)""",
         (sid3, k3, "probe", 2, 0, dumps(mcq("HBM bandwidth is about 3 TB/s. Which step does it limit most?",
                                             ["Prefill", "Decode", "Tokenization", "Sampling"], 1, "Decode reads all weights per token.")), ts))
    db.set_meta("last_session", sid)
    db.set_meta("last_book", "b-mock0")


class _NoJobs:
    """Sessions in the mock are written directly; nothing is queued."""

    def enqueue(self, *a, **k) -> int:
        return 0

    def active(self, *a, **k) -> bool:
        return False
