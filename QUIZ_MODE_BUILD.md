# CogPrint — Quiz Mode (primary) + Flashcard Mode (secondary, practice-only)

**Status:** ✅ **BUILT & VERIFIED** (2026-07-05, Bot B). All acceptance criteria met:
26/26 backend tests, eslint + build clean, and browser-verified end-to-end — a quiz
round logged exactly one session (objectively-graded score), a flashcard round logged
none, the practice banner renders, and real distractors (3 per card) were generated
live by Claude Opus 4.8. This document is kept as the design record.
**Read order:** `CONSUMER_APP_BUILD.md` (product vision + current state) → this file
(this specific feature) → `HANDOVER.md` (backend deep-dive) → the code.

---

## Why this exists

The original consumer-app build (see `CONSUMER_APP_BUILD.md`) shipped flashcards with a
**self-reported** correctness signal: the learner taps "Again" or "Got it" themselves.
This is exactly the thing CogPrint's own scientific premise rejects one layer up —
CogPrint exists to measure *actual* response to study techniques, not self-reported
experience (the same reasoning that rules out "learning styles" as a framing). Self-graded
flashcards reintroduce that exact problem at the data-capture layer: people are lenient
with themselves, so `quiz_score` — which drives every downstream computation (Ebbinghaus
stability fits, LinUCB bandit rewards, technique-effectiveness ranking, the fingerprint
itself) — becomes noise dressed as signal.

**Decision:** keep flashcards (they're genuinely useful for low-friction practice/review),
but they must never be the thing that produces measurement. Add a **Quiz mode** —
objectively graded, multiple-choice — as the primary, default mode, and demote flashcards
to an optional secondary mode whose results are never logged as sessions.

---

## The design

Two modes, one shared cached question bank per material (no extra generation cost):

| | Quiz mode (primary, default) | Flashcard mode (secondary, optional) |
|---|---|---|
| Interaction | 4 tappable options (answer + 3 shuffled distractors) | today's tap-to-reveal → Again/Got it |
| Grading | deterministic string match, no LLM call at answer time | self-reported |
| Feeds the fingerprint? | **Yes** — `POST /sessions` with the real fraction-correct score | **No** — never posts a session |
| Framing | "the test" | "practice — not scored" |

Both modes read the exact same generated cards for a material. This is a UI/consumption
difference, not a second generation pipeline.

---

## Backend changes

### `schemas/question.py`
Add one field to `Flashcard`:
```python
distractors: list[str] = Field(default_factory=list)  # 3 plausible wrong answers
```
`default_factory=list` matters: old cached `questions_json` blobs (written before this
change) will parse fine with an empty list rather than crashing. Treat an empty
`distractors` as "quiz mode unavailable for this card, render it as flashcard-only."

No new correct-index field — `answer` stays the single source of truth for both the
flashcard reveal text *and* the correct multiple-choice option. A separate index would be
redundant and could drift out of sync with the option list.

### `agents/question_generator.py`
Update the system prompt so the LLM produces 3 distractors per card alongside
`question`/`answer`/`concept`/`difficulty` — same difficulty tier, plausible to someone
who hasn't fully learned the material, not absurd/joke answers, not near-duplicates of
the correct answer. Still **one generation call per material**, still cached exactly as
today — no change to cost or latency profile, no new LLM call at answer time (grading is
a local string comparison).

### `main.py`
No new endpoint. `POST /materials/{id}/questions` already returns full `Flashcard`
objects — they'll just carry `distractors` too.

### Tests
Extend `tests/test_questions.py`: mock `generate_flashcards` to return cards with
`distractors`, assert they round-trip through the cache and the existing flag-exclusion
logic unchanged. Keep the existing 503-without-key and flag tests passing as-is.

---

## Frontend changes (`app/`)

### `app/src/types.ts`
Add `distractors: string[]` to the `Flashcard` interface.

### `app/src/pages/Cards.tsx` (or split into a quiz component + reuse the existing
flashcard UI as the secondary mode — file structure is an implementation choice; keep
the question-fetch/flag logic shared, not duplicated)

- Small mode toggle at the top: **Quiz** / **Flashcards**, **Quiz selected by default**
  every round.
- **Quiz mode:** show the question, then 4 tappable options = `[answer, ...distractors]`,
  **shuffled per card** (don't reuse a fixed order — a fixed position for the correct
  answer becomes a giveaway pattern over a session). Correct tap → green flash; wrong →
  red flash (≤300ms, matching the app's existing micro-interaction style); auto-advance.
  No typing, no added friction vs. today's swipe pace.
- **Flashcard mode:** unchanged from what exists today.
- **Fallback:** empty `distractors` on a card (stale cache) → render that card in
  flashcard style even inside a Quiz-mode round rather than crashing or blocking.
- Flag button stays shared across both modes, same endpoint, unchanged.
- `finish()`: only log a session (`api.logSession(...)`) when the round was played in
  **Quiz mode**. In Flashcard mode, still route to `/grow` (never dead-end the user) but
  skip `logSession` entirely and show a "practice round — not scored" note instead of the
  score banner.

---

## What NOT to touch

`FingerprintArt.tsx`, `insights.ts` (real/sham `InsightProvider`), the PWA config, the
browser extension (`extension/`), `Study.tsx`, and `Checks.tsx` are already built and
verified working — this feature doesn't need to change any of them. No new dependencies
needed (shuffle + string equality is a few lines of plain TS).

---

## Acceptance criteria

1. `python -m pytest` — all green (existing 24 + new distractor tests).
2. `npm run build` and `npx eslint src` — both clean in `app/`.
3. Manually verified: a full Quiz-mode round logs a session and updates the fingerprint;
   a full Flashcard-mode round does **not** create a new session
   (`GET /users/{id}/sessions` count unchanged after a flashcard-only round).
4. `HANDOVER.md` §9 and `CONSUMER_APP_BUILD.md`'s build-status box updated to reflect
   Quiz mode is live and flashcards are secondary/unscored.
5. Committed and pushed to `master`.

---

## Collaboration reminder (shared repo, two machines)

`git pull origin master` before starting; claim this file/area in `HANDOVER.md` §9 before
touching code; commit + push after every coherent step; don't rewrite unrelated files.
