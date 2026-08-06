"""
Tests for the evaluator itself.

An evaluation harness that is wrong is worse than none: it produces a number
that looks like evidence and gets believed. The first version of this one
declared per-technique personalisation a 100% winner on data generated with
the per-technique effect set to exactly zero — because its baseline could not
represent population-level technique differences either, so PERSONAL beat it
for a reason that had nothing to do with personalisation.

So the harness is tested the way an instrument is calibrated: feed it data
where the truth is known by construction, and require it to report that truth
in both directions.

  - No effect present  -> must NOT claim one (false-positive check).
  - Large effect present -> must find it (power check).

These use the real MCMC sampler, which is seeded from the OS and therefore
non-deterministic. The margins asserted below are wide enough that sampler
noise does not flip them; they are not tight numeric pins, deliberately.
"""

import pytest

from evaluation.predictive_baseline import (
    Cell,
    evaluate,
    paired_bootstrap,
    prospective_split,
    simulate_cohort,
)


# ── Calibration: does the verdict track the truth? ────────────────────────────


@pytest.mark.slow
def test_reports_no_advantage_when_there_is_none():
    """tau=0: everyone is suited by the same techniques.

    Per-technique fitting still has more parameters and less data each, so it
    should if anything do slightly *worse* here. What it must not do is win.
    """
    cells = simulate_cohort(n_users=6, sessions_per_technique=6, tau_technique=0.0, seed=11)
    scores = evaluate(cells)
    _, confidence = paired_bootstrap(scores["PERSONAL"], scores["PERSON"])
    assert confidence < 0.95, (
        f"claimed a personalisation advantage that does not exist "
        f"(won {confidence:.0%} of resamples)"
    )


@pytest.mark.slow
def test_finds_the_advantage_when_it_is_large():
    """tau=0.6: which technique suits you varies substantially between people.

    If the harness cannot see an effect this size with this much data, it
    cannot see anything, and a null result from it would mean nothing.
    """
    cells = simulate_cohort(n_users=6, sessions_per_technique=6, tau_technique=0.6, seed=11)
    scores = evaluate(cells)
    gain, confidence = paired_bootstrap(scores["PERSONAL"], scores["PERSON"])
    assert confidence > 0.95, f"failed to detect a large real effect ({confidence:.0%})"
    assert gain > 0


@pytest.mark.slow
def test_person_level_fitting_beats_the_flat_prior():
    """People genuinely differ in overall memory strength in the simulation,
    so the middle model must earn its keep — otherwise a PERSONAL win could be
    coming from the person level and be misread as a technique effect."""
    cells = simulate_cohort(n_users=6, sessions_per_technique=6, tau_technique=0.0, seed=5)
    scores = evaluate(cells)
    _, confidence = paired_bootstrap(scores["PERSON"], scores["PRIOR"])
    assert confidence > 0.95


# ── The split ─────────────────────────────────────────────────────────────────


def test_holdout_is_the_chronological_tail():
    """A random split would put a session's 24h check in train and its 7d check
    in test. They share one latent stability and one material, so the model
    would be half-shown its own answer — and the most flexible predictor would
    benefit most, which is exactly the predictor under scrutiny."""
    cell = Cell(1, "active_recall", [(1.0, 0.9), (7.0, 0.7), (1.0, 0.88), (7.0, 0.65)])
    train, heldout = prospective_split(cell, holdout_fraction=0.5)
    assert train == [(1.0, 0.9), (7.0, 0.7)]
    assert heldout == [(1.0, 0.88), (7.0, 0.65)]


def test_a_cell_too_small_to_split_is_dropped_entirely():
    """Rather than being scored on a fit made from nothing."""
    assert prospective_split(Cell(1, "active_recall", [(1.0, 0.9)])) == ([], [])
    assert prospective_split(Cell(1, "active_recall", [(1.0, 0.9), (7.0, 0.6)])) == ([], [])


def test_every_predictor_is_scored_on_identical_points():
    """Comparing predictors that saw different test sets is the easiest way to
    manufacture a win. They must be scored point for point."""
    cells = simulate_cohort(n_users=2, sessions_per_technique=4, tau_technique=0.3, seed=3)
    scores = evaluate(cells)
    counts = {name: s.n for name, s in scores.items()}
    assert len(set(counts.values())) == 1, counts
    assert counts["PRIOR"] > 0


def test_unsplittable_cohort_yields_no_scores_rather_than_a_crash():
    cells = [Cell(1, "active_recall", [(1.0, 0.9)]), Cell(2, "re_reading", [(7.0, 0.4)])]
    scores = evaluate(cells)
    assert all(s.n == 0 for s in scores.values())


# ── The simulator ─────────────────────────────────────────────────────────────


def test_simulated_retention_stays_in_range():
    """Observation noise must not produce a retention above 1 or below 0, which
    would be unfittable by the Ebbinghaus model and silently distort the fit."""
    cells = simulate_cohort(n_users=4, sessions_per_technique=5, tau_technique=0.6, seed=7)
    for cell in cells:
        for _, r in cell.observations:
            assert 0.0 < r <= 1.0


def test_simulation_is_reproducible_from_its_seed():
    a = simulate_cohort(3, 3, 0.4, seed=42)
    b = simulate_cohort(3, 3, 0.4, seed=42)
    assert [c.observations for c in a] == [c.observations for c in b]
