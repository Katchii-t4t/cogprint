import { describe, expect, it } from "vitest";
import { DELIVERABLE_MODES, STUDY_MODES, resolveMode } from "./study";

/**
 * `resolveMode` reads `?mode=` straight out of the URL, so its input is
 * attacker-controlled in the ordinary sense: anyone can type anything there.
 * Two things must hold no matter what arrives — the round must render, and the
 * technique it logs must be one the user actually performed.
 */

describe("resolveMode", () => {
  it("returns the requested mode when it is one the app can run", () => {
    expect(resolveMode("practice_testing").technique).toBe("practice_testing");
    expect(resolveMode("elaborative_interrogation").technique).toBe(
      "elaborative_interrogation"
    );
  });

  it("refuses a real technique the app cannot actually deliver as a round", () => {
    // Spaced repetition is a schedule and interleaving is an ordering. Logging
    // either as the technique of a single flashcard round would feed the
    // fingerprint a session that never happened — the exact dishonesty the
    // technique-logging work existed to remove.
    expect(resolveMode("spaced_repetition").technique).toBe("active_recall");
    expect(resolveMode("interleaving").technique).toBe("active_recall");
    expect(resolveMode("mind_maps").technique).toBe("active_recall");
  });

  it("falls back on junk, absence and object-prototype keys", () => {
    for (const input of [
      null,
      undefined,
      "",
      "not_a_technique",
      "ACTIVE_RECALL",
      "constructor",
      "__proto__",
      "toString",
    ]) {
      const mode = resolveMode(input);
      expect(mode.technique).toBe("active_recall");
      expect(mode.deliverable).toBe(true);
    }
  });

  it("never returns a non-deliverable mode for any input", () => {
    const inputs = [...Object.keys(STUDY_MODES), "junk", "", null];
    for (const input of inputs) {
      expect(resolveMode(input).deliverable).toBe(true);
    }
  });
});

describe("the mode table", () => {
  it("keys every entry by its own technique", () => {
    // A mismatch here would log one technique while showing another's
    // instructions, and nothing else in the app would notice.
    for (const [key, mode] of Object.entries(STUDY_MODES)) {
      expect(mode.technique).toBe(key);
    }
  });

  it("lists exactly the deliverable modes in the picker", () => {
    const expected = Object.values(STUDY_MODES)
      .filter((m) => m.deliverable)
      .map((m) => m.technique)
      .sort();
    expect(DELIVERABLE_MODES.map((m) => m.technique).sort()).toEqual(expected);
  });

  it("gives every mode an instruction, so no round starts unexplained", () => {
    for (const mode of Object.values(STUDY_MODES)) {
      expect(mode.instruction.trim().length).toBeGreaterThan(0);
      expect(mode.label.trim().length).toBeGreaterThan(0);
    }
  });
});
