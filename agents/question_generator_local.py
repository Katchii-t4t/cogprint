"""
API-free flashcard generation (§2.4) — cloze-deletion cards from the concept graph.

This is the zero-LLM, $0-runtime, offline drop-in for agents/question_generator.py.
It fills the exact same `GeneratedFlashcards` schema, so the API endpoint and the
frontend never know which generator produced the cards.

How it works
------------
1. Reuse the pure-NumPy MaterialAnalyzer (TF-IDF → LSA → TextRank) to extract the
   material's key concepts, each already typed (factual|conceptual|procedural) and
   difficulty-graded. No API call.
2. For each important concept, find a sentence in the source that contains it and
   blank the concept out → a cloze question ("______ fixes carbon dioxide.").
   Cloze deletion is Anki's most popular, research-backed format (Roediger &
   Karpicke retrieval practice), not a downgrade.
3. Distractors = other concepts of the SAME cognitive type (so they're plausible),
   falling back to any other concept. A card with <3 distractors still renders as a
   flashcard (the schema allows an empty distractor list).

Every card is grounded in a real source sentence, which also satisfies the
"ground each card in the source" quality rule (§3.4) for free.
"""

from __future__ import annotations

import random
import re

from agents.material_analyzer import MaterialAnalyzer, _sentences
from schemas.question import Flashcard, GeneratedFlashcards
from schemas.session import KnowledgeConcept

_BLANK = "______"
_MIN_CLOZE_WORDS = 5     # skip too-short sentences — a blank there tests nothing
_MAX_CLOZE_WORDS = 40    # skip sprawling sentences — too much to read as a prompt


def is_available() -> bool:
    """Always true — no key, no network, no dependency beyond NumPy."""
    return True


def _term_pattern(term: str) -> re.Pattern:
    """Case-insensitive, whole-phrase matcher for a concept term."""
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


def _pick_sentence(term: str, sentences: list[str]) -> str | None:
    """The shortest reasonable sentence containing the term (shorter = tighter cloze)."""
    pat = _term_pattern(term)
    candidates = [
        s for s in sentences
        if pat.search(s) and _MIN_CLOZE_WORDS <= len(s.split()) <= _MAX_CLOZE_WORDS
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda s: len(s.split()))


def _make_cloze(sentence: str, term: str) -> str:
    """Blank every occurrence of the term; collapse the result to one clean line."""
    blanked = _term_pattern(term).sub(_BLANK, sentence)
    return " ".join(blanked.split())


def _distractors(
    answer: KnowledgeConcept,
    by_type: dict[str, list[str]],
    all_terms: list[str],
    k: int = 3,
) -> list[str]:
    """Up to k plausible wrong answers: same cognitive type first, then any other."""
    same = [t for t in by_type.get(answer.concept_type, []) if t.lower() != answer.concept.lower()]
    random.shuffle(same)
    picks = same[:k]
    if len(picks) < k:
        others = [
            t for t in all_terms
            if t.lower() != answer.concept.lower() and t not in picks
        ]
        random.shuffle(others)
        picks.extend(others[: k - len(picks)])
    return picks[:k]


def generate_flashcards(
    title: str,
    raw_text: str,
    n: int = 8,
    seed: int | None = None,
) -> GeneratedFlashcards:
    """Generate up to `n` cloze flashcards locally. Never raises for a missing key.

    Falls back gracefully: if the material yields no usable cloze sentence for a
    concept, that concept is turned into a relation prompt instead so the round is
    never empty. Signature mirrors question_generator.generate_flashcards.
    """
    if seed is not None:
        random.seed(seed)

    if not raw_text.strip():
        return GeneratedFlashcards(cards=[])

    km = MaterialAnalyzer().analyze(title, raw_text)
    concepts = km.concepts
    if not concepts:
        return GeneratedFlashcards(cards=[])

    sentences = _sentences(raw_text)
    by_type: dict[str, list[str]] = {}
    for c in concepts:
        by_type.setdefault(c.concept_type, []).append(c.concept)
    all_terms = [c.concept for c in concepts]

    n = max(1, min(int(n), 30))
    cards: list[Flashcard] = []

    for c in concepts:
        if len(cards) >= n:
            break
        sentence = _pick_sentence(c.concept, sentences)
        if sentence:
            question = _make_cloze(sentence, c.concept)
        elif c.related_concepts:
            # No clean cloze — make a relation prompt so the concept still gets a card.
            question = f"Which key concept connects to: {', '.join(c.related_concepts[:2])}?"
        else:
            question = f"Recall the key term defined in '{title}' for this idea."

        cards.append(Flashcard(
            question=question,
            answer=c.concept,
            concept=c.concept,
            difficulty=c.difficulty,
            distractors=_distractors(c, by_type, all_terms),
        ))

    return GeneratedFlashcards(cards=cards)
