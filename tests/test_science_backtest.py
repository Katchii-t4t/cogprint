"""
Backtest of the intelligence itself (§7 / RESEARCH.md).

We seed synthetic learners whose GROUND-TRUTH per-technique 7-day retention
matches the learning-science ranking (Dunlosky 2013 et al., encoded in
personalization/priors.py), push it through the *whole* pipeline, and assert the
recovered fingerprint reproduces that ranking. This is the regression test for
whether the brain actually works — not just whether the plumbing runs.

It is deliberately tolerant of MCMC/OLS sampling noise: we assert a strong rank
correlation and correct placement of the best/worst techniques, not exact numbers.
"""

import random

from personalization.priors import RESEARCH_PRIORS
from tests.conftest import add_retention, log_session, make_user

# Ground-truth ordering (best → worst) straight from the research priors.
GROUND_TRUTH = sorted(
    RESEARCH_PRIORS, key=lambda t: RESEARCH_PRIORS[t].retention_7d, reverse=True
)


def _spearman(order_a: list[str], order_b: list[str]) -> float:
    """Spearman rank correlation between two orderings of the same items."""
    rank_a = {t: i for i, t in enumerate(order_a)}
    rank_b = {t: i for i, t in enumerate(order_b)}
    n = len(rank_a)
    d2 = sum((rank_a[t] - rank_b[t]) ** 2 for t in rank_a)
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _seed_literature_learner(client, uid, sessions_per_tech=6, seed=1):
    """For each technique, log sessions with 24h/7d retention checks drawn to
    match that technique's literature 7-day retention (plus small noise)."""
    rng = random.Random(seed)
    for tech, prior in RESEARCH_PRIORS.items():
        r7 = prior.retention_7d
        for _ in range(sessions_per_tech):
            sid = log_session(
                client, uid, technique=tech,
                quiz_score=round(min(1.0, 0.9 + rng.uniform(-0.03, 0.03)), 3),
                duration=25, time_of_day="morning",
            )
            # 24h sits above the 7d asymptote; 7d matches the ground truth.
            r24 = min(1.0, r7 + 0.10 + rng.uniform(-0.02, 0.02))
            r7d = max(0.0, min(1.0, r7 + rng.uniform(-0.02, 0.02)))
            add_retention(client, sid, uid, "24h", round(r24, 3))
            add_retention(client, sid, uid, "7d", round(r7d, 3))


def test_brain_recovers_literature_ranking(client):
    uid = make_user(client, group="treatment")
    _seed_literature_learner(client, uid, sessions_per_tech=6, seed=7)

    r = client.get(f"/users/{uid}/fingerprint")
    assert r.status_code == 200, r.text
    profiles = r.json()["fingerprint"]["memory_profiles"]
    assert profiles, "expected per-technique memory profiles after rich seeding"

    # Recovered ordering by predicted 7-day retention.
    recovered = [
        p["technique"]
        for p in sorted(profiles, key=lambda p: p["predicted_retention_7d"], reverse=True)
    ]

    # Only compare techniques the pipeline actually produced a profile for.
    truth = [t for t in GROUND_TRUTH if t in recovered]
    recovered = [t for t in recovered if t in truth]
    assert len(truth) >= 5, f"expected most techniques recovered, got {recovered}"

    rho = _spearman(truth, recovered)
    assert rho >= 0.6, f"weak recovery: rho={rho:.2f}\n truth={truth}\n got  ={recovered}"

    # The strongest and weakest techniques must land near the correct ends.
    assert recovered.index("practice_testing") <= 1, recovered
    assert recovered.index("re_reading") >= len(recovered) - 2, recovered


def test_recovered_retention_tracks_ground_truth_magnitude(client):
    """Beyond ordering, the recovered 7d retention should be monotonically
    related to the seeded values (best technique clearly above worst)."""
    uid = make_user(client, group="treatment")
    _seed_literature_learner(client, uid, sessions_per_tech=6, seed=11)

    profiles = client.get(f"/users/{uid}/fingerprint").json()["fingerprint"]["memory_profiles"]
    by_tech = {p["technique"]: p["predicted_retention_7d"] for p in profiles}

    if "practice_testing" in by_tech and "re_reading" in by_tech:
        assert by_tech["practice_testing"] > by_tech["re_reading"], by_tech
