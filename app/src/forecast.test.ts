import { describe, expect, it } from "vitest";
import { archetype, buildForecast } from "./forecast";
import { fingerprint, memoryProfile, techniqueStats } from "./test/fixtures";

/**
 * The forecast is the app's most confident-looking claim ("storm warning"), and
 * it is derived entirely client-side. Guardrail #3 says never over-claim: the
 * cases below are the ones where a wrong bucket would tell someone their memory
 * is fine when it is not, or panic them when it is.
 */

describe("buildForecast bucketing", () => {
  it("puts a profile exactly on the 0.5 line in cooling, not fading", () => {
    const fp = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.5 })],
    });
    const f = buildForecast(fp, 0);
    expect(f.fading).toBe(0);
    expect(f.cooling).toBe(1);
  });

  it("puts a profile exactly on the 0.8 line in solid, not cooling", () => {
    const fp = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.8 })],
    });
    const f = buildForecast(fp, 0);
    expect(f.cooling).toBe(0);
    expect(f.solid).toBe(1);
  });

  it("counts each profile exactly once across the three buckets", () => {
    const fp = fingerprint({
      memory_profiles: [
        memoryProfile("a", { predicted_retention_7d: 0.2 }),
        memoryProfile("b", { predicted_retention_7d: 0.6 }),
        memoryProfile("c", { predicted_retention_7d: 0.95 }),
        memoryProfile("d", { predicted_retention_7d: 0.49999 }),
      ],
    });
    const f = buildForecast(fp, 0);
    expect(f.fading + f.cooling + f.solid).toBe(4);
    expect([f.fading, f.cooling, f.solid]).toEqual([2, 1, 1]);
  });
});

describe("buildForecast weather", () => {
  it("is unknown only when there is genuinely nothing to say", () => {
    const f = buildForecast(fingerprint(), 0);
    expect(f.weather).toBe("unknown");
    expect(f.summary).toMatch(/not enough data/i);
  });

  it("is not unknown when reviews are due but no curve has been fitted yet", () => {
    // A brand-new user has no memory profiles but can still have checks due.
    // Reporting "no data" while the schedule is asking for a review is the
    // dishonest combination.
    const f = buildForecast(fingerprint(), 1);
    expect(f.weather).toBe("cloudy");
  });

  it("escalates to stormy on a single fading concept", () => {
    const fp = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.3 })],
    });
    expect(buildForecast(fp, 0).weather).toBe("stormy");
  });

  it("escalates to stormy on three due reviews even when everything is solid", () => {
    const fp = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.95 })],
    });
    expect(buildForecast(fp, 3).weather).toBe("stormy");
    expect(buildForecast(fp, 2).weather).toBe("cloudy");
  });

  it("is clear only when nothing is cooling and nothing is due", () => {
    const fp = fingerprint({
      memory_profiles: [
        memoryProfile("a", { predicted_retention_7d: 0.9 }),
        memoryProfile("b", { predicted_retention_7d: 0.85 }),
      ],
    });
    expect(buildForecast(fp, 0).weather).toBe("clear");
  });
});

describe("buildForecast summary", () => {
  it("pluralises rather than saying '1 concepts'", () => {
    const one = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.2 })],
    });
    expect(buildForecast(one, 0).summary).toContain("1 concept fading");

    const two = fingerprint({
      memory_profiles: [
        memoryProfile("a", { predicted_retention_7d: 0.2 }),
        memoryProfile("b", { predicted_retention_7d: 0.1 }),
      ],
    });
    expect(buildForecast(two, 0).summary).toContain("2 concepts fading");
  });

  it("never renders an empty clause list in a storm", () => {
    const fp = fingerprint({
      memory_profiles: [memoryProfile("a", { predicted_retention_7d: 0.2 })],
    });
    const s = buildForecast(fp, 0).summary;
    expect(s).not.toMatch(/—\s*\./);
    expect(s).not.toContain(", .");
  });
});

describe("archetype", () => {
  it("refuses to type someone at low confidence", () => {
    // Guardrail #3: an identity label is a strong claim. At low N there is no
    // evidence for it, and it would be sticky in the user's head.
    expect(archetype(fingerprint({ confidence: "low", improving_over_time: true }))).toBeNull();
  });

  it("prefers 'climber' over every other read when the trend is up", () => {
    const fp = fingerprint({
      confidence: "high",
      improving_over_time: true,
      technique_effectiveness: [
        techniqueStats("a", { relative_effectiveness: "best" }),
        techniqueStats("b", { relative_effectiveness: "good" }),
        techniqueStats("c", { relative_effectiveness: "poor" }),
      ],
    });
    expect(archetype(fp)?.key).toBe("climber");
  });

  it("does not read a missing trend as a downward one", () => {
    // improving_over_time is null until there is enough data. `=== true` is the
    // only correct check; a truthiness test would type everyone as a climber.
    const fp = fingerprint({
      confidence: "medium",
      improving_over_time: null,
      memory_profiles: [memoryProfile("a", { avg_stability_days: 12 })],
    });
    expect(archetype(fp)?.key).toBe("marathoner");
  });

  it("calls a single standout technique a specialist", () => {
    const fp = fingerprint({
      confidence: "medium",
      technique_effectiveness: [
        techniqueStats("a", { relative_effectiveness: "best" }),
        techniqueStats("b", { relative_effectiveness: "average" }),
        techniqueStats("c", { relative_effectiveness: "poor" }),
      ],
    });
    expect(archetype(fp)?.key).toBe("specialist");
  });

  it("calls two joint-best techniques an explorer", () => {
    const fp = fingerprint({
      confidence: "medium",
      technique_effectiveness: [
        techniqueStats("a", { relative_effectiveness: "best" }),
        techniqueStats("b", { relative_effectiveness: "best" }),
        techniqueStats("c", { relative_effectiveness: "poor" }),
      ],
    });
    expect(archetype(fp)?.key).toBe("explorer");
  });

  it("needs three rated techniques before splitting specialist from explorer", () => {
    // With two rated techniques, "one is best" carries almost no information.
    const fp = fingerprint({
      confidence: "medium",
      technique_effectiveness: [
        techniqueStats("a", { relative_effectiveness: "best" }),
        techniqueStats("b", { relative_effectiveness: "poor" }),
      ],
      memory_profiles: [memoryProfile("a", { avg_stability_days: 3 })],
    });
    expect(archetype(fp)?.key).toBe("sprinter");
  });

  it("splits sprinter from marathoner at a week of stability", () => {
    const at = (days: number) =>
      archetype(
        fingerprint({
          confidence: "medium",
          memory_profiles: [memoryProfile("a", { avg_stability_days: days })],
        })
      )?.key;
    expect(at(6.9)).toBe("sprinter");
    expect(at(7)).toBe("marathoner");
  });

  it("ignores unfitted profiles when averaging stability", () => {
    // A zero-stability row means "no curve yet", not "forgets instantly".
    // Averaging it in would drag a genuine marathoner down to sprinter.
    const fp = fingerprint({
      confidence: "medium",
      memory_profiles: [
        memoryProfile("a", { avg_stability_days: 0 }),
        memoryProfile("b", { avg_stability_days: 14 }),
      ],
    });
    expect(archetype(fp)?.key).toBe("marathoner");
  });

  it("always returns something typable at medium confidence", () => {
    // The Grow screen renders the archetype card unconditionally above low
    // confidence; returning null there would leave a hole.
    expect(archetype(fingerprint({ confidence: "medium" }))).not.toBeNull();
  });
});
