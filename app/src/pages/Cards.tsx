import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, currentHour, lastMaterialId as storedMaterialId } from "../store";
import type { Flashcard } from "../types";

/**
 * The study round. Two modes over one shared question bank:
 *
 *  - QUIZ (default) — multiple-choice, objectively graded by string equality.
 *    The ONLY mode that logs a session and feeds the fingerprint. Cards whose
 *    distractors are missing (pre-quiz cache) fall back to flashcard display
 *    inside the round and are excluded from the score.
 *  - FLASHCARDS — the classic tap-to-reveal / Again / Got it self-report loop.
 *    Practice only: never logs a session, never touches the fingerprint.
 */

type Mode = "quiz" | "flash";
type CardState = "front" | "back";
type Result = "correct" | "wrong";

interface CardResult {
  cardId: number;
  correct: boolean;
  flagged: boolean;
  /** True only for objectively-graded (multiple-choice) answers — the only
      results allowed to feed the fingerprint. */
  measured: boolean;
}

/** Reading the clock is a legitimate side effect in event handlers, but the
    react-hooks purity lint can't statically tell handlers from render helpers,
    so the impure call lives behind this module-scope helper. */
const now = () => Date.now();

/** Fisher–Yates, non-mutating. */
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function Cards() {
  const [params] = useSearchParams();
  const materialId = params.get("m") ? Number(params.get("m")) : storedMaterialId();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>("quiz");
  const [cards, setCards] = useState<Flashcard[]>([]);
  /** cardId -> shuffled options (answer + distractors), fixed for the round so
      the correct answer's position can't become a pattern mid-card. */
  const [options, setOptions] = useState<Record<number, string[]>>({});
  const [idx, setIdx] = useState(0);
  const [cardState, setCardState] = useState<CardState>("front");
  const [picked, setPicked] = useState<string | null>(null);
  const [results, setResults] = useState<CardResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [needsSetup, setNeedsSetup] = useState(false);
  const [swipeX, setSwipeX] = useState(0);
  const [logging, setLogging] = useState(false);

  const touchStartX = useRef(0);
  const startTime = useRef(0);
  const endTime = useRef(0);
  const advanceTimer = useRef<number | null>(null);

  useEffect(() => {
    startTime.current = now();
    return () => {
      if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
    };
  }, []);

  useEffect(() => {
    const userId = currentUserId();
    if (!userId || !materialId) { navigate("/"); return; }

    api
      .getQuestions(materialId)
      .then((r) => {
        const active = r.cards.filter((c) => !c.flagged);
        setCards(active);
        // Shuffle each card's options once per round (in the effect, not in
        // render, so the order is stable and the render stays pure).
        const opts: Record<number, string[]> = {};
        for (const c of active) {
          if (c.distractors.length > 0) {
            opts[c.id] = shuffle([c.answer, ...c.distractors]);
          }
        }
        setOptions(opts);
      })
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
  // A card is quiz-gradeable only if it has distractors (older cached sets don't).
  const quizable = current ? (options[current.id]?.length ?? 0) > 0 : false;
  const quizCard = mode === "quiz" && quizable;

  function switchMode(next: Mode) {
    if (next === mode) return;
    // Switching restarts the round — mixed-mode scores would be meaningless.
    if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
    setMode(next);
    setIdx(0);
    setResults([]);
    setCardState("front");
    setPicked(null);
    setSwipeX(0);
    startTime.current = now();
  }

  function flip() {
    if (!quizCard && cardState === "front") setCardState("back");
  }

  async function flag() {
    if (!materialId || !current || picked !== null) return;
    await api.flagQuestion(materialId, current.id).catch(() => {});
    advanceWith([...results, { cardId: current.id, correct: false, flagged: true, measured: false }]);
  }

  /** Flashcard-style self-report (flash mode, or fallback cards in quiz mode).
      Never measured. */
  function answer(result: Result) {
    endTime.current = now();
    advanceWith([
      ...results,
      { cardId: current.id, correct: result === "correct", flagged: false, measured: false },
    ]);
  }

  /** Quiz answer: objective, deterministic grading by string equality. */
  function pick(option: string) {
    if (picked !== null) return; // ignore double-taps while feedback shows
    setPicked(option);
    const correct = option === current.answer;
    const next = [
      ...results,
      { cardId: current.id, correct, flagged: false, measured: true },
    ];
    endTime.current = now();
    // Brief pause so the feedback lands — longer on a miss so the correct
    // answer can actually be read. (Transitions themselves stay ≤300ms.)
    advanceTimer.current = window.setTimeout(
      () => advanceWith(next),
      correct ? 600 : 1400
    );
  }

  function advanceWith(nextResults: CardResult[]) {
    setResults(nextResults);
    setCardState("front");
    setPicked(null);
    setSwipeX(0);
    if (idx < cards.length - 1) {
      setIdx((i) => i + 1);
    } else {
      finish(nextResults);
    }
  }

  async function finish(finalResults: CardResult[]) {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }

    // Only objectively-graded answers may produce measurement.
    const gradeable = finalResults.filter((r) => r.measured && !r.flagged);

    if (mode === "quiz" && gradeable.length > 0) {
      setLogging(true);
      const score = gradeable.filter((r) => r.correct).length / gradeable.length;
      // endTime is stamped in the answer handlers (pick/answer) — reading the
      // clock here would trip the react-hooks purity rule via the timer path.
      const durationMin = Math.max(
        1,
        Math.round((endTime.current - startTime.current) / 60_000)
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
    } else {
      // Flash mode — or a quiz round with zero gradeable cards (stale cache).
      // Practice only: no session, no score, no fingerprint effect.
      navigate("/grow?practice=1");
    }
  }

  // Touch swipe handlers (flashcard-style cards only)
  function onTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (quizCard || cardState !== "back") return;
    setSwipeX(e.touches[0].clientX - touchStartX.current);
  }
  function onTouchEnd() {
    if (quizCard || cardState !== "back") return;
    if (swipeX > 80) answer("correct");
    else if (swipeX < -80) answer("wrong");
    else setSwipeX(0);
  }

  if (loading) return <LoadingState />;
  if (needsSetup) return <NeedsSetupState materialId={materialId} navigate={navigate} />;
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
  const opts = quizCard ? options[current.id] : [];

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
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

      {/* Mode toggle — Quiz is the default; flashcards are practice-only */}
      <div className="flex flex-col items-center gap-1 mb-4">
        <div className="flex bg-ink-700 rounded-full p-1 neural-border">
          <button
            onClick={() => switchMode("quiz")}
            className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
              mode === "quiz" ? "bg-neural text-ink-900" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Quiz
          </button>
          <button
            onClick={() => switchMode("flash")}
            className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
              mode === "flash" ? "bg-neural text-ink-900" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Flashcards
          </button>
        </div>
        {mode === "flash" && (
          <span className="text-slate-600 text-[10px]">Practice — not scored</span>
        )}
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
          key={`${mode}-${idx}`}
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
            className={`w-full rounded-3xl bg-ink-700 neural-border p-8 select-none
                       min-h-[220px] flex flex-col items-center justify-center gap-4 relative ${
                         quizCard ? "" : "cursor-pointer"
                       }`}
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

            {quizCard ? (
              <p className="text-white text-center text-lg font-medium leading-snug">
                {current.question}
              </p>
            ) : cardState === "front" ? (
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

        {/* Quiz options — objective grading, one tap */}
        {quizCard && (
          <div className="w-full flex flex-col gap-2 animate-fade-up">
            {opts.map((opt) => {
              const isCorrect = opt === current.answer;
              const isPicked = opt === picked;
              let cls =
                "bg-ink-700 neural-border text-slate-200 hover:bg-ink-600";
              if (picked !== null) {
                if (isCorrect) {
                  cls = "bg-green-950/50 border border-green-500/60 text-green-300";
                } else if (isPicked) {
                  cls = "bg-red-950/50 border border-red-500/60 text-red-300";
                } else {
                  cls = "bg-ink-700 neural-border text-slate-500 opacity-50";
                }
              }
              return (
                <button
                  key={opt}
                  onClick={() => pick(opt)}
                  disabled={picked !== null}
                  className={`w-full py-3.5 px-4 rounded-2xl text-sm font-medium text-left
                              transition-all duration-200 active:scale-[0.98] ${cls}`}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        )}

        {/* Flashcard answer buttons — only after flip, never on quiz cards */}
        {!quizCard && cardState === "back" && (
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

        {/* Fallback note: pre-quiz card inside a quiz round */}
        {mode === "quiz" && !quizable && (
          <p className="text-slate-600 text-[10px]">
            Older card — shown as a flashcard, not counted in your score
          </p>
        )}

        {/* Flag button — shared across modes, hidden once a quiz answer is locked */}
        {picked === null && (
          <button
            onClick={flag}
            className="text-slate-600 text-xs hover:text-slate-400 transition-colors"
          >
            🚩 Confusing question? Flag it
          </button>
        )}
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Generating questions…</p>
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
          <h2 className="text-white font-bold text-xl">Questions need setup</h2>
          <p className="text-slate-400 text-sm mt-2 leading-relaxed">
            Question generation is powered by an AI model that isn't configured
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
          backend <code className="text-slate-500">.env</code> to enable questions.
        </p>
      </div>
    </div>
  );
}
