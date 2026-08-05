import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { setState } from "../store";

/**
 * Landing page for an emailed magic link (§1.1).
 *
 * Serves both purposes the backend issues links for — confirming an address
 * and signing in on a new device — because the redemption call is identical
 * and the user experiences both as "I clicked the link and I'm in".
 */

type Phase = "verifying" | "done" | "invalid";

export default function Verify() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>("verifying");
  // React 18 mounts effects twice in dev StrictMode; the token is single-use,
  // so a second redemption would fail a link that actually worked.
  const redeemed = useRef(false);

  useEffect(() => {
    const token = params.get("token");
    if (!token) { setPhase("invalid"); return; }
    if (redeemed.current) return;
    redeemed.current = true;

    api
      .verifyMagicLink(token)
      .then((user) => {
        setState({ userId: user.id, group: user.group });
        setPhase("done");
        window.setTimeout(() => navigate("/grow"), 900);
      })
      .catch(() => setPhase("invalid"));
  }, [params, navigate]);

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 px-4 py-8 max-w-lg mx-auto w-full">
      <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
        {phase === "verifying" && (
          <>
            <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
            <p className="text-slate-400 text-sm">Checking your link…</p>
          </>
        )}

        {phase === "done" && (
          <div className="animate-fade-up flex flex-col items-center gap-3">
            <div className="w-14 h-14 rounded-full bg-neural/10 border border-neural/20 flex items-center justify-center">
              <span className="text-2xl" aria-hidden="true">✓</span>
            </div>
            <p className="text-white font-semibold">You're in</p>
            <p className="text-slate-400 text-sm">Taking you to your fingerprint…</p>
          </div>
        )}

        {phase === "invalid" && (
          <div className="animate-fade-up flex flex-col items-center gap-4 rounded-2xl bg-ink-700 neural-border p-6">
            <span className="text-2xl" aria-hidden="true">⏳</span>
            <div>
              <p className="text-white font-semibold">That link has expired</p>
              <p className="text-slate-400 text-sm mt-1 leading-relaxed">
                Links work once and last 15 minutes. Ask for a fresh one and
                it'll be in your inbox in a moment.
              </p>
            </div>
            <button
              onClick={() => navigate("/")}
              className="px-6 py-3 rounded-2xl bg-neural text-ink-900 font-bold text-sm
                         hover:bg-neural-glow active:scale-[0.98] transition-all
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
            >
              Request a new link →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
