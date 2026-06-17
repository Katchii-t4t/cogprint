import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId } from "../store";
import type { StudyPlanResponse, StudyPlanDay, PendingCheckItem } from "../types";
import { label } from "../insights";

const TECHNIQUE_ICONS: Record<string, string> = {
  spaced_repetition: "🔁",
  active_recall: "⚡",
  re_reading: "📖",
  mind_maps: "🗺️",
  interleaving: "🔀",
  elaborative_interrogation: "❓",
  practice_testing: "✏️",
};

const TIME_ICONS: Record<string, string> = {
  morning: "🌅",
  afternoon: "☀️",
  evening: "🌆",
  night: "🌙",
};

export default function Plan() {
  const [params] = useSearchParams();
  const materialId = params.get("m") ? Number(params.get("m")) : undefined;
  const navigate = useNavigate();

  const [plan, setPlan] = useState<StudyPlanResponse | null>(null);
  const [pending, setPending] = useState<PendingCheckItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }

    Promise.all([
      api.getStudyPlan(userId, materialId),
      api.getPendingChecks(userId),
    ])
      .then(([p, checks]) => {
        setPlan(p);
        setPending(checks);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [materialId, navigate]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState msg={error} onBack={() => navigate("/")} />;
  if (!plan) return null;

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full">
      {/* Header */}
      <div className="sticky top-0 z-10 glass px-4 pt-8 pb-4 border-b border-ink-500/40">
        <button onClick={() => navigate("/")} className="text-slate-500 text-sm mb-3 hover:text-slate-300">
          ← New material
        </button>
        <h1 className="text-xl font-bold text-white">Your 14-day plan</h1>
        <p className="text-slate-400 text-sm mt-1">{plan.general_advice}</p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 pb-32">
        {/* Pending checks banner */}
        {pending.length > 0 && (
          <div
            className="rounded-2xl p-4 border border-amber-500/30 bg-amber-950/20 cursor-pointer"
            onClick={() => navigate(`/checks?m=${materialId ?? ""}`)}
          >
            <p className="text-amber-300 font-medium text-sm">
              ⏰ {pending.length} retention check{pending.length > 1 ? "s" : ""} waiting
            </p>
            <p className="text-amber-400/60 text-xs mt-0.5">
              Tap to complete — these help train your fingerprint
            </p>
          </div>
        )}

        {plan.days.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            expanded={expanded === day.day}
            onToggle={() => setExpanded(expanded === day.day ? null : day.day)}
          />
        ))}
      </div>

      {/* CTA */}
      <div className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-lg px-4 pb-6 pt-4 glass border-t border-ink-500/30">
        <button
          onClick={() => navigate(materialId ? `/cards?m=${materialId}` : "/cards")}
          className="w-full py-4 rounded-2xl bg-neural text-ink-900 font-bold text-base
                     hover:bg-neural-glow active:scale-[0.98] transition-all"
        >
          Start flashcards →
        </button>
      </div>
    </div>
  );
}

function DayCard({
  day,
  expanded,
  onToggle,
}: {
  day: StudyPlanDay;
  expanded: boolean;
  onToggle: () => void;
}) {
  const icon = TECHNIQUE_ICONS[day.technique] ?? "📚";
  const timeIcon = TIME_ICONS[day.time_of_day] ?? "🕐";

  return (
    <div
      className="rounded-2xl bg-ink-700 neural-border p-4 cursor-pointer transition-all
                 hover:border-neural/30 active:scale-[0.99]"
      onClick={onToggle}
    >
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-ink-500 flex items-center justify-center text-xs font-bold text-neural shrink-0">
          {day.day}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span>{icon}</span>
            <span className="text-slate-200 font-medium text-sm truncate">
              {label(day.technique)}
            </span>
          </div>
          <p className="text-slate-500 text-xs mt-0.5 truncate">{day.topic_focus}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-slate-400 text-xs">{timeIcon} {day.session_duration_minutes}m</span>
          <span className="text-slate-600 text-xs">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded && (
        <p className="mt-3 text-slate-400 text-xs leading-relaxed border-t border-ink-500/40 pt-3">
          {day.rationale}
        </p>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Building your plan…</p>
    </div>
  );
}

function ErrorState({ msg, onBack }: { msg: string; onBack: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900 px-6">
      <p className="text-red-400 text-sm text-center">{msg}</p>
      <button onClick={onBack} className="text-neural text-sm">← Go back</button>
    </div>
  );
}
