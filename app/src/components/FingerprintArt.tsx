import { useEffect, useMemo, useState } from "react";

/**
 * The living cognitive fingerprint — the brand centrepiece.
 *
 * A generative neural/root system that is:
 *  - unique per user (deterministic PRNG seeded by userId)
 *  - grown by data (branch reach + node count scale with session_count)
 *  - shaped by the user's measured technique vigor (7 main roots, one per
 *    technique; stronger techniques grow longer, brighter roots)
 *
 * Sham-safety: the component only consumes numbers (seed, sessions, vigor[]).
 * Real and sham modes feed it the same shapes, so the visual is identical in
 * structure either way — content differences live in the InsightView, not here.
 *
 * All motion ≤300ms per element (staggered draw-in), plus a slow ambient
 * breathe on the core. Pure SVG + CSS transitions — no libraries.
 */

// Deterministic PRNG (mulberry32)
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Branch {
  d: string;          // main path
  subs: string[];     // sub-branch paths
  tips: Array<{ x: number; y: number; r: number }>;
  vigor: number;      // 0..1 → opacity/width/colour
  delay: number;      // draw-in stagger (ms)
}

function buildBranches(seed: number, sessions: number, vigor: number[]): Branch[] {
  const rnd = mulberry32(seed * 2654435761 + 7);
  const growth = Math.min(1, 0.3 + (sessions / 20) * 0.7); // small on day one → full at ~20 sessions
  const C = 140;
  const branches: Branch[] = [];
  const baseAngle = rnd() * Math.PI * 2;

  for (let i = 0; i < 7; i++) {
    const v = vigor[i] ?? 0.35 + rnd() * 0.3;
    const angle = baseAngle + (i / 7) * Math.PI * 2 + (rnd() - 0.5) * 0.35;
    const reach = (46 + v * 62) * growth + rnd() * 8;

    // Main root: two chained quadratic curves with organic wobble
    const midA = angle + (rnd() - 0.5) * 0.5;
    const m1x = C + Math.cos(midA) * reach * 0.45;
    const m1y = C + Math.sin(midA) * reach * 0.45;
    const endA = angle + (rnd() - 0.5) * 0.6;
    const ex = C + Math.cos(endA) * reach;
    const ey = C + Math.sin(endA) * reach;
    const c1x = C + Math.cos(angle + 0.3) * reach * 0.25;
    const c1y = C + Math.sin(angle + 0.3) * reach * 0.25;
    const c2x = C + Math.cos(midA - 0.2) * reach * 0.75;
    const c2y = C + Math.sin(midA - 0.2) * reach * 0.75;
    const d = `M ${C} ${C} Q ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${m1x.toFixed(1)} ${m1y.toFixed(1)} Q ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${ex.toFixed(1)} ${ey.toFixed(1)}`;

    // Sub-branches sprout as data accumulates (0–3 per root)
    const subCount = Math.min(3, Math.floor((sessions / 4) * (0.5 + v)));
    const subs: string[] = [];
    const tips: Array<{ x: number; y: number; r: number }> = [{ x: ex, y: ey, r: 2.2 + v * 1.6 }];
    for (let s = 0; s < subCount; s++) {
      const t = 0.45 + s * 0.22;
      const bx = C + Math.cos(midA) * reach * t;
      const by = C + Math.sin(midA) * reach * t;
      const sa = angle + (rnd() > 0.5 ? 1 : -1) * (0.5 + rnd() * 0.5);
      const sr = reach * (0.25 + rnd() * 0.2);
      const sx = bx + Math.cos(sa) * sr;
      const sy = by + Math.sin(sa) * sr;
      const scx = bx + Math.cos(sa + 0.4) * sr * 0.5;
      const scy = by + Math.sin(sa + 0.4) * sr * 0.5;
      subs.push(`M ${bx.toFixed(1)} ${by.toFixed(1)} Q ${scx.toFixed(1)} ${scy.toFixed(1)}, ${sx.toFixed(1)} ${sy.toFixed(1)}`);
      tips.push({ x: sx, y: sy, r: 1.2 + rnd() * 1.2 });
    }

    branches.push({ d, subs, tips, vigor: v, delay: i * 70 });
  }
  return branches;
}

export default function FingerprintArt({
  seed,
  sessions,
  vigor = [],
  size = 280,
  className = "",
}: {
  seed: number;
  sessions: number;
  /** 0..1 per technique (7 entries) — same shape for real and sham. */
  vigor?: number[];
  size?: number;
  className?: string;
}) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const branches = useMemo(() => buildBranches(seed, sessions, vigor),
    [seed, sessions, vigor]);

  // Per-user hue shift keeps it on-brand cyan but subtly personal (172–204).
  const hue = 172 + (Math.abs(seed * 2654435761) % 33);
  const glow = `hsl(${hue} 90% 60%)`;
  const dim = `hsl(${hue} 70% 45%)`;

  // Memory ring: one faint dot per session (cap 24) orbiting the whole print.
  const ringDots = useMemo(() => {
    const rnd = mulberry32(seed + 99);
    const n = Math.min(24, sessions);
    return Array.from({ length: n }, (_, i) => {
      const a = (i / Math.max(n, 8)) * Math.PI * 2 + rnd() * 0.2;
      const r = 126 + rnd() * 6;
      return { x: 140 + Math.cos(a) * r, y: 140 + Math.sin(a) * r, o: 0.25 + rnd() * 0.4 };
    });
  }, [seed, sessions]);

  return (
    <svg
      viewBox="0 0 280 280"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="Your cognitive fingerprint"
    >
      <defs>
        <filter id="fpGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id="fpCore">
          <stop offset="0%" stopColor={glow} stopOpacity="0.9" />
          <stop offset="60%" stopColor={glow} stopOpacity="0.25" />
          <stop offset="100%" stopColor={glow} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Memory ring — accumulating session dots */}
      {ringDots.map((p, i) => (
        <circle key={`rd${i}`} cx={p.x} cy={p.y} r="1.3" fill={dim}
          opacity={drawn ? p.o : 0}
          style={{ transition: `opacity 300ms ease ${200 + i * 30}ms` }} />
      ))}

      {/* Roots */}
      <g filter="url(#fpGlow)">
        {branches.map((b, i) => (
          <g key={i}>
            <path d={b.d} fill="none" stroke={b.vigor > 0.6 ? glow : dim}
              strokeWidth={1 + b.vigor * 1.8} strokeLinecap="round"
              pathLength={1} strokeDasharray={1}
              strokeDashoffset={drawn ? 0 : 1}
              opacity={0.35 + b.vigor * 0.6}
              style={{ transition: `stroke-dashoffset 300ms ease-out ${b.delay}ms` }} />
            {b.subs.map((s, j) => (
              <path key={j} d={s} fill="none" stroke={dim} strokeWidth={0.8}
                strokeLinecap="round" pathLength={1} strokeDasharray={1}
                strokeDashoffset={drawn ? 0 : 1} opacity={0.4}
                style={{ transition: `stroke-dashoffset 280ms ease-out ${b.delay + 120 + j * 60}ms` }} />
            ))}
            {/* Synapse tips */}
            {b.tips.map((t, j) => (
              <circle key={`t${j}`} cx={t.x} cy={t.y} r={t.r}
                fill={b.vigor > 0.6 ? glow : dim}
                opacity={drawn ? 0.5 + b.vigor * 0.5 : 0}
                style={{ transition: `opacity 240ms ease ${b.delay + 180 + j * 50}ms` }} />
            ))}
          </g>
        ))}
      </g>

      {/* Breathing core */}
      <circle cx="140" cy="140" r="26" fill="url(#fpCore)" className="breathe" />
      <circle cx="140" cy="140" r="5.5" fill={glow} className="breathe" />
      <circle cx="140" cy="140" r="11" fill="none" stroke={glow} strokeOpacity="0.35" strokeWidth="1" />
    </svg>
  );
}
