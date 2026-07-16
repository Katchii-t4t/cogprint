import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { currentUserId, getState, setState } from "../store";
import { buildView, label, type InsightView } from "../insights";
import FingerprintArt from "../components/FingerprintArt";
import { renderShareCard, shareFingerprint } from "../lib/shareCard";
import {
  buildForecast,
  archetype,
  WEATHER_META,
  type MemoryForecast,
  type Archetype,
} from "../forecast";
import { getStreak, type StreakInfo } from "../streak";
import type { FingerprintProfile, PendingCheckItem, BuddyForecast } from "../types";

/** Fixed technique order so the art's 7 roots always map the same way
    (identical structure in real and sham modes). */
const TECH_ORDER = [
  "spaced_repetition", "active_recall", "re_reading", "mind_maps",
  "interleaving", "elaborative_interrogation", "practice_testing",
];

function vigorFrom(view: InsightView | null): number[] {
  if (!view) return [];
  const byTech = new Map(view.techniqueRows.map((r) => [r.technique, r.barFraction]));
  return TECH_ORDER.map((t) => byTech.get(t) ?? 0);
}

const EFFECTIVENESS_COLORS: Record<string, string> = {
  best: "bg-neural",
  good: "bg-cyan-600",
  average: "bg-slate-500",
  poor: "bg-slate-700",
};

export default function Grow() {
  const [params] = useSearchParams();
  const score = params.get("score");
  const practice = params.get("practice") === "1";
  const navigate = useNavigate();

  const [view, setView] = useState<InsightView | null>(null);
  const [pendingList, setPendingList] = useState<PendingCheckItem[]>([]);
  const [forecast, setForecast] = useState<MemoryForecast | null>(null);
  const [arch, setArch] = useState<Archetype | null>(null);
  const [streak, setStreak] = useState<StreakInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [name, setName] = useState<string | null>(() => getState().name);

  async function handleShare(v: InsightView) {
    if (sharing) return;
    setSharing(true);
    try {
      const blob = await renderShareCard({
        seed: currentUserId() ?? 1,
        sessions: v.sessionCount,
        vigor: vigorFrom(v),
        confidence: v.confidence,
      });
      await shareFingerprint(blob);
    } catch {
      // Rendering/share failed — stay quiet; the on-screen art is unaffected.
    } finally {
      setSharing(false);
    }
  }

  useEffect(() => {
    const userId = currentUserId();
    if (!userId) { navigate("/"); return; }

    const { group } = getState();
    const isTreatment = (group ?? "treatment") === "treatment";

    // Streak is behavioural (local, not fingerprint-derived) — safe for both groups.
    setStreak(getStreak());

    Promise.all([
      api.getFingerprint(userId),
      api.getPendingChecks(userId),
    ])
      .then(([fingerprint, checks]) => {
        // insights.ts (master) takes userId for the deterministic sham seed.
        setView(buildView(fingerprint.fingerprint, group ?? "treatment", userId));
        setPendingList(checks);
        // Personalised surfaces (#1 forecast, #2 archetype) are treatment-only,
        // preserving the RCT blind. Control users still get the sham insights +
        // the streak so the screen never looks empty.
        if (isTreatment) {
          const fp: FingerprintProfile = fingerprint.fingerprint;
          setForecast(buildForecast(fp, checks.length));
          setArch(archetype(fp));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) return <LoadingState />;

  const v = view;
  const sessionCount = v?.sessionCount ?? 0;
  const confidence = v?.confidence ?? "low";
  const pending = pendingList.length;

  return (
    <div className="flex flex-col min-h-dvh bg-ink-900 max-w-lg mx-auto w-full">
      {/* Header */}
      <div className="px-4 pt-8 pb-4">
        <div className="flex items-center justify-between mb-6">
          <button onClick={() => navigate("/")} className="text-slate-500 text-sm hover:text-slate-300">
            ← Paste more
          </button>
          <button
            onClick={() => navigate("/plan")}
            className="text-neural text-sm"
          >
            Study plan →
          </button>
        </div>

        {/* Practice banner — flashcard rounds are rehearsal, never measurement */}
        {practice && (
          <div className="rounded-2xl bg-ink-700 neural-border p-4 mb-4 animate-fade-up">
            <div className="flex items-center gap-3">
              <span className="text-3xl">🌿</span>
              <div>
                <p className="text-white font-bold">Practice round — not scored</p>
                <p className="text-slate-400 text-xs">
                  Flashcards are rehearsal. Quiz rounds are what grow your fingerprint.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Score banner */}
        {score !== null && (
          <div className="rounded-2xl bg-ink-700 neural-border p-4 mb-4 animate-fade-up">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{Number(score) >= 80 ? "🔥" : Number(score) >= 50 ? "💪" : "📈"}</span>
              <div>
                <p className="text-white font-bold">{score}% correct this session</p>
                <p className="text-slate-400 text-xs">
                  {Number(score) >= 80
                    ? "Excellent retention — your fingerprint is growing."
                    : "Every session teaches the algorithm something new."}
                </p>
              </div>
            </div>
          </div>
        )}

      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-24 space-y-6">
        {/* Fingerprint header */}
        <div className="animate-fade-up">
          <h1 className="text-2xl font-bold text-white">
            {name ? `${name}'s fingerprint` : "Your fingerprint"}
          </h1>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <ConfidencePill confidence={confidence} />
            <span className="text-slate-500 text-xs">{sessionCount} session{sessionCount !== 1 ? "s" : ""}</span>
            {arch && <ArchetypeBadge archetype={arch} />}
          </div>
        </div>

        {/* #4 Retention streak — behavioural, shown to everyone */}
        {streak && streak.current > 0 && <StreakBadge streak={streak} />}

        {/* #1 Memory weather forecast (treatment only) */}
        {forecast && forecast.weather !== "unknown" && (
          <ForecastCard forecast={forecast} onReview={() => navigate("/checks")} />
        )}

        {/* #5 Boss battles — due retention checks reframed */}
        {pending > 0 && (
          <BossSection
            checks={pendingList}
            weakestTechnique={weakestTechnique(v)}
            onFight={() => navigate("/checks")}
          />
        )}

        {/* Low confidence — growing state */}
        {confidence === "low" && (
          <GrowingState sessionCount={sessionCount} onStudy={() => navigate("/")} />
        )}

        {/* Medium / high — full fingerprint */}
        {confidence !== "low" && v && (
          <>
            {/* The living fingerprint — the payoff, front and centre */}
            <div className="flex flex-col items-center animate-fade-up -mt-2">
              <FingerprintArt
                seed={currentUserId() ?? 1}
                sessions={sessionCount}
                vigor={vigorFrom(v)}
                size={272}
              />
              {/* The growth engine: every shared fingerprint is marketing */}
              <button
                onClick={() => handleShare(v)}
                disabled={sharing}
                className="mt-1 px-5 py-2 rounded-full bg-ink-700 neural-border text-neural text-xs
                           font-semibold hover:bg-ink-600 active:scale-[0.97] transition-all
                           disabled:opacity-50"
              >
                {sharing ? "Rendering…" : "⤴ Share your fingerprint"}
              </button>
            </div>
            {/* Top technique */}
            {v.topTechnique && (
              <Section title="Best technique for you">
                <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-neural/10 border border-neural/20 flex items-center justify-center">
                    <span className="text-neural text-lg">⚡</span>
                  </div>
                  <div>
                    <p className="text-white font-semibold">{label(v.topTechnique)}</p>
                    {v.bestTimeOfDay && (
                      <p className="text-slate-400 text-xs mt-0.5">
                        Best time: {v.bestTimeOfDay}
                      </p>
                    )}
                  </div>
                </div>
              </Section>
            )}

            {/* Technique bars */}
            {v.techniqueRows.length > 0 && (
              <Section title="Technique effectiveness">
                <div className="space-y-3">
                  {v.techniqueRows.map((row) => (
                    <div key={row.technique}>
                      <div className="flex justify-between mb-1">
                        <span className="text-slate-300 text-xs">{label(row.technique)}</span>
                        {row.label && (
                          <span
                            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                              row.label === "best"
                                ? "text-neural bg-neural/10"
                                : row.label === "good"
                                ? "text-cyan-400 bg-cyan-900/20"
                                : "text-slate-500 bg-slate-800"
                            }`}
                          >
                            {row.label}
                          </span>
                        )}
                      </div>
                      <div className="h-1.5 bg-ink-500 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${
                            EFFECTIVENESS_COLORS[row.label ?? "average"]
                          }`}
                          style={{ width: `${row.barFraction * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Retention / memory profiles */}
            {v.retentionRows.length > 0 && (
              <Section title="Memory stability per technique">
                <div className="grid grid-cols-2 gap-3">
                  {v.retentionRows.map((r) => (
                    <div
                      key={r.technique}
                      className="rounded-2xl bg-ink-700 neural-border p-3 flex flex-col gap-1"
                    >
                      <p className="text-slate-400 text-[10px] font-medium uppercase tracking-wider">
                        {label(r.technique)}
                      </p>
                      <p className="text-white font-bold text-xl">
                        {Math.round(r.predicted7d * 100)}%
                      </p>
                      <p className="text-slate-500 text-[10px]">at 7 days · {r.label}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Insights */}
            {v.insights.length > 0 && (
              <Section title="What your data says">
                <div className="space-y-3">
                  {v.insights.map((ins, i) => (
                    <div
                      key={i}
                      className="rounded-2xl bg-ink-700 neural-border p-4"
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <p className="text-slate-200 text-sm leading-relaxed">{ins.text}</p>
                      {ins.action && (
                        <p className="text-neural text-xs mt-2 font-medium">→ {ins.action}</p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Trend */}
            {v.improving !== null && (
              <Section title="Trend">
                <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-center gap-3">
                  <span className="text-2xl">{v.improving ? "📈" : "📊"}</span>
                  <p className="text-slate-300 text-sm">
                    {v.improving
                      ? "You're improving over time. Keep the streak going."
                      : "Your scores are stable. Try mixing techniques to break through."}
                  </p>
                </div>
              </Section>
            )}

            {/* Save your progress — value delivered, now the soft commitment
                moment (no login wall, no account; spec §7). */}
            {!name && (
              <SaveProgress userId={currentUserId() ?? 0} onSaved={setName} />
            )}
          </>
        )}

        {/* #9 study-buddy accountability */}
        <BuddyCard />
      </div>

      {/* Bottom CTA */}
      <div className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-lg px-4 pb-6 pt-4 glass border-t border-ink-500/30">
        <button
          onClick={() => navigate("/")}
          className="w-full py-4 rounded-2xl bg-ink-600 border border-ink-400 text-slate-200 font-semibold
                     hover:bg-ink-500 active:scale-[0.98] transition-all"
        >
          + Study more material
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="animate-fade-up">
      <p className="text-slate-500 text-xs font-medium uppercase tracking-widest mb-3">{title}</p>
      {children}
    </div>
  );
}

function ConfidencePill({ confidence }: { confidence: string }) {
  const styles: Record<string, string> = {
    low: "bg-slate-800 text-slate-400",
    medium: "bg-neural-muted text-neural",
    high: "bg-neural/20 text-neural border border-neural/30",
  };
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-widest ${styles[confidence]}`}>
      {confidence} confidence
    </span>
  );
}

function GrowingState({ sessionCount, onStudy }: { sessionCount: number; onStudy: () => void }) {
  const needed = Math.max(0, 5 - sessionCount);

  return (
    <div className="rounded-3xl bg-ink-700 neural-border p-6 flex flex-col items-center gap-6 animate-fade-up">
      {/* The young fingerprint — same organism the user will watch grow */}
      <FingerprintArt
        seed={currentUserId() ?? 1}
        sessions={sessionCount}
        size={200}
      />

      <div className="text-center">
        <p className="text-white font-semibold">Your fingerprint is growing</p>
        <p className="text-slate-400 text-sm mt-1">
          {needed > 0
            ? `${needed} more session${needed !== 1 ? "s" : ""} to unlock your first insights`
            : "Processing your first insights…"}
        </p>
      </div>

      <button
        onClick={onStudy}
        className="w-full py-3 rounded-xl bg-neural/10 border border-neural/20 text-neural text-sm font-medium
                   hover:bg-neural/20 active:scale-[0.98] transition-all"
      >
        Study more →
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-dvh gap-4 bg-ink-900">
      <div className="w-10 h-10 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
      <p className="text-slate-400 text-sm">Loading your fingerprint…</p>
    </div>
  );
}

/** The soft save moment: name yourself + copy your CogPrint ID to return on
    another device. Client-side only; dismissible; shown once per session. */
function SaveProgress({ userId, onSaved }: { userId: number; onSaved: (n: string) => void }) {
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [hidden, setHidden] = useState(
    () => sessionStorage.getItem("cog_save_dismissed") === "1"
  );

  if (hidden) return null;

  function save() {
    const n = draft.trim();
    if (!n) return;
    setState({ name: n });
    onSaved(n);
  }

  async function copyId() {
    try {
      await navigator.clipboard.writeText(String(userId));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable — the ID is still visible to copy manually.
    }
  }

  return (
    <div className="rounded-2xl bg-ink-700 neural-border p-4 animate-fade-up">
      <div className="flex items-start justify-between">
        <p className="text-white font-semibold text-sm">Save your progress</p>
        <button
          onClick={() => { sessionStorage.setItem("cog_save_dismissed", "1"); setHidden(true); }}
          className="text-slate-600 text-xs hover:text-slate-400 px-1"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      <p className="text-slate-400 text-xs mt-1">
        Your fingerprint lives on this device. Give yourself a name, and keep
        your CogPrint ID to pick up where you left off anywhere.
      </p>

      <div className="flex gap-2 mt-3">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder="Your name"
          className="flex-1 bg-ink-800 neural-border rounded-xl px-3 py-2 text-sm text-slate-200
                     placeholder-slate-600 focus:outline-none focus:border-neural/50"
        />
        <button
          onClick={save}
          disabled={!draft.trim()}
          className="px-4 py-2 rounded-xl bg-neural text-ink-900 text-sm font-bold
                     disabled:opacity-30 hover:bg-neural-glow active:scale-[0.97] transition-all"
        >
          Save
        </button>
      </div>

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-ink-500/40">
        <p className="text-slate-500 text-xs">
          Your CogPrint ID: <span className="text-neural font-mono font-semibold">#{userId}</span>
        </p>
        <button onClick={copyId} className="text-neural text-xs font-medium">
          {copied ? "Copied ✓" : "Copy ID"}
        </button>
      </div>
    </div>
  );
}
// --- #2 archetype badge -----------------------------------------------------
function ArchetypeBadge({ archetype }: { archetype: Archetype }) {
  return (
    <span
      className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-neural/10 text-neural
                 border border-neural/20 uppercase tracking-widest"
      title={`${archetype.blurb} (based on your data so far)`}
    >
      {archetype.emoji} {archetype.name}
    </span>
  );
}

// --- #4 streak badge --------------------------------------------------------
function StreakBadge({ streak }: { streak: StreakInfo }) {
  return (
    <div className="rounded-2xl bg-ink-700 neural-border p-4 flex items-center gap-3 animate-fade-up">
      <span className="text-3xl">{streak.keptToday ? "🔥" : "🌙"}</span>
      <div className="flex-1">
        <p className="text-white font-bold">
          {streak.current} day{streak.current !== 1 ? "s" : ""} memory streak
        </p>
        <p className="text-slate-400 text-xs mt-0.5">
          {streak.keptToday
            ? "You kept your memory strong today. Keep it alive!"
            : "Study or run a check today to keep the streak alive."}
        </p>
      </div>
      {streak.longest > streak.current && (
        <span className="text-slate-500 text-[10px] text-right">
          best<br />
          <span className="text-slate-300 font-semibold">{streak.longest}d</span>
        </span>
      )}
    </div>
  );
}

// --- #1 memory weather forecast --------------------------------------------
function ForecastCard({
  forecast,
  onReview,
}: {
  forecast: MemoryForecast;
  onReview: () => void;
}) {
  const meta = WEATHER_META[forecast.weather];
  return (
    <div className="rounded-2xl bg-ink-700 neural-border p-4 animate-fade-up">
      <div className="flex items-center gap-3">
        <span className="text-3xl">{meta.icon}</span>
        <div className="flex-1">
          <p className={`font-bold ${meta.tint}`}>Memory forecast · {meta.label}</p>
          <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">
            {forecast.summary}
          </p>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <ForecastChip n={forecast.fading} label="fading" tint="text-rose-300" />
        <ForecastChip n={forecast.cooling} label="cooling" tint="text-amber-300" />
        <ForecastChip n={forecast.solid} label="solid" tint="text-neural" />
      </div>
      {(forecast.weather === "stormy" || forecast.pendingChecks > 0) && (
        <button
          onClick={onReview}
          className="w-full mt-3 py-2.5 rounded-xl bg-neural/10 border border-neural/20 text-neural
                     text-sm font-medium hover:bg-neural/20 active:scale-[0.98] transition-all"
        >
          Clear the skies — review now →
        </button>
      )}
    </div>
  );
}

function ForecastChip({ n, label, tint }: { n: number; label: string; tint: string }) {
  return (
    <div className="flex-1 rounded-xl bg-ink-800 border border-ink-500/40 py-2 text-center">
      <p className={`font-bold ${tint}`}>{n}</p>
      <p className="text-slate-500 text-[10px] uppercase tracking-wider">{label}</p>
    </div>
  );
}

// --- #5 boss battles --------------------------------------------------------
function weakestTechnique(v: InsightView | null): string | null {
  if (!v || v.retentionRows.length === 0) return null;
  const weakest = [...v.retentionRows].sort(
    (a, b) => a.predicted7d - b.predicted7d
  )[0];
  return weakest ? weakest.technique : null;
}

function BossSection({
  checks,
  weakestTechnique,
  onFight,
}: {
  checks: PendingCheckItem[];
  weakestTechnique: string | null;
  onFight: () => void;
}) {
  return (
    <Section title="Memory bosses">
      <div className="space-y-3">
        {weakestTechnique && (
          <div className="rounded-2xl bg-rose-950/20 border border-rose-500/30 p-4">
            <p className="text-rose-300 font-semibold text-sm">
              👹 Final boss: {label(weakestTechnique)}
            </p>
            <p className="text-rose-400/60 text-xs mt-0.5">
              Your weakest-decay technique. Beat its checks to level it up.
            </p>
          </div>
        )}
        {checks.map((c, i) => {
          const overdueDays = Math.max(
            0,
            Math.round((Date.now() - new Date(c.due_date).getTime()) / 86_400_000)
          );
          const hp = Math.min(100, 40 + overdueDays * 20);
          return (
            <div
              key={`${c.session_id}-${c.check_type}`}
              className="rounded-2xl bg-ink-700 neural-border p-4"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-200 text-sm font-medium">
                  ⚔️ {c.check_type} check
                </span>
                <span className="text-slate-500 text-[10px]">
                  {overdueDays > 0 ? `overdue ${overdueDays}d` : "ready"}
                </span>
              </div>
              <div className="h-1.5 bg-ink-500 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-rose-500/70 transition-all duration-700"
                  style={{ width: `${hp}%` }}
                />
              </div>
            </div>
          );
        })}
        <button
          onClick={onFight}
          className="w-full py-3 rounded-xl bg-neural text-ink-900 font-semibold
                     hover:bg-neural-glow active:scale-[0.98] transition-all"
        >
          Fight bosses →
        </button>
      </div>
    </Section>
  );
}

// --- #9 study-buddy accountability -----------------------------------------
function BuddyCard() {
  const [myCode, setMyCode] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [buddyCode, setBuddyCode] = useState<string | null>(getState().buddyCode);
  const [buddy, setBuddy] = useState<BuddyForecast | null>(null);
  const [err, setErr] = useState("");

  // Fetch (or lazily create) my own share code once.
  useEffect(() => {
    const userId = currentUserId();
    if (!userId) return;
    api.getShareCode(userId).then((r) => setMyCode(r.share_code)).catch(() => {});
  }, []);

  // Whenever we're following a buddy, load their forecast.
  useEffect(() => {
    if (!buddyCode) { setBuddy(null); return; }
    api
      .getBuddyForecast(buddyCode)
      .then(setBuddy)
      .catch(() => setErr("Couldn't find a buddy with that code."));
  }, [buddyCode]);

  function follow() {
    const code = input.trim().toUpperCase();
    if (!code) return;
    if (code === myCode) { setErr("That's your own code!"); return; }
    setErr("");
    setState({ buddyCode: code });
    setBuddyCode(code);
    setInput("");
  }

  function unfollow() {
    setState({ buddyCode: null });
    setBuddyCode(null);
    setBuddy(null);
  }

  return (
    <Section title="Study buddy">
      <div className="rounded-2xl bg-ink-700 neural-border p-4 space-y-4">
        {/* My code to share */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-xs">Your buddy code</p>
            <p className="text-neural font-bold text-lg tracking-widest font-mono">
              {myCode ?? "······"}
            </p>
          </div>
          {myCode && (
            <button
              onClick={() => navigator.clipboard?.writeText(myCode).catch(() => {})}
              className="text-slate-400 text-xs px-3 py-1.5 rounded-lg bg-ink-600 border border-ink-400
                         hover:text-slate-200 transition-colors"
            >
              Copy
            </button>
          )}
        </div>

        {/* Buddy forecast, or the follow form */}
        {buddy ? (
          <div className="border-t border-ink-500/40 pt-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-slate-200 text-sm font-medium">
                👥 Buddy {buddyCode}
              </p>
              <button onClick={unfollow} className="text-slate-500 text-xs hover:text-slate-300">
                Unfollow
              </button>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              {buddy.fading > 0
                ? `${buddy.fading} concept${buddy.fading > 1 ? "s" : ""} fading`
                : "memory holding strong"}
              {buddy.reviews_due > 0 && ` · ${buddy.reviews_due} review${buddy.reviews_due > 1 ? "s" : ""} due`}
              {` · ${buddy.session_count} session${buddy.session_count !== 1 ? "s" : ""}`}
            </p>
            {buddy.fading > 0 && (
              <p className="text-amber-300/80 text-xs mt-1">
                Nudge them to review before it slips away 👀
              </p>
            )}
          </div>
        ) : (
          <div className="border-t border-ink-500/40 pt-3">
            <p className="text-slate-400 text-xs mb-2">Follow a buddy's forecast</p>
            <div className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Enter their code"
                maxLength={12}
                className="flex-1 bg-ink-800 border border-ink-500/60 rounded-lg px-3 py-2 text-sm text-white
                           placeholder:text-slate-600 uppercase tracking-widest focus:border-neural/40 outline-none"
              />
              <button
                onClick={follow}
                className="px-4 py-2 rounded-lg bg-neural text-ink-900 text-sm font-semibold
                           hover:bg-neural-glow transition-all"
              >
                Follow
              </button>
            </div>
            {err && <p className="text-rose-400 text-xs mt-2">{err}</p>}
          </div>
        )}
      </div>
    </Section>
  );
}
