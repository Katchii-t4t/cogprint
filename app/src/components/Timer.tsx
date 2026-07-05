import { useEffect, useRef, useState } from "react";

type Mode = "focus" | "break";

/**
 * A compact Pomodoro-style focus timer for the study plan / study screen.
 * Defaults to the plan's recommended session length, then a 5-minute break.
 * Pure client-side — it doesn't log anything; the flashcard round is what
 * captures study data.
 *
 * Has two presentations sharing one clock:
 *  - collapsed pill (default, unobtrusive)
 *  - full-screen calm mode (spec: "full-screen calm, optional ambient") —
 *    a distraction-free overlay with a large ring and a slow ambient glow.
 *    Never mandatory; one tap in, one tap out.
 */
export default function Timer({
  focusMinutes = 25,
  onFocusEnd,
}: {
  focusMinutes?: number;
  /** Fired once when a focus period completes (not on break end). Used to
      quietly wake the flashcard tab — never auto-navigates. */
  onFocusEnd?: () => void;
}) {
  const breakMinutes = 5;
  const [mode, setMode] = useState<Mode>("focus");
  const [secondsLeft, setSecondsLeft] = useState(focusMinutes * 60);
  const [running, setRunning] = useState(false);
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const intervalRef = useRef<number | null>(null);

  const total = (mode === "focus" ? focusMinutes : breakMinutes) * 60;

  useEffect(() => {
    if (!running) return;
    intervalRef.current = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          const endingMode = mode;
          const nextMode: Mode = endingMode === "focus" ? "break" : "focus";
          setMode(nextMode);
          setRunning(false);
          if (endingMode === "focus") onFocusEnd?.();
          return (nextMode === "focus" ? focusMinutes : breakMinutes) * 60;
        }
        return s - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, mode, focusMinutes]);

  function reset() {
    setRunning(false);
    setMode("focus");
    setSecondsLeft(focusMinutes * 60);
  }

  const mins = Math.floor(secondsLeft / 60);
  const secs = secondsLeft % 60;
  const fraction = 1 - secondsLeft / total;

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

  if (fullscreen) {
    return <FullscreenRing
      mode={mode} mins={mins} secs={secs} fraction={fraction}
      running={running}
      onToggle={() => setRunning((r) => !r)}
      onReset={reset}
      onExit={() => setFullscreen(false)}
    />;
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
        <div className="flex items-center gap-3">
          <button onClick={() => setFullscreen(true)} className="text-slate-500 text-xs hover:text-slate-300">
            Full screen ⤢
          </button>
          <button onClick={() => setOpen(false)} className="text-slate-500 text-xs hover:text-slate-300">
            Hide
          </button>
        </div>
      </div>

      <Ring mins={mins} secs={secs} fraction={fraction} mode={mode} size={128} strokeWidth={6} />

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

function Ring({
  mins, secs, fraction, mode, size, strokeWidth,
}: { mins: number; secs: number; fraction: number; mode: Mode; size: number; strokeWidth: number }) {
  const r = (size - strokeWidth) / 2 - 2;
  const circ = 2 * Math.PI * r;
  const c = size / 2;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full -rotate-90">
        <circle cx={c} cy={c} r={r} fill="none" stroke="#1e2d4a" strokeWidth={strokeWidth} />
        <circle
          cx={c} cy={c} r={r} fill="none"
          stroke={mode === "focus" ? "#22d3ee" : "#fbbf24"}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - fraction)}
          className="transition-all duration-1000 ease-linear"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-bold text-white tabular-nums" style={{ fontSize: size / 4 }}>
          {mins}:{secs.toString().padStart(2, "0")}
        </span>
      </div>
    </div>
  );
}

/** Distraction-free full-viewport mode: ambient breathing glow, one big ring,
    minimal chrome. Tap the ring's border area or the exit hint to leave. */
function FullscreenRing({
  mode, mins, secs, fraction, running, onToggle, onReset, onExit,
}: {
  mode: Mode; mins: number; secs: number; fraction: number; running: boolean;
  onToggle: () => void; onReset: () => void; onExit: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-ink-900 flex flex-col items-center justify-center gap-10 animate-fade-in">
      {/* Ambient ombré breathing backdrop */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: mode === "focus"
            ? "radial-gradient(circle at 50% 45%, rgba(34,211,238,0.08), transparent 60%)"
            : "radial-gradient(circle at 50% 45%, rgba(251,191,36,0.08), transparent 60%)",
        }}
      />
      <button
        onClick={onExit}
        className="absolute top-6 right-6 text-slate-500 text-sm hover:text-slate-300 z-10"
      >
        ✕ Exit
      </button>

      <span
        className={`text-xs font-semibold uppercase tracking-[0.3em] ${
          mode === "focus" ? "text-neural" : "text-amber-400"
        }`}
      >
        {mode === "focus" ? "Deep focus" : "Break"}
      </span>

      <div className="breathe" style={{ animationDuration: "6s" }}>
        <Ring mins={mins} secs={secs} fraction={fraction} mode={mode} size={260} strokeWidth={4} />
      </div>

      <div className="flex gap-4">
        <button
          onClick={onToggle}
          className="px-8 py-3 rounded-xl bg-neural text-ink-900 font-bold text-sm
                     hover:bg-neural-glow active:scale-[0.97] transition-all"
        >
          {running ? "Pause" : "Start"}
        </button>
        <button
          onClick={onReset}
          className="px-6 py-3 rounded-xl bg-ink-700 border border-ink-400 text-slate-300 text-sm font-medium
                     hover:bg-ink-500 active:scale-[0.97] transition-all"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
