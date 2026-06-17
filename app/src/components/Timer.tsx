import { useEffect, useRef, useState } from "react";

type Mode = "focus" | "break";

/**
 * A compact Pomodoro-style focus timer for the study plan screen.
 * Defaults to the plan's recommended session length, then a 5-minute break.
 * Pure client-side — it doesn't log anything; the flashcard round is what
 * captures study data.
 */
export default function Timer({ focusMinutes = 25 }: { focusMinutes?: number }) {
  const breakMinutes = 5;
  const [mode, setMode] = useState<Mode>("focus");
  const [secondsLeft, setSecondsLeft] = useState(focusMinutes * 60);
  const [running, setRunning] = useState(false);
  const [open, setOpen] = useState(false);
  const intervalRef = useRef<number | null>(null);

  const total = (mode === "focus" ? focusMinutes : breakMinutes) * 60;

  useEffect(() => {
    if (!running) return;
    intervalRef.current = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          // Switch mode when the period ends.
          const nextMode: Mode = mode === "focus" ? "break" : "focus";
          setMode(nextMode);
          setRunning(false);
          return (nextMode === "focus" ? focusMinutes : breakMinutes) * 60;
        }
        return s - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [running, mode, focusMinutes]);

  function reset() {
    setRunning(false);
    setMode("focus");
    setSecondsLeft(focusMinutes * 60);
  }

  const mins = Math.floor(secondsLeft / 60);
  const secs = secondsLeft % 60;
  const fraction = 1 - secondsLeft / total;
  const r = 52;
  const circ = 2 * Math.PI * r;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full rounded-2xl bg-ink-700 neural-border p-4 flex items-center justify-between
                   hover:border-neural/30 active:scale-[0.99] transition-all"
      >
        <span className="flex items-center gap-2 text-slate-300 text-sm font-medium">
          ⏱️ Focus timer
        </span>
        <span className="text-neural text-xs">Open →</span>
      </button>
    );
  }

  return (
    <div className="w-full rounded-2xl bg-ink-700 neural-border p-5 flex flex-col items-center gap-4 animate-fade-up">
      <div className="flex items-center justify-between w-full">
        <span
          className={`text-xs font-semibold uppercase tracking-widest ${
            mode === "focus" ? "text-neural" : "text-amber-400"
          }`}
        >
          {mode === "focus" ? "Focus" : "Break"}
        </span>
        <button onClick={() => setOpen(false)} className="text-slate-500 text-xs hover:text-slate-300">
          Hide
        </button>
      </div>

      {/* Ring */}
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 128 128" className="w-full h-full -rotate-90">
          <circle cx="64" cy="64" r={r} fill="none" stroke="#1e2d4a" strokeWidth="6" />
          <circle
            cx="64"
            cy="64"
            r={r}
            fill="none"
            stroke={mode === "focus" ? "#22d3ee" : "#fbbf24"}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={circ * (1 - fraction)}
            className="transition-all duration-1000 ease-linear"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-3xl font-bold text-white tabular-nums">
            {mins}:{secs.toString().padStart(2, "0")}
          </span>
        </div>
      </div>

      {/* Controls */}
      <div className="flex gap-3 w-full">
        <button
          onClick={() => setRunning((r) => !r)}
          className="flex-1 py-3 rounded-xl bg-neural text-ink-900 font-bold text-sm
                     hover:bg-neural-glow active:scale-[0.97] transition-all"
        >
          {running ? "Pause" : "Start"}
        </button>
        <button
          onClick={reset}
          className="px-5 py-3 rounded-xl bg-ink-600 border border-ink-400 text-slate-300 text-sm font-medium
                     hover:bg-ink-500 active:scale-[0.97] transition-all"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
