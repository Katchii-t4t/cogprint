"""
Unit tests for material-aware technique matching in the study planner.

These exercise the pure matching helpers directly (no DB / API needed):
    score(technique) = material_fit(technique) × learner_effectiveness(technique)

Two behaviours matter:
  1. Cold start (no measured effectiveness) → the MATERIAL decides. The text's
     best-fit technique wins, NOT the learner's global-best (the old bug, where
     any global-best that merely appeared in the candidate list auto-won and
     flattened every recommendation toward one technique).
  2. A large enough measured personal advantage can override a weaker material
     fit — but only as a modulation, never a hard gate.
"""

from agents.study_planner import (
    _ROTATION_BAND,
    _delayed_retention,
    _priority,
    _material_weights,
    _technique_effectiveness_map,
    _technique_for_concept,
    _material_profile,
)
from schemas.fingerprint import FingerprintProfile, TechniqueStats
from schemas.session import KnowledgeConcept, KnowledgeMap


# ── material weights ──────────────────────────────────────────────────────────

def test_material_weights_rank_descending():
    w = _material_weights("advanced", "conceptual")
    # elaborative_interrogation is the best fit for advanced-conceptual text.
    assert w["elaborative_interrogation"] == 1.0
    assert w["active_recall"] < w["elaborative_interrogation"]
    assert w["interleaving"] < w["active_recall"]


def test_material_weights_unknown_context_has_default():
    w = _material_weights("nonsense", "nonsense")
    assert w  # non-empty sensible default, no crash
    assert max(w.values()) == 1.0


# ── cold-start: material decides ──────────────────────────────────────────────

def test_cold_start_material_drives_pick():
    # No measured data at all → every effectiveness defaults to 0.70 internally.
    tech = _technique_for_concept("foundational", "factual", best_overall="active_recall", eff_map={})
    assert tech == "spaced_repetition"  # the material's best fit for factual/foundational


def test_cold_start_global_best_does_not_auto_win():
    # The OLD logic returned best_overall whenever it appeared in the candidate
    # list, flattening everything. active_recall IS a candidate for advanced-
    # conceptual, but elaborative_interrogation fits the material better, so at
    # cold start the material must win.
    tech = _technique_for_concept("advanced", "conceptual", best_overall="active_recall", eff_map={})
    assert tech == "elaborative_interrogation"


# ── measured advantage modulates ──────────────────────────────────────────────

def test_strong_personal_advantage_overrides_weaker_material_fit():
    # active_recall is the 2nd-best material fit here (weight 0.72), but if the
    # learner measurably crushes it (0.99) vs a flat prior on the top fit, the
    # personal signal should tip the pick to active_recall.
    eff = {"active_recall": 0.99, "elaborative_interrogation": 0.70}
    tech = _technique_for_concept("advanced", "conceptual", best_overall="active_recall", eff_map=eff)
    assert tech == "active_recall"


def test_material_still_wins_when_personal_edge_is_small():
    # A tiny personal edge on a poorly-fitting technique must NOT override a
    # strong material fit — material is a modulation, the guardrail holds.
    eff = {"mind_maps": 0.75, "spaced_repetition": 0.70}
    tech = _technique_for_concept("foundational", "factual", best_overall="mind_maps", eff_map=eff)
    assert tech == "spaced_repetition"


# ── no technique may be structurally unreachable ──────────────────────────────

def _stats(technique, **kw):
    base = dict(
        technique=technique, sessions_observed=6, avg_immediate_score=None,
        avg_retention_24h=None, avg_retention_7d=None, relative_effectiveness=None,
    )
    base.update(kw)
    return TechniqueStats(**base)


def test_a_technique_in_no_context_list_can_still_be_scheduled():
    """re_reading appears in none of the context candidate lists, so it only
    ever gets the material floor. It must still be reachable for a learner
    whose own delayed retention says it works.

    This was the concrete failure: a learner measured at 0.90 retention on
    re-reading was told by the fingerprint screen that re-reading was their
    best technique, while the plan scheduled it zero times out of fourteen and
    filled the days with a technique they had never tried. Two surfaces, two
    answers, and the one the user follows was the wrong one.
    """
    eff = {"re_reading": 0.90, "spaced_repetition": 0.43, "practice_testing": 0.42}
    tech = _technique_for_concept(
        "foundational", "factual", best_overall="re_reading", eff_map=eff
    )
    assert tech == "re_reading"


def test_an_unmeasured_prior_does_not_beat_a_measured_result():
    """A population average and this learner's own measurement are different
    kinds of claim. Practice testing carries the highest prior of all, but a
    technique the learner has actually been measured on should not lose to a
    technique they have never tried on the strength of the literature alone."""
    eff = {"spaced_repetition": 0.70}
    tech = _technique_for_concept(
        "foundational", "factual", best_overall="spaced_repetition", eff_map=eff
    )
    assert tech == "spaced_repetition"


# ── variety, but only where the model is indifferent ──────────────────────────

def test_plan_rotates_across_days_when_techniques_score_alike():
    """Fourteen identical days is bad practice and bad product."""
    picks = {
        _technique_for_concept("foundational", "factual", "spaced_repetition", {}, day)
        for day in range(14)
    }
    assert len(picks) > 1


def test_rotation_never_reaches_below_the_band():
    """Variety is bought only where it costs nothing. A technique the model
    rates clearly worse must never be scheduled just to look varied."""
    eff = {"spaced_repetition": 0.90, "mind_maps": 0.20, "re_reading": 0.15}
    picks = {
        _technique_for_concept("foundational", "factual", "spaced_repetition", eff, day)
        for day in range(30)
    }
    assert "mind_maps" not in picks
    assert "re_reading" not in picks


def test_rotation_is_deterministic_for_a_given_day():
    """Same fingerprint, same day, same plan — reloading must not reshuffle."""
    args = ("intermediate", "conceptual", "active_recall", {"active_recall": 0.8})
    assert all(
        _technique_for_concept(*args, day) == _technique_for_concept(*args, day)
        for day in range(10)
    )


def test_rotation_band_is_a_fraction_not_a_free_for_all():
    assert 0.5 < _ROTATION_BAND < 1.0


# ── only delayed retention counts as evidence ─────────────────────────────────

def test_immediate_score_is_not_treated_as_retention():
    """Immediate quiz score measures encoding, not forgetting — and it is
    exactly where the fluency illusion lives. Re-reading feels, and immediately
    tests, better than it retains. Letting it stand in for retention would
    favour precisely the techniques the literature warns about, using the
    number most biased in their favour."""
    assert _delayed_retention(_stats("re_reading", avg_immediate_score=0.99)) is None

    fp = FingerprintProfile(
        session_count=8,
        technique_effectiveness=[_stats("re_reading", avg_immediate_score=0.99)],
    )
    # Falls back to the research prior for re_reading (0.50), not to 0.99.
    assert _technique_effectiveness_map(fp)["re_reading"] == 0.50


def test_a_measured_zero_is_data_not_a_missing_value():
    """`a or b or c` treats a genuine 0.0 as absent and silently falls through
    to a weaker source. Total failure to retain is a real, informative result."""
    assert _delayed_retention(_stats("re_reading", avg_retention_7d=0.0)) == 0.0
    assert _delayed_retention(
        _stats("re_reading", avg_retention_7d=0.0, avg_retention_24h=0.8)
    ) == 0.0


def test_delayed_retention_prefers_the_longer_delay():
    stats = _stats("active_recall", avg_retention_7d=0.6, avg_retention_24h=0.85)
    assert _delayed_retention(stats) == 0.6


# ── review urgency must use the learner's own curve ───────────────────────────

def test_review_priority_uses_the_measured_stability():
    """`stabilities` is keyed by technique, and _priority looked it up by
    concept name — a key that is never in it. Every review's urgency therefore
    fell back to the 10-day default, so a learner with a measured 40-day curve
    was scheduled identically to one with a 4-day curve. The rationale text
    printed beside it used the correct value, so the plan explained itself with
    one number and ordered itself by another."""
    common = dict(
        concept="Glucose", current_day=10, last_studied={"Glucose": 3},
        eff_map={"active_recall": 0.8}, technique="active_recall", is_new=False,
    )
    fragile = _priority(stabilities={"active_recall": 2.0}, **common)
    durable = _priority(stabilities={"active_recall": 60.0}, **common)

    # Seven days after study: the fragile memory is nearly gone and urgently
    # needs review; the durable one is barely faded.
    assert fragile > durable
    assert fragile > 0.7
    assert durable < 0.2


def test_new_concepts_outrank_every_review():
    """First exposure has to happen before anything can be reviewed."""
    review = _priority(
        concept="Glucose", current_day=30, last_studied={"Glucose": 0},
        stabilities={"active_recall": 1.0}, eff_map={"active_recall": 1.0},
        technique="active_recall", is_new=False,
    )
    new = _priority(
        concept="Rubisco", current_day=1, last_studied={}, stabilities={},
        eff_map={}, technique="active_recall", is_new=True,
    )
    assert new >= review


# ── material profile aggregation ──────────────────────────────────────────────

def _concept(name, difficulty, ctype):
    return KnowledgeConcept(concept=name, difficulty=difficulty, concept_type=ctype)


def test_material_profile_dominant_type_and_difficulty():
    km = KnowledgeMap(
        title="Sample",
        total_concepts=4,
        concepts=[
            _concept("a", "advanced", "conceptual"),
            _concept("b", "advanced", "conceptual"),
            _concept("c", "advanced", "conceptual"),
            _concept("d", "foundational", "factual"),
        ],
        suggested_study_order=["a", "b", "c", "d"],
    )
    prof = _material_profile(km)
    assert prof.dominant_type == "conceptual"
    assert prof.dominant_difficulty == "advanced"
    # mixes are normalised proportions summing to ~1
    assert abs(sum(prof.type_mix.values()) - 1.0) < 0.02
    assert abs(sum(prof.difficulty_mix.values()) - 1.0) < 0.02
    assert prof.type_mix["conceptual"] == 0.75
    # summary names the material-favoured technique for advanced-conceptual text
    assert "elaborative interrogation" in prof.summary


def test_material_profile_empty_is_safe():
    km = KnowledgeMap(title="Empty", total_concepts=0, concepts=[], suggested_study_order=[])
    prof = _material_profile(km)
    assert prof.dominant_type and prof.dominant_difficulty  # sensible defaults, no crash
