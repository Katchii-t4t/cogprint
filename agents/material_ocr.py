"""
Material OCR — photo of notes/textbook → study-material text (Claude vision).

Like agents/question_generator.py, this is an ISOLATED LLM service module —
the second and only other LLM call in CogPrint. It is purely a text-acquisition
front door: it returns transcribed text which the frontend then feeds into the
ordinary POST /materials/analyze flow, so the whole downstream pipeline
(knowledge map, plan, questions, fingerprint) is reused unchanged and stays
API-free.

Design (mirrors question_generator):
  * Key from the ANTHROPIC_API_KEY environment variable only — never in code,
    args, or logs.
  * Model configurable via COGPRINT_OCR_MODEL (default claude-opus-4-8, which
    supports vision), so cost/quality is a config change.
  * Raises OcrUnavailable when the SDK/key is missing or the API call fails,
    so the endpoint can return a clean 503 and the UI can degrade gracefully.
  * The LLM only TRANSCRIBES — it computes nothing and judges nothing.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-opus-4-8"

ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}

_INSTRUCTION = (
    "Transcribe all study-material text visible in this image. Output only the "
    "transcribed text, preserving headings, lists, and structure, and writing "
    "math notation as plainly as you can. If the text is handwritten, do your "
    "best. Do not add commentary, summaries, or translations — transcription "
    "only, in the language shown."
)


class OcrUnavailable(RuntimeError):
    """Raised when OCR can't run (no SDK, no API key, or the call failed)."""


def is_available() -> bool:
    """True if OCR can run right now (SDK present + key set)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def extract_text_from_image(image_base64: str, media_type: str) -> str:
    """Transcribe the study material in a base64-encoded image.

    Raises OcrUnavailable if the LLM can't be reached or returns nothing.
    """
    if not is_available():
        raise OcrUnavailable(
            "Photo scanning needs the 'anthropic' package installed and the "
            "ANTHROPIC_API_KEY environment variable set."
        )

    import anthropic

    model = os.getenv("COGPRINT_OCR_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic()  # key resolved from ANTHROPIC_API_KEY

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {"type": "text", "text": _INSTRUCTION},
                ],
            }],
        )
    except anthropic.APIError as e:
        raise OcrUnavailable(f"OCR request failed: {e}") from e

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise OcrUnavailable("No readable text found in the image.")
    return text
