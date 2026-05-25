import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPendingChecks, logRetentionCheck } from "../api";
import Layout from "../components/Layout";
import type { PendingCheckItem } from "../types";

function daysSince(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

export default function RetentionCheck() {
  const userId = Number(localStorage.getItem("cogprint_user_id"));
  const [pending, setPending] = useState<PendingCheckItem[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [done, setDone] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState<string | null>(null);

  useEffect(() => {
    getPendingChecks(userId)
      .then(setPending)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  const key = (item: PendingCheckItem) => `${item.session_id}-${item.check_type}`;

  async function handleSubmit(item: PendingCheckItem) {
    const k = key(item);
    const score = scores[k];
    if (score === undefined) return;
    setSubmitting(k);
    try {
      await logRetentionCheck({
        session_id: item.session_id,
        user_id: userId,
        check_type: item.check_type,
        score: score / 100,
      });
      setDone((prev) => new Set([...prev, k]));
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSubmitting(null);
    }
  }

  const activePending = pending.filter((p) => !done.has(key(p)));

  return (
    <Layout>
      <div className="max-w-xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Retention checks</h1>
        <p className="text-sm text-gray-500 mb-6">
          These measure how well you've retained material from past sessions. They're the most important signal for your cognitive fingerprint.
        </p>

        {loading ? (
          <p className="text-gray-400 text-sm">Loading…</p>
        ) : activePending.length === 0 ? (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
            <p className="text-2xl mb-2">✅</p>
            <p className="font-semibold text-green-800">All caught up!</p>
            <p className="text-sm text-green-600 mt-1">No pending retention checks right now.</p>
            <Link
              to="/dashboard"
              className="inline-block mt-4 text-sm text-brand-600 hover:underline"
            >
              Back to dashboard
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {activePending.map((item) => {
              const k = key(item);
              const isDone = done.has(k);
              return (
                <div
                  key={k}
                  className={`bg-white rounded-xl border shadow-sm p-5 ${
                    isDone ? "border-green-200 opacity-60" : "border-gray-200"
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <span
                        className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                          item.check_type === "24h"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-purple-100 text-purple-700"
                        }`}
                      >
                        {item.check_type === "24h" ? "24-hour check" : "7-day check"}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400">
                      Session {daysSince(item.session_date)} days ago
                    </span>
                  </div>

                  <p className="text-sm text-gray-600 mb-3">
                    How well do you remember the material from session #{item.session_id}?
                  </p>

                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>Retention score</span>
                      <span className="font-medium text-brand-600">
                        {scores[k] !== undefined ? `${scores[k]}%` : "—"}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={scores[k] ?? 50}
                      onChange={(e) =>
                        setScores((prev) => ({ ...prev, [k]: Number(e.target.value) }))
                      }
                      className="w-full accent-brand-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400">
                      <span>0% — forgot everything</span>
                      <span>100% — remember it all</span>
                    </div>
                  </div>

                  <button
                    onClick={() => handleSubmit(item)}
                    disabled={scores[k] === undefined || submitting === k}
                    className="mt-4 w-full py-2.5 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
                  >
                    {submitting === k ? "Saving…" : "Submit"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {done.size > 0 && (
          <p className="mt-4 text-sm text-green-600 text-center">
            ✓ {done.size} check{done.size > 1 ? "s" : ""} submitted — your fingerprint is being updated.
          </p>
        )}
      </div>
    </Layout>
  );
}
