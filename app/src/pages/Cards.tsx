import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, currentHour, lastMaterialId as storedMaterialId } from "../store";
import { recordActivity } from "../streak";
import { resolveMode } from "../study";
import type { Flashcard } from "../types";

type Result = "correct" | "wrong";

interface CardResult {
  cardId: number;
  correct: boolean;
  flagged: boolean;
}

export default function Cards() {
  const [params] = useSearchParams();
  const materialId = params.get("m") ? Number(params.get("m")) : storedMaterialId();
  // #3 fix: the study mode drives which technique we honestly log (default: active recall).
  const mode = resolveMode(params.get("mode"));
  const navigate = useNavigate();

  const [cards, setCards] = useState<Flashcard[]>([]);
  const [idx, setIdx] = useState(0);
  // For re-reading the answer is shown up front; every other mode reveals it.
  const [revealed, setRevealed] = useState(mode.interaction === "reread");
  const [results, setResults] = useState<CardResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [needsSetup, setNeedsSetup] = useState(false);
  const [swipeX, setSwipeX] = useState(0);
  const [logging, setLogging] = useState(false);

  const touchStartX = useRef(0);
  const startTime = useRef(Date.now());

  useEffect(() => {
    const userId = currentUserId();
    if (!userId || !materialId) { navigate("/"); return; }

    api
      .getQuestions(materialId)
      .then((r) => setCards(r.cards.filter((c) => !c.flagged)))
      .catch((e) => {
        if (e.message.startsWith("503")) {
          setNeedsSetup(true);
        } else {
          setError(e.message);
        }
      })
      .finally(() => setLoading(false));
  }, [materialId, navigate]);

  const current = cards[idx];
  const canSwipe = revealed && (mode.interaction === "flip" || mode.interaction === "test");

  function reveal() {
    if (!revealed) setRevealed(true);
  }

  async function flag() {
    if (!materialId || !current) return;
    await api.flagQuestion(materialId, current.id).catch(() => {});
    setResults((r) => [...r, { cardId: current.id, correct: false, flagged: true }]);
    advance();
  }

  function answer(result: Result) {
    setResults((r) => [
      ...r,
      { cardId: current.id, correct: result === "correct", flagged: false },
    ]);
    advance();
  }

  function advance() {
    // Re-reading shows the answer immediately; all other modes hide it again.
    setRevealed(mode.interaction === "reread");
    setSwipeX(0);
    if (idx < cards.length - 1) {
      setIdx((i) => i + 1);
    } else {
      finish();
    }
  }

  async function finish() {
    setLogging(true);
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }

    const nonFlagged = results.filter((r) => !r.flagged);
    const score =
      nonFlagged.length > 0
        ? nonFlagged.filter((r) => r.correct).length / nonFlagged.length
        : 0;

    const durationMin = Math.max(
      1,
      Math.round((Date.now() - startTime.current) / 60_000)
    );

    // #4 retention streak — record this round locally (best-effort, no backend).
    recordActivity(score);

    try {
      await api.logSession({
        user_id: userId,
        material_id: materialId ?? undefined,
        // Honest technique for THIS session — no longer hardcoded active_recall.
        technique: mode.technique,
        duration_minutes: durationMin,
        time_of_day: currentHour(),
        quiz_score: score,
      });
    } catch {
      // fingerprint rebuild is best-effort
    }

    navigate(`/grow?score=${Math.round(score * 100)}`);
  }

  // Touch swipe handlers (only meaningful once the answer is revealed in flip/test).
  function onTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (!canSwipe) return;
    setSwipeX(e.touches[0].clientX - touchStartX.current);
  }
  function onTouchEnd() {
    if (!canSwipe) return;
    if (swipeX > 80) answer("correct");
    else if (swipeX < -80) answer("wrong");
    else setSwipeX(0);
  }

  if (loading) return <LoadingState />;
  if (needsSetup) return <NeedsSetupState materialId={materialId} navigate={navigate} />;
  if (error) return <ErrorState msg={error} onBack={() => navigate("/")} />;
  if (logging) return <LoggingState mode={mode.label} />;
  if (cards.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-dvh bg-ink-900 gap-4 px-6">
        <p className="text-slate-400 text-center">No flashcards available for this material.</p>
        <button onClick={() => navigate("/grow")} className="text-neural text-sm">
          See your fingerprint →
        </button>
      </div>
    );
  }

  const progress = idx / cards.length;
  const showRating = revealed; // rating (correct/wrong) is available once revealed

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <button onClick={() => navigate("/")} className="text-slate-500 text-sm hover:text-slate-300">
          ✕
        </button>
        <span className="text-slate-400 text-sm">
          {idx + 1} / {cards.length}
        </span>
        <button
          onClick={() => navigate(`/grow`)}
          className="text-slate-500 text-sm hover:text-slate-300"
        >
          Skip all
        </button>
      </div>

      {/* Mode banner — makes the technique explicit and honest */}
      <div className="flex items-center gap-2 mb-4 rounded-xl bg-ink-700/60 border border-ink-500/40 px-3 py-2">
        <span>{mode.emoji}</span>
        <div className="min-w-0">
          <p className="text-slate-200 text-xs font-semibold">{mode.label}</p>
          <p className="text-slate-500 text-[11px] leading-tight truncate">{mode.instruction}</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-ink-500 rounded-full mb-8 overflow-hidden">
        <div
          className="h-full bg-neural rounded-full transition-all duration-300"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Card */}
      <div className="flex-1 flex flex-col items-center justify-center gap-6">
        <div
          className="w-full card-swipe-enter"
          key={idx}
          style={{
            transform: `translateX(${swipeX}px) rotate(${swipeX * 0.04}deg)`,
            transition: swipeX === 0 ? "transform 0.2s" : "none",
          }}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
          onClick={mode.interaction === "flip" ? reveal : undefined}
        >
          <div
            className="w-full rounded-3xl bg-ink-700 neural-border p-8 select-none
                       min-h-[260px] flex flex-col items-center justify-center gap-4 relative"
            style={{
              cursor: mode.interaction === "flip" && !revealed ? "pointer" : "default",
              boxShadow:
                swipeX > 40
                  ? "0 0 32px rgba(34,197,94,0.25)"
                  : swipeX < -40
                  ? "0 0 32px rgba(239,68,68,0.25)"
                  : "0 0 20px rgba(34,211,238,0.06)",
            }}
          >
            {/* Difficulty badge */}
            <div className="absolute top-4 left-4">
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-ink-500 text-slate-400 uppercase tracking-wider">
                {current.difficulty}
              </span>
            </div>
            {/* Concept badge */}
            <div className="absolute top-4 right-4">
              <span className="text-[10px] text-neural/60 font-medium">{current.concept}</span>
            </div>

            {/* Question is always visible */}
            <p className="text-white text-center text-lg font-medium leading-snug">
              {current.question}
            </p>

            {/* Elaborative mode: prompt the learner to explain before revealing */}
            {mode.interaction === "explain" && !revealed && (
              <p className="text-slate-500 text-xs text-center">
                Say (or think) <span className="text-neural/70">why</span> this is true, then reveal.
              </p>
            )}

            {/* Answer */}
            {revealed ? (
              <div className="w-full border-t border-ink-500/40 pt-4 mt-1">
                <p className="text-neural-glow text-center text-base leading-relaxed">
                  {current.answer}
                </p>
                {canSwipe && swipeX === 0 && (
                  <p className="text-slate-600 text-xs text-center mt-3">
                    ← Wrong · Swipe or tap below · Correct →
                  </p>
                )}
              </div>
            ) : (
              mode.interaction !== "explain" && (
                <p className="text-slate-600 text-xs">
                  {mode.interaction === "test" ? "Commit your answer, then reveal ↓" : "Tap to reveal →"}
                </p>
              )
            )}
          </div>
        </div>

        {/* Reveal button (test + explain modes need a deliberate reveal) */}
        {!revealed && mode.interaction !== "flip" && (
          <button
            onClick={reveal}
            className="w-full py-4 rounded-2xl bg-ink-600 border border-ink-400 text-slate-200
                       font-semibold hover:bg-ink-500 active:scale-[0.97] transition-all animate-fade-up"
          >
            Reveal answer
          </button>
        )}

        {/* Rating buttons — shown once the answer is revealed */}
        {showRating && (
          <div className="w-full flex gap-3 animate-fade-up">
            <button
              onClick={() => answer("wrong")}
              className="flex-1 py-4 rounded-2xl bg-red-950/40 border border-red-800/40
                         text-red-400 font-semibold hover:bg-red-900/40 active:scale-[0.97]
                         transition-all"
            >
              {mode.interaction === "reread" ? "✕ Couldn't recall" : "✕ Again"}
            </button>
            <button
              onClick={() => answer("correct")}
              className="flex-1 py-4 rounded-2xl bg-green-950/40 border border-green-700/30
                         text-green-400 font-semibold hover:bg-green-900/40 active:scale-[0.97]
                         transition-all"
            >
              {mode.interaction === "reread" ? "✓ Could recall" : "✓ Got it"}
            </button>
          </div>
        )}

        {/* Flag button */}
        <button
          onClick={flag}
          className="text-slate-600 text-xs hover:text-slate-400 transition-colors"
        >
          🚩 Confusing question? Flag it
        </button>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Generating flashcards…</p>
    </div>
  );
}

function LoggingState({ mode }: { mode: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Logging your {mode} session…</p>
    </div>
  );
}

function ErrorState({ msg, onBack }: { msg: string; onBack: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900 px-6">
      <p className="text-red-400 text-sm text-center">{msg}</p>
      <button onClick={onBack} className="text-neural text-sm">← Go back</button>
    </div>
  );
}

function NeedsSetupState({
  materialId,
  navigate,
}: {
  materialId: number | null;
  navigate: (to: string) => void;
}) {
  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full px-6 py-8">
      <button onClick={() => navigate("/")} className="text-slate-500 text-sm hover:text-slate-300 mb-8">
        ← Home
      </button>
      <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
        <div className="text-5xl">🔑</div>
        <div>
          <h2 className="text-white font-bold text-xl">Flashcards need setup</h2>
          <p className="text-slate-400 text-sm mt-2 leading-relaxed">
            Flashcard generation is powered by an AI model that isn't configured
            on this server yet. The rest of CogPrint — your study plan and your
            growing fingerprint — works right now.
          </p>
        </div>
        <div className="w-full flex flex-col gap-3 mt-2">
          <button
            onClick={() => navigate(materialId ? `/plan?m=${materialId}` : "/plan")}
            className="w-full py-4 rounded-2xl bg-neural text-ink-900 font-bold hover:bg-neural-glow active:scale-[0.98] transition-all"
          >
            See your study plan →
          </button>
          <button
            onClick={() => navigate("/grow")}
            className="w-full py-3 rounded-xl bg-ink-700 neural-border text-slate-300 text-sm font-medium hover:bg-ink-600 transition-all"
          >
            See your fingerprint
          </button>
        </div>
        <p className="text-slate-600 text-xs mt-4">
          Admin: set <code className="text-slate-500">ANTHROPIC_API_KEY</code> in the
          backend <code className="text-slate-500">.env</code> to enable flashcards.
        </p>
      </div>
    </div>
  );
}
