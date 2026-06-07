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
