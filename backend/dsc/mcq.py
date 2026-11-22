"""Multiple-choice helpers shared by every place that asks a generated question (SPEC §26).

- ``shuffle``: a model tends to put the right option in the same place, so a learner could find it by position.
  Every generated question is shuffled once, when it is stored, and its ``answer`` index is remapped.
- ``chance`` and the guess rule in ``progress.guessed``: confidence means "how likely is my pick right". With n
  options, 1/n is a blind guess, so the guess line depends on the number of options.
"""

from __future__ import annotations

import random

# The learner's confidence is a probability that the pick is right. A right answer at or below this, or at or below
# chance, counts as a guess (half evidence).
DOUBT = 0.30

# Tests turn this off to keep the model's option order (most fixtures put the right option first).
SHUFFLE = True


def chance(n_options: int) -> float:
    return 1.0 / n_options if n_options >= 2 else 1.0


def guess_line(n_options: int) -> float:
    return max(chance(n_options), DOUBT)


def shuffle(q: dict, rng: random.Random | None = None) -> dict:
    """A copy of the question with its options in a random order and ``answer`` pointing to the same option.
    A question with an invalid answer index is returned unchanged (the callers reject it)."""
    opts = list(q.get("options") or [])
    ans = q.get("answer")
    if not SHUFFLE or not isinstance(ans, int) or not 0 <= ans < len(opts) or len(opts) < 2:
        return dict(q)
    order = list(range(len(opts)))
    (rng or random).shuffle(order)
    return {**q, "options": [opts[i] for i in order], "answer": order.index(ans)}


# The question schema for every generated multiple-choice question. ``explanation`` comes before ``answer`` on
# purpose: the model reasons out why the right option is right first, then commits to it.
SCHEMA = {"type": "object", "required": ["prompt", "options", "explanation", "answer"], "properties": {
    "prompt": {"type": "string"},
    "options": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
    "explanation": {"type": "string"},
    "answer": {"type": "integer"}}}
