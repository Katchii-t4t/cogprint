"""
API-free cloze flashcard generation (§2.4). No key, no network — the generator
must always produce valid, source-grounded cards from the concept graph, and the
/questions endpoint must fall back to it instead of returning 503 when no LLM key
is configured.
"""

import os

from agents.question_generator_local import generate_flashcards, is_available
from schemas.question import GeneratedFlashcards
from tests.conftest import make_user  # noqa: F401  (ensures app import side effects)

SAMPLE = (
    "Photosynthesis converts light energy into chemical energy. "
    "The Calvin cycle fixes carbon dioxide into glucose. "
    "Chlorophyll absorbs light in the thylakoid membrane. "
    "ATP and NADPH power the light-independent reactions. "
    "Cellular respiration then releases the stored energy for the cell."
)


def test_generator_is_always_available():
    assert is_available() is True


def test_generates_valid_cards_without_a_key():
    out = generate_flashcards("Photosynthesis", SAMPLE, n=6, seed=1)
    assert isinstance(out, GeneratedFlashcards)
    assert len(out.cards) > 0
    for c in out.cards:
        assert c.question.strip()
        assert c.answer.strip()
        assert c.concept.strip()
        assert c.difficulty in {"foundational", "intermediate", "advanced"}


def test_cloze_hides_the_answer_and_blanks_it():
    out = generate_flashcards("Photosynthesis", SAMPLE, n=8, seed=2)
    cloze = [c for c in out.cards if "______" in c.question]
    assert cloze, "expected at least one cloze-style card from prose"
    for c in cloze:
        # The answer term must not be readable in its own cloze prompt.
        assert c.answer.lower() not in c.question.lower()


def test_distractors_never_include_the_answer():
    out = generate_flashcards("Photosynthesis", SAMPLE, n=8, seed=3)
    for c in out.cards:
        lowered = {d.lower() for d in c.distractors}
        assert c.answer.lower() not in lowered
        assert len(c.distractors) == len(set(lowered))  # no dupes


def test_respects_n_and_is_deterministic_with_seed():
    a = generate_flashcards("Photosynthesis", SAMPLE, n=3, seed=42)
    b = generate_flashcards("Photosynthesis", SAMPLE, n=3, seed=42)
    assert len(a.cards) <= 3
    assert [c.question for c in a.cards] == [c.question for c in b.cards]


def test_empty_material_yields_no_cards():
    out = generate_flashcards("Empty", "", n=5)
    assert out.cards == []


def test_endpoint_falls_back_to_cloze_without_key(client):
    """With no ANTHROPIC_API_KEY, /questions must serve local cloze cards, not 503."""
    assert "ANTHROPIC_API_KEY" not in os.environ  # conftest strips it
    uid = make_user(client)
    mat = client.post("/materials/analyze", json={"title": "Photosynthesis", "raw_text": SAMPLE})
    assert mat.status_code in (200, 201), mat.text
    mid = mat.json()["material_id"]

    r = client.post(f"/materials/{mid}/questions?n=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated_by"] == "local:cloze"
    assert len(body["cards"]) > 0
