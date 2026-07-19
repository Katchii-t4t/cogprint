"""
Material library (§3.3): GET /users/{id}/materials — the returning-user home.
Derived from the user's own sessions, review-aware, cross-device.
"""

from tests.conftest import make_user, backdate_session

TEXT = (
    "Photosynthesis converts light energy into chemical energy. "
    "The Calvin cycle fixes carbon dioxide into glucose. "
    "Chlorophyll absorbs light in the thylakoid membrane."
)


def _analyze(client, title, text=TEXT):
    r = client.post("/materials/analyze", json={"title": title, "raw_text": text})
    assert r.status_code in (200, 201), r.text
    return r.json()["material_id"]


def _log(client, user_id, material_id, technique="active_recall", quiz_score=0.8):
    r = client.post("/sessions", json={
        "user_id": user_id, "material_id": material_id, "technique": technique,
        "duration_minutes": 25, "time_of_day": "morning", "quiz_score": quiz_score,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_empty_library_for_new_user(client):
    uid = make_user(client)
    r = client.get(f"/users/{uid}/materials")
    assert r.status_code == 200
    assert r.json() == []


def test_unknown_user_404(client):
    r = client.get("/users/999999/materials")
    assert r.status_code == 404


def test_studied_material_appears_with_metadata(client):
    uid = make_user(client)
    mid = _analyze(client, "Photosynthesis")
    _log(client, uid, mid)

    r = client.get(f"/users/{uid}/materials")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    it = items[0]
    assert it["material_id"] == mid
    assert it["title"] == "Photosynthesis"
    assert it["session_count"] == 1
    assert it["concept_count"] > 0
    assert 0.0 <= it["predicted_retention"] <= 1.0
    assert it["reviews_due"] == 0  # just studied, nothing due yet


def test_multiple_sessions_aggregate_into_one_entry(client):
    uid = make_user(client)
    mid = _analyze(client, "Photosynthesis")
    _log(client, uid, mid)
    _log(client, uid, mid)
    _log(client, uid, mid)

    items = client.get(f"/users/{uid}/materials").json()
    assert len(items) == 1
    assert items[0]["session_count"] == 3


def test_reviews_due_counts_overdue_checks(client):
    uid = make_user(client)
    mid = _analyze(client, "Photosynthesis")
    sid = _log(client, uid, mid)
    # Push the session 8 days into the past → both 24h and 7d checks come due.
    backdate_session(sid, days=8)

    items = client.get(f"/users/{uid}/materials").json()
    assert items[0]["reviews_due"] >= 1
    assert items[0]["fading"] in (True, False)  # computed, not crashing


def test_sorted_by_last_studied_desc(client):
    uid = make_user(client)
    m1 = _analyze(client, "First")
    s1 = _log(client, uid, m1)
    m2 = _analyze(client, "Second")
    _log(client, uid, m2)
    # Make m1's latest session older than m2's.
    backdate_session(s1, days=3)

    items = client.get(f"/users/{uid}/materials").json()
    assert [it["title"] for it in items] == ["Second", "First"]
