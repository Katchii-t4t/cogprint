"""
Zero is a measurement, not a missing value.

`a or b` treats 0.0 as absent. That idiom appeared in four places in this
codebase, each on a quantity where zero is both legal and the most extreme
possible reading — total forgetting, a sleepless night — so the fallback
replaced the strongest signal in the data with something milder or invented.

Two were fixed earlier (the planner's effectiveness map, and `_priority`'s
stability lookup). These pin the rest, and pin the class, so the idiom cannot
quietly come back on a numeric field.
"""

import numpy as np

from agents.study_planner import _rationale
from personalization.fingerprint_builder import _rank_recommended_techniques
from personalization.linucb import build_context
from schemas.fingerprint import TechniqueStats


def _stats(technique, **kw):
    base = dict(
        technique=technique, sessions_observed=6, avg_immediate_score=None,
        avg_retention_24h=None, avg_retention_7d=None, relative_effectiveness=None,
    )
    base.update(kw)
    return TechniqueStats(**base)


def test_a_sleepless_night_is_not_rewritten_as_seven_hours():
    """0 hours is a legal input and a real thing that happens to students. It
    was being replaced with a healthy 7 before the model ever saw it — and
    sleep is one of the conditions the fingerprint reports back as advice, so
    the fabrication came out of the other end."""
    slept_none = build_context(0.0, 3, "morning", 30, 5)
    slept_seven = build_context(7.0, 3, "morning", 30, 5)
    assert slept_none[1] == 0.0
    assert not np.allclose(slept_none, slept_seven)


def test_missing_sleep_still_falls_back_to_the_baseline():
    """The fallback is for absent data, which is what it was always for."""
    assert build_context(None, 3, "morning", 30, 5)[1] == 0.7


def test_total_forgetting_is_not_reported_as_none_forgotten():
    """R=0.0 is the most urgent review there is. `R or 1.0` read it as "no
    estimate" and printed 0% forgetting beside it."""
    text = _rationale("Glucose", "active_recall", is_new=False, lag=30, S=2.0, R=0.0)
    assert "100% forgetting" in text


def test_a_missing_prediction_still_reads_as_nothing_forgotten():
    text = _rationale("Glucose", "active_recall", is_new=False, lag=1, S=20.0, R=None)
    assert "0% forgetting" in text


def test_a_forgotten_technique_is_not_ranked_by_its_immediate_score():
    """The chain `avg_retention_7d or avg_retention_24h or avg_immediate_score`
    fell through a measured 0.0 to the score the user got on the day. A
    technique they had completely forgotten a week later was therefore ranked
    by how well it felt at the time — the fluency illusion, promoted straight
    into the recommendation list.
    """
    forgotten = _stats("re_reading", avg_retention_7d=0.0, avg_immediate_score=0.99)
    durable = _stats("practice_testing", avg_retention_7d=0.80, avg_immediate_score=0.80)

    ranked = _rank_recommended_techniques(
        bandit_scores={}, tech_stats=[forgotten, durable], n=3
    )
    assert ranked.index("practice_testing") < ranked.index("re_reading")


def test_the_idiom_is_gone_from_the_numeric_paths():
    """A guard against reintroduction. `x or <number>` on a measured quantity
    is the bug; this catches it coming back into the files it was found in."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\bor\s+[0-9]+\.[0-9]+\b")
    offenders = []
    for name in (
        "personalization/linucb.py",
        "personalization/fingerprint_builder.py",
        "personalization/forgetting_curve.py",
        "agents/study_planner.py",
    ):
        for i, line in enumerate((root / name).read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue  # prose in a comment describing the bug is fine
            if pattern.search(line):
                offenders.append(f"{name}:{i}: {stripped}")
    assert not offenders, "falsy-zero fallback reintroduced:\n" + "\n".join(offenders)
