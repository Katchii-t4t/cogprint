"""Tests for the optional API-key auth on sensitive endpoints."""

from tests.conftest import log_session, make_user


def test_open_mode_allows_sensitive_endpoints(client):
    """With no COGPRINT_API_KEY set, researcher endpoints are open."""
    assert client.get("/users/all").status_code == 200
    assert client.get("/export/study-data").status_code == 200


def test_keyed_mode_enforces_api_key(client, monkeypatch):
    monkeypatch.setenv("COGPRINT_API_KEY", "s3cret-test-key")

    # Missing header -> 401
    assert client.get("/users/all").status_code == 401
    assert client.get("/export/study-data").status_code == 401

    # Wrong header -> 401
    assert client.get("/users/all", headers={"X-API-Key": "nope"}).status_code == 401

    # Correct header -> 200
    ok = {"X-API-Key": "s3cret-test-key"}
    assert client.get("/users/all", headers=ok).status_code == 200
    assert client.get("/export/study-data", headers=ok).status_code == 200


def test_keyed_mode_leaves_participant_endpoints_open(client, monkeypatch):
    """Participant-facing endpoints stay open even when the key is set
    (the key guards bulk-data endpoints, not participant onboarding)."""
    monkeypatch.setenv("COGPRINT_API_KEY", "s3cret-test-key")
    uid = make_user(client, group="treatment")
    log_session(client, uid)
    assert client.get(f"/users/{uid}/fingerprint").status_code == 200
    assert client.get(f"/users/{uid}/pending-checks").status_code == 200
