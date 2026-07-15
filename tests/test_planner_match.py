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
    _material_weights,
    _technique_for_concept,
    _material_profile,
)
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
