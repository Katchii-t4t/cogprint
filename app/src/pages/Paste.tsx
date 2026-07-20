import { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import {
  addRecent, dismissNudge, getState, nudgeAllowed, setState,
  type RecentMaterial,
} from "../store";

type Phase = "idle" | "reading" | "ocr" | "done";

/** Downscale a photo client-side (longest edge ~1600px, JPEG 0.85) to bound
    upload size and vision cost, then base64-encode it. */
async function imageFileToBase64Jpeg(file: File): Promise<{ b64: string; media: string }> {
  const bitmap = await createImageBitmap(file);
  const maxEdge = 1600;
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas unavailable");
  ctx.drawImage(bitmap, 0, 0, w, h);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
  return { b64: dataUrl.slice(dataUrl.indexOf(",") + 1), media: "image/jpeg" };
}

export default function Paste() {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [conceptCount, setConceptCount] = useState(0);
  const [error, setError] = useState("");
  const [recents] = useState<RecentMaterial[]>(() => getState().recents);
  const [nudge, setNudge] = useState<
    | { kind: "fade"; materialId: number; title: string }
    | { kind: "checks"; count: number }
    | null
  >(null);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoreId, setRestoreId] = useState("");
  const [restoreErr, setRestoreErr] = useState("");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  async function handlePhoto(file: File) {
    setError("");
    setPhase("ocr");
    try {
      const { b64, media } = await imageFileToBase64Jpeg(file);
      const r = await api.ocr(b64, media);
      setText(r.text);
      setPhase("idle"); // land the text in the textarea so the user can glance/edit
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setError(
        msg.startsWith("503")
          ? "Photo scanning needs setup — the AI key isn't configured on this server yet. You can still paste text."
          : "Couldn't read that photo. Try a clearer shot, or paste the text instead."
      );
      setPhase("idle");
    }
  }

  async function handleRestore() {
    const id = parseInt(restoreId, 10);
    if (!id || Number.isNaN(id)) {
      setRestoreErr("Enter your numeric CogPrint ID (e.g. 42).");
      return;
    }
    setRestoreErr("");
    try {
      const user = await api.getUser(id);
      setState({ userId: user.id, group: user.group });
      navigate("/grow");
    } catch {
      setRestoreErr("We couldn't find that ID — double-check it and try again.");
    }
  }

  // Predicted-forgetting nudge — gentle, dismissible, rate-limited (~6h).
  // Prefers naming the specific fading material (Ebbinghaus, from the user's
  // own data); falls back to the generic pending-checks reminder.
  useEffect(() => {
    const { userId } = getState();
    if (!userId || !nudgeAllowed()) return;
    Promise.all([
      api.getReviewSuggestions(userId).catch(() => []),
      api.getPendingChecks(userId).catch(() => []),
    ]).then(([suggestions, checks]) => {
      const fading = suggestions.find((s) => s.fading);
      if (fading) {
        setNudge({ kind: "fade", materialId: fading.material_id, title: fading.title });
      } else if (checks.length > 0) {
        setNudge({ kind: "checks", count: checks.length });
      }
    });
  }, []);

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
      {/* Logo + library shortcut for returning users */}
      <div className="flex items-center gap-2 mb-10">
        <NeuralDot />
        <span className="text-neural font-semibold tracking-widest text-sm uppercase">
          CogPrint
        </span>
        <div className="flex-1" />
        {getState().userId && (
          <button
            onClick={() => navigate("/library")}
            className="text-slate-400 text-xs px-3 py-1.5 rounded-lg bg-ink-700 neural-border
                       hover:text-neural hover:border-neural/40 active:scale-[0.97] transition-all
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neural/50"
          >
            📚 Library
          </button>
        )}
      </div>

      {phase === "idle" && (
        <div className="animate-fade-up flex flex-col flex-1 gap-6">
          {/* Predicted-forgetting nudge — gentle, dismissible */}
          {nudge && (
            <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-start gap-3 animate-fade-up">
              <span className="text-lg mt-0.5">🌱</span>
              <div className="flex-1">
                <p className="text-slate-200 text-sm">
                  {nudge.kind === "fade" ? (
                    <>
                      You're about to forget{" "}
                      <span className="text-neural">
                        “{nudge.title.length > 44 ? nudge.title.slice(0, 44) + "…" : nudge.title}”
                      </span>{" "}
                      — a 2-minute review locks it in.
                    </>
                  ) : (
                    <>Some material is about to fade — a 2-minute review locks it in.</>
                  )}
                </p>
                <button
                  onClick={() =>
                    navigate(nudge.kind === "fade" ? `/cards?m=${nudge.materialId}` : "/checks")
                  }
                  className="text-neural text-xs font-medium mt-1"
                >
                  Quick review →
                </button>
              </div>
              <button
                onClick={() => { dismissNudge(); setNudge(null); }}
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

          {/* Photo -> OCR: snap notes or a textbook page instead of typing */}
          <input
            ref={photoInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = ""; // allow re-picking the same file
              if (f) handlePhoto(f);
            }}
          />
          <button
            onClick={() => photoInputRef.current?.click()}
            className="w-full py-3 rounded-2xl bg-ink-700 neural-border text-slate-300 text-sm
                       font-medium hover:bg-ink-600 active:scale-[0.98] transition-all"
          >
            📷 Snap a photo of your notes
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

          {/* Restore by CogPrint ID — the other half of "save your progress" */}
          <div className="text-center">
            {!restoreOpen ? (
              <button
                onClick={() => setRestoreOpen(true)}
                className="text-slate-600 text-xs hover:text-slate-400 transition-colors"
              >
                Have a CogPrint ID? Restore your progress
              </button>
            ) : (
              <div className="flex flex-col gap-2 animate-fade-up">
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={restoreId}
                    onChange={(e) => setRestoreId(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleRestore()}
                    placeholder="Your CogPrint ID, e.g. 42"
                    className="flex-1 bg-ink-700 neural-border rounded-xl px-3 py-2 text-sm text-slate-200
                               placeholder-slate-600 focus:outline-none focus:border-neural/50"
                  />
                  <button
                    onClick={handleRestore}
                    className="px-4 py-2 rounded-xl bg-ink-600 border border-ink-400 text-slate-200 text-sm
                               font-medium hover:bg-ink-500 active:scale-[0.97] transition-all"
                  >
                    Restore
                  </button>
                </div>
                {restoreErr && <p className="text-red-400 text-xs">{restoreErr}</p>}
              </div>
            )}
          </div>
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

      {phase === "ocr" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 animate-fade-in">
          <ReadingAnimation />
          <div className="text-center">
            <p className="text-neural font-medium">Reading your photo…</p>
            <p className="text-slate-500 text-sm mt-1">
              Transcribing the text so you can review it
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
