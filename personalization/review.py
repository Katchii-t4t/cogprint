"""
Deterministic per-material review suggestions — "you're about to forget X".

Predicted retention uses the same Ebbinghaus model the rest of the pipeline is
built on:  R(t) = exp(-t / S),  where t is days since the material was last
studied and S is memory stability in days.

Scientific-integrity notes:
  * No LLM anywhere — pure arithmetic, unit-testable.
  * Personalised S comes only from the user's OWN fingerprint (their measured
    memory_profiles). Control users have a generic profile with no
    memory_profiles, so they automatically get the population default — the
    RCT blinding is preserved without any special-casing here.
  * Scheduling reviews off the forgetting curve is established memory science
    (the study planner already does it); this makes no claim that any
    *technique* works better for the user, so the two-track rule is respected.
"""

from __future__ import annotations

import math

# Same default stability the OLS fitter falls back to (see forgetting_curve.py
# usage in the study planner), and the same review threshold it schedules by.
DEFAULT_STABILITY_DAYS = 10.0
FADING_THRESHOLD = 0.85


def predicted_retention(days_since: float, stability_days: float) -> float:
    """R(t) = exp(-t/S), clamped to [0, 1]; S floored to avoid div-by-~0."""
    s = max(0.5, float(stability_days))
    t = max(0.0, float(days_since))
    return max(0.0, min(1.0, math.exp(-t / s)))
