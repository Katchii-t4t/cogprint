import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getState, lastMaterialId as storedMaterialId } from "../store";
import Timer from "../components/Timer";

/**
 * Screen 3 in the ideal-product spec — "Study / Focus mode": distraction-free
 * reading of the user's own material, with a quiet CogPrint tab that only
 * comes alive when a focus interval ends. Never interrupts mid-flow: the tab
 * stays dim and silent while the user reads; nothing auto-navigates.
 */
export default function Study() {
  const [params] = useSearchParams();
  const materialId = params.get("m") ? Number(params.get("m")) : storedMaterialId();
  const navigate = useNavigate();
  const { lastMaterialText, lastMaterialTitle } = getState();
  const [awake, setAwake] = useState(false);

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full relative">
      {/* Minimal header — recedes so the material is the hero */}
      <div className="flex items-center justify-between px-4 pt-6 pb-3">
        <button
          onClick={() => navigate(materialId ? `/plan?m=${materialId}` : "/plan")}
          className="text-slate-500 text-sm hover:text-slate-300"
        >
          ← Plan
        </button>
        <span className="text-slate-600 text-xs truncate max-w-[50%]">{lastMaterialTitle}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-5 pb-28">
        <Timer
          focusMinutes={25}
          onFocusEnd={() => setAwake(true)}
        />

        <div className="mt-6">
          {lastMaterialText ? (
            <p className="text-slate-300 text-[15px] leading-[1.85] whitespace-pre-wrap font-light">
              {lastMaterialText}
            </p>
          ) : (
            <div className="rounded-2xl bg-ink-700 neural-border p-6 text-center">
              <p className="text-slate-400 text-sm">
                This material's text isn't cached on this device.
              </p>
              <p className="text-slate-600 text-xs mt-1">
                Read from your own notes or textbook, then head to flashcards when ready.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Quiet corner tab — dim while studying, comes alive at the end of a
          focus interval. Tapping it (in either state) goes to flashcards;
          the user is never forced there. */}
      <button
        onClick={() => navigate(materialId ? `/cards?m=${materialId}` : "/cards")}
        className={`fixed bottom-6 right-5 w-14 h-14 rounded-full flex items-center justify-center
                    transition-all duration-300 active:scale-90 ${
                      awake
                        ? "bg-neural shadow-[0_0_28px_rgba(34,211,238,0.55)] scale-110"
                        : "bg-ink-700 neural-border opacity-50"
                    }`}
        aria-label="Open flashcards"
      >
        <span className={`text-xl ${awake ? "" : "breathe"}`}>🧠</span>
        {awake && (
          <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-white animate-ping" />
        )}
      </button>
    </div>
  );
}
