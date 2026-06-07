"""
Optional API-key authentication for sensitive researcher endpoints.

Design goals:
  * Zero-config for local development and the current closed pilot: if the
    ``COGPRINT_API_KEY`` environment variable is **unset**, the dependency is a
    no-op and every endpoint stays open (so nothing breaks locally).
  * One env var away from real protection: set ``COGPRINT_API_KEY`` to a long
    random string and the protected endpoints then require a matching
    ``X-API-Key`` request header.

This guards the bulk-data endpoints (full participant list, CSV export) that
are the real GDPR exposure — a single request there reveals *every*
participant's data. Per-participant tokens are a later, larger piece of work
(see HANDOVER §8); this closes the highest-risk hole with minimal surface.

The comparison is constant-time (``secrets.compare_digest``) to avoid leaking
the key through response-timing differences.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

API_KEY_ENV = "COGPRINT_API_KEY"


def api_key_required() -> bool:
    """True if an API key is configured (and therefore enforced)."""
    return bool(os.getenv(API_KEY_ENV))


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency: enforce the API key *iff* one is configured.

    - No ``COGPRINT_API_KEY`` set  -> auth disabled, request allowed.
    - Key set and header matches    -> allowed.
    - Key set and header missing/wrong -> 401.
    """
    expected = os.getenv(API_KEY_ENV)
    if not expected:
        return  # Auth disabled — open mode for local dev / closed pilot.

    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "API-Key"},
        )
