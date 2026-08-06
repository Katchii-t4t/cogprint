"""
Tests for the Monte Carlo studies.

Same principle as test_predictive_baseline.py: a simulation that cannot be
trusted produces confident numbers about nothing. These check that the
simulated world behaves as claimed and that the policies being compared are
actually different things.
"""

import math

import pytest

from evaluation.monte_carlo import (
    TECHNIQUES,
    _power_law_b,
    make_learner,
    run_loop,
    study_closed_loop,
    study_misspecified,
)
import numpy as np


def test_every_technique_the_planner_can_return_is_simulated():
    """The planner may return any technique in a context's candidate list. A
    simulated world missing one crashes on first recommendation — and would
    quietly exclude re_reading and mind_maps, whose reachability is the whole
    question."""
    from personalization.priors import RESEARCH_PRIORS

    assert set(TECHNIQUES) == set(RESEARCH_PRIORS)


def test_power_law_matches_the_exponential_at_seven_days():
    """The two worlds have to agree where the product reports, or any
    difference found later is just a different target, not misspecification."""
    for target in (0.3, 0.5, 0.85):
        b = _power_law_b(target)
        assert (1.0 + 7.0) ** (-b) == pytest.approx(target, abs=1e-9)


def test_a_learner_has_one_genuinely_best_technique():
    rng = np.random.default_rng(0)
    learner = make_learner(rng, tau=0.5)
    assert learner.best in TECHNIQUES
    assert learner.true_S[learner.best] == max(learner.true_S.values())


def test_zero_spread_makes_the_research_ranking_correct():
    """At tau=0 every learner's stabilities are the priors times one common
    multiplier, so the literature's top technique really is everyone's best.
    That is what makes DUNLOSKY a fair ceiling in that column."""
    rng = np.random.default_rng(3)
    for _ in range(20):
        assert make_learner(rng, tau=0.0).best == "practice_testing"


def test_oracle_is_an_upper_bound_on_achieved_retention():
    """If any policy beats the oracle, the scoring is wrong."""
    results = study_closed_loop(n_learners=12, n_sessions=20, tau=0.5, seed=4)
    ceiling = results["ORACLE"]["retention"]
    for policy, r in results.items():
        assert r["retention"] <= ceiling + 1e-9, policy


def test_exploration_actually_explores():
    """EXPLORER must sample more techniques than PLANNER, or the comparison
    prices nothing and a null result would be meaningless."""
    results = study_closed_loop(n_learners=12, n_sessions=40, tau=0.4, seed=5)
    assert results["EXPLORER"]["tried"] > results["PLANNER"]["tried"]


def test_only_the_chosen_technique_produces_evidence():
    """The asymmetry is the point of the study: a technique the policy stops
    choosing stops generating data, and its estimate freezes."""
    rng = np.random.default_rng(6)
    learner = make_learner(rng, tau=0.0)
    result = run_loop(learner, "DUNLOSKY", n_sessions=30, rng=rng)
    assert result.techniques_tried == 1


def test_misspecification_is_measured_against_its_own_control():
    """Fitting the exponential to exponential data must look better than
    fitting it to power-law data on coverage, or the study is not detecting
    misspecification at all."""
    ok = study_misspecified(12, 5, tau=0.4, seed=2, power_law=False)
    bad = study_misspecified(12, 5, tau=0.4, seed=2, power_law=True)
    assert ok.coverage >= bad.coverage
    assert 0.0 <= bad.coverage <= 1.0


@pytest.mark.slow
def test_ranking_survives_the_wrong_forgetting_curve():
    """The finding this study exists to establish: the numbers are biased
    under a power law, but the ORDER of techniques is what the recommendation
    consumes, and the order holds. A biased estimate that ranks correctly
    still gives correct advice."""
    result = study_misspecified(40, 6, tau=0.4, seed=2, power_law=True)
    assert result.rank_agreement > 0.85
    assert abs(result.median_bias) < 0.1


def test_retention_helper_matches_the_ebbinghaus_form():
    from evaluation.monte_carlo import _retention

    assert _retention(0.0, 10.0) == pytest.approx(1.0)
    assert _retention(10.0, 10.0) == pytest.approx(math.exp(-1.0))
