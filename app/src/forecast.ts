import type { FingerprintProfile } from "./types";

/**
 * #1 Memory weather forecast + #2 Learner archetype.
 *
 * Both are computed purely client-side from data the backend already returns
 * (`FingerprintProfile`) — zero extra API cost. The forecast turns the invisible
 * forgetting-curve math into a glanceable "decay radar"; the archetype gives the
 * user an identity based on the shape of their own curve.
 */

export type MemoryWeather = "clear" | "cloudy" | "stormy" | "unknown";

export interface MemoryForecast {
  weather: MemoryWeather;
  fading: number; // concepts predicted below ~50% retention
  cooling: number; // 50–80%
  solid: number; // > 80%
  pendingChecks: number; // reviews literally due now
  summary: string;
}

/**
 * Bucket the user's memory profiles by predicted 7-day retention and fold in the
 * number of retention checks that are actually due. `pendingChecks` comes from
 * `api.getPendingChecks(userId)` — those are concepts the schedule wants reviewed.
 */
export function buildForecast(
  fp: FingerprintProfile,
  pendingChecks: number
): MemoryForecast {
  let fading = 0;
  let cooling = 0;
  let solid = 0;

  for (const m of fp.memory_profiles) {
    const r = m.predicted_retention_7d;
    if (r < 0.5) fading++;
    else if (r < 0.8) cooling++;
    else solid++;
  }

  const known = fading + cooling + solid;

  let weather: MemoryWeather;
  if (known === 0 && pendingChecks === 0) weather = "unknown";
  else if (fading > 0 || pendingChecks >= 3) weather = "stormy";
  else if (cooling > 0 || pendingChecks > 0) weather = "cloudy";
  else weather = "clear";

  const summary = buildSummary(weather, fading, cooling, pendingChecks);

  return { weather, fading, cooling, solid, pendingChecks, summary };
}

function buildSummary(
  weather: MemoryWeather,
  fading: number,
  cooling: number,
  pending: number
): string {
  if (weather === "unknown")
    return "Not enough data yet — study a little to see your forecast.";
  if (weather === "stormy") {
    const bits: string[] = [];
    if (fading > 0)
      bits.push(`${fading} concept${fading > 1 ? "s" : ""} fading fast`);
    if (pending > 0)
      bits.push(`${pending} review${pending > 1 ? "s" : ""} due`);
    return `Storm warning — ${bits.join(", ")}. A quick review clears the skies.`;
  }
  if (weather === "cloudy") {
    if (pending > 0)
      return `Getting cloudy — ${pending} review${pending > 1 ? "s" : ""} due soon.`;
    return `Getting cloudy — ${cooling} concept${cooling > 1 ? "s" : ""} starting to cool.`;
  }
  return "Clear skies — your memory is holding strong. Nice work.";
}

export const WEATHER_META: Record<
  MemoryWeather,
  { icon: string; label: string; tint: string }
> = {
  clear: { icon: "☀️", label: "Clear", tint: "text-neural" },
  cloudy: { icon: "⛅", label: "Cloudy", tint: "text-amber-300" },
  stormy: { icon: "⛈️", label: "Stormy", tint: "text-rose-300" },
  unknown: { icon: "🌫️", label: "Forming", tint: "text-slate-400" },
};

// ---------------------------------------------------------------------------
// #2 Learner archetype (heuristic on the user's OWN curve shape — not cross-user
// clustering; that needs a population + a backend job, noted in COGPRINT_IDEAS.md).
// ---------------------------------------------------------------------------

export type ArchetypeKey =
  | "sprinter"
  | "marathoner"
  | "specialist"
  | "explorer"
  | "climber";

export interface Archetype {
  key: ArchetypeKey;
  name: string;
  emoji: string;
  blurb: string;
}

const ARCHETYPES: Record<ArchetypeKey, Archetype> = {
  sprinter: {
    key: "sprinter",
    name: "Sprinter",
    emoji: "⚡",
    blurb: "You learn fast but forget fast. Tighter review spacing keeps it locked in.",
  },
  marathoner: {
    key: "marathoner",
    name: "Marathoner",
    emoji: "🏔️",
    blurb: "What you learn, you keep. Durable memory — you can space reviews further apart.",
  },
  specialist: {
    key: "specialist",
    name: "Specialist",
    emoji: "🎯",
    blurb: "One technique clearly works best for you. Lean into it, but sample others now and then.",
  },
  explorer: {
    key: "explorer",
    name: "Explorer",
    emoji: "🧭",
    blurb: "You're effective across many techniques. Interleaving suits you well.",
  },
  climber: {
    key: "climber",
    name: "Climber",
    emoji: "📈",
    blurb: "You're getting measurably better over time. Momentum is on your side — keep going.",
  },
};

/**
 * Returns null below `medium` confidence (not enough signal to type someone).
 */
export function archetype(fp: FingerprintProfile): Archetype | null {
  if (fp.confidence === "low") return null;

  // Trending up beats everything else — it's the most motivating true statement.
  if (fp.improving_over_time === true) return ARCHETYPES.climber;

  // Specialist vs explorer: spread of relative effectiveness.
  const best = fp.technique_effectiveness.filter(
    (t) => t.relative_effectiveness === "best"
  ).length;
  const rated = fp.technique_effectiveness.filter(
    (t) => t.relative_effectiveness != null
  ).length;
  if (rated >= 3 && best === 1) return ARCHETYPES.specialist;
  if (rated >= 3 && best >= 2) return ARCHETYPES.explorer;

  // Sprinter vs marathoner: average memory stability.
  const stabilities = fp.memory_profiles
    .map((m) => m.avg_stability_days)
    .filter((d) => d > 0);
  if (stabilities.length > 0) {
    const avg = stabilities.reduce((a, b) => a + b, 0) / stabilities.length;
    return avg >= 7 ? ARCHETYPES.marathoner : ARCHETYPES.sprinter;
  }

  return ARCHETYPES.explorer;
}
