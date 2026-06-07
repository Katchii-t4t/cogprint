import { useEffect, useState } from "react";
import { getFingerprint } from "../api";
import Layout from "../components/Layout";
import type { FingerprintProfile, TechniqueStats } from "../types";

const CONFIDENCE_CONFIG = {
  low:    { label: "Getting started",        color: "bg-gray-100 text-gray-700",    bar: "bg-gray-400"    },
  medium: { label: "Learning your patterns", color: "bg-amber-100 text-amber-700",  bar: "bg-amber-400"   },
  high:   { label: "Fully personalized",     color: "bg-green-100 text-green-700",  bar: "bg-green-500"   },
};

const EFFECTIVENESS_COLORS = {
  best:    "text-green-700 bg-green-50",
  good:    "text-blue-700 bg-blue-50",
  average: "text-gray-600 bg-gray-100",
  poor:    "text-red-600 bg-red-50",
};

function pct(v: number | null | undefined) {
  return v !== null && v !== undefined ? `${Math.round(v * 100)}%` : "—";
}

function corr(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}

function ScoreBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-gray-400 text-xs">no data</span>;
  const width = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full bg-brand-500 rounded-full" style={{ width: `${width}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-700 w-8 text-right">{width}%</span>
    </div>
  );
}

export default function FingerprintPage() {
  const userId = Number(localStorage.getItem("cogprint_user_id"));
  const [fp, setFp] = useState<FingerprintProfile | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getFingerprint(userId)
      .then((r) => { setFp(r.fingerprint); setUpdatedAt(r.updated_at); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) {
    return (
      <Layout>
        <p className="text-gray-400 text-sm">Loading fingerprint…</p>
      </Layout>
    );
  }

  if (!fp) {
    return (
      <Layout>
        <p className="text-gray-500">Could not load fingerprint.</p>
      </Layout>
    );
  }

  const conf = CONFIDENCE_CONFIG[fp.confidence];

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Your Cognitive Fingerprint</h1>
            {updatedAt && (
              <p className="text-xs text-gray-400 mt-1">
                Last updated: {new Date(updatedAt).toLocaleString()}
              </p>
            )}
          </div>
          <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${conf.color}`}>
            {conf.label}
          </span>
        </div>

        {/* Confidence progress */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex justify-between text-sm mb-2">
            <span className="font-medium text-gray-700">Personalization progress</span>
            <span className="text-gray-500">{fp.session_count} sessions</span>
          </div>
          <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${conf.bar}`}
              style={{ width: `${Math.min(100, (fp.session_count / 20) * 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-1.5">
            <span>0</span><span>5 (basic)</span><span>16 (full)</span>
          </div>
        </div>

        {fp.confidence === "low" && (
          <div className="bg-gray-50 border border-dashed border-gray-300 rounded-xl p-5 text-center">
            <p className="text-sm text-gray-500">
              Complete {5 - fp.session_count} more session{5 - fp.session_count !== 1 ? "s" : ""} to unlock personalized insights.
            </p>
            {fp.data_gaps.length > 0 && (
              <ul className="mt-3 space-y-1">
                {fp.data_gaps.map((g, i) => (
                  <li key={i} className="text-xs text-gray-400">• {g}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {fp.confidence !== "low" && (
          <>
            {/* Insights */}
            {fp.insights.length > 0 && (
              <div className="bg-brand-50 border border-brand-100 rounded-xl p-5">
                <h2 className="font-semibold text-brand-800 mb-3">Key insights</h2>
                <ul className="space-y-2">
                  {fp.insights.map((ins, i) => (
                    <li key={i} className="text-sm text-brand-900 flex gap-2">
                      <span>💡</span> {ins}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Technique effectiveness */}
            {fp.technique_effectiveness.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h2 className="font-semibold text-gray-900 mb-4">Technique effectiveness</h2>
                <p className="text-xs text-gray-400 mb-3">
                  Primary metric: 7-day retention (true measure of learning)
                </p>
                <div className="space-y-4">
                  {fp.technique_effectiveness.map((t: TechniqueStats) => (
                    <div key={t.technique}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium capitalize">
                            {t.technique.replace(/_/g, " ")}
                          </span>
                          {t.relative_effectiveness && (
                            <span
                              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                EFFECTIVENESS_COLORS[t.relative_effectiveness]
                              }`}
                            >
                              {t.relative_effectiveness}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-400">n={t.sessions_observed}</span>
                      </div>
                      <div className="space-y-1.5 pl-1">
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-gray-400 w-20 shrink-0">Immediate</span>
                          <div className="flex-1">
                            <ScoreBar value={t.avg_immediate_score} />
                          </div>
                        </div>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-gray-400 w-20 shrink-0">24h retention</span>
                          <div className="flex-1">
                            <ScoreBar value={t.avg_retention_24h} />
                          </div>
                        </div>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-gray-500 font-medium w-20 shrink-0">7d retention</span>
                          <div className="flex-1">
                            <ScoreBar value={t.avg_retention_7d} />
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Optimal conditions */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <h2 className="font-semibold text-gray-900 mb-4">Optimal study conditions</h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <ConditionRow
                  label="Best time of day"
                  value={fp.optimal_conditions.best_time_of_day ?? "—"}
                />
                <ConditionRow
                  label="Ideal session length"
                  value={
                    fp.optimal_conditions.optimal_session_duration_minutes
                      ? `${fp.optimal_conditions.optimal_session_duration_minutes} min`
                      : "—"
                  }
                />
                <ConditionRow
                  label="Min sleep recommended"
                  value={
                    fp.optimal_conditions.min_sleep_hours_recommended
                      ? `${fp.optimal_conditions.min_sleep_hours_recommended}h`
                      : "—"
                  }
                />
                <ConditionRow
                  label="Max stress recommended"
                  value={
                    fp.optimal_conditions.max_stress_level_recommended
                      ? `${fp.optimal_conditions.max_stress_level_recommended}/5`
                      : "—"
                  }
                />
              </div>

              <div className="mt-4 pt-4 border-t space-y-2">
                <p className="text-xs font-medium text-gray-500 mb-2">Correlation with quiz score (Pearson r)</p>
                <CorrRow label="Sleep hours" value={fp.optimal_conditions.sleep_score_correlation} positive />
                <CorrRow label="Stress level" value={fp.optimal_conditions.stress_score_correlation} positive={false} />
                <CorrRow label="Session duration" value={fp.optimal_conditions.duration_score_correlation} positive />
              </div>
            </div>

            {/* Trend */}
            {fp.improving_over_time !== null && (
              <div
                className={`rounded-xl border p-4 flex gap-3 items-center ${
                  fp.improving_over_time
                    ? "bg-green-50 border-green-200"
                    : "bg-red-50 border-red-200"
                }`}
              >
                <span className="text-xl">{fp.improving_over_time ? "📈" : "📉"}</span>
                <div>
                  <p className={`font-medium text-sm ${fp.improving_over_time ? "text-green-800" : "text-red-800"}`}>
                    {fp.improving_over_time ? "You're improving over time" : "Scores have been declining"}
                  </p>
                  {fp.avg_score_trend_per_week !== null && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      {fp.avg_score_trend_per_week > 0 ? "+" : ""}
                      {(fp.avg_score_trend_per_week * 100).toFixed(1)}% per week
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Data gaps */}
            {fp.data_gaps.length > 0 && (
              <div className="bg-gray-50 rounded-xl border border-dashed border-gray-300 p-4">
                <h3 className="text-sm font-medium text-gray-600 mb-2">Data gaps</h3>
                <ul className="space-y-1">
                  {fp.data_gaps.map((g, i) => (
                    <li key={i} className="text-xs text-gray-400">• {g}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}

function ConditionRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-medium text-gray-800 mt-0.5 capitalize">{value}</p>
    </div>
  );
}

function CorrRow({
  label,
  value,
  positive,
}: {
  label: string;
  value: number | null | undefined;
  positive: boolean;
}) {
  const isSignificant = value !== null && value !== undefined && Math.abs(value) >= 0.2;
  const isGood = isSignificant && (positive ? value! > 0 : value! < 0);
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span
        className={`font-mono font-medium ${
          !isSignificant
            ? "text-gray-400"
            : isGood
            ? "text-green-600"
            : "text-red-500"
        }`}
      >
        {value !== null && value !== undefined ? corr(value) : "—"}
      </span>
    </div>
  );
}
