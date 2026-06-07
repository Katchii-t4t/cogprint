"""
Agent 4 — Question Generator (the ONLY LLM call in CogPrint).

Everything else in this backend is API-free classical ML. Generating good
flashcard questions from arbitrary study text is the one task that genuinely
benefits from an LLM, so it is isolated here behind a single function. Swap this
module's body for a local model or a template engine later and nothing upstream
(the API, the frontend, Screen 3) has to change.

Design:
  * Reads the API key from the ANTHROPIC_API_KEY environment variable via the
    SDK's default client — the key never appears in code, args, or logs.
  * Model is configurable via COGPRINT_QGEN_MODEL (default: claude-opus-4-8) so
    the cost/quality trade-off is a config change, not a code change.
  * If the SDK isn't installed or no key is configured, raises
    QuestionGenUnavailable so the API can return a clean "needs setup" response
    and the UI can degrade gracefully instead of crashing.
  * Uses structured outputs (messages.parse + a Pydantic schema) so the result
    is always valid, parsed flashcards — no brittle JSON scraping.

Scientific-integrity note: questions must be answerable from the provided text
and test *recall of the material*. This is not "learning styles" — it produces
the retrieval items the study/recall loop measures.
"""

from __future__ import annotations

import os

from schemas.question import GeneratedFlashcards

DEFAULT_MODEL = "claude-opus-4-8"
MAX_INPUT_CHARS = 24_000  # ~6k tokens of source text; keeps cost bounded


class QuestionGenUnavailable(RuntimeError):
    """Raised when question generation can't run (no SDK or no API key)."""


def is_available() -> bool:
    """True if question generation can run right now (SDK present + key set)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _system_prompt() -> str:
    return (
        "You are CogPrint's question generator. From the study material you are "
        "given, write clear retrieval-practice flashcards that test recall and "
        "understanding of the material itself.\n"
        "Rules:\n"
        "- Every question must be answerable from the provided text alone.\n"
        "- One concept per card. Prefer 'why/how/what' over trivia.\n"
        "- Keep answers concise and factual.\n"
        "- Set difficulty to foundational, intermediate, or advanced.\n"
        "- Do NOT reference 'learning styles' or the learner's traits; cards are "
        "about the material, not the person."
    )


def generate_flashcards(
    title: str,
    raw_text: str,
    n: int = 8,
    model: str | None = None,
) -> GeneratedFlashcards:
    """Generate `n` flashcards for `raw_text`.

    Raises QuestionGenUnavailable if the LLM can't be reached (missing SDK/key).
    """
    if not is_available():
        raise QuestionGenUnavailable(
            "Question generation needs the 'anthropic' package installed and the "
            "ANTHROPIC_API_KEY environment variable set."
        )

    import anthropic

    model = model or os.getenv("COGPRINT_QGEN_MODEL", DEFAULT_MODEL)
    text = raw_text.strip()[:MAX_INPUT_CHARS]
    n = max(1, min(int(n), 30))

    client = anthropic.Anthropic()  # key resolved from ANTHROPIC_API_KEY
    user = (
        f"Material title: {title}\n\n"
        f"Generate exactly {n} flashcards from this material:\n\n{text}"
    )

    try:
        response = client.messages.parse(
            model=model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=_system_prompt(),
            messages=[{"role": "user", "content": user}],
            output_format=GeneratedFlashcards,
        )
    except anthropic.APIError as e:  # auth, rate limit, server, etc.
        raise QuestionGenUnavailable(f"LLM request failed: {e}") from e

    parsed = response.parsed_output
    if parsed is None or not parsed.cards:
        raise QuestionGenUnavailable("LLM returned no usable flashcards.")
    return parsed
