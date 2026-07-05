/**
 * Pure generative geometry for the cognitive fingerprint.
 *
 * Extracted from components/FingerprintArt.tsx so the exact same organism can
 * be (a) rendered live on the Grow screen and (b) rasterized into the share
 * card (lib/shareCard.ts) without duplicating the math. Everything here is
 * deterministic in (seed, sessions, vigor) — no clock, no global state.
 */

// Deterministic PRNG (mulberry32)
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface Branch {
  d: string;          // main path
  subs: string[];     // sub-branch paths
  tips: Array<{ x: number; y: number; r: number }>;
  vigor: number;      // 0..1 → opacity/width/colour
  delay: number;      // draw-in stagger (ms) — used by the live component only
}

export function buildBranches(seed: number, sessions: number, vigor: number[]): Branch[] {
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

/** Per-user hue shift keeps it on-brand cyan but subtly personal (172–204). */
export function fingerprintHue(seed: number): number {
  return 172 + (Math.abs(seed * 2654435761) % 33);
}

export interface RingDot { x: number; y: number; o: number }

/** Memory ring: one faint dot per session (cap 24) orbiting the whole print. */
export function buildRingDots(seed: number, sessions: number): RingDot[] {
  const rnd = mulberry32(seed + 99);
  const n = Math.min(24, sessions);
  return Array.from({ length: n }, (_, i) => {
    const a = (i / Math.max(n, 8)) * Math.PI * 2 + rnd() * 0.2;
    const r = 126 + rnd() * 6;
    return { x: 140 + Math.cos(a) * r, y: 140 + Math.sin(a) * r, o: 0.25 + rnd() * 0.4 };
  });
}

/**
 * A fully-drawn static snapshot of the fingerprint as a standalone SVG string
 * (inline presentation attributes only — no CSS classes, no animation), for
 * rasterizing onto the share card canvas.
 */
export function fingerprintSvgMarkup(seed: number, sessions: number, vigor: number[] = []): string {
  const branches = buildBranches(seed, sessions, vigor);
  const dots = buildRingDots(seed, sessions);
  const hue = fingerprintHue(seed);
  const glow = `hsl(${hue} 90% 60%)`;
  const dim = `hsl(${hue} 70% 45%)`;

  const parts: string[] = [];
  parts.push(
    `<defs><filter id="fpG" x="-40%" y="-40%" width="180%" height="180%">` +
    `<feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/>` +
    `<feMergeNode in="SourceGraphic"/></feMerge></filter>` +
    `<radialGradient id="fpC"><stop offset="0%" stop-color="${glow}" stop-opacity="0.9"/>` +
    `<stop offset="60%" stop-color="${glow}" stop-opacity="0.25"/>` +
    `<stop offset="100%" stop-color="${glow}" stop-opacity="0"/></radialGradient></defs>`
  );

  for (const p of dots) {
    parts.push(`<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="1.3" fill="${dim}" opacity="${p.o.toFixed(2)}"/>`);
  }

  parts.push(`<g filter="url(#fpG)">`);
  for (const b of branches) {
    const col = b.vigor > 0.6 ? glow : dim;
    parts.push(
      `<path d="${b.d}" fill="none" stroke="${col}" stroke-width="${(1 + b.vigor * 1.8).toFixed(2)}" ` +
      `stroke-linecap="round" opacity="${(0.35 + b.vigor * 0.6).toFixed(2)}"/>`
    );
    for (const s of b.subs) {
      parts.push(`<path d="${s}" fill="none" stroke="${dim}" stroke-width="0.8" stroke-linecap="round" opacity="0.4"/>`);
    }
    for (const t of b.tips) {
      parts.push(
        `<circle cx="${t.x.toFixed(1)}" cy="${t.y.toFixed(1)}" r="${t.r.toFixed(2)}" fill="${col}" ` +
        `opacity="${(0.5 + b.vigor * 0.5).toFixed(2)}"/>`
      );
    }
  }
  parts.push(`</g>`);

  parts.push(
    `<circle cx="140" cy="140" r="26" fill="url(#fpC)"/>` +
    `<circle cx="140" cy="140" r="5.5" fill="${glow}"/>` +
    `<circle cx="140" cy="140" r="11" fill="none" stroke="${glow}" stroke-opacity="0.35" stroke-width="1"/>`
  );

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 280">${parts.join("")}</svg>`;
}
