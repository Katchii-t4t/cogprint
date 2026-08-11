"""
Input size limits (SEC-004).

`POST /materials/analyze` is deliberately unauthenticated — you can try the
product before you have an account — and it feeds its payload straight into a
pipeline whose cost grows superlinearly in sentence count, then stores the text
indefinitely. Unbounded, that is a CPU sink and an unbounded storage bill
reachable by anyone with curl.

These tests pin both directions: the abusive payload is refused, and a
realistically long chapter still works. A limit that quietly breaks real use is
its own kind of outage.
"""

from schemas.session import (
    MAX_IMAGE_BASE64_CHARS,
    MAX_MATERIAL_CHARS,
    MAX_TITLE_CHARS,
)
from tests.conftest import auth, make_user

SENTENCE = "Chlorophyll in the thylakoid membrane absorbs photons of light. "


def test_material_over_the_limit_is_refused(client):
    r = client.post("/materials/analyze", json={
        "title": "Huge", "raw_text": "a" * (MAX_MATERIAL_CHARS + 1),
    })
    assert r.status_code == 422


def test_a_realistically_long_chapter_still_works(client):
    """~40k characters — a long chapter. The limit must not break real use."""
    text = SENTENCE * 640
    assert len(text) < MAX_MATERIAL_CHARS
    r = client.post("/materials/analyze", json={"title": "Long chapter", "raw_text": text})
    assert r.status_code == 201, r.text
    assert r.json()["knowledge_map"]["concepts"]


def test_empty_material_is_refused(client):
    """An empty paste produces an empty knowledge map and a useless plan; it is
    a mistake, not a request."""
    assert client.post(
        "/materials/analyze", json={"title": "x", "raw_text": ""}
    ).status_code == 422
    assert client.post(
        "/materials/analyze", json={"title": "", "raw_text": SENTENCE}
    ).status_code == 422


def test_oversized_title_is_refused(client):
    r = client.post("/materials/analyze", json={
        "title": "t" * (MAX_TITLE_CHARS + 1), "raw_text": SENTENCE * 5,
    })
    assert r.status_code == 422


def test_oversized_image_is_refused(client):
    """Vision OCR is billed per image, so the cap is a spend control first."""
    r = client.post("/materials/ocr", json={
        "image_base64": "A" * (MAX_IMAGE_BASE64_CHARS + 1), "media_type": "image/jpeg",
    })
    assert r.status_code == 422


def test_oversized_event_properties_are_refused(client):
    uid = make_user(client)
    r = client.post("/events", json={
        "event_name": "spam", "user_id": uid, "properties": {"blob": "x" * 5000},
    })
    assert r.status_code == 422


def test_ordinary_event_properties_still_work(client):
    uid = make_user(client)
    r = client.post("/events", json={
        "event_name": "round_completed",
        "user_id": uid,
        "properties": {"technique": "active_recall", "cards": 8, "score_bucket": "high"},
    })
    assert r.status_code == 202


# ── query parameters, found by probing a running instance ─────────────────────

def _material(client):
    return client.post("/materials/analyze", json={
        "title": "Cells",
        "raw_text": (
            "Mitochondria produce ATP through cellular respiration. Glycolysis "
            "splits glucose in the cytoplasm. The Krebs cycle runs in the matrix. "
            "The electron transport chain builds a proton gradient."
        ),
    }).json()["material_id"]


def test_the_plan_horizon_is_bounded(client):
    """?total_days=100000 generated a hundred thousand plan days: a 45 MB
    response after 8.8 seconds of CPU, from a single request. A handful in
    parallel takes the service down."""
    uid = make_user(client)
    mid = _material(client)
    r = client.post(
        f"/users/{uid}/study-plan?material_id={mid}&total_days=100000", headers=auth(uid)
    )
    assert r.status_code == 422


def test_a_zero_or_negative_horizon_is_refused(client):
    """Both returned 200 with an empty plan, under a heading promising days."""
    uid = make_user(client)
    mid = _material(client)
    for days in (0, -5):
        r = client.post(
            f"/users/{uid}/study-plan?material_id={mid}&total_days={days}",
            headers=auth(uid),
        )
        assert r.status_code == 422, days


def test_a_realistic_horizon_still_works(client):
    uid = make_user(client)
    mid = _material(client)
    r = client.post(
        f"/users/{uid}/study-plan?material_id={mid}&total_days=90", headers=auth(uid)
    )
    assert r.status_code == 200
    assert len(r.json()["days"]) == 90


def test_the_card_count_is_bounded(client):
    """With an API key configured, n is how many cards an LLM is asked to
    write — so this is a spend control as well as a size one."""
    mid = _material(client)
    assert client.post(f"/materials/{mid}/questions?n=100000").status_code == 422
    assert client.post(f"/materials/{mid}/questions?n=0").status_code == 422
    assert client.post(f"/materials/{mid}/questions?n=-1").status_code == 422
    assert client.post(f"/materials/{mid}/questions?n=8").status_code == 200


# ── material that contains nothing to study ───────────────────────────────────

def test_text_with_no_extractable_concepts_is_refused(client):
    """Each of these returned 201 with an empty knowledge map, landing the user
    on a blank screen with no explanation and nothing to do — on the front door
    of the product."""
    for label, text in (
        ("whitespace", "   \n\t  "),
        ("single char", "a"),
        ("punctuation", "... !!! ??? ---"),
        ("emoji", "🧠🧬🔬 " * 20),
    ):
        r = client.post("/materials/analyze", json={"title": "t", "raw_text": text})
        assert r.status_code == 422, f"{label} was accepted: {r.text}"
        assert "study" in r.json()["detail"].lower()


def test_a_refused_paste_leaves_no_row_behind(client):
    """Analysis happens before the write now, so an unusable paste cannot fill
    the table with rows nothing will ever read."""
    import database

    before = database.SessionLocal().query(database.Material).count()
    client.post("/materials/analyze", json={"title": "t", "raw_text": "   "})
    after = database.SessionLocal().query(database.Material).count()
    assert after == before


def test_limits_do_not_depend_on_being_authenticated(client):
    """The analyse endpoint is open by design, so its limits are the only
    thing standing between an anonymous caller and the CPU."""
    r = client.post("/materials/analyze", json={
        "title": "Huge", "raw_text": "a" * (MAX_MATERIAL_CHARS + 1),
    }, headers=auth(make_user(client)))
    assert r.status_code == 422
