import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { currentUserId } from "../store";
import { recordActivity } from "../streak";
import type { PendingCheckItem } from "../types";

export default function Checks() {
  const navigate = useNavigate();
  const [checks, setChecks] = useState<PendingCheckItem[]>([]);
  const [current, setCurrent] = useState(0);
  const [score, setScore] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }
    api.getPendingChecks(userId)
      .then(setChecks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [navigate]);

  async function submit() {
    if (score === null) return;
    const userId = currentUserId();
    if (!userId) return;
    setSubmitting(true);

    const check = checks[current];
    await api
      .logRetentionCheck({
        session_id: check.session_id,
        user_id: userId,
        check_type: check.check_type as "24h" | "7d",
        score: score / 100,
      })
      .catch(() => {});

    // #4 retention streak — a completed check counts toward the streak.
    recordActivity(score / 100);

    if (current < checks.length - 1) {
      setCurrent((c) => c + 1);
      setScore(null);
    } else {
      setDone(true);
    }
    setSubmitting(false);
  }

  if (loading) return <LoadingState />;

  if (checks.length === 0 || done) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-dvh bg-ink-900 gap-6 px-6">
        <div className="text-5xl">{done ? "🎯" : "✓"}</div>
        <div className="text-center">
          <p className="text-white font-bold text-lg">
            {done ? "All caught up!" : "No pending checks"}
          </p>
          <p className="text-slate-400 text-sm mt-1">
            {done
              ? "Your fingerprint has been updated with the new data."
              : "Check back after your next study session."}
          </p>
        </div>
        <button
          onClick={() => navigate("/grow")}
          className="w-full max-w-xs py-4 rounded-2xl bg-neural text-ink-900 font-bold hover:bg-neural-glow transition-all"
        >
          See your fingerprint →
        </button>
      </div>
    );
  }

  const check = checks[current];
  const daysSince = Math.round(
    (Date.now() - new Date(check.session_date).getTime()) / 86_400_000
  );

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <button onClick={() => navigate("/grow")} className="text-slate-500 text-sm hover:text-slate-300">
          ← Skip
        </button>
        <span className="text-slate-400 text-sm">
          {current + 1} / {checks.length}
        </span>
      </div>

      <div className="animate-fade-up flex flex-col gap-6">
        <div>
          <span className="text-xs text-slate-500 uppercase tracking-widest">
            {check.check_type} retention check · {daysSince} day{daysSince !== 1 ? "s" : ""} later
          </span>
          <h2 className="text-2xl font-bold text-white mt-2">
            How much do you still remember?
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            From an earlier study session
          </p>
        </div>

        {/* Score slider */}
        <div className="rounded-2xl bg-ink-700 neural-border p-6 flex flex-col items-center gap-4">
          <div className="text-5xl font-bold text-white">
            {score !== null ? `${score}%` : "—"}
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={score ?? 50}
            onChange={(e) => setScore(Number(e.target.value))}
            className="w-full accent-neural"
          />
          <div className="flex justify-between w-full text-xs text-slate-600">
            <span>Nothing</span>
            <span>Everything</span>
          </div>
        </div>

        {/* Quick buttons */}
        <div className="grid grid-cols-4 gap-2">
          {[25, 50, 75, 100].map((v) => (
            <button
              key={v}
              onClick={() => setScore(v)}
              className={`py-3 rounded-xl text-sm font-semibold transition-all
                ${score === v
                  ? "bg-neural text-ink-900"
                  : "bg-ink-700 neural-border text-slate-400 hover:text-slate-200"
                }`}
            >
              {v}%
            </button>
          ))}
        </div>

        <button
          onClick={submit}
          disabled={score === null || submitting}
          className="w-full py-4 rounded-2xl bg-neural text-ink-900 font-bold text-base
                     disabled:opacity-30 hover:bg-neural-glow active:scale-[0.98] transition-all"
        >
          {submitting ? "Saving…" : current < checks.length - 1 ? "Next →" : "Finish →"}
        </button>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
    </div>
  );
}
