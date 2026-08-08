"""
Pytest fixtures for the CogPrint backend.

Critical ordering detail: database.py builds its engine from DATABASE_URL at
*import time*, so we must point the app at an isolated temp SQLite database
BEFORE importing the app. That is why the env vars are set at module top, above
the app imports.
"""

import os
import sys
import tempfile

import pytest

# --- Isolate the app onto a throwaway DB before it is imported --------------
_TMP_DIR = tempfile.mkdtemp(prefix="cogprint_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'test.db')}"
os.environ.pop("COGPRINT_API_KEY", None)  # tests assume auth is OFF unless they opt in
os.environ.pop("CORS_ORIGINS", None)

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402


@pytest.fixture()
def client():
    """A TestClient with a freshly reset schema for each test.

    Note: Starlette's TestClient runs BackgroundTasks to completion before the
    request returns, so the fingerprint rebuild triggered by POST /sessions has
    already finished by the time the call returns in tests.
    """
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    with TestClient(main.app) as c:
        yield c


# user_id -> plaintext recovery token, so helpers and tests can authenticate as
# a user they created without every call site threading the token through.
#
# Deliberately NOT an automatic header injection on the client: that would make
# every test pass whether authorization worked or not, which is exactly the
# property that let eleven endpoints ship unauthenticated. Tests must ask for
# credentials explicitly, so a route that stops checking them fails a test.
_TOKENS: dict[int, str] = {}


def auth(user_id):
    """Headers that authenticate as `user_id`. Empty for an unknown id, so a
    test can deliberately call as an anonymous stranger."""
    token = _TOKENS.get(user_id)
    return {"Authorization": f"Bearer {token}"} if token else {}


def token_for(user_id):
    return _TOKENS[user_id]


def register_token(user_id, token):
    """Record a token for a user this module did not create.

    Some suites call POST /users directly because they need the plaintext token
    for the endpoint under test (export, delete, rotation). They still want the
    shared helpers to authenticate for them.
    """
    _TOKENS[user_id] = token
    return user_id


def make_user(client, group="treatment", pre_test_score=None):
    body = {"group": group}
    if pre_test_score is not None:
        body["pre_test_score"] = pre_test_score
    r = client.post("/users", json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    _TOKENS[payload["id"]] = payload["recovery_token"]
    return payload["id"]


def log_session(client, user_id, technique="active_recall", quiz_score=0.7,
                duration=30, time_of_day="morning", sleep_hours=7.5, stress_level=3):
    body = {
        "user_id": user_id,
        "technique": technique,
        "duration_minutes": duration,
        "time_of_day": time_of_day,
        "quiz_score": quiz_score,
        "sleep_hours": sleep_hours,
        "stress_level": stress_level,
    }
    r = client.post("/sessions", json=body, headers=auth(user_id))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def add_retention(client, session_id, user_id, check_type, score):
    r = client.post("/retention-checks", json={
        "session_id": session_id, "user_id": user_id,
        "check_type": check_type, "score": score,
    }, headers=auth(user_id))
    return r


def backdate_session(session_id, days=0, hours=0):
    """Move a session's created_at into the past so retention checks come due."""
    from datetime import timedelta
    db = database.SessionLocal()
    try:
        obj = db.get(database.StudySession, session_id)
        obj.created_at = database.utcnow() - timedelta(days=days, hours=hours)
        db.commit()
    finally:
        db.close()
