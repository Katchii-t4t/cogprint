"""
Account recovery via unguessable token.

The flow this replaces let anyone claim any account by typing a number: ids are
sequential, so counting upward walked the whole user table. These tests pin both
halves of the fix — that recovery works for the legitimate holder of a token,
and that the enumeration attack no longer has a door to knock on.
"""

import auth
import database
import pytest


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Each test gets a fresh attempt budget (the limiter is process-global)."""
    auth.reset_rate_limits()
    yield
    auth.reset_rate_limits()


def _create(client, group="treatment"):
    r = client.post("/users", json={"group": group})
    assert r.status_code == 201, r.text
    return r.json()


# ── issuing ───────────────────────────────────────────────────────────────────

def test_create_user_returns_a_recovery_token(client):
    body = _create(client)
    token = body["recovery_token"]
    assert token.startswith("cog_")
    assert len(token) > 30  # 24 random bytes, url-safe encoded


def test_plaintext_token_is_never_persisted(client):
    token = _create(client)["recovery_token"]
    db = database.SessionLocal()
    try:
        stored = [u.recovery_token_hash for u in db.query(database.User).all()]
    finally:
        db.close()
    assert token not in stored
    assert database.hash_recovery_token(token) in stored


def test_tokens_are_unique_per_user(client):
    assert _create(client)["recovery_token"] != _create(client)["recovery_token"]


# ── recovering ────────────────────────────────────────────────────────────────

def test_valid_token_recovers_the_right_account(client):
    created = _create(client)
    r = client.post("/auth/recover", json={"recovery_token": created["recovery_token"]})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == created["id"]
    assert r.json()["group"] == created["group"]


def test_recovery_response_does_not_leak_the_token(client):
    created = _create(client)
    r = client.post("/auth/recover", json={"recovery_token": created["recovery_token"]})
    assert "recovery_token" not in r.json()


def test_unknown_token_is_rejected(client):
    _create(client)
    r = client.post("/auth/recover", json={"recovery_token": "cog_" + "a" * 32})
    assert r.status_code == 404


def test_another_users_token_never_returns_your_account(client):
    a = _create(client)
    b = _create(client)
    r = client.post("/auth/recover", json={"recovery_token": b["recovery_token"]})
    assert r.json()["id"] == b["id"] != a["id"]


# ── the attack this feature exists to stop ────────────────────────────────────

def test_sequential_id_enumeration_cannot_claim_accounts(client):
    """The old hole: POST an id, get the account. Walk 1..N, own everything.

    Recovery is now token-only, so ids are useless as credentials — every
    attempt to pass one must fail, whether it names a real user or not.
    """
    real_ids = [_create(client)["id"] for _ in range(3)]

    for candidate in real_ids + [99, 1000]:
        r = client.post("/auth/recover", json={"recovery_token": str(candidate)})
        assert r.status_code in (404, 422), (
            f"id {candidate} was accepted as a credential: {r.status_code} {r.text}"
        )


def test_user_lookup_by_id_is_not_a_public_endpoint(client, monkeypatch):
    """GET /users/{id} enumerates group + scores, so it sits behind the API key
    whenever one is configured."""
    uid = _create(client)["id"]
    monkeypatch.setenv("COGPRINT_API_KEY", "test-key")

    assert client.get(f"/users/{uid}").status_code == 401
    ok = client.get(f"/users/{uid}", headers={"X-API-Key": "test-key"})
    assert ok.status_code == 200
    assert ok.json()["id"] == uid


# ── rotation ──────────────────────────────────────────────────────────────────

def test_rotation_issues_a_new_token_for_the_same_account(client):
    created = _create(client)
    r = client.post("/auth/recover/rotate", json={"recovery_token": created["recovery_token"]})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == created["id"]
    assert r.json()["recovery_token"] != created["recovery_token"]


def test_rotation_invalidates_the_previous_token(client):
    created = _create(client)
    old = created["recovery_token"]
    new = client.post("/auth/recover/rotate", json={"recovery_token": old}).json()["recovery_token"]

    assert client.post("/auth/recover", json={"recovery_token": old}).status_code == 404
    assert client.post("/auth/recover", json={"recovery_token": new}).status_code == 200


def test_rotation_requires_a_valid_token(client):
    _create(client)
    r = client.post("/auth/recover/rotate", json={"recovery_token": "cog_" + "z" * 32})
    assert r.status_code == 404


# ── rate limiting ─────────────────────────────────────────────────────────────

def test_repeated_failed_attempts_are_throttled(client):
    _create(client)
    codes = [
        client.post("/auth/recover", json={"recovery_token": f"cog_{i:032d}"}).status_code
        for i in range(15)
    ]
    assert 429 in codes, "brute-force attempts were never throttled"
    assert codes.count(404) <= 10  # the configured per-window budget
