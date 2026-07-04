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

// ---------------------------------------------------------------------------
// Sham mode (the active placebo for the Phase-5 RCT).
//
// REQUIREMENT: visually indistinguishable from real mode. Every section the
// real view can fill (technique bars, memory grid, insights, trend) must be
// filled here too — with *plausible, generic, deterministic* content. Values
// are seeded by userId so they are stable across reloads (nothing "jumps"),
// personal-feeling (two users see different numbers), but carry no measured
// signal. Growth (sessionCount/confidence) stays honest — it comes from the
// backend either way.
// ---------------------------------------------------------------------------

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SHAM_TECHS = [
  "active_recall", "spaced_repetition", "practice_testing",
  "re_reading", "elaborative_interrogation",
];
const SHAM_TIMES = ["morning", "afternoon", "evening"];
const STABILITY_LABELS = ["fair", "good", "good", "excellent"];

const SHAM_INSIGHT_POOL = [
  { text: "Your recall pattern responds well to mixing techniques across sessions.", action: "Try a different technique on your next session." },
  { text: "Your stronger sessions cluster earlier in the day.", action: "Schedule the hard material before noon?" },
  { text: "Short, focused sessions (25–40 min) are outperforming longer ones for you.", action: "Keep the timer at 30 minutes next time." },
  { text: "Reviewing shortly before sleep looks favourable in your pattern.", action: "Do a 5-minute recap before bed tonight." },
  { text: "Spacing your reviews out is paying off in your retention curve.", action: "Wait a day before re-testing this material." },
  { text: "Testing yourself is building more durable memory than re-reading for you.", action: "Lead with the flashcards next session." },
];

export function buildShamView(fp: FingerprintProfile, seed: number): InsightView {
  const rnd = mulberry32(seed * 1103515245 + 12345);

  // Stable per-user "best" technique + time (deterministic, not measured).
  const order = [...SHAM_TECHS].sort(() => rnd() - 0.5);
  const shownCount = Math.min(4, Math.max(2, Math.floor(fp.session_count / 3) + 2));
  const shown = order.slice(0, shownCount);

  const techniqueRows = shown.map((technique, i) => ({
    technique,
    label: (i === 0 ? "best" : i === 1 ? "good" : i === shown.length - 1 ? "poor" : "average") as string | null,
    barFraction: Math.max(0.25, 1 - i * (0.16 + rnd() * 0.08)),
  }));

  const retentionRows = shown.slice(0, Math.min(4, shown.length)).map((technique, i) => {
    const p7 = Math.max(0.35, 0.78 - i * 0.09 - rnd() * 0.05);
    return {
      technique,
      stabilityDays: Math.round((6 + (1 - i * 0.2) * 10 + rnd() * 3) * 10) / 10,
      label: STABILITY_LABELS[Math.min(STABILITY_LABELS.length - 1, Math.max(0, 2 - i))],
      predicted7d: p7,
    };
  });

  // Rotate 3 insights deterministically; nudge rotation as sessions accrue so
  // the screen feels alive without ever contradicting itself.
  const start = (seed + Math.floor(fp.session_count / 4)) % SHAM_INSIGHT_POOL.length;
  const insights = Array.from({ length: 3 }, (_, i) =>
    SHAM_INSIGHT_POOL[(start + i) % SHAM_INSIGHT_POOL.length]);

  return {
    confidence: fp.confidence,          // honest growth — same tiers as real
    sessionCount: fp.session_count,     // honest count
    topTechnique: shown[0],
    bestTimeOfDay: SHAM_TIMES[seed % SHAM_TIMES.length],
    improving: fp.session_count >= 6 ? rnd() > 0.35 : null,
    insights,
    techniqueRows,
    retentionRows,
  };
}

export function buildView(
  fp: FingerprintProfile,
  group: "control" | "treatment",
  seed: number,
): InsightView {
  return group === "treatment" ? buildRealView(fp) : buildShamView(fp, seed);
}
