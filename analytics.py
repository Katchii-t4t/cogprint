"""
First-party event tracking.

The point of this module is to make the beta measurable: without it there is no
way to answer whether people come back, which is the single question the whole
validation exercise exists to settle.

Like the background fingerprint rebuild, tracking never raises. A telemetry
problem must not turn a successful study session into a failed request — the
event is the least important thing happening in any call site that uses it.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from database import AnalyticsEvent

logger = logging.getLogger("cogprint")

# Properties are attacker-influenced on the client endpoint, so the column is
# bounded here rather than trusting callers.
MAX_PROPERTIES_CHARS = 2048


def track_event(
    db: Session,
    user_id: Optional[int],
    event_name: str,
    properties: Optional[dict] = None,
) -> None:
    """Record one event. Swallows and logs any failure."""
    try:
        payload = None
        if properties:
            payload = json.dumps(properties)[:MAX_PROPERTIES_CHARS]

        db.add(AnalyticsEvent(
            user_id=user_id,
            event_name=event_name[:64],
            properties_json=payload,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — telemetry must never break the request
        logger.exception("failed to record analytics event %s", event_name)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
