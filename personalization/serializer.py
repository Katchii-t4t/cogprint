from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from database import RetentionCheck, StudySession
from personalization.forgetting_curve import compute_memory_profiles, format_for_prompt


def _pearson_r(x: list[float], y: list[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return None
    return round(num / (denom_x * denom_y), 3)


def _fmt(val: Optional[float], precision: int = 2) -> str:
    return f"{val:.{precision}f}" if val is not None else "N/A"


def serialize_for_agent2(
    sessions: list[StudySession],
    retention_checks: list[RetentionCheck],
) -> tuple[str, dict]:
    """
    Converts raw DB records into a structured text block injected into Agent 2's prompt.
    Pre-computes all statistics (Pearson r, per-technique averages, trajectory) so that
    the LLM only needs to synthesize patterns, not do arithmetic.

    Returns ``(prompt_text, memory_profiles)``: the rendered prompt block plus the
    raw Ebbinghaus profiles dict. (Legacy narrative-mode helper — not used by the
    live API-free pipeline; kept for a future optional narrative mode.)
    """
    n = len(sessions)
    if n == 0:
        return "No sessions recorded yet."

    # Index retention checks by session_id and type
    retention_by_session: dict[int, dict[str, float]] = defaultdict(dict)
    for rc in retention_checks:
        retention_by_session[rc.session_id][rc.check_type] = rc.score

    # --- Per-technique aggregates ---
    technique_data: dict[str, dict] = defaultdict(
        lambda: {"immediate": [], "r24h": [], "r7d": []}
    )
    for s in sessions:
        td = technique_data[s.technique.value]
        td["immediate"].append(s.quiz_score)
        rc = retention_by_session.get(s.id, {})
        if "24h" in rc:
            td["r24h"].append(rc["24h"])
        if "7d" in rc:
            td["r7d"].append(rc["7d"])

    technique_lines = []
    for tech, td in sorted(technique_data.items()):
        avg_imm = sum(td["immediate"]) / len(td["immediate"]) if td["immediate"] else None
        avg_24h = sum(td["r24h"]) / len(td["r24h"]) if td["r24h"] else None
        avg_7d = sum(td["r7d"]) / len(td["r7d"]) if td["r7d"] else None
        technique_lines.append(
            f"  {tech}: n={len(td['immediate'])}, "
            f"immediate={_fmt(avg_imm)}, "
            f"24h_retention={_fmt(avg_24h)}, "
            f"7d_retention={_fmt(avg_7d)}"
        )

    # --- Time of day breakdown ---
    tod_data: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        tod_data[s.time_of_day.value].append(s.quiz_score)

    tod_lines = []
    for tod, scores in sorted(tod_data.items()):
        avg = sum(scores) / len(scores)
        tod_lines.append(f"  {tod}: n={len(scores)}, avg_immediate={_fmt(avg)}")

    # --- Correlations: sleep, stress, duration vs. quiz_score ---
    sleep_pairs = [(s.sleep_hours, s.quiz_score) for s in sessions if s.sleep_hours is not None]
    stress_pairs = [(s.stress_level, s.quiz_score) for s in sessions if s.stress_level is not None]
    duration_pairs = [(float(s.duration_minutes), s.quiz_score) for s in sessions]

    sleep_r = _pearson_r([p[0] for p in sleep_pairs], [p[1] for p in sleep_pairs])
    stress_r = _pearson_r([p[0] for p in stress_pairs], [p[1] for p in stress_pairs])
    duration_r = _pearson_r([p[0] for p in duration_pairs], [p[1] for p in duration_pairs])

    # Sleep breakdown by bucket
    sleep_buckets: dict[str, list[float]] = defaultdict(list)
    for sleep, score in sleep_pairs:
        if sleep < 6:
            bucket = "<6h"
        elif sleep < 7:
            bucket = "6–7h"
        elif sleep < 8:
            bucket = "7–8h"
        else:
            bucket = "8h+"
        sleep_buckets[bucket].append(score)

    sleep_lines = []
    for bucket in ["<6h", "6–7h", "7–8h", "8h+"]:
        scores = sleep_buckets.get(bucket, [])
        if scores:
            sleep_lines.append(f"  {bucket}: n={len(scores)}, avg_score={_fmt(sum(scores)/len(scores))}")

    # Stress breakdown by level
    stress_buckets: dict[int, list[float]] = defaultdict(list)
    for stress, score in stress_pairs:
        stress_buckets[int(stress)].append(score)

    stress_lines = [
        f"  stress={level}: n={len(scores)}, avg_score={_fmt(sum(scores)/len(scores))}"
        for level, scores in sorted(stress_buckets.items())
    ]

    # --- Weekly learning trajectory (avg immediate score per week) ---
    if sessions:
        first_date = min(s.created_at for s in sessions)
        weekly_scores: dict[int, list[float]] = defaultdict(list)
        for s in sessions:
            week = int((s.created_at - first_date).days / 7)
            weekly_scores[week].append(s.quiz_score)

        trajectory_lines = [
            f"  Week {week+1}: n={len(scores)}, avg={_fmt(sum(scores)/len(scores))}"
            for week, scores in sorted(weekly_scores.items())
        ]

        # Simple linear trend: slope of weekly averages
        weekly_avgs = [(week, sum(s) / len(s)) for week, s in sorted(weekly_scores.items())]
        trend_r = _pearson_r([w for w, _ in weekly_avgs], [a for _, a in weekly_avgs]) if len(weekly_avgs) >= 3 else None
    else:
        trajectory_lines = ["  No data"]
        trend_r = None

    # --- Ebbinghaus forgetting-curve fits (pre-computed, not LLM-inferred) ---
    memory_profiles = compute_memory_profiles(sessions, retention_checks)
    curve_block = format_for_prompt(memory_profiles)

    # --- Assemble prompt text ---
    parts = [
        f"TOTAL SESSIONS: {n}",
        "",
        "=== TECHNIQUE PERFORMANCE ===",
        "(primary metric: 7d_retention > 24h_retention > immediate)",
        *technique_lines,
        "",
        "=== PERFORMANCE BY TIME OF DAY ===",
        *tod_lines,
        "",
        "=== SLEEP ANALYSIS ===",
        f"Pearson r (sleep_hours vs quiz_score): {_fmt(sleep_r, 3)}  [n={len(sleep_pairs)}]",
        *(sleep_lines or ["  Insufficient data"]),
        "",
        "=== STRESS ANALYSIS ===",
        f"Pearson r (stress_level vs quiz_score): {_fmt(stress_r, 3)}  [n={len(stress_pairs)}]",
        *(stress_lines or ["  Insufficient data"]),
        "",
        "=== SESSION DURATION ANALYSIS ===",
        f"Pearson r (duration_minutes vs quiz_score): {_fmt(duration_r, 3)}  [n={n}]",
        "",
        "=== WEEKLY LEARNING TRAJECTORY ===",
        *trajectory_lines,
        f"Score trend (weekly Pearson r): {_fmt(trend_r, 3)}",
        "",
        "=== EBBINGHAUS FORGETTING-CURVE FITS ===",
        "Model: R(t) = e^(−t/S)  |  S = stability (days)  |  higher S = slower forgetting",
        "S benchmarks: <5d poor | 5–10d fair | 10–20d good | >20d excellent",
        curve_block,
    ]

    return "\n".join(parts), memory_profiles
