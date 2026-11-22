"""Shuffled options and the guess rule (SPEC §26)."""

import random

from dsc import mcq, progress


def test_shuffle_keeps_the_right_option_right(monkeypatch):
    monkeypatch.setattr(mcq, "SHUFFLE", True)
    q = {"prompt": "p", "options": ["a", "b", "c", "d"], "answer": 2, "explanation": "e"}
    seen = set()
    for seed in range(40):
        out = mcq.shuffle(q, random.Random(seed))
        assert out["options"][out["answer"]] == "c" and sorted(out["options"]) == ["a", "b", "c", "d"]
        seen.add(out["answer"])
    assert seen == {0, 1, 2, 3} and q["options"] == ["a", "b", "c", "d"]  # every position happens; input unchanged
    bad = {"prompt": "p", "options": ["a", "b"], "answer": 5, "explanation": "e"}
    assert mcq.shuffle(bad) == bad


def test_shuffle_can_be_turned_off_for_tests():
    q = {"prompt": "p", "options": ["a", "b", "c"], "answer": 0, "explanation": "e"}
    assert mcq.shuffle(q, random.Random(1)) == q  # conftest turns it off


def test_the_guess_line_follows_the_number_of_options():
    assert mcq.chance(4) == 0.25 and mcq.guess_line(4) == 0.30 and mcq.guess_line(2) == 0.5
    assert progress.guessed(True, 0.3, 4) and not progress.guessed(True, 0.5, 4)
    assert progress.guessed(True, 0.5, 2) and not progress.guessed(True, 0.7, 2)  # a coin flip on two options
    assert not progress.guessed(False, 0.0, 4) and not progress.guessed(True, None, 4)


def test_the_schema_asks_for_the_explanation_before_the_answer():
    keys = list(mcq.SCHEMA["properties"])
    assert keys.index("explanation") < keys.index("answer")
