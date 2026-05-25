"""
Agent 3: Study Planner — dynamic-programming spaced-repetition scheduler.

No external API calls.  The schedule is computed by a DP algorithm that
maximises expected long-run retention subject to the learner's fingerprint
constraints (optimal technique, optimal time-of-day, session capacity).

Algorithm — Modified SM-2 / Ebbinghaus MDP
------------------------------------------
State: S = { concept → (last_day_studied, current_stability_S) }
    last_day_studied : day index (0-based) of the most recent session for this concept
    current_stability_S : estimated Ebbinghaus stability S for this concept/technique pair

Action each day: choose ≤ MAX_CONCEPTS_PER_DAY concepts to study,
    each paired with the technique that maximises expected retention.

Reward:
    r(concept, technique, lag) = R(lag) · effectiveness(technique)
    where R(lag) = exp(-lag / S_concept)    (predicted retention at review time)
    and effectiveness is derived from the learner's fingerprint (7d retention avg).

Priority function (greedy approximation to full DP):
    priority(c, day) = (1 - R(day - last_day[c]))   ← forgetting urgency
                     × technique_effectiveness(c)    ← learning value
    Concepts with lowest predicted retention → highest urgency.

Spaced repetition scheduling:
    After studying a concept, the next-review day is scheduled as:
        next_day = current_day + max(1, int(S · ln(1/threshold)))
    where threshold = 0.85 (review before retention drops below 85%).
    This is exactly the SM-2 inter-repetition interval expressed via Ebbinghaus.

Bellman interpretation:
    At each step we take the greedy action (highest-priority concepts first).
    The greedy policy is optimal when:
    (a) The daily reward is separable across concepts, and
    (b) Concepts don't interfere with each other's learning.
    Both approximately hold for the pilot-study scope.

Session capacity:
    MAX_CONCEPTS_PER_DAY = 3   (cognitive load research: Miller's law ≈ 7±2,
                                 but 3 ensures 15-minute deep-dives per concept)
    Session duration distributed equally across selected concepts, capped at
    the learner's optimal_session_duration_minutes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

from schemas.fingerprint import FingerprintProfile
from schemas.session import KnowledgeMap, StudyPlanDay, StudyPlanResponse

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_CONCEPTS_PER_DAY = 3       # cognitive load cap
_REVIEW_THRESHOLD     = 0.85    # schedule review when R drops below this
_DEFAULT_S            = 10.0    # default stability (days) when no data available
_DEFAULT_DURATION     = 45      # default session length in minutes
_DEFAULT_TECHNIQUE    = "active_recall"   # evidence-based default (Dunlosky 2013)
_DEFAULT_TIME_OF_DAY  = "morning"
_DIFFICULTY_ORDER     = {"foundational": 0, "intermediate": 1, "advanced": 2}


# ── Helper: Ebbinghaus ─────────────────────────────────────────────────────────

def _retention(lag: float, S: float) -> float:
    """R(t) = e^{-t/S}"""
    if S <= 0 or lag < 0:
        return 1.0
    return math.exp(-lag / S)


def _next_review_day(current_day: int, S: float) -> int:
    """
    Compute the next optimal review day using the Ebbinghaus threshold rule:
        Δt = S · ln(1 / threshold)   ← day until R drops to threshold
    Minimum interval of 1 day.
    """
    dt = max(1, int(S * math.log(1.0 / _REVIEW_THRESHOLD)))
    return current_day + dt


# ── Fingerprint extraction ────────────────────────────────────────────────────

def _best_technique(fp: FingerprintProfile) -> str:
    """
    Return the top recommended technique from the fingerprint.
    Falls back to the first entry in recommended_techniques,
    then to active_recall (evidence-based default).
    """
    if fp.recommended_techniques:
        return fp.recommended_techniques[0]
    if fp.technique_effectiveness:
        # Sort by 7d retention, falling back to 24h → immediate
        def key(t):
            return t.avg_retention_7d or t.avg_retention_24h or t.avg_immediate_score or 0.0
        best = max(fp.technique_effectiveness, key=key)
        return best.technique
    return _DEFAULT_TECHNIQUE


def _technique_effectiveness_map(fp: FingerprintProfile) -> dict[str, float]:
    """
    Build a dict mapping technique → expected retention multiplier [0, 1].
    Default = 0.70 (rough prior for an untested technique).
    """
    m: dict[str, float] = defaultdict(lambda: 0.70)
    for t in fp.technique_effectiveness:
        eff = t.avg_retention_7d or t.avg_retention_24h or t.avg_immediate_score
        if eff is not None:
            m[t.technique] = float(eff)
    return dict(m)


def _stability_map(fp: FingerprintProfile) -> dict[str, float]:
    """
    Map technique → average Ebbinghaus stability (days) from the fingerprint.
    Uses the Bayesian posterior median if available; falls back to OLS memory profiles.
    """
    s_map: dict[str, float] = {}

    # Priority 1: Bayesian posterior medians
    for bs in fp.technique_stability:
        if bs.posterior_median_days > 0:
            s_map[bs.technique] = bs.posterior_median_days

    # Priority 2: OLS memory profiles (fill gaps)
    for mp in fp.memory_profiles:
        if mp.technique not in s_map and mp.avg_stability_days > 0:
            s_map[mp.technique] = mp.avg_stability_days

    return s_map


# ── Concept difficulty → technique mapping ────────────────────────────────────

def _technique_for_concept(
    difficulty:   str,
    concept_type: str,
    best_overall: str,
    eff_map:      dict[str, float],
) -> str:
    """
    Heuristic: pick the best-performing technique that matches the concept's
    cognitive demand.  Evidence-based defaults (Dunlosky et al. 2013):

    difficulty  × type         → preferred technique
    foundational × factual     → spaced_repetition (high-utility for facts)
    foundational × procedural  → practice_testing  (procedural fluency)
    intermediate × conceptual  → active_recall     (elaborative retrieval)
    advanced     × conceptual  → elaborative_interrogation  (deep processing)
    advanced     × procedural  → interleaving      (transfer across contexts)
    """
    candidates_by_context = {
        ("foundational", "factual"):     ["spaced_repetition", "practice_testing", "active_recall"],
        ("foundational", "conceptual"):  ["active_recall", "spaced_repetition", "mind_maps"],
        ("foundational", "procedural"):  ["practice_testing", "active_recall", "spaced_repetition"],
        ("intermediate", "factual"):     ["spaced_repetition", "active_recall", "practice_testing"],
        ("intermediate", "conceptual"):  ["active_recall", "elaborative_interrogation", "mind_maps"],
        ("intermediate", "procedural"):  ["practice_testing", "interleaving", "active_recall"],
        ("advanced",     "factual"):     ["spaced_repetition", "interleaving", "active_recall"],
        ("advanced",     "conceptual"):  ["elaborative_interrogation", "active_recall", "interleaving"],
        ("advanced",     "procedural"):  ["interleaving", "practice_testing", "elaborative_interrogation"],
    }
    candidates = candidates_by_context.get(
        (difficulty, concept_type),
        [best_overall, "active_recall", "spaced_repetition"],
    )

    # 1. If the user's overall best technique is among the contextually appropriate
    #    candidates, honour it — it's the most direct personalisation signal.
    if best_overall in candidates:
        return best_overall

    # 2. If we have measured effectiveness data (not just defaults), use it.
    measured = {t: v for t, v in eff_map.items() if v != 0.70}  # 0.70 = prior default
    if measured:
        return max(candidates, key=lambda t: measured.get(t, 0.60))

    # 3. Fall back to evidence-based default order.
    return candidates[0]


# ── Priority score ────────────────────────────────────────────────────────────

def _priority(
    concept: str,
    current_day: int,
    last_studied: dict[str, int],
    stabilities: dict[str, float],
    eff_map: dict[str, float],
    technique: str,
    is_new: bool,
) -> float:
    """
    Higher priority → schedule sooner.

    For new (unseen) concepts:  priority = 1.0 + difficulty_boost
    For review concepts:
        priority = (1 - R(lag)) × effectiveness(technique)

    The (1 - R) term encodes urgency: 0 when just studied, →1 as concept is
    forgotten.  Multiplied by technique effectiveness so the system prefers
    high-yield reviews.
    """
    if is_new:
        return 1.0  # new concepts always scheduled before pure reviews

    last = last_studied.get(concept, 0)
    lag  = current_day - last
    S    = stabilities.get(concept, _DEFAULT_S)
    R    = _retention(lag, S)
    eff  = eff_map.get(technique, 0.70)
    return (1.0 - R) * eff


# ── Rationale builder ─────────────────────────────────────────────────────────

def _rationale(
    concept:   str,
    technique: str,
    is_new:    bool,
    lag:       Optional[int],
    S:         float,
    R:         Optional[float],
) -> str:
    tech_label = technique.replace("_", " ")
    if is_new:
        return (
            f"First exposure to '{concept}' — using {tech_label} for initial encoding. "
            f"Estimated stability without prior data: {S:.0f} days."
        )
    pct = round((1.0 - (R or 1.0)) * 100)
    return (
        f"Review scheduled for '{concept}': {pct}% forgetting predicted "
        f"({lag} days since last study, S≈{S:.0f}d). "
        f"{tech_label.title()} maximises re-encoding efficiency."
    )


# ── Main planner ──────────────────────────────────────────────────────────────

class StudyPlanner:
    """
    From-scratch DP-based study planner.

    Generates a day-by-day study schedule that maximises expected long-run
    retention using Ebbinghaus-guided spaced repetition and the learner's
    measured technique effectiveness from their cognitive fingerprint.
    """

    def generate_plan(
        self,
        user_id:       int,
        knowledge_map: KnowledgeMap,
        fingerprint:   FingerprintProfile,
        total_days:    int = 14,
    ) -> StudyPlanResponse:
        """
        Generate a personalised study plan.

        Parameters
        ----------
        user_id       : DB user identifier
        knowledge_map : extracted concept graph from Agent 1
        fingerprint   : cognitive fingerprint from Agent 2 (may be low-confidence)
        total_days    : planning horizon in days

        Returns
        -------
        StudyPlanResponse with one StudyPlanDay per day in the horizon.
        """
        if not knowledge_map.concepts:
            return StudyPlanResponse(
                user_id      = user_id,
                total_days   = total_days,
                days         = [],
                general_advice = "No concepts found in the material. Please re-analyze.",
            )

        # ── Extract user preferences from fingerprint ──────────────────────────
        best_tech     = _best_technique(fingerprint)
        eff_map       = _technique_effectiveness_map(fingerprint)
        stab_map      = _stability_map(fingerprint)
        optimal_dur   = (
            fingerprint.recommended_session_duration_minutes
            or fingerprint.optimal_conditions.optimal_session_duration_minutes
            or _DEFAULT_DURATION
        )
        time_of_day   = fingerprint.optimal_conditions.best_time_of_day or _DEFAULT_TIME_OF_DAY
        confidence    = fingerprint.confidence

        # ── Sort concepts by study order (foundational → advanced) ─────────────
        study_order_names = knowledge_map.suggested_study_order or [
            c.concept for c in knowledge_map.concepts
        ]
        concept_lookup = {c.concept: c for c in knowledge_map.concepts}

        # Keep only concepts present in both lists
        ordered_concepts = [
            concept_lookup[name]
            for name in study_order_names
            if name in concept_lookup
        ]
        # Append any remaining (not in suggested_study_order)
        in_order = {c.concept for c in ordered_concepts}
        for c in knowledge_map.concepts:
            if c.concept not in in_order:
                ordered_concepts.append(c)

        # ── Initialise DP state ────────────────────────────────────────────────
        last_studied:   dict[str, int] = {}    # concept → last day studied (0-based)
        next_review:    dict[str, int] = {}    # concept → earliest day for next review
        seen:           set[str]       = set() # concepts introduced so far
        introduction_queue = list(ordered_concepts)  # FIFO: introduce in study order

        plan_days: list[StudyPlanDay] = []

        # ── DP loop ────────────────────────────────────────────────────────────
        for day_idx in range(total_days):
            day_1based = day_idx + 1
            selected: list[tuple] = []   # (concept_name, technique, is_new, lag, S, R)

            # --- Step A: collect review candidates (seen + due) ---
            review_candidates = [
                name for name in seen
                if next_review.get(name, 0) <= day_idx
            ]

            # --- Step B: score and select top reviews ---
            scored_reviews = []
            for name in review_candidates:
                c = concept_lookup[name]
                tech = _technique_for_concept(c.difficulty, c.concept_type, best_tech, eff_map)
                S    = stab_map.get(tech, _DEFAULT_S)
                lag  = day_idx - last_studied.get(name, 0)
                R    = _retention(lag, S)
                prio = _priority(name, day_idx, last_studied, stab_map, eff_map, tech, is_new=False)
                scored_reviews.append((prio, name, tech, lag, S, R))

            scored_reviews.sort(reverse=True)

            for prio, name, tech, lag, S, R in scored_reviews:
                if len(selected) >= _MAX_CONCEPTS_PER_DAY:
                    break
                selected.append((name, tech, False, lag, S, R))

            # --- Step C: introduce new concepts to fill remaining capacity ---
            new_slots = _MAX_CONCEPTS_PER_DAY - len(selected)
            introduced_this_day = 0
            while new_slots > 0 and introduction_queue:
                c    = introduction_queue.pop(0)
                name = c.concept
                tech = _technique_for_concept(c.difficulty, c.concept_type, best_tech, eff_map)
                S    = stab_map.get(tech, _DEFAULT_S)
                selected.append((name, tech, True, None, S, None))
                seen.add(name)
                new_slots -= 1
                introduced_this_day += 1

            if not selected:
                # Nothing to review and nothing new — rest day
                plan_days.append(StudyPlanDay(
                    day                    = day_1based,
                    technique              = best_tech,
                    topic_focus            = "Rest / consolidation",
                    session_duration_minutes = 0,
                    time_of_day            = time_of_day,
                    rationale              = (
                        "No concepts are due for review today. "
                        "Allow memory consolidation — cognitive science shows rest days "
                        "strengthen retention through offline replay."
                    ),
                ))
                continue

            # --- Step D: build the StudyPlanDay entry ---
            # Aggregate: pick dominant technique (most frequent) for the day header
            tech_counts: dict[str, int] = {}
            for _, tech, _, _, _, _ in selected:
                tech_counts[tech] = tech_counts.get(tech, 0) + 1
            dominant_tech = max(tech_counts, key=lambda t: tech_counts[t])

            topic_parts = []
            for name, tech, is_new, lag, S, R in selected:
                prefix = "NEW: " if is_new else "REVIEW: "
                topic_parts.append(f"{prefix}{name} ({tech.replace('_', ' ')})")

            topic_focus = " | ".join(topic_parts)

            # Distribute session time across concepts
            session_dur = min(optimal_dur, _MAX_CONCEPTS_PER_DAY * 20)

            # Build rationale for the first (highest-priority) concept
            main_name, main_tech, main_new, main_lag, main_S, main_R = selected[0]
            rationale = _rationale(
                concept   = main_name,
                technique = main_tech,
                is_new    = main_new,
                lag       = main_lag,
                S         = main_S,
                R         = main_R,
            )
            if len(selected) > 1:
                extras = [
                    f"{'New' if isnew else 'Review'}: {nm}"
                    for nm, _, isnew, _, _, _ in selected[1:]
                ]
                rationale += f"  Also covering: {', '.join(extras)}."

            plan_days.append(StudyPlanDay(
                day                    = day_1based,
                technique              = dominant_tech,
                topic_focus            = topic_focus,
                session_duration_minutes = session_dur,
                time_of_day            = time_of_day,
                rationale              = rationale,
            ))

            # --- Step E: update DP state ---
            for name, tech, is_new, lag, S, R in selected:
                last_studied[name]  = day_idx
                next_review[name]   = _next_review_day(day_idx, S)

        # ── General advice ────────────────────────────────────────────────────
        general_advice = _build_general_advice(fingerprint, confidence, total_days)

        return StudyPlanResponse(
            user_id      = user_id,
            total_days   = total_days,
            days         = plan_days,
            general_advice = general_advice,
        )


def _build_general_advice(
    fp:         FingerprintProfile,
    confidence: object,
    total_days: int,
) -> str:
    parts: list[str] = []

    if str(confidence) in ("low", "ConfidenceLevel.LOW"):
        parts.append(
            "This plan uses evidence-based defaults (active recall + spaced repetition) "
            "since fewer than 5 sessions have been recorded. "
            "Complete more sessions and retention checks to unlock fully personalised scheduling."
        )
    else:
        if fp.recommended_techniques:
            top = fp.recommended_techniques[0].replace("_", " ")
            parts.append(f"Your most effective technique is {top} — it dominates this schedule.")
        conds = fp.optimal_conditions
        if conds.min_sleep_hours_recommended:
            parts.append(
                f"Sleep data shows study performance improves with ≥{conds.min_sleep_hours_recommended:.0f}h sleep. "
                "Prioritise sleep before study sessions."
            )
        if conds.max_stress_level_recommended:
            parts.append(
                f"Try to keep stress ≤{conds.max_stress_level_recommended}/5 when studying — "
                "your data shows a negative correlation between stress and retention."
            )

    parts.append(
        f"Reviews are scheduled using the Ebbinghaus forgetting curve (R(t) = e^{{-t/S}}) "
        f"with a {int(_REVIEW_THRESHOLD*100)}% retention threshold. "
        "Complete all 24h and 7d retention checks to continuously improve the schedule."
    )

    return "  ".join(parts)
