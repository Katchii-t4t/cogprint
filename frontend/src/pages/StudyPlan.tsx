import { useState } from "react";
import { analyzeMaterial, generateStudyPlan } from "../api";
import Layout from "../components/Layout";
import type { StudyPlanDay, StudyPlanResponse } from "../types";

const TIME_ICONS: Record<string, string> = {
  morning: "🌅", afternoon: "☀️", evening: "🌆", night: "🌙",
};

export default function StudyPlan() {
  const userId = Number(localStorage.getItem("cogprint_user_id"));

  // Step 1: paste material
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [totalDays, setTotalDays] = useState(14);
  const [materialId, setMaterialId] = useState<number | null>(null);

  // UI state
  const [step, setStep] = useState<"input" | "analyzing" | "generating" | "done">("input");
  const [plan, setPlan] = useState<StudyPlanResponse | null>(null);
  const [error, setError] = useState("");

  async function handleGenerate() {
    if (!title.trim() || !rawText.trim()) {
      return setError("Please enter both a title and the material text.");
    }
    setError("");
    setStep("analyzing");
    try {
      const analysis = await analyzeMaterial(title, rawText);
      setMaterialId(analysis.material_id);
      setStep("generating");
      const generatedPlan = await generateStudyPlan(userId, analysis.material_id, totalDays);
      setPlan(generatedPlan);
      setStep("done");
    } catch (e: any) {
      setError(e.message);
      setStep("input");
    }
  }

  return (
    <Layout>
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Study plan generator</h1>
        <p className="text-sm text-gray-500 mb-6">
          Paste your learning material and get a personalized day-by-day study schedule based on your cognitive fingerprint.
        </p>

        {(step === "input" || step === "analyzing" || step === "generating") && (
          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Material title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Chapter 5: Cellular Respiration"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Material text
              </label>
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="Paste your notes, textbook section, or any learning material here…"
                rows={10}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-y"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Study duration: <span className="text-brand-600">{totalDays} days</span>
              </label>
              <input
                type="range"
                min={7}
                max={30}
                step={1}
                value={totalDays}
                onChange={(e) => setTotalDays(Number(e.target.value))}
                className="w-full accent-brand-600"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>7 days</span><span>30 days</span>
              </div>
            </div>

            {error && (
              <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>
            )}

            {(step === "analyzing" || step === "generating") ? (
              <div className="bg-brand-50 border border-brand-100 rounded-xl p-5 text-center">
                <div className="animate-pulse text-brand-600 font-medium">
                  {step === "analyzing"
                    ? "🔍 Analyzing material and building knowledge map…"
                    : "🧠 Generating your personalized study plan…"}
                </div>
                <p className="text-xs text-gray-400 mt-2">This takes about 15–30 seconds.</p>
              </div>
            ) : (
              <button
                onClick={handleGenerate}
                className="w-full py-3 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 transition-colors"
              >
                Generate my study plan
              </button>
            )}
          </div>
        )}

        {step === "done" && plan && (
          <div className="space-y-5">
            <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
              <p className="font-medium text-brand-800">
                {plan.total_days}-day personalized plan ready ✨
              </p>
              <p className="text-sm text-brand-700 mt-1">{plan.general_advice}</p>
            </div>

            <div className="space-y-3">
              {plan.days.map((day: StudyPlanDay) => (
                <div
                  key={day.day}
                  className="bg-white rounded-xl border border-gray-200 shadow-sm p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-brand-600 bg-brand-50 px-2.5 py-1 rounded-full">
                      Day {day.day}
                    </span>
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <span>{TIME_ICONS[day.time_of_day] ?? "🕐"} {day.time_of_day}</span>
                      <span>· {day.session_duration_minutes} min</span>
                    </div>
                  </div>
                  <p className="font-medium text-gray-900 text-sm">{day.topic_focus}</p>
                  <p className="text-xs text-gray-500 mt-0.5 capitalize">
                    {day.technique.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-gray-400 mt-2 italic">{day.rationale}</p>
                </div>
              ))}
            </div>

            <button
              onClick={() => { setStep("input"); setPlan(null); setTitle(""); setRawText(""); }}
              className="w-full py-2.5 rounded-xl border border-gray-300 text-gray-700 text-sm hover:bg-gray-50 transition-colors"
            >
              Generate another plan
            </button>
          </div>
        )}
      </div>
    </Layout>
  );
}
