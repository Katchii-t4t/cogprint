import { useEffect, useMemo, useState } from "react";
import {
  buildBranches,
  buildRingDots,
  fingerprintHue,
} from "../lib/fingerprint";

/**
 * The living cognitive fingerprint — the brand centrepiece.
 *
 * A generative neural/root system that is:
 *  - unique per user (deterministic PRNG seeded by userId)
 *  - grown by data (branch reach + node count scale with session_count)
 *  - shaped by the user's measured technique vigor (7 main roots, one per
 *    technique; stronger techniques grow longer, brighter roots)
 *
 * The geometry lives in lib/fingerprint.ts (shared with the share-card
 * exporter); this component adds the live presentation: staggered draw-in
 * (≤300ms per element) and the breathing core. Sham-safety: only numbers in,
 * identical structure in both modes.
 */
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
  const ringDots = useMemo(() => buildRingDots(seed, sessions), [seed, sessions]);

  const hue = fingerprintHue(seed);
  const glow = `hsl(${hue} 90% 60%)`;
  const dim = `hsl(${hue} 70% 45%)`;

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
