import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, currentHour } from "../store";
import type { Flashcard } from "../types";

type CardState = "front" | "back";
type Result = "correct" | "wrong";

interface CardResult {
  cardId: number;
  correct: boolean;
  flagged: boolean;
}

export default function Cards() {
  const [params] = useSearchParams();
  const materialId = params.get("m") ? Number(params.get("m")) : null;
  const navigate = useNavigate();

  const [cards, setCards] = useState<Flashcard[]>([]);
  const [idx, setIdx] = useState(0);
  const [cardState, setCardState] = useState<CardState>("front");
  const [results, setResults] = useState<CardResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
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
          setError("Flashcard generation needs an API key to be configured. Ask your study admin.");
        } else {
          setError(e.message);
        }
      })
      .finally(() => setLoading(false));
  }, [materialId, navigate]);

  const current = cards[idx];

  function flip() {
    if (cardState === "front") setCardState("back");
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
    setCardState("front");
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

    try {
      await api.logSession({
        user_id: userId,
        material_id: materialId ?? undefined,
        technique: "active_recall",
        duration_minutes: durationMin,
        time_of_day: currentHour(),
        quiz_score: score,
      });
    } catch {
      // fingerprint rebuild is best-effort
    }

    navigate(`/grow?score=${Math.round(score * 100)}`);
  }

  // Touch swipe handlers
  function onTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (cardState !== "back") return;
    setSwipeX(e.touches[0].clientX - touchStartX.current);
  }
  function onTouchEnd() {
    if (cardState !== "back") return;
    if (swipeX > 80) answer("correct");
    else if (swipeX < -80) answer("wrong");
    else setSwipeX(0);
  }

  if (loading) return <LoadingState />;
  if (error) return <ErrorState msg={error} onBack={() => navigate("/")} />;
  if (logging) return <LoggingState />;
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

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
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
          onClick={flip}
        >
          <div
            className="w-full rounded-3xl bg-ink-700 neural-border p-8 cursor-pointer select-none
                       min-h-[260px] flex flex-col items-center justify-center gap-4 relative"
            style={{
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

            {cardState === "front" ? (
              <>
                <p className="text-white text-center text-lg font-medium leading-snug">
                  {current.question}
                </p>
                <p className="text-slate-600 text-xs">Tap to reveal →</p>
              </>
            ) : (
              <>
                <p className="text-neural-glow text-center text-base leading-relaxed">
                  {current.answer}
                </p>
                {swipeX === 0 && (
                  <p className="text-slate-600 text-xs mt-2">
                    ← Wrong · Swipe or tap below · Correct →
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Answer buttons — only shown after flip */}
        {cardState === "back" && (
          <div className="w-full flex gap-3 animate-fade-up">
            <button
              onClick={() => answer("wrong")}
              className="flex-1 py-4 rounded-2xl bg-red-950/40 border border-red-800/40
                         text-red-400 font-semibold hover:bg-red-900/40 active:scale-[0.97]
                         transition-all"
            >
              ✕ Again
            </button>
            <button
              onClick={() => answer("correct")}
              className="flex-1 py-4 rounded-2xl bg-green-950/40 border border-green-700/30
                         text-green-400 font-semibold hover:bg-green-900/40 active:scale-[0.97]
                         transition-all"
            >
              ✓ Got it
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

function LoggingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Updating your fingerprint…</p>
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
