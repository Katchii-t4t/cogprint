"""
End-to-end exercise of the cognitive-fingerprint pipeline.

Drives enough real data through the API that the rebuild touches every stage:
per-technique stats, Ebbinghaus OLS fits, hierarchical Bayesian MCMC, the
LinUCB batch refit, trend detection and insight generation. The goal is not to
pin exact numbers (the math is allowed to evolve) but to prove the pipeline
runs to completion on realistic data and the RCT control/treatment split holds.
"""

from tests.conftest import add_retention, log_session, make_user

TECHNIQUES = ["active_recall", "spaced_repetition", "re_reading"]


def _seed_rich_history(client, uid, sessions_per_tech=6):
    """Log several sessions per technique, each with 24h + 7d retention checks.

    active_recall is made clearly the strongest technique so the recommender
    has a signal to find.
    """
    strength = {"active_recall": 0.9, "spaced_repetition": 0.75, "re_reading": 0.55}
    for tech in TECHNIQUES:
        base = strength[tech]
        for i in range(sessions_per_tech):
            quiz = min(1.0, base + (i % 3) * 0.02)
            sid = log_session(
                client, uid, technique=tech, quiz_score=quiz,
                duration=25 + (i % 3) * 10,
                time_of_day=["morning", "afternoon", "evening"][i % 3],
                sleep_hours=6.5 + (i % 4) * 0.5,
                stress_level=2 + (i % 3),
            )
            # Retention decays from the immediate score; stronger techniques hold better.
            add_retention(client, sid, uid, "24h", round(min(1.0, base - 0.05), 3))
            add_retention(client, sid, uid, "7d", round(max(0.0, base - 0.15), 3))


def test_full_pipeline_high_confidence(client):
    uid = make_user(client, group="treatment", pre_test_score=0.4)
    _seed_rich_history(client, uid, sessions_per_tech=6)  # 18 sessions

    r = client.get(f"/users/{uid}/fingerprint")
    assert r.status_code == 200, r.text
    fp = r.json()["fingerprint"]

    assert fp["session_count"] == 18
    # 16+ sessions -> high confidence per the spec.
    assert fp["confidence"] == "high"
    # The pipeline should surface technique recommendations and insights.
    assert isinstance(fp["recommended_techniques"], list)
    assert len(fp["recommended_techniques"]) >= 1
    assert isinstance(fp["insights"], list)
    # LinUCB expected rewards should be populated for a treatment user.
    assert isinstance(fp.get("bandit_expected_rewards"), dict)
    assert len(fp["bandit_expected_rewards"]) >= 1


def test_force_rebuild_is_idempotent(client):
    uid = make_user(client, group="treatment")
    _seed_rich_history(client, uid, sessions_per_tech=2)

    a = client.post(f"/users/{uid}/fingerprint/rebuild").json()["fingerprint"]
    b = client.post(f"/users/{uid}/fingerprint/rebuild").json()["fingerprint"]
    # Same input data -> same session_count and confidence on repeated rebuilds.
    assert a["session_count"] == b["session_count"]
    assert a["confidence"] == b["confidence"]


def test_control_group_is_blinded(client):
    """RCT blinding: a control user should NOT receive the full personalised
    treatment, even with identical rich data."""
    treat = make_user(client, group="treatment")
    ctrl = make_user(client, group="control")
    _seed_rich_history(client, treat, sessions_per_tech=6)
    _seed_rich_history(client, ctrl, sessions_per_tech=6)

    t_fp = client.get(f"/users/{treat}/fingerprint").json()["fingerprint"]
    c_fp = client.get(f"/users/{ctrl}/fingerprint").json()["fingerprint"]

    # Treatment runs the full bandit; control gets a generic profile with no
    # personalised bandit rewards. They must not be identical.
    assert t_fp.get("bandit_expected_rewards")
    assert not c_fp.get("bandit_expected_rewards")


def test_empty_user_returns_generic_fingerprint(client):
    uid = make_user(client, group="treatment")
    fp = client.get(f"/users/{uid}/fingerprint").json()["fingerprint"]
    assert fp["session_count"] == 0
    assert fp["confidence"] == "low"
