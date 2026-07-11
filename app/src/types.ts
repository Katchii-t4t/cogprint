export type StudyGroup = "control" | "treatment";
export type StudyTechnique =
  | "spaced_repetition"
  | "active_recall"
  | "re_reading"
  | "mind_maps"
  | "interleaving"
  | "elaborative_interrogation"
  | "practice_testing";
export type TimeOfDay = "morning" | "afternoon" | "evening" | "night";
export type ConfidenceLevel = "low" | "medium" | "high";

export interface User {
  id: number;
  group: StudyGroup;
  pre_test_score: number | null;
  post_test_score: number | null;
  created_at: string;
}

export interface StudySession {
  id: number;
  user_id: number;
  material_id: number | null;
  technique: StudyTechnique;
  duration_minutes: number;
  time_of_day: TimeOfDay;
  sleep_hours: number | null;
  stress_level: number | null;
  quiz_score: number;
  created_at: string;
}

export interface RetentionCheck {
  id: number;
  session_id: number;
  user_id: number;
  check_type: "24h" | "7d";
  score: number;
  checked_at: string;
}

export interface TechniqueStats {
  technique: string;
  sessions_observed: number;
  avg_immediate_score: number | null;
  avg_retention_24h: number | null;
  avg_retention_7d: number | null;
  relative_effectiveness: "best" | "good" | "average" | "poor" | null;
}

export interface OptimalConditions {
  best_time_of_day: string | null;
  optimal_session_duration_minutes: number | null;
  min_sleep_hours_recommended: number | null;
  max_stress_level_recommended: number | null;
  sleep_score_correlation: number | null;
  stress_score_correlation: number | null;
  duration_score_correlation: number | null;
}

export interface TechniqueMemoryProfile {
  technique: string;
  avg_stability_days: number;
  stability_label: string;
  predicted_retention_7d: number;
  optimal_review_interval_days: number;
  sessions_with_curve_data: number;
  avg_7d_retention: number | null;
}

export interface BayesianStabilityStats {
  technique: string;
  posterior_mean_days: number;
  posterior_median_days: number;
  posterior_std_days: number;
  ci_lower_days: number;
  ci_upper_days: number;
  n_observations: number;
  population_informed: boolean;
}

export interface FingerprintProfile {
  session_count: number;
  confidence: ConfidenceLevel;
  technique_effectiveness: TechniqueStats[];
  optimal_conditions: OptimalConditions;
  recommended_techniques: string[];
  recommended_session_duration_minutes: number | null;
  insights: string[];
  data_gaps: string[];
  improving_over_time: boolean | null;
  avg_score_trend_per_week: number | null;
  memory_profiles: TechniqueMemoryProfile[];
  technique_stability: BayesianStabilityStats[];
  bandit_expected_rewards: Record<string, number>;
}

export interface FingerprintResponse {
  user_id: number;
  fingerprint: FingerprintProfile;
  updated_at: string;
}

export interface StudyPlanDay {
  day: number;
  technique: string;
  topic_focus: string;
  session_duration_minutes: number;
  time_of_day: string;
  rationale: string;
}

export interface StudyPlanResponse {
  user_id: number;
  total_days: number;
  days: StudyPlanDay[];
  general_advice: string;
}

export interface KnowledgeConcept {
  concept: string;
  difficulty: string;
  concept_type: string;
  related_concepts: string[];
}

export interface KnowledgeMap {
  title: string;
  total_concepts: number;
  concepts: KnowledgeConcept[];
  suggested_study_order: string[];
}

export interface MaterialAnalysisResponse {
  material_id: number;
  knowledge_map: KnowledgeMap;
}

export interface PendingCheckItem {
  session_id: number;
  check_type: "24h" | "7d";
  session_date: string;
  due_date: string;
}

export interface Flashcard {
  id: number;
  question: string;
  answer: string;
  concept: string;
  difficulty: string;
  flagged: boolean;
}

export interface ShareCodeResponse {
  user_id: number;
  share_code: string;
}

/** #9 study-buddy — privacy-safe summary only (no content or raw scores). */
export interface BuddyForecast {
  share_code: string;
  confidence: ConfidenceLevel;
  session_count: number;
  fading: number;
  cooling: number;
  solid: number;
  reviews_due: number;
}

export interface QuestionsResponse {
  material_id: number;
  title: string;
  cards: Flashcard[];
  generated_by: string;
}
