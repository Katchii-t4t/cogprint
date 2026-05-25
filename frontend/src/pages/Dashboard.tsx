import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFingerprint, getPendingChecks, listSessions } from "../api";
import Layout from "../components/Layout";
import type { FingerprintProfile, PendingCheckItem, StudySession } from "../types";

const CONFIDENCE_COLORS = {
  low:    "bg-gray-100 text-gray-600",
  medium: "bg-amber-100 text-amber-700",
  high:   "bg-green-100 text-green-700",
};

const CONFIDENCE_LABELS = {
  low:    "Getting started",
  medium: "Learning your patterns",
  high:   "Fully personalized",
};

function pct(v: number | null) {
  return v !== null ? `${Math.round(v * 100)}%` : "—";
}

export default function Dashboard() {
  const userId = Number(localStorage.getItem("cogprint_user_id"));
  const name = localStorage.getItem("cogprint_name") ?? "Participant";

  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [fingerprint, setFingerprint] = useState<FingerprintProfile | null>(null);
  const [pending, setPending] = useState<PendingCheckItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listSessions(userId),
      getFingerprint(userId),
      getPendingChecks(userId),
    ])
      .then(([s, fp, p]) => {
        setSessions(s);
        setFingerprint(fp.fingerprint);
        setPending(p);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  const avgScore =
    sessions.length > 0
      ? sessions.reduce((sum, s) => sum + s.quiz_score, 0) / sessions.length
      : null;

  return (
    <Layout>
      <div className="space-y-6">
        {/* Welcome */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome back, {name} 👋
          </h1>
          <p className="text-gray-500 text-sm mt-1">Participant ID: #{userId}</p>
        </div>

        {loading ? (
          <div className="text-gray-400 text-sm">Loading your data…</div>
        ) : (
          <>
            {/* Alert: pending checks */}
            {pending.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
                <div>
                  <p className="font-medium text-amber-800">
                    {pending.length} retention check{pending.length > 1 ? "s" : ""} ready
                  </p>
                  <p className="text-sm text-amber-600 mt-0.5">
                    Complete them now to improve your fingerprint accuracy.
                  </p>
                </div>
                <Link
                  to="/retention-check"
                  className="ml-4 px-4 py-2 bg-amber-500 text-white text-sm font-medium rounded-lg hover:bg-amber-600 transition-colors"
                >
                  Complete →
                </Link>
              </div>
            )}

            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Sessions logged" value={String(sessions.length)} />
              <StatCard label="Avg quiz score" value={pct(avgScore)} />
              <StatCard
                label="Retention checks"
                value={pending.length > 0 ? `${pending.length} due` : "Up to date ✓"}
                accent={pending.length > 0}
              />
              <StatCard
                label="Fingerprint"
                value={
                  fingerprint
                    ? fingerprint.confidence.charAt(0).toUpperCase() + fingerprint.confidence.slice(1)
                    : "—"
                }
              />
            </div>

            {/* Fingerprint teaser */}
            {fingerprint && (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-semibold text-gray-900">Your Cognitive Fingerprint</h2>
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                      CONFIDENCE_COLORS[fingerprint.confidence]
                    }`}
                  >
                    {CONFIDENCE_LABELS[fingerprint.confidence]}
                  </span>
                </div>

                {fingerprint.confidence === "low" ? (
                  <div className="space-y-2">
                    <p className="text-sm text-gray-500">
                      Complete at least 5 sessions to unlock personalized insights.
                    </p>
                    {/* Progress bar */}
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-500 rounded-full transition-all"
                        style={{ width: `${Math.min(100, (fingerprint.session_count / 5) * 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-400">
                      {fingerprint.session_count}/5 sessions
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {fingerprint.insights.slice(0, 2).map((ins, i) => (
                      <p key={i} className="text-sm text-gray-700 flex gap-2">
                        <span className="text-brand-500">•</span> {ins}
                      </p>
                    ))}
                    <Link
                      to="/fingerprint"
                      className="text-sm text-brand-600 hover:underline block mt-2"
                    >
                      See full fingerprint →
                    </Link>
                  </div>
                )}
              </div>
            )}

            {/* Quick actions */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <ActionCard
                to="/log-session"
                emoji="📝"
                title="Log a study session"
                desc="Record what you studied, how long, and your quiz score"
              />
              <ActionCard
                to="/study-plan"
                emoji="📅"
                title="Generate study plan"
                desc="Get a personalized day-by-day schedule for new material"
              />
            </div>

            {/* Recent sessions */}
            {sessions.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h2 className="font-semibold text-gray-900 mb-3">Recent sessions</h2>
                <div className="space-y-2">
                  {sessions.slice(0, 5).map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between text-sm py-2 border-b last:border-0"
                    >
                      <div>
                        <span className="font-medium capitalize">
                          {s.technique.replace(/_/g, " ")}
                        </span>
                        <span className="text-gray-400 ml-2">
                          {s.duration_minutes} min · {s.time_of_day}
                        </span>
                      </div>
                      <span className="font-medium text-brand-700">
                        {pct(s.quiz_score)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}

function StatCard({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <p className="text-xs text-gray-500 font-medium">{label}</p>
      <p
        className={`text-xl font-bold mt-1 ${
          accent ? "text-amber-600" : "text-gray-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function ActionCard({
  to,
  emoji,
  title,
  desc,
}: {
  to: string;
  emoji: string;
  title: string;
  desc: string;
}) {
  return (
    <Link
      to={to}
      className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 hover:border-brand-300 hover:shadow-md transition-all flex gap-4 items-start"
    >
      <span className="text-2xl">{emoji}</span>
      <div>
        <p className="font-semibold text-gray-900">{title}</p>
        <p className="text-sm text-gray-500 mt-0.5">{desc}</p>
      </div>
    </Link>
  );
}
