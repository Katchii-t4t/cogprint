"""
First-party analytics (§2.1).

The funnel endpoint is the instrument the beta exists to read, so the D1/D7
arithmetic is pinned against a hand-built timeline rather than trusted. The
other tests hold the two properties that make tracking safe to call anywhere:
it never raises, and it never blocks a real request from succeeding.
"""

from datetime import timedelta

import pytest

import analytics
import database
from tests.conftest import make_user


def _seed_event(user_id, event_name, when):
    """Insert an event at a chosen time — the funnel is time-relative, so tests
    need to place events rather than only create them 'now'."""
    db = database.SessionLocal()
    try:
        db.add(database.AnalyticsEvent(
            user_id=user_id, event_name=event_name, created_at=when,
        ))
        db.commit()
    finally:
        db.close()


def _count(event_name):
    db = database.SessionLocal()
    try:
        return db.query(database.AnalyticsEvent).filter_by(event_name=event_name).count()
    finally:
        db.close()


# ── the tracking helper ───────────────────────────────────────────────────────

def test_track_event_records(client):
    uid = make_user(client)
    db = database.SessionLocal()
    try:
        analytics.track_event(db, uid, "unit_test_event", {"a": 1})
    finally:
        db.close()
    assert _count("unit_test_event") == 1


def test_track_event_never_raises_on_bad_input(client):
    """Telemetry must not be able to break a caller, whatever it is handed."""
    db = database.SessionLocal()
    try:
        # Unserialisable properties would blow up json.dumps if unguarded.
        analytics.track_event(db, None, "bad_props", {"obj": object()})
    finally:
        db.close()
    # No exception is the assertion; the event simply doesn't land.


def test_oversized_properties_are_truncated(client):
    uid = make_user(client)
    db = database.SessionLocal()
    try:
        analytics.track_event(db, uid, "big", {"blob": "x" * 50_000})
    finally:
        db.close()

    db = database.SessionLocal()
    try:
        row = db.query(database.AnalyticsEvent).filter_by(event_name="big").first()
        assert len(row.properties_json) <= analytics.MAX_PROPERTIES_CHARS
    finally:
        db.close()


# ── server-side instrumentation ───────────────────────────────────────────────

def test_core_actions_are_instrumented(client):
    uid = make_user(client)
    assert _count("user_created") >= 1

    client.post("/materials/analyze", json={
        "title": "T", "raw_text": "Photosynthesis converts light into chemical energy.",
    })
    assert _count("material_pasted") >= 1

    client.post("/sessions", json={
        "user_id": uid, "technique": "active_recall", "duration_minutes": 20,
        "time_of_day": "morning", "quiz_score": 0.8,
    })
    assert _count("session_logged") >= 1


# ── the client endpoint ───────────────────────────────────────────────────────

def test_client_events_are_accepted_without_auth(client):
    r = client.post("/events", json={"event_name": "plan_viewed", "properties": {"x": 1}})
    assert r.status_code == 202, r.text
    assert _count("plan_viewed") == 1


def test_client_event_accepts_anonymous_users(client):
    """The pre-account part of the funnel is the most important to see."""
    r = client.post("/events", json={"event_name": "anon_view"})
    assert r.status_code == 202
    db = database.SessionLocal()
    try:
        assert db.query(database.AnalyticsEvent).filter_by(event_name="anon_view").first().user_id is None
    finally:
        db.close()


# ── the funnel view ───────────────────────────────────────────────────────────

def test_funnel_requires_the_api_key(client, monkeypatch):
    monkeypatch.setenv("COGPRINT_API_KEY", "k")
    assert client.get("/analytics/funnel").status_code == 401
    assert client.get("/analytics/funnel", headers={"X-API-Key": "k"}).status_code == 200


def test_funnel_counts_events(client):
    client.post("/events", json={"event_name": "a"})
    client.post("/events", json={"event_name": "a"})
    client.post("/events", json={"event_name": "b"})

    data = client.get("/analytics/funnel").json()
    assert data["event_counts"]["a"] == 2
    assert data["event_counts"]["b"] == 1


def test_d1_and_d7_return_rates(client):
    """Two users, one returning on both days and one never — so the expected
    rates are exactly 0.5, which a broken window calculation won't produce."""
    returner = make_user(client)
    quitter = make_user(client)

    start = database.utcnow() - timedelta(days=10)
    for uid in (returner, quitter):
        _seed_event(uid, "session_logged", start)

    # Inside the D1 and D7 windows respectively.
    _seed_event(returner, "session_logged", start + timedelta(days=1, hours=3))
    _seed_event(returner, "session_logged", start + timedelta(days=7, hours=2))

    data = client.get("/analytics/funnel").json()
    assert data["d1"]["eligible"] == 2
    assert data["d7"]["eligible"] == 2
    assert data["d1"]["return_rate"] == 0.5
    assert data["d7"]["return_rate"] == 0.5


def test_users_whose_window_has_not_elapsed_are_excluded(client):
    """A cohort that signed up yesterday must not drag D7 toward zero by
    construction — they simply haven't had the chance to return yet."""
    uid = make_user(client)
    _seed_event(uid, "session_logged", database.utcnow() - timedelta(hours=2))

    data = client.get("/analytics/funnel").json()
    assert data["d7"]["eligible"] == 0
    assert data["d7"]["return_rate"] is None
