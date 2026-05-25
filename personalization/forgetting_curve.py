"""
Ebbinghaus forgetting-curve engine for CogPrint.

Model:  R(t) = e^(−t / S)

  R  = retention probability (0–1)
  t  = time since study event (days)
  S  = stability (days) — the core individual parameter.
       Higher S → slower forgetting → stronger memory formation.

Fitting S from CogPrint's two retention checkpoints (24 h and 7 d):

  Taking ln of both sides:  ln R_i = −t_i / S
  OLS through the origin in log-retention space:

       S = −Σ t_i²  /  Σ (t_i · ln R_i)

If only one checkpoint is available, S is solved analytically:
       S = −t / ln(R)

Stability benchmarks (derived from memory research literature):
  S < 5 d  → poor     — material is being forgotten rapidly
  5–10 d   → fair
  10–20 d  → good
  > 20 d   → excellent — very durable memory trace
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

from database import RetentionCheck, StudySession

# ── Constants ─────────────────────────────────────────────────────────────────
REVIEW_THRESHOLD  = 0.85   # schedule a review when predicted R drops below this
_CLIP             = 0.01   # clamp retention away from 0/1 before taking log
_S_MIN, _S_MAX    = 0.1, 730.0  # sanity bounds (days); discard outliers


# ── Core math ─────────────────────────────────────────────────────────────────

def _clip(r: float) -> float:
    return max(_CLIP, min(1.0 - _CLIP, r))


def fit_stability(
    r_24h: Optional[float],
    r_7d: Optional[float],
) -> Optional[float]:
    """
    Estimate the Ebbinghaus stability S (days) from up to two retention
    observations at t=1 day and t=7 days.

    Returns None when there is no usable data.
    """
    pts: list[tuple[float, float]] = []
    if r_24h is not None:
        pts.append((1.0, _clip(r_24h)))
    if r_7d is not None:
        pts.append((7.0, _clip(r_7d)))

    if not pts:
        return None

    # Analytical solution for a single observation
    if len(pts) == 1:
        t, r = pts[0]
        s = -t / math.log(r)
        return round(s, 3) if _S_MIN <= s <= _S_MAX else None

    # OLS through origin for two observations
    num   = sum(t * t          for t, _ in pts)
    denom = sum(t * math.log(r) for t, r in pts)
    if denom == 0:
        return None
    s = -num / denom
    return round(s, 3) if _S_MIN <= s <= _S_MAX else None


def predict_retention(S: float, days: float) -> float:
    """Predicted retention at `days` after study: R(t) = e^(−t/S)."""
    return round(max(0.0, min(1.0, math.exp(-days / S))), 4)


def days_until_threshold(S: float, threshold: float = REVIEW_THRESHOLD) -> int:
    """
    Days from study until predicted retention first drops to `threshold`.
    This is the optimal next-review interval.
    """
    return max(1, int(-S * math.log(_clip(threshold))))


def stability_label(S: float) -> str:
    if S < 5:   return "poor"
    if S < 10:  return "fair"
    if S < 20:  return "good"
    return "excellent"


# ── Per-technique aggregation ─────────────────────────────────────────────────

def compute_memory_profiles(
    sessions: list[StudySession],
    retention_checks: list[RetentionCheck],
) -> dict[str, dict]:
    """
    Fits an Ebbinghaus curve for every session that has retention data, then
    aggregates per technique.

    Returns a dict keyed by technique name (str).  Each value is a plain dict
    compatible with TechniqueMemoryProfile (schemas/fingerprint.py).

    Only techniques with at least one fitted S value are included.
    """
    # Index retention checks by (session_id, check_type) for O(1) lookup
    rc_idx: dict[tuple[int, str], float] = {
        (rc.session_id, rc.check_type): rc.score
        for rc in retention_checks
    }

    tech_stabs: dict[str, list[float]] = defaultdict(list)
    tech_r7d:   dict[str, list[float]] = defaultdict(list)

    for s in sessions:
        r24 = rc_idx.get((s.id, "24h"))
        r7d = rc_idx.get((s.id, "7d"))

        S = fit_stability(r24, r7d)
        if S is not None:
            tech_stabs[s.technique.value].append(S)
        if r7d is not None:
            tech_r7d[s.technique.value].append(r7d)

    profiles: dict[str, dict] = {}
    for tech, stabs in tech_stabs.items():
        avg_S = round(sum(stabs) / len(stabs), 2)
        profiles[tech] = {
            "technique":                    tech,
            "avg_stability_days":           avg_S,
            "stability_label":              stability_label(avg_S),
            "predicted_retention_7d":       predict_retention(avg_S, 7.0),
            "optimal_review_interval_days": days_until_threshold(avg_S),
            "sessions_with_curve_data":     len(stabs),
            "avg_7d_retention":             round(
                                                sum(tech_r7d[tech]) / len(tech_r7d[tech]), 3
                                            ) if tech_r7d.get(tech) else None,
        }

    return profiles


def format_for_prompt(profiles: dict[str, dict]) -> str:
    """
    Render memory profiles as a human-readable block for injection into
    the Agent 2 system prompt.
    """
    if not profiles:
        return "  No retention checkpoint data available yet."

    lines: list[str] = []
    for p in sorted(profiles.values(), key=lambda x: -(x["avg_stability_days"] or 0)):
        lines.append(
            f"  {p['technique']:<30} "
            f"S={p['avg_stability_days']:>6.1f}d ({p['stability_label']:<9})  "
            f"R(7d)={p['predicted_retention_7d']:.2f}  "
            f"review_by=day_{p['optimal_review_interval_days']:<3}  "
            f"n={p['sessions_with_curve_data']}"
        )
    return "\n".join(lines)
