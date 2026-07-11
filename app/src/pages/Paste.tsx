import { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { getState, setState } from "../store";

type Phase = "idle" | "reading" | "done";

export default function Paste() {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [conceptCount, setConceptCount] = useState(0);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // #8 shared decks — opening a `/?deck=<materialId>` link imports that deck.
  // The plan/technique/fingerprint are still computed for THIS user, so the
  // deck is shared but the personalization is your own (nothing leaks).
  useEffect(() => {
    const deck = params.get("deck");
    if (!deck) return;
    const materialId = Number(deck);
    if (!Number.isFinite(materialId)) return;

    (async () => {
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
        setState({ lastMaterialId: materialId });
        navigate(`/plan?m=${materialId}`);
      } catch {
        setPhase("idle");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      });
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
