"""Tests for the LLM-backed flashcard endpoint (mocked — no real API calls)."""

import agents.question_generator as qg
from schemas.question import Flashcard, GeneratedFlashcards

MATERIAL_TEXT = (
    "Photosynthesis converts light energy into chemical energy. It occurs in "
    "the chloroplasts. The light reactions produce ATP and NADPH. The Calvin "
    "cycle fixes carbon dioxide into glucose using ATP and NADPH."
)


def _make_material(client):
    r = client.post("/materials/analyze", json={"title": "Photosynthesis", "raw_text": MATERIAL_TEXT})
    assert r.status_code == 201, r.text
    return r.json()["material_id"]


def test_questions_unavailable_without_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mid = _make_material(client)
    r = client.post(f"/materials/{mid}/questions")
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_questions_happy_path_and_cache(client, monkeypatch):
    canned = GeneratedFlashcards(cards=[
        Flashcard(question="Where does photosynthesis occur?", answer="In the chloroplasts.",
                  concept="location", difficulty="foundational"),
        Flashcard(question="What do the light reactions produce?", answer="ATP and NADPH.",
                  concept="light reactions", difficulty="intermediate"),
    ])

    calls = {"n": 0}

    def fake_generate(title, raw_text, n=8, model=None):
        calls["n"] += 1
        return canned

    monkeypatch.setattr(qg, "generate_flashcards", fake_generate)

    mid = _make_material(client)

    # First call generates via the (mocked) LLM.
    r1 = client.post(f"/materials/{mid}/questions")
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert len(body["cards"]) == 2
    assert body["generated_by"].startswith("llm:")
    assert calls["n"] == 1

    # Second call serves from cache — no regeneration.
    r2 = client.post(f"/materials/{mid}/questions")
    assert r2.status_code == 200
    assert r2.json()["generated_by"] == "cache"
    assert calls["n"] == 1

    # refresh=true forces regeneration.
    r3 = client.post(f"/materials/{mid}/questions", params={"refresh": "true"})
    assert r3.status_code == 200
    assert r3.json()["generated_by"].startswith("llm:")
    assert calls["n"] == 2


def test_is_available_reflects_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert qg.is_available() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # is_available also needs the SDK importable; anthropic is in requirements.
    assert qg.is_available() is True


def _mock_three_cards(monkeypatch):
    canned = GeneratedFlashcards(cards=[
        Flashcard(question="Q0", answer="A0", concept="c0"),
        Flashcard(question="Q1", answer="A1", concept="c1"),
        Flashcard(question="Q2", answer="A2", concept="c2"),
    ])
    monkeypatch.setattr(qg, "generate_flashcards", lambda *a, **k: canned)


def test_flag_excludes_card_and_keeps_stable_ids(client, monkeypatch):
    _mock_three_cards(monkeypatch)
    mid = _make_material(client)

    cards = client.post(f"/materials/{mid}/questions").json()["cards"]
    assert [c["id"] for c in cards] == [0, 1, 2]
    assert all(c["flagged"] is False for c in cards)

    # Flag the middle card.
    r = client.post(f"/materials/{mid}/questions/flag", json={"card_id": 1})
    assert r.status_code == 200
    assert r.json()["flagged_count"] == 1

    # Default study set now excludes the flagged card; ids stay stable (0 and 2).
    cards = client.post(f"/materials/{mid}/questions").json()["cards"]
    assert [c["id"] for c in cards] == [0, 2]

    # include_flagged=true shows all three with the flag marked.
    allc = client.post(f"/materials/{mid}/questions", params={"include_flagged": "true"}).json()["cards"]
    assert [c["id"] for c in allc] == [0, 1, 2]
    assert [c["flagged"] for c in allc] == [False, True, False]


def test_flag_is_idempotent_and_validates(client, monkeypatch):
    _mock_three_cards(monkeypatch)
    mid = _make_material(client)
    client.post(f"/materials/{mid}/questions")

    assert client.post(f"/materials/{mid}/questions/flag", json={"card_id": 0}).json()["flagged_count"] == 1
    # Flagging the same card again is a no-op.
    assert client.post(f"/materials/{mid}/questions/flag", json={"card_id": 0}).json()["flagged_count"] == 1
    # Out-of-range card_id -> 404.
    assert client.post(f"/materials/{mid}/questions/flag", json={"card_id": 99}).status_code == 404
    # Negative card_id rejected by the schema -> 422.
    assert client.post(f"/materials/{mid}/questions/flag", json={"card_id": -1}).status_code == 422


def test_distractors_roundtrip_cache_and_flag(client, monkeypatch):
    """Quiz mode: distractors survive generation -> cache -> flag exclusion."""
    canned = GeneratedFlashcards(cards=[
        Flashcard(question="Q0", answer="A0", concept="c0",
                  distractors=["W1", "W2", "W3"]),
        Flashcard(question="Q1", answer="A1", concept="c1",
                  distractors=["X1", "X2", "X3"]),
    ])
    monkeypatch.setattr(qg, "generate_flashcards", lambda *a, **k: canned)
    mid = _make_material(client)

    r1 = client.post(f"/materials/{mid}/questions").json()
    assert [c["distractors"] for c in r1["cards"]] == [["W1", "W2", "W3"], ["X1", "X2", "X3"]]

    # Cache round-trip preserves distractors.
    r2 = client.post(f"/materials/{mid}/questions").json()
    assert r2["generated_by"] == "cache"
    assert r2["cards"][0]["distractors"] == ["W1", "W2", "W3"]

    # Flag exclusion still works with distractors present.
    client.post(f"/materials/{mid}/questions/flag", json={"card_id": 0})
    r3 = client.post(f"/materials/{mid}/questions").json()
    assert [c["id"] for c in r3["cards"]] == [1]
    assert r3["cards"][0]["distractors"] == ["X1", "X2", "X3"]


def test_old_cache_without_distractors_still_parses(client, monkeypatch):
    """A questions_json blob written before the distractors field existed must
    parse cleanly (default []) rather than 500 — quiz mode falls back per-card."""
    import database

    _mock_three_cards(monkeypatch)
    mid = _make_material(client)
    client.post(f"/materials/{mid}/questions")

    # Overwrite the cache with the pre-distractors shape.
    db = database.SessionLocal()
    try:
        mat = db.get(database.Material, mid)
        mat.questions_json = (
            '{"cards": [{"question": "Old Q", "answer": "Old A", '
            '"concept": "old", "difficulty": "intermediate"}], "flagged": []}'
        )
        db.commit()
    finally:
        db.close()

    r = client.post(f"/materials/{mid}/questions")
    assert r.status_code == 200
    body = r.json()
    assert body["generated_by"] == "cache"
    assert body["cards"][0]["question"] == "Old Q"
    assert body["cards"][0]["distractors"] == []  # defaulted, not crashed
