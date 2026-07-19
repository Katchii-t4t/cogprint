"""
Cold-start seeding (§2.1): research-derived priors must be sane, correctly
ordered, and actually reach the Bayesian pipeline so a brand-new user gets a
differentiated, research-grounded fingerprint instead of one flat default.
"""

import math

from personalization.priors import (
    RESEARCH_PRIORS,
    prior_effectiveness,
    prior_stability_days,
)
from personalization.hierarchical_memory import HierarchicalMemoryModel


ALL_TECHNIQUES = [
    "practice_testing", "spaced_repetition", "active_recall",
    "elaborative_interrogation", "interleaving", "mind_maps", "re_reading",
]


# ── the priors themselves ─────────────────────────────────────────────────────

def test_all_seven_techniques_have_priors():
    assert set(RESEARCH_PRIORS) == set(ALL_TECHNIQUES)


def test_priors_are_valid_probabilities_with_breadth():
    for name, p in RESEARCH_PRIORS.items():
        assert 0.0 < p.retention_7d < 1.0, name
        assert p.sigma >= 0.10, f"{name}: prior should stay honestly broad"
        assert p.source, name


def test_prior_ordering_matches_dunlosky_ranking():
    # The literature's reliable claim is the *ordering*, so that is what we pin.
    values = [prior_effectiveness(t) for t in ALL_TECHNIQUES]
    assert values == sorted(values, reverse=True)
    assert prior_effectiveness("practice_testing") > prior_effectiveness("re_reading")


def test_stability_days_consistent_with_retention():
    # S = -7/ln(R7): higher retention ⇒ longer stability, and the round-trip holds.
    for t in ALL_TECHNIQUES:
        S = prior_stability_days(t)
        r7 = math.exp(-7.0 / S)
        assert abs(r7 - prior_effectiveness(t)) < 1e-9, t
    assert prior_stability_days("practice_testing") > prior_stability_days("re_reading")


def test_unknown_technique_falls_back_to_neutral_defaults():
    assert prior_effectiveness("nonsense") == 0.70
    assert prior_stability_days("nonsense") == 14.0


# ── reaching the Bayesian pipeline ────────────────────────────────────────────

def test_population_fitted_flag():
    m = HierarchicalMemoryModel()
    assert m.population_fitted is False
    m.fit_population([5.0, 10.0, 20.0])          # < 4 estimates → keeps defaults
    assert m.population_fitted is False
    m.fit_population([5.0, 10.0, 20.0, 40.0])    # real cohort → fitted
    assert m.population_fitted is True


def test_prior_only_posteriors_are_differentiated_by_technique():
    """A user with ZERO retention data must still get different stability
    posteriors per technique (research prior), not one global default."""
    def prior_only_median(technique: str) -> float:
        m = HierarchicalMemoryModel()
        m.pop.log_mean = math.log(prior_stability_days(technique))
        return m.fit_user([]).median  # no data → sample from the prior

    pt = prior_only_median("practice_testing")   # prior S ≈ 43d
    rr = prior_only_median("re_reading")         # prior S ≈ 10d
    # Huge prior gap ⇒ robust to MCMC sampling noise.
    assert pt > rr * 1.5, (pt, rr)


def test_prior_only_summary_is_flagged_as_not_population_informed():
    m = HierarchicalMemoryModel()
    s = m.fit_user([])
    assert s.population_informed is False  # honesty flag survives (§2.1 UX)
