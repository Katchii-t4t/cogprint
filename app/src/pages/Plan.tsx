import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, lastMaterialId as storedMaterialId } from "../store";
import type { StudyPlanResponse, StudyPlanDay, PendingCheckItem } from "../types";
import { label } from "../insights";
import { DELIVERABLE_MODES, resolveMode } from "../study";

/** #3 "why this card, why now" — the retention math behind a scheduled day. */
interface TechniqueWhy {
  retention7d: number;
  intervalDays: number;
}

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
  const materialId = params.get("m") ? Number(params.get("m")) : storedMaterialId();
  const navigate = useNavigate();

  const [plan, setPlan] = useState<StudyPlanResponse | null>(null);
  const [pending, setPending] = useState<PendingCheckItem[]>([]);
  const [whyByTechnique, setWhyByTechnique] = useState<Record<string, TechniqueWhy>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  // Chosen study mode for the next round; defaults to the plan's day-1 technique.
  const [chosenTechnique, setChosenTechnique] = useState<string | null>(null);

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }
    if (!materialId) {
      // No material to plan around — send the user back to paste one.
      navigate("/");
      return;
    }

    Promise.all([
      api.getStudyPlan(userId, materialId),
      api.getPendingChecks(userId),
      api.getFingerprint(userId).catch(() => null),
    ])
      .then(([p, checks, fp]) => {
        setPlan(p);
        setPending(checks);
        if (fp) {
          // Map each technique to its retention math for the "why now" chip.
          const map: Record<string, TechniqueWhy> = {};
          for (const m of fp.fingerprint.memory_profiles) {
            map[m.technique] = {
              retention7d: m.predicted_retention_7d,
              intervalDays: m.optimal_review_interval_days,
            };
          }
          setWhyByTechnique(map);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [materialId, navigate]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState msg={error} onBack={() => navigate("/")} />;
  if (!plan) return null;

  // Effective mode = user's choice, else the plan's day-1 recommendation.
  const effectiveMode = resolveMode(chosenTechnique ?? plan.days[0]?.technique);

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full">
      {/* Header */}
      <div className="sticky top-0 z-10 glass px-4 pt-8 pb-4 border-b border-ink-500/40">
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => navigate("/")} className="text-slate-500 text-sm hover:text-slate-300">
            ← New material
          </button>
          {materialId && <ShareDeckButton materialId={materialId} />}
        </div>
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
            why={whyByTechnique[day.technique] ?? null}
            expanded={expanded === day.day}
            onToggle={() => setExpanded(expanded === day.day ? null : day.day)}
          />
        ))}
      </div>

      {/* CTA */}
      <div className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-lg px-4 pb-6 pt-4 glass border-t border-ink-500/30 space-y-3">
        {/* Study-mode picker — the honest fix for "always active recall". Defaults
            to the plan's recommended technique; the technique you pick is carried
            through Study → the round and logged as the session's technique. */}
        <ModePicker
          selected={effectiveMode.technique}
          recommended={resolveMode(plan.days[0]?.technique).technique}
          onSelect={setChosenTechnique}
        />
        {/* Begin = read/focus first (Study), which carries the mode into the round. */}
        <button
          onClick={() =>
            navigate(
              materialId
                ? `/study?m=${materialId}&mode=${effectiveMode.technique}`
                : `/study?mode=${effectiveMode.technique}`
            )
          }
          className="w-full py-4 rounded-2xl bg-neural text-ink-900 font-bold text-base
                     hover:bg-neural-glow active:scale-[0.98] transition-all"
        >
          Begin {effectiveMode.label} →
        </button>
        <button
          onClick={() =>
            navigate(
              materialId
                ? `/cards?m=${materialId}&mode=${effectiveMode.technique}`
                : `/cards?mode=${effectiveMode.technique}`
            )
          }
          className="w-full text-slate-500 text-xs hover:text-slate-300 text-center"
        >
          Skip straight to the round
        </button>
      </div>
    </div>
  );
}

function DayCard({
  day,
  why,
  expanded,
  onToggle,
}: {
  day: StudyPlanDay;
  why: TechniqueWhy | null;
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
        <div className="mt-3 border-t border-ink-500/40 pt-3 space-y-2">
          {/* #3 why this card, why now — the retention math made explicit */}
          {why && (
            <p className="text-neural text-xs font-medium">
              🧠 Why now: {label(day.technique)} holds ~{Math.round(why.retention7d * 100)}%
              at 7 days for you; its review window is ~{Math.round(why.intervalDays)} day
              {Math.round(why.intervalDays) !== 1 ? "s" : ""}.
            </p>
          )}
          <p className="text-slate-400 text-xs leading-relaxed">{day.rationale}</p>
        </div>
      )}
    </div>
  );
}

function ModePicker({
  selected,
  recommended,
  onSelect,
}: {
  selected: string;
  recommended: string;
  onSelect: (technique: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar">
      {DELIVERABLE_MODES.map((m) => {
        const active = m.technique === selected;
        return (
          <button
            key={m.technique}
            onClick={() => onSelect(m.technique)}
            className={`shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium
                        border transition-all active:scale-[0.97] ${
              active
                ? "bg-neural/15 border-neural/40 text-neural"
                : "bg-ink-700 border-ink-500/40 text-slate-400 hover:text-slate-200"
            }`}
            title={m.instruction}
          >
            <span>{m.emoji}</span>
            {m.label}
            {m.technique === recommended && (
              <span className="text-[9px] px-1 py-px rounded-full bg-neural/20 text-neural uppercase tracking-wider">
                rec
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function ShareDeckButton({ materialId }: { materialId: number }) {
  const [copied, setCopied] = useState(false);

  function share() {
    const url = `${window.location.origin}/?deck=${materialId}`;
    // Prefer the native share sheet on mobile; fall back to clipboard.
    if (navigator.share) {
      navigator
        .share({ title: "Study this on CogPrint", url })
        .catch(() => copyLink(url));
    } else {
      copyLink(url);
    }
  }

  function copyLink(url: string) {
    navigator.clipboard?.writeText(url).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => {}
    );
  }

  return (
    <button
      onClick={share}
      className="text-neural text-sm px-3 py-1.5 rounded-lg bg-neural/10 border border-neural/20
                 hover:bg-neural/20 transition-all"
    >
      {copied ? "Link copied ✓" : "Share deck ↗"}
    </button>
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
