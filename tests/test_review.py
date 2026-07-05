"""Tests for GET /users/{id}/review-suggestions (deterministic Ebbinghaus)."""

from datetime import datetime, timedelta

import database
from personalization.review import predicted_retention
from tests.conftest import make_user

MATERIAL_TEXT = (
    "Photosynthesis converts light energy into chemical energy. It occurs in "
    "the chloroplasts. The light reactions produce ATP and NADPH. The Calvin "
    "cycle fixes carbon dioxide into glucose using ATP and NADPH."
)


def _analyze(client, title):
    r = client.post("/materials/analyze", json={"title": title, "raw_text": MATERIAL_TEXT})
    assert r.status_code == 201, r.text
    return r.json()["material_id"]


def _session_on(client, uid, mid):
    r = client.post("/sessions", json={
        "user_id": uid, "material_id": mid, "technique": "active_recall",
        "duration_minutes": 30, "time_of_day": "morning", "quiz_score": 0.8,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _backdate(session_id, days):
    db = database.SessionLocal()
    try:
        obj = db.get(database.StudySession, session_id)
        obj.created_at = datetime.utcnow() - timedelta(days=days)
        db.commit()
    finally:
        db.close()


def test_predicted_retention_math():
    assert predicted_retention(0, 10) == 1.0
    assert abs(predicted_retention(10, 10) - 0.3679) < 0.001
    # Clamps: negative time -> 1.0; tiny stability floored, not div-by-zero.
    assert predicted_retention(-5, 10) == 1.0
    assert 0.0 <= predicted_retention(100, 0.0001) <= 1.0


def test_review_suggestions_flags_fading_material(client):
    uid = make_user(client, group="treatment")
    old_mid = _analyze(client, "Old material")
    new_mid = _analyze(client, "Fresh material")
    sid_old = _session_on(client, uid, old_mid)
    _session_on(client, uid, new_mid)
    _backdate(sid_old, days=30)

    r = client.get(f"/users/{uid}/review-suggestions")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2

    # Sorted ascending by predicted retention -> the stale one first.
    stale = items[0]
    assert stale["material_id"] == old_mid
    assert stale["fading"] is True
    assert stale["predicted_retention"] < 0.2  # exp(-30/10) ~ 0.05

    fresh = items[1]
    assert fresh["material_id"] == new_mid
    assert fresh["fading"] is False
    assert fresh["predicted_retention"] > 0.95


def test_review_suggestions_empty_and_404(client):
    uid = make_user(client)
    assert client.get(f"/users/{uid}/review-suggestions").json() == []
    assert client.get("/users/99999/review-suggestions").status_code == 404
