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

from personalization.priors import prior_effectiveness, prior_stability_days
from schemas.fingerprint import FingerprintProfile
from schemas.session import KnowledgeMap, MaterialProfile, StudyPlanDay, StudyPlanResponse

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
        best = max(fp.technique_effectiveness, key=lambda t: _delayed_retention(t) or 0.0)
        return best.technique
    return _DEFAULT_TECHNIQUE


def _delayed_retention(t) -> float | None:
    """A technique's measured *delayed* retention, or None if it has none yet.

    Immediate quiz score is deliberately excluded. It measures encoding, not
    forgetting, and it is exactly where the fluency illusion lives: re-reading
    feels — and immediately tests — better than it retains. Letting it stand in
    for retention would systematically favour the techniques the literature
    warns about, using the one number most biased in their favour.

    Explicit `is not None` rather than `or`: a genuine measured retention of
    0.0 is data, and the previous `a or b or c` chain silently skipped it and
    fell through to the next, weaker source.
    """
    if t.avg_retention_7d is not None:
        return float(t.avg_retention_7d)
    if t.avg_retention_24h is not None:
        return float(t.avg_retention_24h)
    return None


def _technique_effectiveness_map(fp: FingerprintProfile) -> dict[str, float]:
    """
    Build a dict mapping technique → expected retention multiplier [0, 1].
    Untested techniques default to the research prior (Dunlosky 2013 et al.,
    see personalization/priors.py) instead of a flat constant — so cold-start
    recommendations are differentiated and research-defensible from session 0.
    """
    m: dict[str, float] = {
        tech: prior_effectiveness(tech)
        for tech in (
            "practice_testing", "spaced_repetition", "active_recall",
            "elaborative_interrogation", "interleaving", "mind_maps", "re_reading",
        )
    }
    for t in fp.technique_effectiveness:
        eff = _delayed_retention(t)
        if eff is not None:
            m[t.technique] = eff
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


# ── Concept difficulty × type → technique matching ────────────────────────────
#
# Evidence-based ordering per cognitive context (Dunlosky et al. 2013). The FIRST
# technique fits the context best, the rest are progressively weaker fits. This is
# the *material* signal — which techniques the text itself calls for, before we
# know anything about the learner.
#
#   foundational × factual     → spaced_repetition (high-utility for facts)
#   foundational × procedural  → practice_testing  (procedural fluency)
#   intermediate × conceptual  → active_recall     (elaborative retrieval)
#   advanced     × conceptual  → elaborative_interrogation  (deep processing)
#   advanced     × procedural  → interleaving      (transfer across contexts)
_CANDIDATES_BY_CONTEXT: dict[tuple[str, str], list[str]] = {
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

# Rank → material weight. Descending, with a FLOOR for techniques the context
# doesn't call out, so a learner with a strong *measured* advantage in some other
# technique can still surface it. This is the honesty guardrail: material type is
# a MODULATION on top of a strong general prior, not a hard gate.
#
# The numbers previously contradicted that sentence. With a floor of 0.45 the
# material term spanned 2.2x, which is wider than the spread in measured
# effectiveness — and since re_reading and mind_maps appear in few or no context
# lists, they were pinned at the floor and could never be scheduled no matter
# what a learner's own retention data said. Meanwhile the fingerprint screen
# happily told that learner re-reading was their best technique. Two surfaces,
# two answers.
#
# At a floor of 0.62 the material term spans 1.6x, so it still decides among
# techniques the learner has no data on (the cold-start case, where it should
# decide), while a clear measured advantage can outweigh it — see _BETA below
# for how much of an advantage, and why that is a derived number.
_RANK_WEIGHTS = [1.0, 0.85, 0.72]
_MATERIAL_FLOOR = 0.62

# Techniques within this ratio of the day's best are treated as equally good,
# and the plan rotates among them across days. Rotation only ever happens inside
# that indifference band: a clearly better technique is never given up for
# variety. Expressed as a log margin because scoring happens in log space, where
# a *multiplicative* band is an additive offset — scaling a log score by 0.85
# is meaningless and inverts once scores go negative.
_ROTATION_BAND = 0.85
_ROTATION_MARGIN = -math.log(_ROTATION_BAND)

# How much the material context is allowed to tilt the choice, as an exponent on
# the material weight in log space:
#
#     score = log(S) + BETA · log(material_weight)
#
# BETA is derived, not tuned. It is fixed by one stated criterion: a technique
# the context does not call out at all (weight = the floor) should overturn a
# rank-1 material fit exactly when the learner's own measured stability for it
# is _EVIDENCE_OVERRIDE_RATIO times higher. Solving
# log(k·S) + BETA·log(floor) = log(S) gives BETA = log(k) / −log(floor).
#
# Why log space at all: the previous form multiplied the material weight by
# 7-day *retention*, which is bounded above by 1.0. A rank-1 technique scored
# 1.0·a and a floor technique at most 0.62·1.0 = 0.62, so once the ranked
# technique measured above 0.62 no possible evidence could overturn it — a
# learner whose practice testing was genuinely 3.3× more durable was still told
# to use active recall. Stability is unbounded above, so a large advantage can
# actually be expressed. (evaluation/monte_carlo.py --loop is the measurement.)
_EVIDENCE_OVERRIDE_RATIO = 3.0
_BETA = math.log(_EVIDENCE_OVERRIDE_RATIO) / -math.log(_MATERIAL_FLOOR)

# Applied to the prior stability of a technique this learner has never tried.
#
# A population average and a personal measurement are not the same kind of
# claim, and without a discount the higher-prior untried technique simply wins.
# Stated as a rule rather than a magic number: an untried technique has to be
# roughly 1/0.6 ≈ 1.7× more durable *in the literature* than what the learner
# has actually measured before the plan switches them to it.
#
# Limitation, stated rather than hidden: this is a flat stand-in for proper
# uncertainty weighting. eff_map carries point estimates with no sample size,
# so a measurement from two sessions gets the same standing as one from twenty.
# The real fix is to pass the posterior (which fingerprint_builder already
# computes) into the planner instead of a bare float.
_UNMEASURED_DISCOUNT = 0.6


def _implied_stability(retention_7d: float) -> float:
    """Ebbinghaus stability implied by a measured 7-day retention: R = e^(−7/S).

    Scoring happens in stability rather than retention because retention is
    bounded above by 1.0 and stability is not. Two techniques at 0.90 and 0.95
    retention look nearly identical on the bounded scale while differing by a
    factor of three in durability — and durability is the thing the schedule
    actually exploits.
    """
    r = min(max(retention_7d, 1e-3), 1.0 - 1e-6)
    return -7.0 / math.log(r)


def _material_weights(difficulty: str, concept_type: str) -> dict[str, float]:
    """Material prior: technique → fit weight in (0, 1] for this concept's context."""
    ordered = _CANDIDATES_BY_CONTEXT.get(
        (difficulty, concept_type),
        ["active_recall", "spaced_repetition", "practice_testing"],  # sensible default
    )
    weights: dict[str, float] = {}
    for i, tech in enumerate(ordered):
        weights[tech] = _RANK_WEIGHTS[i] if i < len(_RANK_WEIGHTS) else _MATERIAL_FLOOR
    return weights


def _technique_for_concept(
    difficulty:   str,
    concept_type: str,
    best_overall: str,
    eff_map:      dict[str, float],
    day_idx:      int = 0,
) -> str:
    """
    Match a technique to a concept by combining TWO signals:

        score(technique) = material_fit(technique) × learner_effectiveness(technique)

    - material_fit comes from the concept's (difficulty × type) context (Dunlosky).
    - learner_effectiveness comes from the fingerprint (measured 7d retention),
      defaulting to the research prior (personalization/priors.py) for
      techniques with no data yet.

    Cold start (no measured data): the pick is material_fit × research prior —
    the text's shape and the literature's technique ranking decide together,
    honestly, from session zero. As retention data accrues, the personal
    posterior replaces the prior and personalises the pick. Crucially,
    the learner's global-best technique no longer auto-wins just by appearing in
    the candidate list (the old behaviour, which flattened everything toward one
    technique) — it only wins where the material also supports it, or where the
    measured personal advantage is large enough to overcome a weaker material fit.
    """
    mat_w = _material_weights(difficulty, concept_type)
    techniques = set(mat_w) | set(eff_map) | {best_overall}

    def score(tech: str) -> float:
        measured = eff_map.get(tech)
        if measured is None:
            stability = prior_stability_days(tech) * _UNMEASURED_DISCOUNT
        else:
            stability = _implied_stability(measured)
        return math.log(stability) + _BETA * math.log(mat_w.get(tech, _MATERIAL_FLOOR))

    scored = sorted(
        techniques,
        # Deterministic ordering: score, then the learner's global best, then
        # name — so an identical fingerprint always yields an identical plan.
        key=lambda t: (score(t), t == best_overall, t),
        reverse=True,
    )
    top = score(scored[0])

    # Rotate across days among techniques the model cannot meaningfully
    # separate. Fourteen identical days is bad practice (varied practice is
    # itself a documented benefit) and bad product, but buying variety by
    # scheduling a technique the model rates clearly worse would be trading the
    # user's time for visual interest. The band is the compromise: vary only
    # where varying costs nothing.
    band = [t for t in scored if score(t) >= top - _ROTATION_MARGIN]
    return band[day_idx % len(band)]


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
    # Keyed by TECHNIQUE. `stabilities` is the fingerprint's per-technique
    # stability map (posterior median, OLS fallback), and this looked the
    # concept name up in it — a key that is never present, so every review's
    # urgency was computed from the 10-day default no matter what the learner's
    # own curve said. The rationale text beside it used the right value, so the
    # plan explained itself with one number and ordered itself by another.
    S    = stabilities.get(technique, _DEFAULT_S)
    R    = _retention(lag, S)
    eff  = eff_map.get(technique, prior_effectiveness(technique))
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


# ── Material profile ──────────────────────────────────────────────────────────

def _material_profile(knowledge_map: KnowledgeMap) -> MaterialProfile:
    """
    Aggregate the per-concept (type × difficulty) distribution into a single
    material-level cognitive profile, and name the technique the material as a
    whole leans toward (material signal only — no learner data involved).
    """
    concepts = knowledge_map.concepts
    n = len(concepts) or 1
    type_counts: dict[str, int] = defaultdict(int)
    diff_counts: dict[str, int] = defaultdict(int)
    for c in concepts:
        type_counts[c.concept_type] += 1
        diff_counts[c.difficulty] += 1

    type_mix = {k: round(v / n, 3) for k, v in type_counts.items()}
    diff_mix = {k: round(v / n, 3) for k, v in diff_counts.items()}

    dominant_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else "conceptual"
    dominant_diff = max(diff_counts, key=lambda k: diff_counts[k]) if diff_counts else "intermediate"

    # Technique the material leans toward, from the material prior alone.
    lead_weights = _material_weights(dominant_diff, dominant_type)
    lead = max(lead_weights, key=lambda k: lead_weights[k])

    type_pct = round(type_mix.get(dominant_type, 0.0) * 100)
    summary = (
        f"This material is mostly {dominant_type} at {dominant_diff} level "
        f"({type_pct}% {dominant_type}). Research favours "
        f"{lead.replace('_', ' ')} for this kind of content — "
        f"we weight it against your own measured strengths."
    )
    return MaterialProfile(
        dominant_type       = dominant_type,
        dominant_difficulty = dominant_diff,
        type_mix            = type_mix,
        difficulty_mix      = diff_mix,
        summary             = summary,
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
        days_since_last_study: Optional[float] = None,
        prior_sessions: int = 0,
    ) -> StudyPlanResponse:
        """
        Generate a personalised study plan.

        Parameters
        ----------
        user_id       : DB user identifier
        knowledge_map : extracted concept graph from Agent 1
        fingerprint   : cognitive fingerprint from Agent 2 (may be low-confidence)
        total_days    : planning horizon in days (e.g. derived from an exam date)
        days_since_last_study : if the user has studied this material before, how
            many days ago the most recent session was — enables adaptive resume.
        prior_sessions : number of prior sessions on this material. >0 switches the
            plan from "introduce everything fresh" to "resume": concepts are
            treated as already-encoded but decayed, so day 1 front-loads whatever
            is fading instead of re-teaching from scratch (§3.3).

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

        # Adaptive resume (§3.3): if the user has studied this material before,
        # don't re-introduce everything from scratch. Treat every concept as
        # already-encoded `days_since_last_study` days ago, so day 1's review
        # scoring — (1 − R(lag)) × effectiveness — front-loads whatever is
        # fading most. New introductions are skipped (the queue is drained).
        resuming = prior_sessions > 0
        if resuming:
            lag0 = int(round(days_since_last_study or 0.0))
            for c in ordered_concepts:
                seen.add(c.concept)
                last_studied[c.concept] = -lag0   # studied lag0 days before day 0
                next_review[c.concept] = 0        # all eligible for review on day 1
            introduction_queue = []               # nothing new to introduce

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
                tech = _technique_for_concept(
                    c.difficulty, c.concept_type, best_tech, eff_map, day_idx
                )
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
                tech = _technique_for_concept(
                    c.difficulty, c.concept_type, best_tech, eff_map, day_idx
                )
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

        # ── Material profile + general advice ──────────────────────────────────
        # The material profile drives material-aware surfacing and leads the
        # advice so the learner sees WHY these techniques were chosen for THIS text.
        material_profile = _material_profile(knowledge_map)
        resume_note = ""
        if resuming:
            gap = int(round(days_since_last_study or 0.0))
            when = "earlier today" if gap == 0 else f"{gap} day{'s' if gap != 1 else ''} ago"
            resume_note = (
                f"Resuming: you last studied this {when}. "
                "This plan picks up from today and front-loads whatever is fading most, "
                "rather than restarting from scratch.  "
            )
        general_advice = (
            resume_note
            + material_profile.summary
            + "  "
            + _build_general_advice(fingerprint, confidence, total_days, plan_days)
        )

        return StudyPlanResponse(
            user_id      = user_id,
            total_days   = total_days,
            days         = plan_days,
            general_advice = general_advice,
            material_profile = material_profile,
        )


def _build_general_advice(
    fp:         FingerprintProfile,
    confidence: object,
    total_days: int,
    plan_days:  list[StudyPlanDay],
) -> str:
    parts: list[str] = []

    if str(confidence) in ("low", "ConfidenceLevel.LOW"):
        # Name the techniques this plan actually contains rather than a fixed
        # pair. The hardcoded "active recall + spaced repetition" survived the
        # move to material-aware matching and had started describing a plan
        # that no longer existed — the screen said one thing and the fourteen
        # days below it said another.
        used = sorted({d.technique for d in plan_days if d.session_duration_minutes > 0})
        named = " + ".join(t.replace("_", " ") for t in used) or "evidence-based defaults"
        parts.append(
            f"This plan uses research-backed defaults ({named}) "
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
