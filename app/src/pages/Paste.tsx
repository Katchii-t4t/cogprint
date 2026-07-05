import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import {
  addRecent, dismissNudge, getState, nudgeAllowed, setState,
  type RecentMaterial,
} from "../store";

type Phase = "idle" | "reading" | "done";

export default function Paste() {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [conceptCount, setConceptCount] = useState(0);
  const [error, setError] = useState("");
  const [recents] = useState<RecentMaterial[]>(() => getState().recents);
  const [pendingChecks, setPendingChecks] = useState(0);
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Predicted-forgetting nudge — gentle, dismissible, rate-limited (~6h).
  useEffect(() => {
    const { userId } = getState();
    if (!userId || !nudgeAllowed()) return;
    api.getPendingChecks(userId)
      .then((checks) => setPendingChecks(checks.length))
      .catch(() => {});
  }, []);

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || phase !== "idle") return;
    setError("");
    setPhase("reading");

    try {
      let { userId, group } = getState();

      if (!userId) {
        const g = Math.random() < 0.5 ? "control" : "treatment";
        const user = await api.createUser(g as "control" | "treatment");
        userId = user.id;
        group = user.group;
        setState({ userId, group });
      }

      const title = trimmed.slice(0, 60) + (trimmed.length > 60 ? "…" : "");
      const result = await api.analyzeMaterial(title, trimmed);
      setState({
        lastMaterialId: result.material_id,
        lastMaterialTitle: result.knowledge_map.title,
        lastMaterialText: trimmed,
      });
      addRecent(result.material_id, result.knowledge_map.title);

      // Pre-generate the flashcards NOW (fire-and-forget) so the Cards screen
      // is instant when the user gets there — never a loading wall mid-loop.
      api.getQuestions(result.material_id).catch(() => {});

      setConceptCount(result.knowledge_map.total_concepts);
      setPhase("done");

      await new Promise((r) => setTimeout(r, 900));
      navigate(`/plan?m=${result.material_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setPhase("idle");
    }
  }

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 px-4 py-8 max-w-lg mx-auto w-full">
      {/* Logo */}
      <div className="flex items-center gap-2 mb-10">
        <NeuralDot />
        <span className="text-neural font-semibold tracking-widest text-sm uppercase">
          CogPrint
        </span>
      </div>

      {phase === "idle" && (
        <div className="animate-fade-up flex flex-col flex-1 gap-6">
          {/* Predicted-forgetting nudge — gentle, dismissible */}
          {pendingChecks > 0 && (
            <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-start gap-3 animate-fade-up">
              <span className="text-lg mt-0.5">🌱</span>
              <div className="flex-1">
                <p className="text-slate-200 text-sm">
                  Some material is about to fade — a 2-minute review locks it in.
                </p>
                <button
                  onClick={() => navigate("/checks")}
                  className="text-neural text-xs font-medium mt-1"
                >
                  Quick review →
                </button>
              </div>
              <button
                onClick={() => { dismissNudge(); setPendingChecks(0); }}
                className="text-slate-600 text-xs hover:text-slate-400 px-1"
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
          )}

          <div>
            <h1 className="text-3xl font-bold text-white leading-tight">
              Paste what you
              <br />
              need to learn.
            </h1>
            <p className="text-slate-400 mt-2 text-sm">
              CogPrint reads your material and builds a study plan around how
              your brain works.
            </p>
          </div>

          <textarea
            ref={textareaRef}
            className="flex-1 min-h-[220px] bg-ink-700 neural-border rounded-2xl p-4 text-slate-200
                       placeholder-slate-600 resize-none text-sm focus:outline-none
                       focus:border-neural/50 focus:neural-glow transition-all"
            placeholder="Paste a chapter, notes, or anything you want to remember…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSubmit();
            }}
          />

          {error && (
            <p className="text-red-400 text-sm bg-red-950/40 rounded-xl p-3">
              {error}
            </p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!text.trim()}
            className="w-full py-4 rounded-2xl bg-neural text-ink-900 font-bold text-base
                       disabled:opacity-30 disabled:cursor-not-allowed transition-all
                       hover:bg-neural-glow active:scale-[0.98]"
          >
            Analyse →
          </button>

          <p className="text-center text-slate-600 text-xs">
            ⌘ + Enter to submit · Your data stays private
          </p>

          {/* Recent materials — jump straight back in (cached, no re-analysis) */}
          {recents.length > 0 && (
            <div>
              <p className="text-slate-600 text-[10px] font-medium uppercase tracking-widest mb-2">
                Recent
              </p>
              <div className="flex flex-col gap-2">
                {recents.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => {
                      setState({ lastMaterialId: r.id, lastMaterialTitle: r.title });
                      navigate(`/plan?m=${r.id}`);
                    }}
                    className="w-full text-left rounded-xl bg-ink-700/60 neural-border px-4 py-3
                               hover:bg-ink-600 active:scale-[0.99] transition-all"
                  >
                    <p className="text-slate-300 text-sm truncate">{r.title}</p>
                    <p className="text-slate-600 text-[10px] mt-0.5">
                      {new Date(r.ts).toLocaleDateString()} · tap to continue
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {phase === "reading" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 animate-fade-in">
          <ReadingAnimation />
          <div className="text-center">
            <p className="text-neural font-medium">Reading your material…</p>
            <p className="text-slate-500 text-sm mt-1">
              Mapping concepts and building your plan
            </p>
          </div>
        </div>
      )}

      {phase === "done" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 animate-fade-in">
          <div className="text-5xl">🧠</div>
          <p className="text-neural font-semibold text-lg">
            Found {conceptCount} concept{conceptCount !== 1 ? "s" : ""}
          </p>
          <p className="text-slate-400 text-sm">Building your plan…</p>
        </div>
      )}
    </div>
  );
}

function NeuralDot() {
  return (
    <div className="relative w-6 h-6 flex items-center justify-center">
      <div className="w-2 h-2 rounded-full bg-neural breathe absolute" />
      <div className="w-5 h-5 rounded-full border border-neural/30 absolute orbit-1" />
    </div>
  );
}

function ReadingAnimation() {
  return (
    <div className="relative w-24 h-24 flex items-center justify-center">
      {/* Outer rings */}
      <div className="absolute inset-0 rounded-full border border-neural/20 animate-ping" />
      <div
        className="absolute inset-2 rounded-full border border-neural/30"
        style={{ animation: "spin 6s linear infinite" }}
      />
      <div
        className="absolute inset-4 rounded-full border border-neural/50"
        style={{ animation: "spin 4s linear infinite reverse" }}
      />
      {/* Core */}
      <div className="w-8 h-8 rounded-full bg-neural/20 neural-border flex items-center justify-center breathe">
        <span className="text-neural text-xs">✦</span>
      </div>
    </div>
  );
}
