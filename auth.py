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
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import Header, HTTPException, Request, status

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


# ── Rate limiting for credential endpoints ────────────────────────────────────
#
# Recovery tokens carry 192 bits of entropy, so online guessing is already
# hopeless; this limiter exists to stop an attacker turning the endpoint into a
# free CPU/DB sink, and to bound damage if a token ever *is* partially leaked.
#
# Deliberate limitations, stated rather than hidden:
#   * In-process memory — with multiple workers each gets its own budget. Move
#     to Redis (or the platform's edge limiter) when the API runs >1 worker.
#   * Keyed on the peer address; behind a proxy that is the proxy unless
#     TRUST_PROXY_HEADER is set, so we opt into X-Forwarded-For explicitly
#     rather than trusting a spoofable header by default.

# Buckets are shared across limiters and namespaced by the limiter's own name,
# so two endpoints with different budgets cannot spend each other's allowance.
_attempts: Dict[str, Deque[float]] = {}


def _client_key(request: Request) -> str:
    if os.getenv("TRUST_PROXY_HEADER"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def make_rate_limiter(
    name: str,
    max_attempts: int,
    window_seconds: float,
    message: str = "Too many attempts. Try again in a few minutes.",
):
    """Build a FastAPI dependency that caps requests per client per window.

    A factory rather than a copied function per endpoint: the sliding-window
    logic exists once, and each credential endpoint picks its own budget.
    """

    def limiter(request: Request) -> None:
        now = time.monotonic()
        key = f"{name}:{_client_key(request)}"
        bucket = _attempts.setdefault(key, deque())

        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=message,
            )

        bucket.append(now)

        # Bound memory: drop buckets that have fully aged out. Cheap because it
        # only runs once the table is large enough to be worth scanning.
        if len(_attempts) > 1024:
            stale = [
                k for k, v in _attempts.items()
                if not v or now - v[-1] > window_seconds
            ]
            for k in stale:
                _attempts.pop(k, None)

    return limiter


rate_limit_recovery = make_rate_limiter(
    "recovery", 10, 300.0,
    "Too many recovery attempts. Try again in a few minutes.",
)

# Sending mail costs money and reaches a third party's inbox, so the budget is
# tighter than for a pure lookup: this bounds both spend and the blast radius if
# someone tries to use the endpoint to harass an address.
rate_limit_email = make_rate_limiter(
    "email", 5, 900.0,
    "Too many email requests. Try again in a few minutes.",
)

# Vision OCR is billed per image, so this is a spend control first and an abuse
# control second. Generous enough for a real study session (photographing a few
# pages), tight enough that a script can't run up a bill unattended.
rate_limit_ocr = make_rate_limiter(
    "ocr", 20, 3600.0,
    "Too many photo scans in a short time. Try again later, or paste the text.",
)


def reset_rate_limits() -> None:
    """Clear all buckets. For tests — never called by application code."""
    _attempts.clear()
