"""
Magic-link email auth.

Two properties carry the security weight and are tested hardest:

  * an address is useless for login until its owner clicks a link sent to it,
    so recording someone else's address gains an attacker nothing;
  * /auth/magic-link/request answers identically whether or not the address
    matches an account — otherwise it is an oracle for "does this person use
    CogPrint", the enumeration problem the id-based restore already taught us.
"""

from datetime import timedelta

import pytest

import auth
import database
import main
from tests.conftest import make_user  # noqa: F401


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    auth.reset_rate_limits()
    yield
    auth.reset_rate_limits()


@pytest.fixture()
def sent(monkeypatch):
    """Capture outbound mail instead of logging it."""
    outbox = []
    monkeypatch.setattr(main, "send_email", lambda to, subject, body_text: outbox.append(
        {"to": to, "subject": subject, "body": body_text}
    ))
    return outbox


def _create(client):
    r = client.post("/users", json={"group": "treatment"})
    assert r.status_code == 201, r.text
    return r.json()


def _link_token(message: str) -> str:
    """Pull the token out of the URL in an email body."""
    _, _, tail = message.partition("token=")
    return tail.split()[0].strip()


def _attach(client, sent, email="learner@example.com"):
    """Create an account, attach an address, and verify it. Returns (user, email)."""
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": email,
    })
    client.post("/auth/magic-link/verify", json={"token": _link_token(sent[-1]["body"])})
    return user, email


# ── attaching an address ──────────────────────────────────────────────────────

def test_attach_requires_a_valid_recovery_token(client, sent):
    r = client.post("/auth/email/attach", json={
        "recovery_token": "cog_" + "x" * 32, "email": "a@example.com",
    })
    assert r.status_code == 404
    assert sent == []


def test_attach_sends_a_verification_link(client, sent):
    user = _create(client)
    r = client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })
    assert r.status_code == 200, r.text
    assert len(sent) == 1
    assert sent[0]["to"] == "learner@example.com"
    assert "token=" in sent[0]["body"]


def test_attached_address_is_not_verified_until_the_link_is_clicked(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })

    db = database.SessionLocal()
    try:
        row = db.query(database.User).filter_by(id=user["id"]).first()
        assert row.email == "learner@example.com"
        assert row.email_verified_at is None
    finally:
        db.close()


def test_email_is_normalised(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "  Learner@Example.COM ",
    })
    assert sent[0]["to"] == "learner@example.com"


def test_obviously_invalid_address_is_rejected(client, sent):
    user = _create(client)
    r = client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "not-an-address",
    })
    assert r.status_code == 422
    assert sent == []


def test_attaching_an_address_verified_elsewhere_reveals_nothing(client, sent):
    _, email = _attach(client, sent)
    other = _create(client)

    r = client.post("/auth/email/attach", json={
        "recovery_token": other["recovery_token"], "email": email,
    })
    # Same status and body as the success path — no hint that it was taken.
    assert r.status_code == 200
    assert "inbox" in r.json()["message"].lower()

    db = database.SessionLocal()
    try:
        row = db.query(database.User).filter_by(id=other["id"]).first()
        assert row.email is None, "the address must not be stolen from its owner"
    finally:
        db.close()


# ── verifying ─────────────────────────────────────────────────────────────────

def test_verify_marks_the_address_as_verified_and_returns_the_account(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })

    r = client.post("/auth/magic-link/verify", json={"token": _link_token(sent[-1]["body"])})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == user["id"]

    db = database.SessionLocal()
    try:
        assert db.query(database.User).filter_by(id=user["id"]).first().email_verified_at
    finally:
        db.close()


def test_a_link_cannot_be_used_twice(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })
    token = _link_token(sent[-1]["body"])

    assert client.post("/auth/magic-link/verify", json={"token": token}).status_code == 200
    assert client.post("/auth/magic-link/verify", json={"token": token}).status_code == 404


def test_an_expired_link_is_rejected(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })
    token = _link_token(sent[-1]["body"])

    db = database.SessionLocal()
    try:
        row = db.query(database.MagicLinkToken).first()
        row.expires_at = database.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert client.post("/auth/magic-link/verify", json={"token": token}).status_code == 404


def test_unknown_token_is_rejected(client):
    assert client.post(
        "/auth/magic-link/verify", json={"token": "z" * 40}
    ).status_code == 404


# ── requesting a sign-in link ─────────────────────────────────────────────────

def test_login_link_is_sent_for_a_verified_address(client, sent):
    _, email = _attach(client, sent)
    sent.clear()

    r = client.post("/auth/magic-link/request", json={"email": email})
    assert r.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to"] == email


def test_login_link_signs_the_user_in(client, sent):
    user, email = _attach(client, sent)
    sent.clear()
    client.post("/auth/magic-link/request", json={"email": email})

    r = client.post("/auth/magic-link/verify", json={"token": _link_token(sent[-1]["body"])})
    assert r.status_code == 200
    assert r.json()["id"] == user["id"]


def test_unknown_address_gets_the_same_answer_and_no_mail(client, sent):
    _, email = _attach(client, sent)
    sent.clear()

    known = client.post("/auth/magic-link/request", json={"email": email})
    sent.clear()
    unknown = client.post("/auth/magic-link/request", json={"email": "nobody@example.com"})

    # Identical response — the only difference is invisible to the caller.
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()
    assert sent == [], "no mail may be sent to an address with no account"


def test_unverified_address_cannot_request_a_login_link(client, sent):
    user = _create(client)
    client.post("/auth/email/attach", json={
        "recovery_token": user["recovery_token"], "email": "learner@example.com",
    })
    sent.clear()

    r = client.post("/auth/magic-link/request", json={"email": "learner@example.com"})
    assert r.status_code == 200  # still the generic answer
    assert sent == [], "an unproven address must not receive sign-in links"


# ── rate limiting ─────────────────────────────────────────────────────────────

def test_email_endpoints_are_throttled(client, sent):
    codes = [
        client.post("/auth/magic-link/request", json={"email": "x@example.com"}).status_code
        for _ in range(9)
    ]
    assert 429 in codes, "email sending was never throttled"
