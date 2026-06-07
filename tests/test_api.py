"""Smoke + behaviour tests for the CogPrint API surface."""

from tests.conftest import (
    add_retention,
    backdate_session,
    log_session,
    make_user,
)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_user(client):
    uid = make_user(client, group="treatment", pre_test_score=0.4)
    r = client.get(f"/users/{uid}")
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == "treatment"
    assert body["pre_test_score"] == 0.4


def test_get_missing_user_404(client):
    assert client.get("/users/99999").status_code == 404


def test_post_test_update(client):
    uid = make_user(client)
    r = client.patch(f"/users/{uid}/post-test", json={"post_test_score": 0.9})
    assert r.status_code == 200
    assert r.json()["post_test_score"] == 0.9


def test_session_validation_rejects_bad_quiz_score(client):
    uid = make_user(client)
    r = client.post("/sessions", json={
        "user_id": uid, "technique": "active_recall", "duration_minutes": 30,
        "time_of_day": "morning", "quiz_score": 1.5,  # out of [0,1]
    })
    assert r.status_code == 422


def test_log_session_and_list(client):
    uid = make_user(client)
    sid = log_session(client, uid, quiz_score=0.8)
    r = client.get(f"/users/{uid}/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == sid


def test_fingerprint_built_after_sessions(client):
    """The background rebuild should have produced a fingerprint by return time."""
    uid = make_user(client, group="treatment")
    for i in range(6):
        log_session(client, uid, technique="active_recall", quiz_score=0.7 + i * 0.02)
    r = client.get(f"/users/{uid}/fingerprint")
    assert r.status_code == 200
    fp = r.json()["fingerprint"]
    assert fp["session_count"] == 6
    assert fp["confidence"] in ("low", "medium", "high")


def test_retention_check_flow(client):
    uid = make_user(client, group="treatment")
    sid = log_session(client, uid, quiz_score=0.8)

    # Nothing due immediately.
    assert client.get(f"/users/{uid}/pending-checks").json() == []

    # Backdate 8 days so both 24h and 7d checks are due.
    backdate_session(sid, days=8)
    pending = client.get(f"/users/{uid}/pending-checks").json()
    due_types = sorted(p["check_type"] for p in pending)
    assert due_types == ["24h", "7d"]

    # Log the 24h check.
    assert add_retention(client, sid, uid, "24h", 0.7).status_code == 201
    # Duplicate is rejected.
    assert add_retention(client, sid, uid, "24h", 0.6).status_code == 409
    # 7d still pending.
    pending = client.get(f"/users/{uid}/pending-checks").json()
    assert [p["check_type"] for p in pending] == ["7d"]


def test_invalid_check_type_rejected(client):
    uid = make_user(client)
    sid = log_session(client, uid)
    r = add_retention(client, sid, uid, "day5", 0.5)
    assert r.status_code == 422


def test_export_csv(client):
    uid = make_user(client, group="treatment")
    log_session(client, uid, quiz_score=0.75)
    r = client.get("/export/study-data")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    text = r.text
    assert "user_id,group,session_id" in text.splitlines()[0]
    assert "active_recall" in text


def test_export_group_filter_validation(client):
    r = client.get("/export/study-data", params={"group": "banana"})
    assert r.status_code == 400


def test_material_analyze_and_study_plan(client):
    """Exercise Agent 1 (material analyzer) and Agent 3 (study planner)."""
    uid = make_user(client, group="treatment")
    text = (
        "The mitochondria is the powerhouse of the cell. It produces ATP through "
        "cellular respiration. Cellular respiration has three stages: glycolysis, "
        "the Krebs cycle, and the electron transport chain. Glycolysis happens in "
        "the cytoplasm. The Krebs cycle occurs in the mitochondrial matrix. The "
        "electron transport chain generates the majority of ATP molecules."
    )
    r = client.post("/materials/analyze", json={"title": "Cell Biology", "raw_text": text})
    assert r.status_code == 201, r.text
    material_id = r.json()["material_id"]
    assert r.json()["knowledge_map"]["concepts"]

    r = client.post(f"/users/{uid}/study-plan",
                    params={"material_id": material_id, "total_days": 7})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["total_days"] == 7
    assert isinstance(plan["days"], list) and len(plan["days"]) >= 1
    assert plan["general_advice"]
