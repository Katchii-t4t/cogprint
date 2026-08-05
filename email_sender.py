"""
Pluggable email delivery.

Design goals mirror auth.py: zero-config locally, one env var away from real
delivery. With no provider configured the message is logged in full, so the
entire magic-link flow is exercisable — in development, in tests, and in CI —
without an account anywhere.

Deliberately stdlib-only. A single JSON POST does not justify a new dependency,
and keeping it dependency-free means the free/offline deployment mode (see
COGPRINT_MODE in the questions endpoint) stays genuinely self-contained.

Failures never propagate. An outbound mail problem must not turn a successful
signup into a 500 — the same rule the background fingerprint rebuild follows.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("cogprint")

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_FROM = "CogPrint <noreply@cogprint.app>"
_TIMEOUT_SECONDS = 10


def provider_configured() -> bool:
    """True when real delivery is possible."""
    return bool(os.getenv("RESEND_API_KEY"))


def send_email(to: str, subject: str, body_text: str) -> None:
    """Deliver a plain-text email, or log it when no provider is configured."""
    if not provider_configured():
        # The recognisable prefix is what you grep for when testing the flow by
        # hand: the link in this output is a working link.
        logger.info(
            "EMAIL (no provider configured)\n  to: %s\n  subject: %s\n%s",
            to, subject, body_text,
        )
        return

    payload = json.dumps({
        "from": os.getenv("EMAIL_FROM", DEFAULT_FROM),
        "to": [to],
        "subject": subject,
        "text": body_text,
    }).encode("utf-8")

    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            if response.status >= 300:
                logger.warning("email provider returned %s for %s", response.status, to)
    except (urllib.error.URLError, OSError, ValueError):
        # Logged, not raised: the caller's request already succeeded on its own
        # terms, and the user can always request another link.
        logger.exception("failed to send email to %s", to)


def frontend_url() -> str:
    """Base URL the emailed links point at.

    Defaults to the Vite dev server so links are clickable during local
    development; set FRONTEND_URL in deployment.
    """
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
