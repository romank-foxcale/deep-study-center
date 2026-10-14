from datetime import datetime, timedelta, timezone

from dsc import engine


def sig(kind, dim, value, delta=0.0, ev=0.0, note="", bumps=1):
    return {"kind": kind, "dimension": dim, "value": value, "delta": delta, "evidence": ev, "note": note, "bumps": bumps}


def test_bkt_three_correct_from_seed_prior_passes_gate():
    p = 0.42
    for _ in range(3):
        p = engine.bkt(p, True)
    assert p >= engine.GATE_P


def test_playbook_verdicts_need_evidence():
    pb = engine.replay_playbook([sig("stated", "angle", "geometric", 0.3, 1.0)])
    assert pb["entries"][0]["verdict"] == "trying"  # strong but not enough evidence
    pb = engine.replay_playbook([sig("stated", "angle", "geometric", 0.3, 2.0)])
    assert pb["entries"][0]["verdict"] == "works"
    pb = engine.replay_playbook([sig("stated", "angle", "algebraic", -0.25, 2.0)])
    assert pb["entries"][0]["verdict"] == "avoid"


def test_playbook_correction_remove_adjust_and_version():
    signals = [
        sig("stated", "angle", "geometric", 0.3, 2.0),
        sig("outcome", "angle", "geometric", -0.03, 0.3, bumps=0),
        sig("correction", "angle", "geometric", note="avoid"),
        sig("stated", "format", "code", 0.1, 1.0),
        sig("remove", "format", "code"),
        sig("adjust", "pace", "pace", 5),
    ]
    pb = engine.replay_playbook(signals)
    assert pb["version"] == 1 + 5  # the outcome signal doesn't bump
    assert [e["value"] for e in pb["entries"]] == ["geometric"]
    assert pb["entries"][0]["verdict"] == "avoid" and "Corrected by you" in pb["entries"][0]["note"]
    assert pb["adjust"]["pace"] == 3  # clamped
    assert engine.replay_playbook(signals + [sig("adjust_set", "pace", "pace", -1)])["adjust"]["pace"] == -1


def test_ranking_avoid_last_and_ties_explore():
    pb = engine.replay_playbook([sig("stated", "angle", "geometric", 0.1, 3.0), sig("stated", "angle", "computational", 0.1, 1.0)])
    assert engine.angle_ranking(pb)[0] == "computational"  # tie on score -> less tested first
    pb = engine.replay_playbook([sig("stated", "angle", "geometric", -0.4, 3.0)])
    assert engine.angle_ranking(pb)[-1] == "geometric"


def test_choose_angles_respects_pins_and_availability():
    pb = engine.replay_playbook([sig("stated", "angle", "geometric", 0.3, 2.0)])
    sections = [{"id": "a", "angles": ["geometric", "algebraic"]}, {"id": "b", "angles": ["computational"]}]
    assert engine.choose_angles(sections, pb, {"a": "algebraic"}) == {"a": "algebraic", "b": "computational"}


def _ev(cid, item, ok, ts, kind="practice"):
    return {"concept_id": cid, "item_id": item, "correct": int(ok), "ts": ts.isoformat(), "kind": kind}


def test_mastery_states_from_evidence():
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    concepts = [{"id": "a", "p_init": 0.42, "prereqs": [], "started": 0},
                {"id": "b", "p_init": 0.1, "prereqs": ["a"], "started": 0}]
    st = engine.derive_concepts(concepts, [])
    assert (st["a"].state, st["b"].state) == ("ready", "locked")

    ev = [_ev("a", f"q{i}", True, t0 + timedelta(minutes=i)) for i in range(3)]
    st = engine.derive_concepts(concepts, ev)
    assert st["a"].state == "learned" and st["b"].state == "ready"

    same_item = [_ev("a", "q0", True, t0 + timedelta(minutes=i)) for i in range(5)]
    assert engine.derive_concepts(concepts, same_item)["a"].state == "learning"  # needs 3 distinct items

    early = ev + [_ev("a", "q0", True, t0 + timedelta(hours=2), "review")]
    assert engine.derive_concepts(concepts, early)["a"].state == "learned"  # too soon to confirm
    later = ev + [_ev("a", "q0", True, t0 + timedelta(hours=30), "review")]
    assert engine.derive_concepts(concepts, later)["a"].state == "mastered"
    failed = later + [_ev("a", "q1", False, t0 + timedelta(days=9), "review")]
    assert engine.derive_concepts(concepts, failed)["a"].state == "rusty"
    fixed = failed + [_ev("a", "q2", True, t0 + timedelta(days=9, hours=1))]
    assert engine.derive_concepts(concepts, fixed)["a"].state == "learned"


def test_fsrs_first_review_is_a_day_later_and_pass_extends():
    learned = "2026-10-01T10:00:00+00:00"
    card, due = engine.first_review(learned)
    assert due.startswith("2026-10-02T10:00")
    card2, due2 = engine.review(card, True, "2026-10-02T11:00:00+00:00")
    assert due2 > "2026-10-04"
    _, due3 = engine.review(card2, False, "2026-10-10T11:00:00+00:00")
    assert due3 < due2 or due3 < "2026-10-12"
