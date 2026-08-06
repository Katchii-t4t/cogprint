import type {
  BayesianStabilityStats,
  FingerprintProfile,
  FingerprintResponse,
  TechniqueStats,
  TechniqueMemoryProfile,
} from "../types";

/**
 * Fingerprint fixtures.
 *
 * Built by overriding a neutral base rather than by hand-writing whole objects
 * per test: when the backend adds a field, one place needs updating, and a test
 * that says `{ confidence: "high" }` reads as the one thing it is actually
 * about.
 */

export function techniqueStats(
  technique: string,
  over: Partial<TechniqueStats> = {}
): TechniqueStats {
  return {
    technique,
    sessions_observed: 4,
    avg_immediate_score: 0.7,
    avg_retention_24h: 0.6,
    avg_retention_7d: 0.5,
    relative_effectiveness: "average",
    ...over,
  };
}

export function memoryProfile(
  technique: string,
  over: Partial<TechniqueMemoryProfile> = {}
): TechniqueMemoryProfile {
  return {
    technique,
    avg_stability_days: 5,
    stability_label: "good",
    predicted_retention_7d: 0.7,
    optimal_review_interval_days: 3,
    sessions_with_curve_data: 4,
    avg_7d_retention: 0.65,
    ...over,
  };
}

/** A posterior wide enough that Grow renders a visible "likely lo–hi%" band —
    the narrow-band case is filtered out as noise by design. */
export function stability(
  technique: string,
  over: Partial<BayesianStabilityStats> = {}
): BayesianStabilityStats {
  return {
    technique,
    posterior_mean_days: 11,
    posterior_median_days: 10,
    posterior_std_days: 3,
    ci_lower_days: 6,
    ci_upper_days: 18,
    n_observations: 9,
    population_informed: true,
    ...over,
  };
}

export function fingerprint(
  over: Partial<FingerprintProfile> = {}
): FingerprintProfile {
  return {
    session_count: 0,
    confidence: "low",
    technique_effectiveness: [],
    optimal_conditions: {
      best_time_of_day: null,
      optimal_session_duration_minutes: null,
      min_sleep_hours_recommended: null,
      max_stress_level_recommended: null,
      sleep_score_correlation: null,
      stress_score_correlation: null,
      duration_score_correlation: null,
    },
    recommended_techniques: [],
    recommended_session_duration_minutes: null,
    insights: [],
    data_gaps: [],
    improving_over_time: null,
    avg_score_trend_per_week: null,
    memory_profiles: [],
    technique_stability: [],
    bandit_expected_rewards: {},
    ...over,
  };
}

/** A fingerprint with enough measured signal that the real view has content to
    show — the interesting case for the RCT blind, since a control user must
    still get a screen that looks equally full. */
export function richFingerprint(
  over: Partial<FingerprintProfile> = {}
): FingerprintProfile {
  return fingerprint({
    session_count: 12,
    confidence: "high",
    technique_effectiveness: [
      techniqueStats("active_recall", {
        avg_immediate_score: 0.92,
        relative_effectiveness: "best",
      }),
      techniqueStats("practice_testing", {
        avg_immediate_score: 0.81,
        relative_effectiveness: "good",
      }),
      techniqueStats("re_reading", {
        avg_immediate_score: 0.44,
        relative_effectiveness: "poor",
      }),
    ],
    recommended_techniques: ["active_recall", "practice_testing"],
    insights: [
      "Which technique holds up after a week? Active recall, by a wide margin.",
      "You score higher in the morning. Move the hard material earlier.",
    ],
    memory_profiles: [
      memoryProfile("active_recall", {
        avg_stability_days: 11.4,
        predicted_retention_7d: 0.88,
        stability_label: "excellent",
      }),
      memoryProfile("re_reading", {
        avg_stability_days: 2.1,
        predicted_retention_7d: 0.31,
        stability_label: "fair",
      }),
    ],
    optimal_conditions: {
      ...fingerprint().optimal_conditions,
      best_time_of_day: "morning",
      optimal_session_duration_minutes: 30,
    },
    // The backend computes and returns these for every user regardless of RCT
    // arm, so a control fixture must carry them too — otherwise a test can
    // never observe them leaking into a control screen.
    technique_stability: [
      stability("active_recall"),
      stability("spaced_repetition"),
      stability("practice_testing"),
      stability("re_reading"),
      stability("elaborative_interrogation"),
    ],
    ...over,
  });
}

/**
 * Exactly what the backend sends a CONTROL participant — everything measured
 * stripped, only the session count and the count-derived confidence left.
 *
 * Using `richFingerprint` for a control test is the mistake worth naming: it
 * asserts against a payload the server will never produce, and it hid the fact
 * that the client's whole fingerprint screen is gated on
 * `confidence !== "low"`. Mirror the real blinded shape here, or control tests
 * prove nothing.
 */
export function blindedFingerprint(
  sessionCount: number,
  confidence: FingerprintProfile["confidence"] = "high"
): FingerprintProfile {
  return fingerprint({
    session_count: sessionCount,
    confidence,
    insights: ["Keep up your regular study routine."],
    data_gaps: ["Personalisation not enabled for this study group."],
  });
}

export function fingerprintResponse(
  userId: number,
  fp: FingerprintProfile,
  over: Partial<FingerprintResponse> = {}
): FingerprintResponse {
  return {
    user_id: userId,
    fingerprint: fp,
    updated_at: "2026-08-06T10:00:00Z",
    rebuild_status: "ok",
    rebuild_at: "2026-08-06T10:00:00Z",
    ...over,
  };
}
