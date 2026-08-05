"""
GDPR self-service export (art. 15) and erasure (art. 17).

Both endpoints authenticate with a recovery token in the body, never a path
user_id — so the tests here also pin that neither reopens the enumeration hole
that the id-based restore had.
"""

import pytest

import auth
import database
from tests.conftest import add_retention, log_session, make_user

TEXT = (
    "Photosynthesis converts light energy into chemical energy. "
    "The Calvin cycle fixes carbon dioxide into glucose."
)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    auth.reset_rate_limits()
    yield
    auth.reset_rate_limits()


def _account_with_history(client):
    """A user with a material, a session and a retention check."""
    created = client.post("/users", json={"group": "treatment"}).json()
    uid, token = created["id"], created["recovery_token"]

    mat = client.post("/materials/analyze", json={"title": "Photosynthesis", "raw_text": TEXT})
    material_id = mat.json()["material_id"]

    r = client.post("/sessions", json={
        "user_id": uid, "material_id": material_id, "technique": "active_recall",
        "duration_minutes": 25, "time_of_day": "morning", "quiz_score": 0.8,
    })
    add_retention(client, r.json()["id"], uid, "24h", 0.75)
    return uid, token, material_id


# ── export ────────────────────────────────────────────────────────────────────

def test_export_returns_the_full_record(client):
    uid, token, material_id = _account_with_history(client)

    r = client.post("/users/me/export", json={"recovery_token": token})
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["account"]["id"] == uid
    assert len(data["study_sessions"]) == 1
    assert len(data["retention_checks"]) == 1
    assert [m["id"] for m in data["materials"]] == [material_id]
    assert data["materials"][0]["raw_text"] == TEXT


def test_export_never_includes_the_credential(client):
    _, token, _ = _account_with_history(client)
    body = client.post("/users/me/export", json={"recovery_token": token}).text
    assert "recovery_token_hash" not in body
    assert database.hash_recovery_token(token) not in body


def test_export_is_scoped_to_the_caller(client):
    _, token_a, _ = _account_with_history(client)
    uid_b, _, _ = _account_with_history(client)

    data = client.post("/users/me/export", json={"recovery_token": token_a}).json()
    assert data["account"]["id"] != uid_b
    assert all(s["id"] for s in data["study_sessions"])
    # B's session must not appear in A's export.
    b_sessions = {
        s.id for s in database.SessionLocal().query(database.StudySession).filter_by(user_id=uid_b)
    }
    assert not b_sessions & {s["id"] for s in data["study_sessions"]}


def test_export_rejects_an_invalid_token(client):
    assert client.post(
        "/users/me/export", json={"recovery_token": "cog_" + "q" * 32}
    ).status_code == 404


# ── erasure ───────────────────────────────────────────────────────────────────

def test_delete_removes_the_account_and_its_children(client):
    uid, token, _ = _account_with_history(client)

    r = client.post("/users/me/delete", json={"recovery_token": token, "confirm": True})
    assert r.status_code == 200, r.text

    db = database.SessionLocal()
    try:
        assert db.query(database.User).filter_by(id=uid).first() is None
        assert db.query(database.StudySession).filter_by(user_id=uid).count() == 0
        assert db.query(database.RetentionCheck).filter_by(user_id=uid).count() == 0
        assert db.query(database.CognitiveFingerprint).filter_by(user_id=uid).count() == 0
    finally:
        db.close()


def test_delete_requires_explicit_confirmation(client):
    uid, token, _ = _account_with_history(client)

    assert client.post(
        "/users/me/delete", json={"recovery_token": token, "confirm": False}
    ).status_code == 422
    # Omitted entirely is a schema error, not an accidental deletion.
    assert client.post(
        "/users/me/delete", json={"recovery_token": token}
    ).status_code == 422

    db = database.SessionLocal()
    try:
        assert db.query(database.User).filter_by(id=uid).first() is not None
    finally:
        db.close()


def test_the_token_stops_working_after_deletion(client):
    _, token, _ = _account_with_history(client)
    client.post("/users/me/delete", json={"recovery_token": token, "confirm": True})

    assert client.post("/auth/recover", json={"recovery_token": token}).status_code == 404
    assert client.post("/users/me/export", json={"recovery_token": token}).status_code == 404


def test_deletion_leaves_shared_materials_intact(client):
    """A Material is not owned by one user — erasing an account must not
    destroy a deck another learner is still studying."""
    _, token_a, material_id = _account_with_history(client)

    uid_b = make_user(client)
    log_session(client, uid_b)  # B exists independently

    client.post("/users/me/delete", json={"recovery_token": token_a, "confirm": True})

    db = database.SessionLocal()
    try:
        assert db.query(database.Material).filter_by(id=material_id).first() is not None
    finally:
        db.close()


def test_delete_rejects_an_invalid_token(client):
    assert client.post(
        "/users/me/delete", json={"recovery_token": "cog_" + "w" * 32, "confirm": True}
    ).status_code == 404
