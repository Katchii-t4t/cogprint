import { useEffect, useState } from "react";
import { exportCSV, updatePostTest } from "../api";

const RESEARCHER_PASSWORD = import.meta.env.VITE_RESEARCHER_PASSWORD ?? "cogprint2025";
const BASE = "/api";

interface ParticipantRow {
  id: number;
  group: string;
  pre_test_score: number | null;
  post_test_score: number | null;
  created_at: string;
  session_count: number;
}

async function fetchAllUsers(): Promise<ParticipantRow[]> {
  // Fetch users and their session counts
  const usersRes = await fetch(`${BASE}/users/all`);
  if (!usersRes.ok) throw new Error("Failed to fetch users");
  return usersRes.json();
}

export default function Researcher() {
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState("");
  const [pwError, setPwError] = useState("");

  const [users, setUsers] = useState<ParticipantRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingPostTest, setEditingPostTest] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState("");

  function handleLogin() {
    if (password === RESEARCHER_PASSWORD) {
      setAuthed(true);
      setPwError("");
    } else {
      setPwError("Incorrect password.");
    }
  }

  useEffect(() => {
    if (!authed) return;
    setLoading(true);
    fetchAllUsers()
      .then(setUsers)
      .catch(() => setError("Could not load participants. Make sure the backend is running."))
      .finally(() => setLoading(false));
  }, [authed]);

  async function handleSavePostTest(userId: number) {
    const val = parseFloat(editingPostTest[userId]);
    if (isNaN(val) || val < 0 || val > 100) {
      return setError("Post-test score must be 0–100.");
    }
    setSavingId(userId);
    setError("");
    try {
      await updatePostTest(userId, val / 100);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, post_test_score: val / 100 } : u))
      );
      setEditingPostTest((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  }

  const controlCount = users.filter((u) => u.group === "control").length;
  const treatmentCount = users.filter((u) => u.group === "treatment").length;

  if (!authed) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm bg-white rounded-2xl shadow-lg p-8 space-y-4">
          <div className="text-center">
            <div className="text-3xl mb-2">🔬</div>
            <h1 className="text-xl font-bold text-gray-900">Researcher Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">CogPrint — Cognitive Fingerprint Project</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="Enter researcher password"
            />
            {pwError && <p className="text-xs text-red-500 mt-1">{pwError}</p>}
          </div>
          <button
            onClick={handleLogin}
            className="w-full py-2.5 rounded-xl bg-brand-600 text-white font-medium hover:bg-brand-700 transition-colors"
          >
            Login
          </button>
          <p className="text-center text-xs text-gray-400">
            <a href="/onboarding" className="hover:underline">← Participant onboarding</a>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="font-bold text-lg">🔬 CogPrint — Researcher Dashboard</h1>
          <p className="text-xs text-gray-400 mt-0.5">Cognitive Fingerprint Project</p>
        </div>
        <button
          onClick={() => setAuthed(false)}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          Sign out
        </button>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Summary cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <SummaryCard label="Total participants" value={String(users.length)} />
          <SummaryCard label="Control group" value={String(controlCount)} />
          <SummaryCard label="Treatment group" value={String(treatmentCount)} />
          <SummaryCard
            label="Post-tests done"
            value={String(users.filter((u) => u.post_test_score !== null).length)}
          />
        </div>

        {/* Export */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="font-semibold text-gray-900 mb-3">Export data for analysis</h2>
          <p className="text-sm text-gray-500 mb-4">
            Download CSV with all session-level data including quiz scores, retention checks,
            pre/post test scores, sleep, and stress. Load directly into R or Python.
          </p>
          <div className="flex gap-3 flex-wrap">
            <button
              onClick={() => exportCSV()}
              className="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              Export all data
            </button>
            <button
              onClick={() => exportCSV("control")}
              className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Export control group
            </button>
            <button
              onClick={() => exportCSV("treatment")}
              className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Export treatment group
            </button>
          </div>
        </div>

        {/* Participant table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">Participants</h2>
          </div>

          {error && (
            <div className="px-5 py-3 bg-red-50 border-b border-red-100">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {loading ? (
            <div className="px-5 py-8 text-sm text-gray-400 text-center">Loading participants…</div>
          ) : users.length === 0 ? (
            <div className="px-5 py-8 text-sm text-gray-400 text-center">No participants yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                  <tr>
                    <th className="px-4 py-3 text-left">ID</th>
                    <th className="px-4 py-3 text-left">Group</th>
                    <th className="px-4 py-3 text-left">Joined</th>
                    <th className="px-4 py-3 text-right">Sessions</th>
                    <th className="px-4 py-3 text-right">Pre-test</th>
                    <th className="px-4 py-3 text-right">Post-test</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-gray-700">#{u.id}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            u.group === "treatment"
                              ? "bg-brand-100 text-brand-700"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {u.group}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{u.session_count}</td>
                      <td className="px-4 py-3 text-right text-gray-600">
                        {u.pre_test_score !== null
                          ? `${Math.round(u.pre_test_score * 100)}%`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {editingPostTest[u.id] !== undefined ? (
                          <input
                            type="number"
                            min={0}
                            max={100}
                            value={editingPostTest[u.id]}
                            onChange={(e) =>
                              setEditingPostTest((prev) => ({ ...prev, [u.id]: e.target.value }))
                            }
                            className="w-16 border border-gray-300 rounded px-2 py-1 text-xs text-right"
                          />
                        ) : (
                          <span className="text-gray-600">
                            {u.post_test_score !== null
                              ? `${Math.round(u.post_test_score * 100)}%`
                              : "—"}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {editingPostTest[u.id] !== undefined ? (
                          <div className="flex gap-1 justify-end">
                            <button
                              onClick={() => handleSavePostTest(u.id)}
                              disabled={savingId === u.id}
                              className="px-2 py-1 rounded text-xs bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50"
                            >
                              {savingId === u.id ? "…" : "Save"}
                            </button>
                            <button
                              onClick={() =>
                                setEditingPostTest((prev) => {
                                  const next = { ...prev };
                                  delete next[u.id];
                                  return next;
                                })
                              }
                              className="px-2 py-1 rounded text-xs border border-gray-300 text-gray-600 hover:bg-gray-50"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() =>
                              setEditingPostTest((prev) => ({
                                ...prev,
                                [u.id]: String(
                                  u.post_test_score !== null
                                    ? Math.round(u.post_test_score * 100)
                                    : ""
                                ),
                              }))
                            }
                            className="px-2 py-1 rounded text-xs border border-gray-300 text-gray-600 hover:bg-gray-50"
                          >
                            {u.post_test_score !== null ? "Edit" : "Set score"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
    </div>
  );
}
