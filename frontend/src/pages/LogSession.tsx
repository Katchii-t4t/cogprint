import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { logSession } from "../api";
import Layout from "../components/Layout";
import type { StudyTechnique, TimeOfDay } from "../types";

const TECHNIQUES: { value: StudyTechnique; label: string }[] = [
  { value: "active_recall",             label: "Active Recall" },
  { value: "spaced_repetition",         label: "Spaced Repetition" },
  { value: "practice_testing",          label: "Practice Testing" },
  { value: "elaborative_interrogation", label: "Elaborative Interrogation" },
  { value: "interleaving",              label: "Interleaving" },
  { value: "mind_maps",                 label: "Mind Maps" },
  { value: "re_reading",                label: "Re-reading" },
];

const TIMES: { value: TimeOfDay; label: string; icon: string }[] = [
  { value: "morning",   label: "Morning",   icon: "🌅" },
  { value: "afternoon", label: "Afternoon", icon: "☀️" },
  { value: "evening",   label: "Evening",   icon: "🌆" },
  { value: "night",     label: "Night",     icon: "🌙" },
];

export default function LogSession() {
  const navigate = useNavigate();
  const userId = Number(localStorage.getItem("cogprint_user_id"));

  const [technique, setTechnique] = useState<StudyTechnique>("active_recall");
  const [duration, setDuration] = useState(45);
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>("morning");
  const [quizScore, setQuizScore] = useState(70);
  const [sleepHours, setSleepHours] = useState<string>("");
  const [stressLevel, setStressLevel] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await logSession({
        user_id: userId,
        technique,
        duration_minutes: duration,
        time_of_day: timeOfDay,
        quiz_score: quizScore / 100,
        sleep_hours: sleepHours ? parseFloat(sleepHours) : undefined,
        stress_level: stressLevel ? parseInt(stressLevel) : undefined,
      });
      navigate("/dashboard");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="max-w-xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Log a session</h1>
        <p className="text-gray-500 text-sm mb-6">
          Record what you studied and your quiz score. The more data you log, the more accurate your fingerprint becomes.
        </p>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Technique */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Study technique
            </label>
            <div className="grid grid-cols-2 gap-2">
              {TECHNIQUES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTechnique(t.value)}
                  className={`px-3 py-2.5 rounded-lg text-sm font-medium border transition-colors text-left ${
                    technique === t.value
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-gray-200 text-gray-700 hover:border-gray-300"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Duration */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Session duration: <span className="text-brand-600">{duration} min</span>
            </label>
            <input
              type="range"
              min={5}
              max={180}
              step={5}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full accent-brand-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>5 min</span><span>180 min</span>
            </div>
          </div>

          {/* Time of day */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Time of day
            </label>
            <div className="grid grid-cols-4 gap-2">
              {TIMES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTimeOfDay(t.value)}
                  className={`py-2.5 rounded-lg text-sm font-medium border transition-colors flex flex-col items-center gap-1 ${
                    timeOfDay === t.value
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  <span>{t.icon}</span>
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Quiz score */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Quiz score: <span className="text-brand-600">{quizScore}%</span>
            </label>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={quizScore}
              onChange={(e) => setQuizScore(Number(e.target.value))}
              className="w-full accent-brand-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>0%</span><span>100%</span>
            </div>
          </div>

          {/* Optional: sleep & stress */}
          <div className="bg-gray-50 rounded-xl p-4 space-y-4">
            <p className="text-sm font-medium text-gray-700">
              Optional — improves fingerprint accuracy
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Sleep last night (hours)
                </label>
                <input
                  type="number"
                  min={0}
                  max={24}
                  step={0.5}
                  value={sleepHours}
                  onChange={(e) => setSleepHours(e.target.value)}
                  placeholder="e.g. 7.5"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Stress level (1 = calm, 5 = very stressed)
                </label>
                <div className="flex gap-1.5 mt-1.5">
                  {[1, 2, 3, 4, 5].map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setStressLevel(stressLevel === String(v) ? "" : String(v))}
                      className={`flex-1 py-1.5 rounded text-sm font-medium border transition-colors ${
                        stressLevel === String(v)
                          ? "border-brand-500 bg-brand-50 text-brand-700"
                          : "border-gray-200 text-gray-600 hover:border-gray-300"
                      }`}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Saving…" : "Log session"}
          </button>
        </form>
      </div>
    </Layout>
  );
}
