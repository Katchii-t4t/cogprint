import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, getState } from "../store";
import { buildView, label, type InsightView } from "../insights";

const EFFECTIVENESS_COLORS: Record<string, string> = {
  best: "bg-neural",
  good: "bg-cyan-600",
  average: "bg-slate-500",
  poor: "bg-slate-700",
};

export default function Grow() {
  const [params] = useSearchParams();
  const score = params.get("score");
  const navigate = useNavigate();

  const [view, setView] = useState<InsightView | null>(null);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }

    const { group } = getState();

    Promise.all([
      api.getFingerprint(userId),
      api.getPendingChecks(userId),
    ])
      .then(([fingerprint, checks]) => {
        setView(buildView(fingerprint.fingerprint, group ?? "treatment"));
        setPending(checks.length);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) return <LoadingState />;

  const v = view;
  const sessionCount = v?.sessionCount ?? 0;
  const confidence = v?.confidence ?? "low";

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full">
      {/* Header */}
      <div className="px-4 pt-8 pb-4">
        <div className="flex items-center justify-between mb-6">
          <button onClick={() => navigate("/")} className="text-slate-500 text-sm hover:text-slate-300">
            ← Paste more
          </button>
          <button
            onClick={() => navigate("/plan")}
            className="text-neural text-sm"
          >
            Study plan →
          </button>
        </div>

        {/* Score banner */}
        {score !== null && (
          <div className="rounded-2xl bg-ink-700 neural-border p-4 mb-4 animate-fade-up">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{Number(score) >= 80 ? "🔥" : Number(score) >= 50 ? "💪" : "📈"}</span>
              <div>
                <p className="text-white font-bold">{score}% correct this session</p>
                <p className="text-slate-400 text-xs">
                  {Number(score) >= 80
                    ? "Excellent retention — your fingerprint is growing."
                    : "Every session teaches the algorithm something new."}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Pending checks */}
        {pending > 0 && (
          <div
            className="rounded-2xl bg-amber-950/20 border border-amber-500/30 p-4 mb-4 cursor-pointer"
            onClick={() => navigate("/checks")}
          >
            <p className="text-amber-300 font-medium text-sm">
              ⏰ {pending} retention check{pending > 1 ? "s" : ""} due
            </p>
            <p className="text-amber-400/60 text-xs mt-0.5">
              Complete them to improve your fingerprint accuracy
            </p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-24 space-y-6">
        {/* Fingerprint header */}
        <div className="animate-fade-up">
          <h1 className="text-2xl font-bold text-white">Your fingerprint</h1>
          <div className="flex items-center gap-2 mt-1">
            <ConfidencePill confidence={confidence} />
            <span className="text-slate-500 text-xs">{sessionCount} session{sessionCount !== 1 ? "s" : ""}</span>
          </div>
        </div>

        {/* Low confidence — growing state */}
        {confidence === "low" && (
          <GrowingState sessionCount={sessionCount} onStudy={() => navigate("/")} />
        )}

        {/* Medium / high — full fingerprint */}
        {confidence !== "low" && v && (
          <>
            {/* Top technique */}
            {v.topTechnique && (
              <Section title="Best technique for you">
                <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-neural/10 border border-neural/20 flex items-center justify-center">
                    <span className="text-neural text-lg">⚡</span>
                  </div>
                  <div>
                    <p className="text-white font-semibold">{label(v.topTechnique)}</p>
                    {v.bestTimeOfDay && (
                      <p className="text-slate-400 text-xs mt-0.5">
                        Best time: {v.bestTimeOfDay}
                      </p>
                    )}
                  </div>
                </div>
              </Section>
            )}

            {/* Technique bars */}
            {v.techniqueRows.length > 0 && (
              <Section title="Technique effectiveness">
                <div className="space-y-3">
                  {v.techniqueRows.map((row) => (
                    <div key={row.technique}>
                      <div className="flex justify-between mb-1">
                        <span className="text-slate-300 text-xs">{label(row.technique)}</span>
                        {row.label && (
                          <span
                            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                              row.label === "best"
                                ? "text-neural bg-neural/10"
                                : row.label === "good"
                                ? "text-cyan-400 bg-cyan-900/20"
                                : "text-slate-500 bg-slate-800"
                            }`}
                          >
                            {row.label}
                          </span>
                        )}
                      </div>
                      <div className="h-1.5 bg-ink-500 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${
                            EFFECTIVENESS_COLORS[row.label ?? "average"]
                          }`}
                          style={{ width: `${row.barFraction * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Retention / memory profiles */}
            {v.retentionRows.length > 0 && (
              <Section title="Memory stability per technique">
                <div className="grid grid-cols-2 gap-3">
                  {v.retentionRows.map((r) => (
                    <div
                      key={r.technique}
                      className="rounded-2xl bg-ink-700 neural-border p-3 flex flex-col gap-1"
                    >
                      <p className="text-slate-400 text-[10px] font-medium uppercase tracking-wider">
                        {label(r.technique)}
                      </p>
                      <p className="text-white font-bold text-xl">
                        {Math.round(r.predicted7d * 100)}%
                      </p>
                      <p className="text-slate-500 text-[10px]">at 7 days · {r.label}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Insights */}
            {v.insights.length > 0 && (
              <Section title="What your data says">
                <div className="space-y-3">
                  {v.insights.map((ins, i) => (
                    <div
                      key={i}
                      className="rounded-2xl bg-ink-700 neural-border p-4"
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <p className="text-slate-200 text-sm leading-relaxed">{ins.text}</p>
                      {ins.action && (
                        <p className="text-neural text-xs mt-2 font-medium">→ {ins.action}</p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Trend */}
            {v.improving !== null && (
              <Section title="Trend">
                <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-center gap-3">
                  <span className="text-2xl">{v.improving ? "📈" : "📊"}</span>
                  <p className="text-slate-300 text-sm">
                    {v.improving
                      ? "You're improving over time. Keep the streak going."
                      : "Your scores are stable. Try mixing techniques to break through."}
                  </p>
                </div>
              </Section>
            )}
          </>
        )}
      </div>

      {/* Bottom CTA */}
      <div className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-lg px-4 pb-6 pt-4 glass border-t border-ink-500/30">
        <button
          onClick={() => navigate("/")}
          className="w-full py-4 rounded-2xl bg-ink-600 border border-ink-400 text-slate-200 font-semibold
                     hover:bg-ink-500 active:scale-[0.98] transition-all"
        >
          + Study more material
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="animate-fade-up">
      <p className="text-slate-500 text-xs font-medium uppercase tracking-widest mb-3">{title}</p>
      {children}
    </div>
  );
}

function ConfidencePill({ confidence }: { confidence: string }) {
  const styles: Record<string, string> = {
    low: "bg-slate-800 text-slate-400",
    medium: "bg-neural-muted text-neural",
    high: "bg-neural/20 text-neural border border-neural/30",
  };
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-widest ${styles[confidence]}`}>
      {confidence} confidence
    </span>
  );
}

function GrowingState({ sessionCount, onStudy }: { sessionCount: number; onStudy: () => void }) {
  const needed = Math.max(0, 5 - sessionCount);
  const fraction = Math.min(1, sessionCount / 5);

  return (
    <div className="rounded-3xl bg-ink-700 neural-border p-6 flex flex-col items-center gap-6 animate-fade-up">
      {/* Fingerprint bloom animation */}
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 128 128" className="w-full h-full">
          {/* Outer rings — grow with data */}
          {[48, 38, 28, 18].map((r, i) => (
            <circle
              key={r}
              cx="64"
              cy="64"
              r={r}
              fill="none"
              stroke="#22d3ee"
              strokeWidth="1"
              strokeDasharray={`${2 * Math.PI * r}`}
              strokeDashoffset={`${2 * Math.PI * r * (1 - fraction * (1 - i * 0.18))}`}
              opacity={0.2 + i * 0.15}
              className="transition-all duration-1000"
            />
          ))}
          {/* Core */}
          <circle cx="64" cy="64" r="8" fill="rgba(34,211,238,0.2)" />
          <circle cx="64" cy="64" r="4" fill="#22d3ee" className="breathe" />
        </svg>
      </div>

      <div className="text-center">
        <p className="text-white font-semibold">Your fingerprint is growing</p>
        <p className="text-slate-400 text-sm mt-1">
          {needed > 0
            ? `${needed} more session${needed !== 1 ? "s" : ""} to unlock your first insights`
            : "Processing your first insights…"}
        </p>
      </div>

      <button
        onClick={onStudy}
        className="w-full py-3 rounded-xl bg-neural/10 border border-neural/20 text-neural text-sm font-medium
                   hover:bg-neural/20 active:scale-[0.98] transition-all"
      >
        Study more →
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Loading your fingerprint…</p>
    </div>
  );
}
