import { describe, expect, it } from "vitest";
import { buildRealView, buildShamView, buildView, label } from "./insights";
import { fingerprint, memoryProfile, richFingerprint, techniqueStats } from "./test/fixtures";

/**
 * Guardrail #2 — preserve the RCT blind.
 *
 * This is the file that decides whether the trial is worth running. If a
 * control user can tell they are in the control arm, the comparison is dead;
 * if a sham value ever carries real measured signal, the control arm is not a
 * control. Both directions are tested here.
 */

describe("the blind: control must never receive measured signal", () => {
  const fp = richFingerprint();

  it("does not pass the user's real insight text through to control", () => {
    const sham = buildView(fp, "control", 42);
    const realTexts = fp.insights.join(" ");
    for (const i of sham.insights) {
      expect(realTexts).not.toContain(i.text);
    }
  });

  it("does not pass the real best technique through to control", () => {
    // The real fingerprint's clear winner is active_recall with re_reading
    // worst. A sham view that happened to reproduce the real ranking would be
    // leaking — so assert the sham ordering is its own, seeded construction.
    const sham = buildShamView(fp, 42);
    const real = buildRealView(fp);
    expect(sham.topTechnique).not.toBe(real.topTechnique);
  });

  it("does not pass real retention numbers through to control", () => {
    const sham = buildShamView(fp, 42);
    const realPredictions = buildRealView(fp).retentionRows.map((r) => r.predicted7d);
    for (const row of sham.retentionRows) {
      expect(realPredictions).not.toContain(row.predicted7d);
    }
  });

  it("does not pass the real best time of day through to control", () => {
    const morning = richFingerprint();
    // Seeds 0..2 map onto morning/afternoon/evening; only one of them can
    // coincide with the real answer, and that is chance, not leakage. Assert
    // the sham value is drawn from its own fixed pool instead.
    const sham = buildShamView(morning, 5);
    expect(["morning", "afternoon", "evening"]).toContain(sham.bestTimeOfDay);
    expect(sham.bestTimeOfDay).toBe("evening"); // seed 5 % 3 === 2 → SHAM_TIMES[2]
  });
});

describe("the blind: control must not look emptier than treatment", () => {
  it("fills every section, even from an empty fingerprint", () => {
    // A day-one control user must not stare at a blank screen while a
    // treatment user sees bars — that difference is visible without any
    // knowledge of the study.
    const sham = buildShamView(fingerprint(), 1);
    expect(sham.techniqueRows.length).toBeGreaterThanOrEqual(2);
    expect(sham.retentionRows.length).toBeGreaterThanOrEqual(2);
    expect(sham.insights).toHaveLength(3);
    expect(sham.topTechnique).not.toBeNull();
    expect(sham.bestTimeOfDay).not.toBeNull();
  });

  it("grows the number of technique rows with sessions, as the real view does", () => {
    const few = buildShamView(fingerprint({ session_count: 1 }), 1);
    const many = buildShamView(fingerprint({ session_count: 20 }), 1);
    expect(many.techniqueRows.length).toBeGreaterThan(few.techniqueRows.length);
  });

  it("labels one row 'best' so the screen has the same shape as the real one", () => {
    const sham = buildShamView(fingerprint({ session_count: 9 }), 3);
    expect(sham.techniqueRows.filter((r) => r.label === "best")).toHaveLength(1);
  });

  it("keeps every sham bar within the same 0..1 range the real view renders", () => {
    for (let seed = 1; seed <= 25; seed++) {
      for (const row of buildShamView(fingerprint({ session_count: seed }), seed).techniqueRows) {
        expect(row.barFraction).toBeGreaterThan(0);
        expect(row.barFraction).toBeLessThanOrEqual(1);
      }
    }
  });

  it("keeps sham retention inside 0..1 so no ring overflows", () => {
    for (let seed = 1; seed <= 25; seed++) {
      for (const row of buildShamView(fingerprint({ session_count: seed }), seed).retentionRows) {
        expect(row.predicted7d).toBeGreaterThan(0);
        expect(row.predicted7d).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("the blind: sham values must be stable and personal", () => {
  it("returns identical content on every call for the same user", () => {
    // Numbers that changed on reload would read as a bug at best and as an
    // obvious tell at worst.
    const fp = fingerprint({ session_count: 7 });
    const a = buildShamView(fp, 12);
    const b = buildShamView(fp, 12);
    expect(b).toEqual(a);
  });

  it("gives different users different content", () => {
    const fp = fingerprint({ session_count: 7 });
    const seen = new Set<string>();
    for (let seed = 1; seed <= 12; seed++) {
      seen.add(JSON.stringify(buildShamView(fp, seed)));
    }
    expect(seen.size).toBeGreaterThan(6);
  });
});

describe("the blind: honest fields stay honest in both arms", () => {
  it("reports the real session count and confidence to control users", () => {
    // Growth is measured, not personalised — faking it would corrupt the one
    // number the analytics funnel reads.
    const fp = fingerprint({ session_count: 11, confidence: "high" });
    const sham = buildView(fp, "control", 4);
    expect(sham.sessionCount).toBe(11);
    expect(sham.confidence).toBe("high");
  });

  it("withholds a trend claim from control users below six sessions", () => {
    // The real view leaves improving_over_time null at low N. A sham "you're
    // improving!" at session two would be both a tell and an over-claim.
    const sham = buildShamView(fingerprint({ session_count: 5 }), 4);
    expect(sham.improving).toBeNull();
  });
});

describe("buildView routing", () => {
  it("sends treatment to the real view and control to the sham", () => {
    const fp = richFingerprint();
    expect(buildView(fp, "treatment", 1)).toEqual(buildRealView(fp));
    expect(buildView(fp, "control", 1)).toEqual(buildShamView(fp, 1));
  });
});

describe("buildRealView", () => {
  it("scales bars against the strongest technique, not against 1.0", () => {
    const view = buildRealView(richFingerprint());
    const best = view.techniqueRows.find((r) => r.technique === "active_recall");
    const worst = view.techniqueRows.find((r) => r.technique === "re_reading");
    expect(best?.barFraction).toBe(1);
    expect(worst?.barFraction).toBeCloseTo(0.44 / 0.92, 5);
  });

  it("does not divide by zero when no technique has been scored yet", () => {
    const fp = fingerprint({
      technique_effectiveness: [
        techniqueStats("a", { avg_immediate_score: null }),
        techniqueStats("b", { avg_immediate_score: null }),
      ],
    });
    const view = buildRealView(fp);
    expect(view.techniqueRows.map((r) => r.barFraction)).toEqual([0, 0]);
    for (const row of view.techniqueRows) expect(Number.isNaN(row.barFraction)).toBe(false);
  });

  it("splits an insight into claim and action at the question mark", () => {
    const fp = fingerprint({
      insights: ["Does spacing help you? Wait a day before the next review."],
    });
    expect(buildRealView(fp).insights[0]).toEqual({
      text: "Does spacing help you?",
      action: "Wait a day before the next review.",
    });
  });

  it("leaves the action empty rather than inventing one", () => {
    const fp = fingerprint({ insights: ["Your recall is holding steady."] });
    expect(buildRealView(fp).insights[0]).toEqual({
      text: "Your recall is holding steady.",
      action: "",
    });
  });

  it("does not produce a dangling action from a trailing question mark", () => {
    const fp = fingerprint({ insights: ["Ready for a harder round?"] });
    const parsed = buildRealView(fp).insights[0];
    expect(parsed.text).toBe("Ready for a harder round?");
    expect(parsed.action).toBe("");
  });

  it("reports no top technique rather than guessing one", () => {
    const view = buildRealView(fingerprint({ recommended_techniques: [] }));
    expect(view.topTechnique).toBeNull();
  });

  it("carries memory profiles through unchanged", () => {
    const fp = fingerprint({
      memory_profiles: [
        memoryProfile("active_recall", {
          avg_stability_days: 9.5,
          predicted_retention_7d: 0.82,
          stability_label: "excellent",
        }),
      ],
    });
    expect(buildRealView(fp).retentionRows).toEqual([
      {
        technique: "active_recall",
        stabilityDays: 9.5,
        label: "excellent",
        predicted7d: 0.82,
      },
    ]);
  });
});

describe("label", () => {
  it("uses the research name where we have one", () => {
    expect(label("elaborative_interrogation")).toBe("Elaborative Q&A");
  });

  it("degrades a technique the backend adds later into something readable", () => {
    // A raw "dual_coding" leaking into the UI is ugly but not broken; a crash
    // would be. This is the deliberate fallback.
    expect(label("dual_coding")).toBe("dual coding");
  });
});
