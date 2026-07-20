import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { currentUserId } from "../store";
import type { MaterialLibraryItem } from "../types";

/**
 * §3.3 — the returning-user home. Every deck the user has studied, newest
 * first, each carrying its live Ebbinghaus state: a retention ring, a fading
 * badge, and how many retention checks are due. Paste becomes "+ new".
 *
 * Design: stays strictly inside the neural system (ink surfaces, cyan primary,
 * 8pt spacing, staggered fade-up entrances ≤300ms, focus-visible rings).
 */

/** Retention → ring color. Mirrors the forecast palette used on Grow. */
function ringTone(r: number, fading: boolean): string {
  if (fading) return "#fb7185";        // rose-400 — slipping
  if (r < 0.75) return "#fbbf24";      // amber-400 — cooling
  return "#22d3ee";                     // neural — solid
}

function relTime(iso: string): string {
  const days = (Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 86_400_000;
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 30) return `${Math.floor(days)}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

export default function Library() {
  const navigate = useNavigate();
  const [items, setItems] = useState<MaterialLibraryItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }
    api
      .getLibrary(userId)
      .then(setItems)
      .catch(() => setError("Couldn't load your library. Pull to retry."));
  }, [navigate]);

  const totalDue = (items ?? []).reduce((n, it) => n + it.reviews_due, 0);

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full">
      {/* Header */}
      <div className="sticky top-0 z-10 glass px-4 pt-8 pb-4 border-b border-ink-500/40">
        <div className="flex items-center justify-between mb-3">
          <button
            onClick={() => navigate("/grow")}
            className="text-slate-500 text-sm hover:text-slate-300 transition-colors
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neural/50 rounded-lg px-1"
          >
            ← Fingerprint
          </button>
          <button
            onClick={() => navigate("/")}
            className="text-neural text-sm px-3 py-1.5 rounded-lg bg-neural/10 border border-neural/20
                       hover:bg-neural/20 active:scale-[0.97] transition-all
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neural/50"
          >
            ＋ New material
          </button>
        </div>
        <h1 className="text-xl font-bold text-white">Your library</h1>
        {items && items.length > 0 && (
          <p className="text-slate-400 text-sm mt-1">
            {items.length} deck{items.length !== 1 ? "s" : ""}
            {totalDue > 0 && (
              <> · <span className="text-amber-300">{totalDue} review{totalDue !== 1 ? "s" : ""} due</span></>
            )}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 pb-16">
        {error && (
          <p className="text-red-400 text-sm bg-red-950/40 rounded-xl p-3">{error}</p>
        )}

        {/* Skeletons while loading — shaped like the real cards, no layout shift */}
        {items === null && !error && (
          <>
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-2xl bg-ink-700 neural-border p-4 animate-pulse">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-ink-500/60" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3.5 w-2/3 rounded bg-ink-500/60" />
                    <div className="h-2.5 w-1/2 rounded bg-ink-500/40" />
                  </div>
                </div>
              </div>
            ))}
          </>
        )}

        {items !== null && items.length === 0 && <EmptyLibrary onNew={() => navigate("/")} />}

        {(items ?? []).map((it, i) => (
          <DeckCard key={it.material_id} item={it} index={i}
                    onOpen={() => navigate(`/plan?m=${it.material_id}`)} />
        ))}
      </div>
    </div>
  );
}

function DeckCard({
  item, index, onOpen,
}: { item: MaterialLibraryItem; index: number; onOpen: () => void }) {
  const pct = Math.round(item.predicted_retention * 100);
  const tone = ringTone(item.predicted_retention, item.fading);
  // SVG retention ring: r=20 → circumference ≈ 125.7
  const C = 2 * Math.PI * 20;

  return (
    <button
      onClick={onOpen}
      style={{ animationDelay: `${Math.min(index, 6) * 50}ms` }}
      className="w-full text-left rounded-2xl bg-ink-700 neural-border p-4 animate-fade-up
                 transition-all hover:border-neural/30 hover:bg-ink-600/70 active:scale-[0.99]
                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neural/50"
    >
      <div className="flex items-center gap-4">
        {/* Retention ring */}
        <div className="relative w-12 h-12 shrink-0" aria-hidden="true">
          <svg viewBox="0 0 48 48" className="w-12 h-12 -rotate-90">
            <circle cx="24" cy="24" r="20" fill="none" stroke="#1e2d4a" strokeWidth="4" />
            <circle
              cx="24" cy="24" r="20" fill="none"
              stroke={tone} strokeWidth="4" strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * C} ${C}`}
              className="transition-all duration-700"
            />
          </svg>
          <span
            className="absolute inset-0 flex items-center justify-center text-[10px] font-bold"
            style={{ color: tone }}
          >
            {pct}%
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm truncate">{item.title}</p>
          <p className="text-slate-500 text-xs mt-1">
            {item.concept_count} concept{item.concept_count !== 1 ? "s" : ""} ·{" "}
            {item.session_count} session{item.session_count !== 1 ? "s" : ""} ·{" "}
            studied {relTime(item.last_studied)}
          </p>
          {(item.reviews_due > 0 || item.fading) && (
            <div className="flex gap-1.5 mt-2">
              {item.reviews_due > 0 && (
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-300 border border-amber-500/20">
                  ⏰ {item.reviews_due} due
                </span>
              )}
              {item.fading && (
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-rose-950/40 text-rose-300 border border-rose-500/20">
                  fading
                </span>
              )}
            </div>
          )}
        </div>

        <span className="text-slate-600 text-sm" aria-hidden="true">→</span>
      </div>
    </button>
  );
}

function EmptyLibrary({ onNew }: { onNew: () => void }) {
  return (
    <div className="rounded-3xl bg-ink-700 neural-border p-8 flex flex-col items-center gap-4 text-center animate-fade-up mt-6">
      <div className="w-14 h-14 rounded-full bg-neural/10 border border-neural/20 flex items-center justify-center">
        <span className="text-2xl" aria-hidden="true">📚</span>
      </div>
      <div>
        <p className="text-white font-semibold">Nothing here yet</p>
        <p className="text-slate-400 text-sm mt-1 leading-relaxed">
          Every material you study lands here, with a live memory forecast for each deck.
        </p>
      </div>
      <button
        onClick={onNew}
        className="mt-2 px-6 py-3 rounded-2xl bg-neural text-ink-900 font-bold text-sm
                   hover:bg-neural-glow active:scale-[0.98] transition-all
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
      >
        Paste your first material →
      </button>
    </div>
  );
}
