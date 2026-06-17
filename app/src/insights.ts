import type { FingerprintProfile, TechniqueStats } from "./types";

export interface InsightView {
  confidence: "low" | "medium" | "high";
  sessionCount: number;
  topTechnique: string | null;
  bestTimeOfDay: string | null;
  improving: boolean | null;
  insights: Array<{ text: string; action: string }>;
  techniqueRows: Array<{
    technique: string;
    label: string | null;
    barFraction: number;
  }>;
  retentionRows: Array<{
    technique: string;
    stabilityDays: number;
    label: string;
    predicted7d: number;
  }>;
}

const TECHNIQUE_LABELS: Record<string, string> = {
  spaced_repetition: "Spaced Repetition",
  active_recall: "Active Recall",
  re_reading: "Re-reading",
  mind_maps: "Mind Maps",
  interleaving: "Interleaving",
  elaborative_interrogation: "Elaborative Q&A",
  practice_testing: "Practice Testing",
};

export function label(t: string) {
  return TECHNIQUE_LABELS[t] ?? t.replace(/_/g, " ");
}

function parseInsight(raw: string): { text: string; action: string } {
  const q = raw.indexOf("?");
  if (q !== -1 && q < raw.length - 1) {
    return { text: raw.slice(0, q + 1), action: raw.slice(q + 2).trim() };
  }
  return { text: raw, action: "" };
}

export function buildRealView(fp: FingerprintProfile): InsightView {
  const topTech =
    fp.recommended_techniques.length > 0 ? fp.recommended_techniques[0] : null;

  const allScores = fp.technique_effectiveness
    .map((t: TechniqueStats) => t.avg_immediate_score ?? 0)
    .filter((s) => s > 0);
  const maxScore = allScores.length ? Math.max(...allScores) : 1;

  const techniqueRows = fp.technique_effectiveness.map((t) => ({
    technique: t.technique,
    label: t.relative_effectiveness,
    barFraction: maxScore > 0 ? (t.avg_immediate_score ?? 0) / maxScore : 0,
  }));

  const retentionRows = fp.memory_profiles.map((m) => ({
    technique: m.technique,
    stabilityDays: m.avg_stability_days,
    label: m.stability_label,
    predicted7d: m.predicted_retention_7d,
  }));

  const insights = fp.insights.map(parseInsight);

  return {
    confidence: fp.confidence,
    sessionCount: fp.session_count,
    topTechnique: topTech,
    bestTimeOfDay: fp.optimal_conditions.best_time_of_day,
    improving: fp.improving_over_time,
    insights,
    techniqueRows,
    retentionRows,
  };
}

const SHAM_INSIGHTS = [
  {
    text: "Mixing techniques across sessions tends to improve long-term retention.",
    action: "Try a different technique next time.",
  },
  {
    text: "Morning sessions are often associated with stronger encoding.",
    action: "Schedule your next session before noon.",
  },
  {
    text: "Short, focused sessions (25–40 min) typically outperform marathon sessions.",
    action: "Set a 30-minute timer for your next session.",
  },
  {
    text: "Sleep consolidates memory — studying just before sleep can help.",
    action: "Try reviewing key concepts right before bed tonight.",
  },
];

export function buildShamView(fp: FingerprintProfile): InsightView {
  return {
    confidence: fp.confidence,
    sessionCount: fp.session_count,
    topTechnique: "spaced_repetition",
    bestTimeOfDay: "morning",
    improving: null,
    insights: SHAM_INSIGHTS,
    techniqueRows: [],
    retentionRows: [],
  };
}

export function buildView(fp: FingerprintProfile, group: "control" | "treatment"): InsightView {
  return group === "treatment" ? buildRealView(fp) : buildShamView(fp);
}
