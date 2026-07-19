"""
Observable fingerprint rebuild (§4.2): the background rebuild must record its
outcome so a silently-stale fingerprint is detectable, and a failed rebuild must
NOT fail the data-logging request that triggered it.

Note: Starlette's TestClient runs BackgroundTasks to completion before the
request returns (see conftest), so the rebuild has already run by the time a
session-log POST returns.
"""

import main
from tests.conftest import make_user, log_session


def test_successful_rebuild_records_ok(client):
    uid = make_user(client)
    log_session(client, uid, technique="active_recall", quiz_score=0.8)

    fp = client.get(f"/users/{uid}/fingerprint").json()
    assert fp["rebuild_status"] == "ok"
    assert fp["rebuild_at"] is not None


def test_manual_rebuild_reports_ok(client):
    uid = make_user(client)
    log_session(client, uid)
    r = client.post(f"/users/{uid}/fingerprint/rebuild")
    assert r.status_code == 200, r.text
    assert r.json()["rebuild_status"] == "ok"


def test_failed_background_rebuild_is_recorded_not_swallowed(client, monkeypatch):
    """A rebuild that raises must (a) not fail the session-log request, and
    (b) leave rebuild_status='failed' on the fingerprint so it's observable."""
    uid = make_user(client)

    def boom(db, user_id):
        raise RuntimeError("simulated MCMC blowup")

    monkeypatch.setattr(main, "rebuild_fingerprint", boom)

    # The session log itself must still succeed (background failure is isolated).
    log_session(client, uid, technique="active_recall", quiz_score=0.7)

    fp = client.get(f"/users/{uid}/fingerprint").json()
    assert fp["rebuild_status"] == "failed"
    assert fp["rebuild_at"] is not None


def test_manual_rebuild_failure_returns_500_and_records(client, monkeypatch):
    uid = make_user(client)

    def boom(db, user_id):
        raise RuntimeError("simulated blowup")

    monkeypatch.setattr(main, "rebuild_fingerprint", boom)
    r = client.post(f"/users/{uid}/fingerprint/rebuild")
    assert r.status_code == 500

    # Status is still stamped even though the endpoint reported failure.
    monkeypatch.undo()  # let the GET's own logic run normally
    fp = client.get(f"/users/{uid}/fingerprint").json()
    assert fp["rebuild_status"] == "failed"
