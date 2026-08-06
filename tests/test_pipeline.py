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

    # Every measured surface must be empty for control. Listing them one by one
    # rather than checking the bandit alone: the bandit was the only field this
    # test used to assert, and a new measured field added later would sail
    # straight through to a control participant.
    assert c_fp["technique_effectiveness"] == []
    assert c_fp["memory_profiles"] == []
    assert c_fp["technique_stability"] == []
    assert c_fp["recommended_techniques"] == []
    assert c_fp["improving_over_time"] is None
    assert c_fp["avg_score_trend_per_week"] is None
    assert all(v is None for v in c_fp["optimal_conditions"].values())


def test_control_confidence_tracks_effort_so_the_blind_holds(client):
    """The blind cuts both ways: control must not receive measured signal, and
    must not receive a *visibly different app* either.

    The client gates its entire fingerprint screen on `confidence != "low"`.
    While this was pinned to LOW, a control participant who had studied for
    weeks kept seeing "your fingerprint is growing — processing your first
    insights", forever, next to an honest "16 sessions" counter — while a
    treatment participant with byte-identical history saw a full screen. No
    knowledge of the study design is needed to notice that.

    Confidence is derived from the session count, which control users already
    receive, so sending it honestly discloses nothing that was being withheld.
    """
    ctrl = make_user(client, group="control")
    _seed_rich_history(client, ctrl, sessions_per_tech=6)  # 18 sessions

    c_fp = client.get(f"/users/{ctrl}/fingerprint").json()["fingerprint"]
    assert c_fp["session_count"] == 18
    assert c_fp["confidence"] == "high"

    # ...and still nothing measured underneath it.
    assert c_fp["technique_effectiveness"] == []
    assert c_fp["memory_profiles"] == []


def test_control_confidence_still_starts_low(client):
    """A control user with no history is low-confidence for the honest reason,
    not because the arm is hardcoded."""
    ctrl = make_user(client, group="control")
    c_fp = client.get(f"/users/{ctrl}/fingerprint").json()["fingerprint"]
    assert c_fp["session_count"] == 0
    assert c_fp["confidence"] == "low"


def test_cold_start_recommendations_follow_the_research_ranking(client):
    """A brand-new user's recommended techniques must be the literature's
    ordering, not an accident of dictionary iteration.

    At n=0 every LinUCB arm returns the same unfitted value and there is no
    retention data, so every technique scored identically and `sorted` — being
    stable — returned whatever order the underlying set happened to produce. In
    practice that put mind_maps and re_reading, the two lowest-utility
    techniques in Dunlosky, at positions 2 and 3 of the first thing a new user
    is ever shown. priors.py existed to prevent exactly this, but only ever fed
    the planner, never this field.
    """
    uid = make_user(client, group="treatment")
    fp = client.post(f"/users/{uid}/fingerprint/rebuild").json()["fingerprint"]

    top3 = fp["recommended_techniques"][:3]
    assert top3 == ["practice_testing", "spaced_repetition", "active_recall"]
    # And the low-utility techniques are nowhere near the top.
    assert "re_reading" not in top3
    assert "mind_maps" not in top3


def test_cold_start_plan_is_not_fourteen_identical_days(client):
    """Variety where the model is indifferent — a plan that repeats one
    technique every day for a fortnight is bad practice and reads as broken."""
    uid = make_user(client, group="treatment")
    material = client.post("/materials/analyze", json={
        "title": "Photosynthesis",
        "raw_text": (
            "Photosynthesis converts light energy into chemical energy. "
            "Chlorophyll in the thylakoid membrane absorbs photons. The Calvin "
            "cycle fixes carbon dioxide into glucose. Stomata regulate gas "
            "exchange. Rubisco catalyses carbon fixation. Glycolysis splits "
            "glucose into pyruvate. The electron transport chain generates a "
            "proton gradient across the inner mitochondrial membrane."
        ),
    }).json()
    plan = client.post(
        f"/users/{uid}/study-plan?material_id={material['material_id']}&total_days=14"
    ).json()

    techniques = {d["technique"] for d in plan["days"] if d["session_duration_minutes"] > 0}
    assert len(techniques) > 1, f"plan collapsed to a single technique: {techniques}"

    # The advice text must describe the plan printed underneath it. It used to
    # name a hardcoded pair that material-aware matching had made obsolete.
    advice = plan["general_advice"]
    for technique in techniques:
        assert technique.replace("_", " ") in advice, (
            f"advice does not mention {technique}, which the plan uses: {advice}"
        )


def test_empty_user_returns_generic_fingerprint(client):
    uid = make_user(client, group="treatment")
    fp = client.get(f"/users/{uid}/fingerprint").json()["fingerprint"]
    assert fp["session_count"] == 0
    assert fp["confidence"] == "low"
