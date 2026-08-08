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


def test_limits_do_not_depend_on_being_authenticated(client):
    """The analyse endpoint is open by design, so its limits are the only
    thing standing between an anonymous caller and the CPU."""
    r = client.post("/materials/analyze", json={
        "title": "Huge", "raw_text": "a" * (MAX_MATERIAL_CHARS + 1),
    }, headers=auth(make_user(client)))
    assert r.status_code == 422
