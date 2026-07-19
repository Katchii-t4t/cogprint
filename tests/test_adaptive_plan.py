"""
Adaptive re-planning (§3.3): a returning learner's plan resumes from today
(concepts as decayed reviews) instead of re-introducing everything, and an exam
date sizes the horizon instead of the hardcoded 14 days.
"""

from datetime import date, timedelta

from tests.conftest import make_user, backdate_session

TEXT = (
    "Photosynthesis converts light energy into chemical energy. "
    "The Calvin cycle fixes carbon dioxide into glucose. "
    "Chlorophyll absorbs light in the thylakoid membrane. "
    "ATP and NADPH power the light-independent reactions."
)


def _analyze(client, title="Photosynthesis"):
    r = client.post("/materials/analyze", json={"title": title, "raw_text": TEXT})
    assert r.status_code in (200, 201), r.text
    return r.json()["material_id"]


def _log(client, uid, mid):
    r = client.post("/sessions", json={
        "user_id": uid, "material_id": mid, "technique": "active_recall",
        "duration_minutes": 25, "time_of_day": "morning", "quiz_score": 0.7,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _plan(client, uid, mid, **params):
    r = client.post(f"/users/{uid}/study-plan", params={"material_id": mid, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_first_time_plan_introduces_new_concepts(client):
    uid = make_user(client, group="treatment")
    mid = _analyze(client)
    plan = _plan(client, uid, mid)
    assert "Resuming" not in plan["general_advice"]
    # Day 1 of a fresh plan introduces concepts.
    assert "NEW:" in plan["days"][0]["topic_focus"]


def test_returning_plan_resumes_with_reviews(client):
    uid = make_user(client, group="treatment")
    mid = _analyze(client)
    sid = _log(client, uid, mid)
    backdate_session(sid, days=6)  # last studied 6 days ago

    plan = _plan(client, uid, mid)
    assert plan["general_advice"].startswith("Resuming")
    assert "6 days ago" in plan["general_advice"]
    # Resuming means day 1 is review, not fresh introduction.
    assert "REVIEW:" in plan["days"][0]["topic_focus"]
    assert "NEW:" not in plan["days"][0]["topic_focus"]


def test_exam_date_sizes_the_horizon(client):
    uid = make_user(client, group="treatment")
    mid = _analyze(client)
    exam = date.today() + timedelta(days=5)
    plan = _plan(client, uid, mid, target_date=exam.isoformat())
    # 5, or 6 across a UTC/local date boundary (endpoint uses UTC date). The
    # point is the exam date sizes the horizon, not the default 14.
    assert plan["total_days"] in (5, 6)


def test_bad_exam_date_is_422(client):
    uid = make_user(client, group="treatment")
    mid = _analyze(client)
    r = client.post(f"/users/{uid}/study-plan", params={"material_id": mid, "target_date": "not-a-date"})
    assert r.status_code == 422


def test_default_horizon_still_14(client):
    uid = make_user(client, group="treatment")
    mid = _analyze(client)
    plan = _plan(client, uid, mid)
    assert plan["total_days"] == 14
