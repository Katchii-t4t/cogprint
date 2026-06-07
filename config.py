"""
Single source of truth for the **retention-check schedule**.

────────────────────────────────────────────────────────────────────────────
⚠️  UNRESOLVED PROTOCOL DECISION — read before changing anything here.
────────────────────────────────────────────────────────────────────────────
The study materials (Google Forms) currently test at **day 1 / 5 / 10 / 30**.
This backend's whole memory model is built around **immediate quiz + 24h + 7d**.
These two schedules do NOT match, and the mismatch makes any cross-analysis
ambiguous. Exactly ONE schedule must be locked (a scientific call for Katchi +
the UiO advisor — see RETENTION_SCHEDULE_DECISION.md), then BOTH the materials
and this code must be aligned to it.

This module centralises the *scheduling-facing* half so the reminder/pending
logic and input validation read from one place. But note the limit honestly:
the **time-coordinates** below (`day_coord`: 1.0 and 7.0 days) are also baked
into the curve-fitting math in:
    personalization/forgetting_curve.py     (OLS fit at t=1, t=7)
    personalization/hierarchical_memory.py  (MCMC observations at t=1, t=7)
    personalization/linucb.py               (reward: 7d gold, 24h×0.85)
    personalization/fingerprint_builder.py  (per-technique aggregation)
    personalization/serializer.py           (legacy narrative aggregation)
Those modules read the string keys ("24h"/"7d") directly. Changing the schedule
therefore is NOT a one-line edit — it also requires updating the math in those
five files. This config makes the *easy* half consistent and documents the
*hard* half so the change is a precise checklist rather than a hunt.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import List


@dataclass(frozen=True)
class RetentionCheckpoint:
    """One scheduled retention test after a study session.

    key       : stable identifier stored in RetentionCheck.check_type and the
                CSV export header (``retention_<key>``). Keep <= 10 chars
                (database.py column is String(10)).
    label     : human-readable name for UI / reminders.
    delay     : how long after the study session this check becomes due.
    day_coord : the x-coordinate (in DAYS) this checkpoint represents in the
                forgetting-curve / MCMC math. Must equal delay-in-days.
    """

    key: str
    label: str
    delay: timedelta
    day_coord: float


# ── The locked schedule. Currently immediate-quiz + 24h + 7d. ────────────────
# (The immediate quiz is StudySession.quiz_score, not a RetentionCheck, so it
#  is not listed here — these are the *delayed* checks only.)
RETENTION_SCHEDULE: List[RetentionCheckpoint] = [
    RetentionCheckpoint(key="24h", label="24-hour check", delay=timedelta(hours=24), day_coord=1.0),
    RetentionCheckpoint(key="7d", label="7-day check", delay=timedelta(days=7), day_coord=7.0),
]

# Derived helpers — import these instead of re-hard-coding the keys anywhere.
CHECK_TYPE_KEYS: List[str] = [c.key for c in RETENTION_SCHEDULE]


def checkpoint_by_key(key: str) -> RetentionCheckpoint:
    for c in RETENTION_SCHEDULE:
        if c.key == key:
            return c
    raise KeyError(f"Unknown retention check_type {key!r}; expected one of {CHECK_TYPE_KEYS}")
