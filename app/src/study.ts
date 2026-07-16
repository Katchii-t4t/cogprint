import type { StudyTechnique } from "./types";

/**
 * Study modes — the fix for the "always active recall" problem (§3 in
 * COGPRINT_PROBLEMS.md). A flashcard round is genuinely active recall, but the
 * app can honestly deliver several distinct study modes and log the *real*
 * technique used, so the fingerprint's technique comparison finally gets varied
 * data from consumer use — not a hardcoded constant.
 *
 * Scientific rule: we only ever log a technique the user actually performed.
 * Some research techniques are properties of *scheduling/ordering*, not a single
 * session mode (spaced repetition = when you review; interleaving = what order;
 * mind maps = a separate artefact). Those are surfaced in the plan, not faked as
 * a card mode — hence `deliverable: false`.
 */

export type Interaction = "flip" | "test" | "explain" | "reread";

export interface StudyMode {
  technique: StudyTechnique;
  label: string;
  emoji: string;
  /** One-line instruction shown at the top of the round. */
  instruction: string;
  /** How the card behaves for this mode. */
  interaction: Interaction;
  /** Can the app deliver this as an in-app study session? */
  deliverable: boolean;
}

export const STUDY_MODES: Record<StudyTechnique, StudyMode> = {
  active_recall: {
    technique: "active_recall",
    label: "Active Recall",
    emoji: "⚡",
    instruction: "Try to remember the answer before you flip.",
    interaction: "flip",
    deliverable: true,
  },
  practice_testing: {
    technique: "practice_testing",
    label: "Practice Testing",
    emoji: "✏️",
    instruction: "Test conditions: commit your answer in your head — no peeking — then reveal.",
    interaction: "test",
    deliverable: true,
  },
  elaborative_interrogation: {
    technique: "elaborative_interrogation",
    label: "Elaborative Q&A",
    emoji: "❓",
    instruction: "Explain *why* it's true in your own words, then check.",
    interaction: "explain",
    deliverable: true,
  },
  re_reading: {
    technique: "re_reading",
    label: "Re-reading",
    emoji: "📖",
    instruction: "Read the concept and answer together, then rate your recall.",
    interaction: "reread",
    deliverable: true,
  },
  // Scheduling/ordering techniques — surfaced in the plan, not session modes.
  spaced_repetition: {
    technique: "spaced_repetition",
    label: "Spaced Repetition",
    emoji: "🔁",
    instruction: "A schedule, not a mode — your plan spaces reviews for you.",
    interaction: "flip",
    deliverable: false,
  },
  interleaving: {
    technique: "interleaving",
    label: "Interleaving",
    emoji: "🔀",
    instruction: "An ordering, not a mode — mix topics across your sessions.",
    interaction: "flip",
    deliverable: false,
  },
  mind_maps: {
    technique: "mind_maps",
    label: "Mind Maps",
    emoji: "🗺️",
    instruction: "A separate artefact — best done on paper or a canvas for now.",
    interaction: "flip",
    deliverable: false,
  },
};

/** The modes the app can actually run as a session, in a sensible display order. */
export const DELIVERABLE_MODES: StudyMode[] = [
  STUDY_MODES.active_recall,
  STUDY_MODES.practice_testing,
  STUDY_MODES.elaborative_interrogation,
  STUDY_MODES.re_reading,
];

const VALID = new Set<string>(Object.keys(STUDY_MODES));

/** Resolve a technique string to a deliverable mode, falling back to active recall. */
export function resolveMode(technique: string | null | undefined): StudyMode {
  if (technique && VALID.has(technique)) {
    const m = STUDY_MODES[technique as StudyTechnique];
    if (m.deliverable) return m;
  }
  return STUDY_MODES.active_recall;
}
