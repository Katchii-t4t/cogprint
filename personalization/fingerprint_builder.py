"""
Pure-Python cognitive fingerprint computation pipeline.

No external API calls.  Every number in the fingerprint comes from one of:
  (a) Descriptive statistics over the user's own session/retention data
  (b) Hierarchical Bayesian MCMC posterior (HierarchicalMemoryModel)
  (c) LinUCB contextual bandit expected-reward estimates
  (d) Rule-based insight generation from (a)–(c)

Pipeline:
  1.  Load sessions + retention checks from DB
  2.  Per-technique descriptive stats  →  TechniqueStats list
  3.  Optimal-condition analysis       →  OptimalConditions
  4.  Ebbinghaus OLS fits              →  TechniqueMemoryProfile list
  5.  Population-level prior fitting   →  HierarchicalMemoryModel.fit_population()
  6.  Per-technique MCMC posterior     →  BayesianStabilityStats list
  7.  LinUCB batch refit               →  bandit_expected_rewards dict
  8.  Score-trend detection            →  improving_over_time, avg_score_trend_per_week
  9.  Rule-based insight generation    →  insights, data_gaps
 10.  Assemble + persist FingerprintProfile
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database import CognitiveFingerprint, RetentionCheck, StudyGroup, StudySession, User, utcnow
from personalization.forgetting_curve import compute_memory_profiles
from personalization.hierarchical_memory import HierarchicalMemoryModel
from personalization.priors import prior_stability_days
from personalization.linucb import (
    ALL_TECHNIQUES,
    LinUCBRecommender,
    best_available_reward,
    build_context_from_session,
)
from schemas.fingerprint import (
    BayesianStabilityStats,
    ConfidenceLevel,
    FingerprintProfile,
    OptimalConditions,
    TechniqueMemoryProfile,
    TechniqueStats,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _avg(lst: list) -> Optional[float]:
    return sum(lst) / len(lst) if lst else None


def _pearson_r(x: list[float], y: list[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    num   = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx    = sum((xi - mx) ** 2 for xi in x) ** 0.5
    dy    = sum((yi - my) ** 2 for yi in y) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


def _confidence_from_count(n: int) -> ConfidenceLevel:
    if n < 5:
        return ConfidenceLevel.LOW
    if n < 16:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_or_create_fingerprint(db: Session, user_id: int) -> CognitiveFingerprint:
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    if not fp:
        fp = CognitiveFingerprint(user_id=user_id, session_count=0)
        db.add(fp)
        db.commit()
        db.refresh(fp)
    return fp


def load_profile(fp: CognitiveFingerprint) -> FingerprintProfile:
    if fp.profile_json:
        return FingerprintProfile.model_validate_json(fp.profile_json)
    return FingerprintProfile(session_count=fp.session_count)


# ── Step 2 — per-technique descriptive statistics ─────────────────────────────

def _compute_technique_stats(
    sessions: list[StudySession],
    retention_checks: list[RetentionCheck],
) -> list[TechniqueStats]:
    """
    Compute per-technique means for immediate, 24h, and 7d scores.
    Assign relative effectiveness labels via rank percentile.
    """
    rc_idx = {
        (rc.session_id, rc.check_type): rc.score
        for rc in retention_checks
    }

    tech_data: dict[str, dict] = defaultdict(
        lambda: {"immediate": [], "r24h": [], "r7d": []}
    )
    for s in sessions:
        td = tech_data[s.technique.value]
        td["immediate"].append(s.quiz_score)
        r24 = rc_idx.get((s.id, "24h"))
        r7d = rc_idx.get((s.id, "7d"))
        if r24 is not None:
            td["r24h"].append(float(r24))
        if r7d is not None:
            td["r7d"].append(float(r7d))

    stats: list[TechniqueStats] = []
    for tech, td in sorted(tech_data.items()):
        stats.append(TechniqueStats(
            technique              = tech,
            sessions_observed      = len(td["immediate"]),
            avg_immediate_score    = _avg(td["immediate"]),
            avg_retention_24h      = _avg(td["r24h"]),
            avg_retention_7d       = _avg(td["r7d"]),
        ))

    # Rank by best available metric: 7d > 24h > immediate
    def primary_score(t: TechniqueStats) -> Optional[float]:
        return t.avg_retention_7d or t.avg_retention_24h or t.avg_immediate_score

    ranked = [(t, primary_score(t)) for t in stats if primary_score(t) is not None]
    if len(ranked) >= 2:
        ranked.sort(key=lambda x: x[1])  # ascending
        n_r = len(ranked)
        for i, (t, _) in enumerate(ranked):
            pct = i / (n_r - 1)
            if pct >= 0.75:
                t.relative_effectiveness = "best"
            elif pct >= 0.50:
                t.relative_effectiveness = "good"
            elif pct >= 0.25:
                t.relative_effectiveness = "average"
            else:
                t.relative_effectiveness = "poor"

    return stats


# ── Step 3 — optimal conditions ────────────────────────────────────────────────

def _compute_optimal_conditions(
    sessions: list[StudySession],
) -> OptimalConditions:
    """
    Compute Pearson r correlations and rule-based threshold recommendations
    for sleep, stress, and session duration.
    """
    # --- Time of day ---
    tod_scores: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        tod_scores[s.time_of_day.value].append(s.quiz_score)

    best_tod: Optional[str] = None
    if tod_scores:
        # Require at least 2 sessions in a slot before calling it "best"
        qualified = {k: v for k, v in tod_scores.items() if len(v) >= 2}
        if qualified:
            best_tod = max(qualified, key=lambda k: sum(qualified[k]) / len(qualified[k]))
        elif tod_scores:
            best_tod = max(tod_scores, key=lambda k: sum(tod_scores[k]) / len(tod_scores[k]))

    # --- Pearson r correlations ---
    sleep_pairs    = [(s.sleep_hours,         s.quiz_score) for s in sessions if s.sleep_hours    is not None]
    stress_pairs   = [(float(s.stress_level), s.quiz_score) for s in sessions if s.stress_level   is not None]
    duration_pairs = [(float(s.duration_minutes), s.quiz_score) for s in sessions]

    sleep_r    = _pearson_r([p[0] for p in sleep_pairs],    [p[1] for p in sleep_pairs])
    stress_r   = _pearson_r([p[0] for p in stress_pairs],   [p[1] for p in stress_pairs])
    duration_r = _pearson_r([p[0] for p in duration_pairs], [p[1] for p in duration_pairs])

    # --- Optimal session duration (bucket analysis) ---
    dur_buckets: dict[int, list[float]] = defaultdict(list)
    for s in sessions:
        d = s.duration_minutes
        bucket = 20 if d < 25 else 30 if d < 40 else 45 if d < 55 else 60 if d < 75 else 90
        dur_buckets[bucket].append(s.quiz_score)

    optimal_duration: Optional[int] = None
    qualified_dur = {b: v for b, v in dur_buckets.items() if len(v) >= 2}
    if qualified_dur:
        optimal_duration = max(qualified_dur, key=lambda b: sum(qualified_dur[b]) / len(qualified_dur[b]))

    # --- Sleep threshold recommendation (rule-based) ---
    min_sleep: Optional[float] = None
    if sleep_r is not None and len(sleep_pairs) >= 5:
        if sleep_r > 0.30:
            min_sleep = 8.0
        elif sleep_r > 0.15:
            min_sleep = 7.0
        elif sleep_r > 0.05:
            min_sleep = 6.5

    # --- Stress threshold recommendation ---
    max_stress: Optional[int] = None
    if stress_r is not None and len(stress_pairs) >= 5:
        if stress_r < -0.30:
            max_stress = 2
        elif stress_r < -0.15:
            max_stress = 3
        elif stress_r < -0.05:
            max_stress = 4

    return OptimalConditions(
        best_time_of_day                   = best_tod,
        optimal_session_duration_minutes   = optimal_duration,
        min_sleep_hours_recommended        = min_sleep,
        max_stress_level_recommended       = max_stress,
        sleep_score_correlation            = sleep_r,
        stress_score_correlation           = stress_r,
        duration_score_correlation         = duration_r,
    )


# ── Step 5 — population prior fitting ─────────────────────────────────────────

def _get_population_estimates(db: Session) -> list[float]:
    """
    Collect OLS S point estimates from all users' stored memory_profiles.
    These feed into HierarchicalMemoryModel.fit_population() (Empirical Bayes MLE).

    Returns a flat list of per-technique S values across all users.
    """
    # Column-only query + raw json.loads: this runs on EVERY rebuild (i.e.
    # every session/retention POST) over every user's stored profile, so we
    # skip ORM row construction and full pydantic validation — only the
    # memory_profiles stability values are needed here.
    rows = (
        db.query(CognitiveFingerprint.profile_json)
        .filter(CognitiveFingerprint.profile_json.isnot(None))
        .all()
    )
    s_values: list[float] = []
    for (profile_json,) in rows:
        try:
            for mp in json.loads(profile_json).get("memory_profiles", []):
                s = mp.get("avg_stability_days")
                if s is not None and s > 0:
                    s_values.append(float(s))
        except Exception:
            continue
    return s_values


# ── Step 6 — per-technique MCMC posteriors ────────────────────────────────────

def _compute_bayesian_stability(
    sessions: list[StudySession],
    retention_checks: list[RetentionCheck],
    model: HierarchicalMemoryModel,
) -> list[BayesianStabilityStats]:
    """
    For each technique the user has tried, fit a posterior over S using
    Metropolis-Hastings MCMC.  Techniques with no retention data receive
    a pure prior sample (population_informed=False).
    """
    rc_idx = {
        (rc.session_id, rc.check_type): rc.score
        for rc in retention_checks
    }

    # Group observations by technique
    tech_obs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for s in sessions:
        key = s.technique.value
        r24 = rc_idx.get((s.id, "24h"))
        r7d = rc_idx.get((s.id, "7d"))
        if r24 is not None:
            tech_obs[key].append((1.0, float(r24)))
        if r7d is not None:
            tech_obs[key].append((7.0, float(r7d)))

    # Ensure all observed techniques are represented
    for s in sessions:
        if s.technique.value not in tech_obs:
            tech_obs[s.technique.value] = []

    results: list[BayesianStabilityStats] = []
    for technique, obs in tech_obs.items():
        # Cold start (§2.1): until Empirical Bayes has a real cohort to fit,
        # centre each technique's stability prior at the literature-implied
        # value (Dunlosky 2013 ranking) instead of one global default — so a
        # brand-new user's posterior is differentiated and research-grounded.
        if not model.population_fitted:
            model.pop.log_mean = math.log(prior_stability_days(technique))
        summary = model.fit_user(obs)
        results.append(BayesianStabilityStats(
            technique             = technique,
            posterior_mean_days   = round(summary.mean, 2),
            posterior_median_days = round(summary.median, 2),
            posterior_std_days    = round(summary.std, 2),
            ci_lower_days         = round(summary.ci_lower, 2),
            ci_upper_days         = round(summary.ci_upper, 2),
            n_observations        = len(obs),
            population_informed   = summary.population_informed,
        ))

    # Sort descending by posterior median (best memory stability first)
    return sorted(results, key=lambda r: r.posterior_median_days, reverse=True)


# ── Step 7 — LinUCB bandit ────────────────────────────────────────────────────

def _load_bandit(fp_row: CognitiveFingerprint) -> LinUCBRecommender:
    """Restore persisted bandit state or initialise a fresh one."""
    if fp_row.bandit_state_json:
        try:
            return LinUCBRecommender.from_json(fp_row.bandit_state_json)
        except Exception:
            pass
    return LinUCBRecommender(techniques=ALL_TECHNIQUES)


# ── Step 8 — learning-trajectory trend ────────────────────────────────────────

def _compute_trend(
    sessions: list[StudySession],
) -> tuple[Optional[bool], Optional[float]]:
    """
    Fit an OLS slope to the sequence of weekly average quiz scores.

    Returns (improving: bool, slope_per_week: float), or (None, None)
    if there are fewer than 6 sessions spanning at least 3 weeks.
    """
    if len(sessions) < 6:
        return None, None

    first_date = min(s.created_at for s in sessions)
    weekly: dict[int, list[float]] = defaultdict(list)
    for s in sorted(sessions, key=lambda x: x.created_at):
        week = int((s.created_at - first_date).days / 7)
        weekly[week].append(s.quiz_score)

    if len(weekly) < 3:
        return None, None

    weeks = sorted(weekly)
    avgs  = [_avg(weekly[w]) for w in weeks]  # type: ignore[arg-type]

    n       = len(weeks)
    mean_w  = sum(weeks) / n
    mean_a  = sum(avgs) / n  # type: ignore[arg-type]
    denom   = sum((w - mean_w) ** 2 for w in weeks)
    if denom == 0:
        return None, None

    slope = sum((w - mean_w) * (a - mean_a)  # type: ignore[operator]
                for w, a in zip(weeks, avgs)) / denom

    return slope > 0, round(slope, 5)


# ── Step 9 — rule-based insights ──────────────────────────────────────────────

def _generate_insights(
    tech_stats:      list[TechniqueStats],
    conditions:      OptimalConditions,
    memory_profiles: dict,
    bandit_scores:   dict[str, float],
    sessions:        list[StudySession],
    improving:       Optional[bool],
    trend_per_week:  Optional[float],
    n:               int,
) -> tuple[list[str], list[str]]:
    """
    Derive human-readable insights and data-gap messages purely from
    computed statistics — no LLM inference.

    Rules are ordered by statistical strength (most informative first).
    Insights cap at 6; data_gaps cap at 4.
    """
    insights:  list[str] = []
    data_gaps: list[str] = []

    # --- Best / worst technique by 7d retention ---
    ranked_7d = sorted(
        [t for t in tech_stats if t.avg_retention_7d is not None],
        key=lambda t: t.avg_retention_7d,  # type: ignore[arg-type]
        reverse=True,
    )
    if ranked_7d:
        best = ranked_7d[0]
        insights.append(
            f"{best.technique.replace('_', ' ').title()} is your strongest technique "
            f"— {round(best.avg_retention_7d * 100)}% 7-day retention."  # type: ignore[operator]
        )
        if len(ranked_7d) >= 2:
            worst = ranked_7d[-1]
            gap = best.avg_retention_7d - worst.avg_retention_7d  # type: ignore[operator]
            if gap >= 0.12:
                insights.append(
                    f"{worst.technique.replace('_', ' ').title()} shows weaker retention "
                    f"({round(worst.avg_retention_7d * 100)}%) — consider reducing reliance on it."  # type: ignore[operator]
                )

    # --- Time of day ---
    if conditions.best_time_of_day:
        insights.append(f"You perform best in the {conditions.best_time_of_day}.")

    # --- Sleep correlation ---
    r_sleep = conditions.sleep_score_correlation
    if r_sleep is not None:
        if r_sleep > 0.35:
            insights.append("Strong link between sleep and scores — aim for ≥ 7h before study sessions.")
        elif r_sleep > 0.20:
            insights.append("More sleep shows a noticeable positive effect on your quiz scores.")

    # --- Stress correlation ---
    r_stress = conditions.stress_score_correlation
    if r_stress is not None:
        if r_stress < -0.35:
            insights.append("High stress substantially reduces your retention. Plan sessions on calmer days.")
        elif r_stress < -0.20:
            insights.append("Lower stress levels are linked to better performance for you.")

    # --- Memory stability (from Ebbinghaus OLS) ---
    mp_with_data = [
        mp for mp in memory_profiles.values()
        if mp.get("avg_stability_days", 0) > 0
    ]
    if mp_with_data:
        best_mp = max(mp_with_data, key=lambda p: p["avg_stability_days"])
        label   = best_mp.get("stability_label", "")
        if label in ("good", "excellent"):
            insights.append(
                f"{best_mp['technique'].replace('_', ' ').title()} gives you the strongest "
                f"memory encoding — {best_mp['avg_stability_days']:.0f}-day stability."
            )

    # --- Improvement trend ---
    if improving is True and trend_per_week is not None and abs(trend_per_week) > 0.003:
        insights.append(
            f"You're improving: +{trend_per_week * 100:.1f}% per week on average."
        )
    elif improving is False and trend_per_week is not None and abs(trend_per_week) > 0.005:
        insights.append(
            "Recent scores are declining — consider varying techniques or shortening sessions."
        )

    # --- Data gaps ---
    total_7d = sum(1 for t in tech_stats if t.avg_retention_7d is not None)
    if total_7d == 0:
        data_gaps.append(
            "No 7-day retention checks completed yet — complete your 7d checks for the richest insights."
        )

    few_obs = [t.technique for t in tech_stats if t.sessions_observed < 3]
    if few_obs:
        names = ", ".join(t.replace("_", " ") for t in few_obs[:3])
        data_gaps.append(f"Needs ≥3 sessions for reliable comparison: {names}.")

    missing_sleep   = sum(1 for s in sessions if s.sleep_hours is None)
    missing_stress  = sum(1 for s in sessions if s.stress_level is None)
    if missing_sleep > n // 3:
        data_gaps.append(
            f"Sleep hours missing for {missing_sleep}/{n} sessions — log sleep for better condition insights."
        )
    if missing_stress > n // 3:
        data_gaps.append(
            f"Stress level missing for {missing_stress}/{n} sessions — log stress for better condition insights."
        )

    return insights[:6], data_gaps[:4]


# ── Step 10 — recommended technique ordering ──────────────────────────────────

def _rank_recommended_techniques(
    bandit_scores:    dict[str, float],
    tech_stats:       list[TechniqueStats],
    n:                int,
) -> list[str]:
    """
    Rank techniques for the 'recommended_techniques' field.

    With ≥10 sessions: trust the LinUCB expected-reward ranking (accounts
    for the user's conditions).

    With < 10 sessions: blend 60% bandit / 40% raw 7d retention average
    so the recommendation is stable when the bandit is under-explored.
    """
    raw_7d = {
        t.technique: t.avg_retention_7d or t.avg_retention_24h or t.avg_immediate_score or 0.0
        for t in tech_stats
    }

    all_techs = list(set(list(bandit_scores.keys()) + list(raw_7d.keys())))

    def blended_score(k: str) -> float:
        b = bandit_scores.get(k, 0.0)
        r = raw_7d.get(k, 0.0)
        if n >= 10:
            return b
        w = min(1.0, n / 10.0)  # linearly interpolate 0→1 as n grows to 10
        return w * b + (1.0 - w) * r

    return sorted(all_techs, key=blended_score, reverse=True)


# ── Main entry point ───────────────────────────────────────────────────────────

def rebuild_fingerprint(db: Session, user_id: int) -> FingerprintProfile:
    """
    Recompute the cognitive fingerprint for a user from all available data.

    For the control group: stores session data but returns a generic profile
    (no personalization shown — preserves RCT blinding for Phase 3).

    For the treatment group: runs the full pipeline (steps 1–10 above).
    """
    # ── Load data ──────────────────────────────────────────────────────────────
    user: User = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    sessions: list[StudySession] = (
        db.query(StudySession)
        .filter_by(user_id=user_id)
        .order_by(StudySession.created_at)
        .all()
    )
    session_ids = [s.id for s in sessions]
    retention_checks: list[RetentionCheck] = (
        db.query(RetentionCheck)
        .filter(RetentionCheck.session_id.in_(session_ids))
        .all()
        if session_ids else []
    )

    n = len(sessions)
    fp_row = get_or_create_fingerprint(db, user_id)

    # ── Control group ──────────────────────────────────────────────────────────
    if user.group == StudyGroup.CONTROL:
        profile = FingerprintProfile(
            session_count = n,
            confidence    = ConfidenceLevel.LOW,
            insights      = ["Keep up your regular study routine."],
            data_gaps     = ["Personalisation not enabled for this study group."],
        )
        fp_row.session_count = n
        fp_row.profile_json  = profile.model_dump_json()
        fp_row.updated_at    = utcnow()
        db.commit()
        return profile

    # ── Below: treatment group only ────────────────────────────────────────────

    # 2. Descriptive stats
    tech_stats = _compute_technique_stats(sessions, retention_checks)

    # 3. Optimal conditions
    conditions = _compute_optimal_conditions(sessions)

    # 4. Ebbinghaus OLS fits
    memory_profiles = compute_memory_profiles(sessions, retention_checks)
    memory_profile_models = [TechniqueMemoryProfile(**mp) for mp in memory_profiles.values()]

    # 5. Population prior — Empirical Bayes MLE from all users' OLS estimates
    hm_model = HierarchicalMemoryModel()
    pop_estimates = _get_population_estimates(db)
    hm_model.fit_population(pop_estimates)  # no-op if < 4 estimates; uses defaults

    # 6. Per-technique MCMC posteriors
    technique_stability = _compute_bayesian_stability(sessions, retention_checks, hm_model)

    # 7. LinUCB bandit: refit from history, compute expected rewards
    bandit = _load_bandit(fp_row)
    bandit.fit_from_history(sessions, retention_checks)
    bandit_scores = bandit.expected_rewards()

    # 8. Score trend
    improving, trend_per_week = _compute_trend(sessions)

    # 9. Rule-based insights
    insights, data_gaps = _generate_insights(
        tech_stats      = tech_stats,
        conditions      = conditions,
        memory_profiles = memory_profiles,
        bandit_scores   = bandit_scores,
        sessions        = sessions,
        improving       = improving,
        trend_per_week  = trend_per_week,
        n               = n,
    )

    # Recommended duration: take optimal_duration from conditions, or None
    rec_duration = conditions.optimal_session_duration_minutes

    # Recommended techniques: bandit-informed ranking
    recommended = _rank_recommended_techniques(bandit_scores, tech_stats, n)

    # 10. Assemble profile
    profile = FingerprintProfile(
        session_count                       = n,
        confidence                          = _confidence_from_count(n),
        technique_effectiveness             = tech_stats,
        optimal_conditions                  = conditions,
        recommended_techniques              = recommended,
        recommended_session_duration_minutes = rec_duration,
        insights                            = insights,
        data_gaps                           = data_gaps,
        improving_over_time                 = improving,
        avg_score_trend_per_week            = trend_per_week,
        memory_profiles                     = memory_profile_models,
        technique_stability                 = technique_stability,
        bandit_expected_rewards             = bandit_scores,
    )

    # Persist profile + bandit state
    fp_row.session_count      = n
    fp_row.profile_json       = profile.model_dump_json()
    fp_row.bandit_state_json  = bandit.to_json()
    fp_row.updated_at         = utcnow()
    db.commit()
    db.refresh(fp_row)

    return profile
