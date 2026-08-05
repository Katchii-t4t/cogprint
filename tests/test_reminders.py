"""
Review reminders (§2.2) — the channel that makes spaced repetition actually work.

The behaviours worth pinning are the ones that protect people: nobody gets mail
they didn't opt into by verifying an address, nobody gets mail when there is
nothing to review, and a doubled cron trigger cannot spam anyone.
"""

import pytest

import auth
import database
import main
from tests.conftest import backdate_session, log_session, make_user


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    auth.reset_rate_limits()
    yield
    auth.reset_rate_limits()


@pytest.fixture()
def sent(monkeypatch):
    outbox = []
    monkeypatch.setattr(main, "send_email", lambda to, subject, body_text: outbox.append(
        {"to": to, "subject": subject, "body": body_text}
    ))
    return outbox


def _verified_user_with_due_review(client, sent, email="learner@example.com"):
    """A user who has verified an address and has a retention check overdue."""
    created = client.post("/users", json={"group": "treatment"}).json()
    client.post("/auth/email/attach", json={
        "recovery_token": created["recovery_token"], "email": email,
    })
    token = sent[-1]["body"].partition("token=")[2].split()[0].strip()
    client.post("/auth/magic-link/verify", json={"token": token})

    sid = log_session(client, created["id"])
    backdate_session(sid, days=8)  # 24h and 7d checks both come due
    sent.clear()
    return created["id"], email


def test_reminder_is_sent_for_due_reviews(client, sent):
    _, email = _verified_user_with_due_review(client, sent)

    r = client.post("/admin/send-reminders")
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 1
    assert len(sent) == 1
    assert sent[0]["to"] == email
    assert "review" in sent[0]["subject"].lower()


def test_unverified_address_is_never_emailed(client, sent):
    created = client.post("/users", json={"group": "treatment"}).json()
    client.post("/auth/email/attach", json={
        "recovery_token": created["recovery_token"], "email": "unverified@example.com",
    })
    sid = log_session(client, created["id"])
    backdate_session(sid, days=8)
    sent.clear()

    r = client.post("/admin/send-reminders")
    assert r.json()["sent"] == 0
    assert sent == [], "an unproven address must never receive reminders"


def test_no_email_when_nothing_is_due(client, sent):
    created = client.post("/users", json={"group": "treatment"}).json()
    client.post("/auth/email/attach", json={
        "recovery_token": created["recovery_token"], "email": "idle@example.com",
    })
    token = sent[-1]["body"].partition("token=")[2].split()[0].strip()
    client.post("/auth/magic-link/verify", json={"token": token})
    log_session(client, created["id"])  # studied just now — nothing due yet
    sent.clear()

    assert client.post("/admin/send-reminders").json()["sent"] == 0
    assert sent == []


def test_a_second_run_does_not_email_again(client, sent):
    """A doubled cron trigger must not double the mail."""
    _verified_user_with_due_review(client, sent)

    first = client.post("/admin/send-reminders").json()
    second = client.post("/admin/send-reminders").json()

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped_recently_emailed"] == 1
    assert len(sent) == 1


def test_cooldown_expires(client, sent):
    uid, _ = _verified_user_with_due_review(client, sent)
    client.post("/admin/send-reminders")
    sent.clear()

    # Move the last-sent stamp beyond the cooldown.
    db = database.SessionLocal()
    try:
        user = db.query(database.User).filter_by(id=uid).first()
        user.last_reminder_sent_at = database.utcnow() - main._REMINDER_COOLDOWN * 2
        db.commit()
    finally:
        db.close()

    assert client.post("/admin/send-reminders").json()["sent"] == 1
    assert len(sent) == 1


def test_endpoint_requires_the_api_key(client, monkeypatch):
    monkeypatch.setenv("COGPRINT_API_KEY", "k")
    assert client.post("/admin/send-reminders").status_code == 401
    assert client.post(
        "/admin/send-reminders", headers={"X-API-Key": "k"}
    ).status_code == 200
