import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createUser } from "../api";

export default function Onboarding() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"new" | "returning" | null>(null);
  const [name, setName] = useState("");
  const [returnId, setReturnId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleNew() {
    if (!name.trim()) return setError("Please enter your name.");
    setLoading(true);
    setError("");
    try {
      // Random 50/50 group assignment (controlled by backend randomness, blinded from participant)
      const group = Math.random() < 0.5 ? "control" : "treatment";
      const user = await createUser(group as "control" | "treatment");
      localStorage.setItem("cogprint_user_id", String(user.id));
      localStorage.setItem("cogprint_name", name.trim());
      navigate("/dashboard");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReturn() {
    const id = parseInt(returnId, 10);
    if (!id || isNaN(id)) return setError("Please enter a valid participant ID.");
    localStorage.setItem("cogprint_user_id", String(id));
    localStorage.setItem("cogprint_name", `Participant #${id}`);
    navigate("/dashboard");
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🧠</div>
          <h1 className="text-3xl font-bold text-gray-900">CogPrint</h1>
          <p className="text-gray-500 mt-1">The Cognitive Fingerprint Project</p>
        </div>

        {mode === null && (
          <div className="bg-white rounded-2xl shadow-lg p-8 space-y-4">
            <h2 className="text-xl font-semibold text-center text-gray-800">Welcome</h2>
            <p className="text-sm text-gray-500 text-center">
              Are you a new or returning participant?
            </p>
            <button
              onClick={() => setMode("new")}
              className="w-full py-3 rounded-xl bg-brand-600 text-white font-medium hover:bg-brand-700 transition-colors"
            >
              I'm a new participant
            </button>
            <button
              onClick={() => setMode("returning")}
              className="w-full py-3 rounded-xl border border-gray-300 text-gray-700 font-medium hover:bg-gray-50 transition-colors"
            >
              I have a participant ID
            </button>
            <div className="pt-2 border-t text-center">
              <a
                href="/researcher"
                className="text-sm text-brand-600 hover:underline"
              >
                Researcher login →
              </a>
            </div>
          </div>
        )}

        {mode === "new" && (
          <div className="bg-white rounded-2xl shadow-lg p-8 space-y-4">
            <button
              onClick={() => { setMode(null); setError(""); }}
              className="text-sm text-gray-400 hover:text-gray-600"
            >
              ← Back
            </button>
            <h2 className="text-xl font-semibold text-gray-800">Join the study</h2>
            <p className="text-sm text-gray-500">
              You'll be randomly assigned to a study group. Your participant ID will be shown after signup — write it down!
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Your name (for display only)
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleNew()}
                placeholder="e.g. Alex"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <button
              onClick={handleNew}
              disabled={loading}
              className="w-full py-3 rounded-xl bg-brand-600 text-white font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Creating account…" : "Join study"}
            </button>
          </div>
        )}

        {mode === "returning" && (
          <div className="bg-white rounded-2xl shadow-lg p-8 space-y-4">
            <button
              onClick={() => { setMode(null); setError(""); }}
              className="text-sm text-gray-400 hover:text-gray-600"
            >
              ← Back
            </button>
            <h2 className="text-xl font-semibold text-gray-800">Welcome back</h2>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Participant ID
              </label>
              <input
                type="number"
                value={returnId}
                onChange={(e) => setReturnId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleReturn()}
                placeholder="e.g. 42"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <button
              onClick={handleReturn}
              className="w-full py-3 rounded-xl bg-brand-600 text-white font-medium hover:bg-brand-700 transition-colors"
            >
              Continue
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
