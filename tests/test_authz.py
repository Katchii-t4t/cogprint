"""
Per-user authorization: the enumeration attack, performed and asserted to fail.

Ids are sequential. Before this suite existed, eleven routes addressed by
`user_id` served or mutated data for any id a caller cared to type. Verified
against a running instance at the time: `GET /users/{id}/materials` returned
the titles of what an identifiable person was studying, `PATCH post-test`
overwrote the study's outcome variable, and `POST /sessions` injected sessions
into a stranger's fingerprint.

Written the way `test_recovery.py` is written — the attack itself is the test,
so a regression fails here rather than in production. Every route is checked
three ways:

  anonymous            -> 401, because no credential was presented
  another user's token -> 404, NOT 403
  the owner's token    -> succeeds

The 404 is deliberate. A 403 would confirm that the id exists and belongs to
someone else, which leaves the endpoint an enumeration oracle even while it
refuses to serve the data. An unknown id and a stranger's id must be
indistinguishable.
"""

import pytest

from tests.conftest import auth, log_session, make_user

TEXT = (
    "Photosynthesis converts light energy into chemical energy. Chlorophyll in "
    "the thylakoid membrane absorbs photons. The Calvin cycle fixes carbon "
    "dioxide into glucose. Rubisco catalyses carbon fixation."
)


@pytest.fixture()
def owner_and_stranger(client):
    """An owner with real history, and an unrelated account to attack from."""
    owner = make_user(client, group="treatment")
    stranger = make_user(client, group="treatment")
    material = client.post(
        "/materials/analyze",
        json={"title": "Oncology exam notes", "raw_text": TEXT},
    ).json()["material_id"]
    log_session(client, owner)
    return owner, stranger, material


def _routes(owner, material_id):
    """(method, path, json) for every route addressed by a user id."""
    return [
        ("GET", f"/users/{owner}/materials", None),
        ("GET", f"/users/{owner}/sessions", None),
        ("GET", f"/users/{owner}/fingerprint", None),
        ("GET", f"/users/{owner}/review-suggestions", None),
        ("GET", f"/users/{owner}/pending-checks", None),
        ("POST", f"/users/{owner}/fingerprint/rebuild", None),
        ("POST", f"/users/{owner}/share-code", None),
        ("POST", f"/users/{owner}/study-plan?material_id={material_id}", None),
        ("PATCH", f"/users/{owner}/post-test", {"post_test_score": 0.0}),
    ]


def test_no_user_route_answers_an_anonymous_caller(client, owner_and_stranger):
    owner, _, material_id = owner_and_stranger
    for method, path, payload in _routes(owner, material_id):
        r = client.request(method, path, json=payload)
        assert r.status_code == 401, f"{method} {path} served an anonymous caller"


def test_no_user_route_answers_a_different_users_token(client, owner_and_stranger):
    owner, stranger, material_id = owner_and_stranger
    for method, path, payload in _routes(owner, material_id):
        r = client.request(method, path, json=payload, headers=auth(stranger))
        assert r.status_code == 404, (
            f"{method} {path} answered a stranger with {r.status_code} "
            f"(404 required: 403 would confirm the account exists)"
        )


def test_the_owner_still_gets_their_own_data(client, owner_and_stranger):
    """The guard must not have been bought by breaking the product."""
    owner, _, material_id = owner_and_stranger
    for method, path, payload in _routes(owner, material_id):
        r = client.request(method, path, json=payload, headers=auth(owner))
        assert r.status_code == 200, f"{method} {path} broke for its owner: {r.text}"


def test_sessions_cannot_be_injected_into_another_account(client, owner_and_stranger):
    """The id is in the body here, so the path-based guard cannot see it.

    Left open, this let anyone poison a stranger's fingerprint — corrupting
    both the personalisation and the study's data, invisibly.
    """
    owner, stranger, material_id = owner_and_stranger
    payload = {
        "user_id": owner, "material_id": material_id, "technique": "re_reading",
        "duration_minutes": 5, "time_of_day": "morning", "quiz_score": 1.0,
    }

    assert client.post("/sessions", json=payload).status_code == 401
    assert client.post("/sessions", json=payload, headers=auth(stranger)).status_code == 404
    assert client.post("/sessions", json=payload, headers=auth(owner)).status_code == 201


def test_retention_checks_cannot_be_injected_into_another_account(client, owner_and_stranger):
    owner, stranger, _ = owner_and_stranger
    sid = log_session(client, owner)
    payload = {"session_id": sid, "user_id": owner, "check_type": "24h", "score": 1.0}

    assert client.post("/retention-checks", json=payload).status_code == 401
    assert client.post(
        "/retention-checks", json=payload, headers=auth(stranger)
    ).status_code == 404


def test_a_malformed_authorization_header_is_not_a_credential(client, owner_and_stranger):
    owner, _, _ = owner_and_stranger
    for header in (
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic abc"},
        {"Authorization": "bearer wrong-token"},
        {"Authorization": "Bearer " + "0" * 48},
    ):
        r = client.get(f"/users/{owner}/materials", headers=header)
        assert r.status_code == 401, f"{header} was accepted"


def test_a_rotated_token_stops_working(client):
    """Rotation is the account-compromise remedy; it has to actually revoke."""
    created = client.post("/users", json={"group": "treatment"}).json()
    uid, old = created["id"], created["recovery_token"]
    old_header = {"Authorization": f"Bearer {old}"}

    assert client.get(f"/users/{uid}/materials", headers=old_header).status_code == 200

    new = client.post(
        "/auth/recover/rotate", json={"recovery_token": old}
    ).json()["recovery_token"]

    assert client.get(f"/users/{uid}/materials", headers=old_header).status_code == 401
    assert client.get(
        f"/users/{uid}/materials", headers={"Authorization": f"Bearer {new}"}
    ).status_code == 200


def test_production_refuses_to_start_without_an_api_key(monkeypatch):
    """SEC-002. `require_api_key` is a no-op when no key is configured, which
    is right for local work and wrong for a deploy: one forgotten environment
    variable exposes the participant list, the CSV export, the analytics funnel
    and the reminder trigger, behind a green health check.

    An instance that refuses to boot is an obvious problem. One that boots and
    serves everyone's data is a quiet one that runs for months.
    """
    import auth as auth_module

    monkeypatch.setenv("COGPRINT_ENV", "prod")
    monkeypatch.delenv("COGPRINT_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="COGPRINT_API_KEY"):
        auth_module.assert_production_config()

    monkeypatch.setenv("COGPRINT_API_KEY", "a-long-random-value")
    auth_module.assert_production_config()  # must not raise


def test_health_reports_the_database_not_just_the_process(client):
    """OPS-008. The platform routes traffic on this. A check that only proves
    the process is alive sends users into an instance whose database is
    unreachable, which then fails per-user with no signal that the deploy is
    broken."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_development_keeps_the_zero_config_promise(monkeypatch):
    import auth as auth_module

    monkeypatch.delenv("COGPRINT_ENV", raising=False)
    monkeypatch.delenv("COGPRINT_API_KEY", raising=False)
    auth_module.assert_production_config()  # must not raise


def test_the_token_never_appears_in_a_url(client, owner_and_stranger):
    """A credential in a query string lands in access logs, browser history and
    Referer headers. It belongs in a header, and only in a header."""
    owner, _, _ = owner_and_stranger
    from tests.conftest import token_for

    token = token_for(owner)
    r = client.get(f"/users/{owner}/materials?token={token}")
    assert r.status_code == 401, "a token in the query string was accepted"
