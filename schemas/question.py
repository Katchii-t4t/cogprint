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
    """One question/answer pair generated from study material."""

    question: str = Field(description="A clear recall question about one concept.")
    answer: str = Field(description="The correct, concise answer.")
    concept: str = Field(description="The concept this card tests (short phrase).")
    difficulty: str = Field(
        default="intermediate",
        description="One of: foundational, intermediate, advanced.",
    )


class GeneratedFlashcards(BaseModel):
    """The structured-output target the LLM fills (no DB ids — see service module)."""

    cards: List[Flashcard]


class QuestionSetResponse(BaseModel):
    """API response: cards for a material, plus how they were produced."""

    material_id: int
    title: str
    cards: List[Flashcard]
    generated_by: str  # "llm:<model>" or "cache"
