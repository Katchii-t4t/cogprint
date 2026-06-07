"""
Pydantic models for LLM-generated flashcards (Screen 3 — the study/recall loop).

These are the ONLY place the question/flashcard shape is defined. The LLM call
that fills them lives behind a single service module (agents/question_generator.py)
so it can be swapped for a cheaper/local method later without touching the API
or the frontend.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Flashcard(BaseModel):
    """One question/answer pair generated from study material.

    This is the LLM's structured-output target — keep it minimal so the model
    only fills meaningful content. Bookkeeping (id, flagged) is added when the
    card is served (see FlashcardOut) and stored (see StoredQuestions).
    """

    question: str = Field(description="A clear recall question about one concept.")
    answer: str = Field(description="The correct, concise answer.")
    concept: str = Field(description="The concept this card tests (short phrase).")
    difficulty: str = Field(
        default="intermediate",
        description="One of: foundational, intermediate, advanced.",
    )


class GeneratedFlashcards(BaseModel):
    """The structured-output target the LLM fills (no ids/flags — added on serve)."""

    cards: List[Flashcard]


class StoredQuestions(BaseModel):
    """What gets cached on the material (questions_json).

    `cards` order is fixed at generation time, so a card's index is its stable
    id. `flagged` holds the ids of cards a learner marked bad/confusing; those
    are excluded from study rounds and from modelling.
    """

    cards: List[Flashcard]
    flagged: List[int] = Field(default_factory=list)


class FlashcardOut(Flashcard):
    """A flashcard as returned to the client: adds a stable id and flag state."""

    id: int
    flagged: bool = False


class QuestionSetResponse(BaseModel):
    """API response: cards for a material, plus how they were produced."""

    material_id: int
    title: str
    cards: List[FlashcardOut]
    generated_by: str  # "llm:<model>" or "cache"


class FlagQuestionRequest(BaseModel):
    """Mark a card as bad/confusing so it's excluded from study + modelling."""

    card_id: int = Field(ge=0, description="Stable id (index) of the card to flag.")
