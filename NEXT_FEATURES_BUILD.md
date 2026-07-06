# CogPrint — Next Features Build Spec (4 features)

**Status:** ✅ **ALL 4 BUILT & VERIFIED** (2026-07-05, Bot B, overnight). Each feature
shipped as its own commit (F1 `1fa1f8b`, F3 `a170e59`, F4 `8f521a6`, F2 `6173476`), all
acceptance criteria met: 34/34 backend tests, eslint + build clean, and browser/API
verified — F1 rendered a real 1104 KB PNG share card; F3 surfaced a backdated material
by name ("You're about to forget 'The water cycle…'"); F4 restored a cleared device by
CogPrint ID and personalised the header; F2 transcribed a real test image verbatim via
Claude vision. This document is kept as the design record.
**Read order:** `CONSUMER_APP_BUILD.md` (vision + state + API contract) → this file →
`HANDOVER.md` (backend) → the code.

Four independent features, each shippable on its own. **Recommended order:**
1 (Shareable fingerprint) → 3 (Smart forgetting nudges) → 4 (Save progress) →
2 (Photo→OCR). Reasoning: 1 and 3 are pure wins with no cost/decisions; 4 is small;
2 adds a paid vision call so do it last with eyes open.

## Global rules (apply to every feature)
- `git pull origin master` first; claim in `HANDOVER.md` §9 before starting; commit +
  push after **each feature** (not all at once); update §9 as you finish each.
- Backend green: `python -m pytest`. Frontend green: `npm run build` **and**
  `npx eslint src` in `app/`. All must pass before every push.
- **Isolate any LLM call behind a service module** (like `agents/question_generator.py`).
  Read `ANTHROPIC_API_KEY` from env only — never in code/args/logs. Degrade to a clean
  503 + friendly UI state when it's missing.
- **Deterministic ML stays deterministic** — never let an LLM compute a number/score.
- **Two-track rule:** don't hard-code or assume a *study finding*. Using the Ebbinghaus
  forgetting curve for review scheduling is fine (established memory science, already used
  in `personalization/forgetting_curve.py`); claiming "technique X works better *for you*"
  before the study validates individual-level stability is not.
- No new heavy dependencies. `app/` uses IPv6 loopback — open it at `http://localhost:5173`
  (not `127.0.0.1`). SQLite has no migrations: if you add a DB column, the dev `cogprint.db`
  must be deleted so `create_all` rebuilds it (it's gitignored test data — safe).

---

## Feature 1 — Shareable fingerprint (the growth engine)

**Why:** the ideal-product spec (§2.6, §7) names the shareable fingerprint as *the*
marketing/growth engine ("the thing people screenshot and share"). Frontend-only, no cost.

**Goal:** a "Share" affordance on the Grow screen that renders a beautiful portrait
**share card PNG** (the user's generative fingerprint, framed with a title, their
confidence/session count, and a small CogPrint wordmark) and offers it via the Web Share
API (`navigator.share({ files })`), falling back to a PNG download when share isn't
available.

**Refactor first (so the art isn't duplicated):**
- Extract the generative geometry from `app/src/components/FingerprintArt.tsx` into a pure
  module `app/src/lib/fingerprint.ts`: export `mulberry32`, `buildBranches(seed, sessions,
  vigor)`, and a new `fingerprintSvgMarkup(seed, sessions, vigor): string` that returns the
  inner SVG (defs + roots + tips + core) as a self-contained string using inline
  attributes/hsl (no CSS classes, no `breathe` animation — a static snapshot).
- `FingerprintArt.tsx` imports from there and keeps rendering exactly as today (the live
  component can still use the `breathe` class for the on-screen version).

**Build the exporter** `app/src/lib/shareCard.ts`:
- `renderShareCard({ seed, sessions, vigor, confidence, title }): Promise<Blob>`:
  1. Create a 1080×1350 canvas, fill a dark background (`#070b12` → subtle radial cyan
     glow to match the app).
  2. Draw text with `ctx.fillText` (use `system-ui`/`sans-serif` — reliable fonts, unlike
     SVG `<text>` which needs embedded fonts): a title line ("My Cognitive Fingerprint"),
     a subtitle (e.g. `${sessions} sessions · ${confidence} confidence`), and a small
     "CogPrint" wordmark + tagline at the bottom.
  3. Rasterize the fingerprint: build a standalone `<svg xmlns … viewBox="0 0 280 280">` +
     `fingerprintSvgMarkup(...)`, make a data URL, load it into an `Image`, `drawImage`
     it centred and scaled. (Wait for `img.onload` before drawing.)
  4. `canvas.toBlob(resolve, "image/png")`.
- `shareFingerprint(blob, filename)`: build a `File`; if
  `navigator.canShare?.({ files: [file] })` → `navigator.share({ files: [file], title, text })`;
  else create an object URL and trigger a download `<a download>`.

**Grow.tsx:** add a "Share your fingerprint" button (visible once `confidence !== "low"`,
i.e. there's real art to show). On tap: `renderShareCard` → `shareFingerprint`. Show a
tiny spinner while rendering; handle failures quietly (fall back to download).

**Acceptance:** button renders a PNG that visually matches the on-screen fingerprint;
Web Share works on a mobile user agent, download works on desktop; `npm run build` +
`npx eslint src` clean. No backend change, no tests needed (pure UI) but keep it typed.

---

## Feature 2 — Photo → OCR (Claude vision)

**Why:** spec §5 wants "Accepts text and images (photo of notes/textbook → OCR)." Typing
in a textbook page or handwritten notes is high friction. **Costs a paid vision call per
image** — that's why it's last.

**Backend** — new isolated service `agents/material_ocr.py` (mirror
`question_generator.py`'s shape: `is_available()`, an `OcrUnavailable` error, env key,
configurable model via `COGPRINT_OCR_MODEL` default `claude-opus-4-8` which supports
vision):
- `extract_text_from_image(image_base64: str, media_type: str) -> str` — one Anthropic
  vision call: a `messages.create` with a user message containing an `image` block
  (`source: {type:"base64", media_type, data}`) + a text instruction:
  *"Transcribe all study-material text visible in this image. Output only the transcribed
  text, preserving headings/structure and math notation as best you can. If it's
  handwritten, do your best; do not add commentary."* Return the text. Raise
  `OcrUnavailable` on missing key / API error.

**Backend** — `main.py` endpoint `POST /materials/ocr`:
- Body model in `schemas/session.py` (or `schemas/material.py`): `{ image_base64: str,
  media_type: str }` (accept `image/png`, `image/jpeg`, `image/webp`; reject others with
  400). Enforce a size cap (e.g. reject if decoded > ~5 MB → 413).
- Returns `{ text: str }`. 503 (not 500) when `OcrUnavailable` — same graceful pattern as
  questions. This endpoint does NOT create a Material — it just returns text; the frontend
  then feeds it into the existing `POST /materials/analyze` flow (so OCR is purely a
  text-acquisition front door and the whole downstream pipeline is reused unchanged).
- Tests (`tests/test_ocr.py`): mock `extract_text_from_image`, assert `{text}` returned;
  503 without key; 400 on a bad media_type. No real API calls in tests.

**Frontend** (`app/src/pages/Paste.tsx`):
- Add a "📷 Snap a photo" button beside the textarea. It opens a hidden
  `<input type="file" accept="image/*" capture="environment">` (mobile → camera).
- On file pick: downscale client-side (draw to a canvas, cap longest edge ~1600px, export
  JPEG ~0.85) to bound payload/cost; base64-encode; `POST /materials/ocr`.
- Show the brain-read animation while OCR runs (never a dead spinner). On success, drop
  the returned text into the textarea (let the user glance/edit) OR auto-proceed to
  analyze — pick the lower-friction option but let them see it first (spec: honest).
- On 503, show the same friendly "needs setup / admin: set ANTHROPIC_API_KEY" state used
  by the questions screen; the rest of the app is unaffected.
- Add `api.ocr(imageBase64, mediaType)` to `app/src/api.ts`.

**Acceptance:** a photo of text becomes editable material and flows into the normal
analyze → plan → quiz loop; 503 path is graceful; pytest + build + eslint green. Note the
per-image cost in the commit message.

---

## Feature 3 — Smart per-topic forgetting nudges

**Why:** spec §5 wants "You're about to forget photosynthesis — 2-minute review?" — a
*specific* fading topic, not just "you have checks due." Uses data the backend already
has. No cost.

**Backend** — `main.py` endpoint `GET /users/{id}/review-suggestions`:
- For each **Material the user has ≥1 StudySession on**: find the most recent session's
  `created_at`; `t = days since`. Pick a stability `S`:
  - Prefer the user's measured stability for the technique used on that material, from the
    fingerprint's `memory_profiles` (`avg_stability_days`); else fall back to a sane
    default (~10 days — the same default `personalization/forgetting_curve.py` already
    uses). Keep this deterministic; no LLM.
  - `predicted_retention = exp(-t / S)` (clamp 0..1).
- Return a list `[{ material_id, title, last_studied, days_since, predicted_retention,
  fading }]` sorted by ascending `predicted_retention`, where `fading = predicted_retention
  < 0.85`. Add a small pure helper (e.g. in `personalization/` or a `review.py`) so it's
  unit-testable.
- Schema in `schemas/session.py`; test in `tests/test_review.py`: seed sessions with
  backdated `created_at`, assert an old material shows low retention + `fading=true` and a
  fresh one doesn't. (Reuse the `backdate_session` helper pattern from `tests/conftest.py`.)

**Frontend** (`app/src/pages/Paste.tsx`, replacing the current generic nudge):
- Call `GET /users/{id}/review-suggestions`; if the top item is `fading`, show the gentle,
  dismissible, rate-limited (~6h, reuse `nudgeAllowed`/`dismissNudge` in `store.ts`) nudge:
  *"You're about to forget '{title}' — a 2-minute review locks it in."* with a "Quick
  review →" action that navigates to `/cards?m={material_id}` (a quiz round on exactly
  that material). Keep the existing pending-checks nudge as a fallback when nothing is
  fading. Add `api.getReviewSuggestions(userId)` to `api.ts`.
- **Framing constraint:** copy is about the user's own decaying retention (their data),
  phrased as an offer to act — never a claim that a technique is better for them.

**Acceptance:** an old material surfaces as "about to forget" with a working review CTA;
nothing fresh triggers it; pytest + build + eslint green.

---

## Feature 4 — "Save your progress" moment

**Why:** spec §7 — accounts only when they want to save; value first, commitment after.
Today the consumer user is an anonymous `localStorage` id, and there's no way to name
yourself or return on another device.

**Design (no login wall, no real auth, minimal backend):**
- **Name:** keep it client-side. Add `name: string | null` to `AppState` in
  `app/src/store.ts`. (Don't add a DB column — there's no migration system and it isn't
  needed for a display name.)
- **The moment:** on `Grow.tsx`, once `confidence !== "low"` (value delivered), show a
  soft "Save your progress" card: a name input (stores to `store`) and the user's
  **CogPrint ID** (their numeric `userId`) with a copy button and one line: "Enter this ID
  on another device to pick up where you left off." Dismissible; don't nag (show once
  per session, or until a name is set).
- **Restore:** on `Paste.tsx`, a small "Have a CogPrint ID? Restore" entry that takes an
  id, validates it with `GET /users/{id}` (404 → friendly "we couldn't find that ID"),
  and on success writes `userId`/`group` to `store` and navigates to `/grow`.
- No backend changes required (`GET /users/{id}` already exists). Optional stretch: add a
  `name` column to `User` + a `PATCH /users/{id}/name` — only if you also handle the DB
  reset; otherwise keep name client-side.

**Acceptance:** a user can name themselves, copy their ID, and restore that ID in a fresh
`localStorage` (verify: clear storage, restore by ID, land on the same fingerprint);
invalid ID is handled; build + eslint green.

---

## What NOT to touch (any feature)
`FingerprintArt.tsx`'s on-screen rendering behaviour, `insights.ts` (real/sham split), the
PWA config, the browser extension, `Study.tsx`, `Checks.tsx`, and the quiz/flashcard logic
in `Cards.tsx` — all built and verified. Feature 1 refactors the fingerprint *geometry*
into `lib/fingerprint.ts` but must not change how the live component looks.

## Collaboration reminder
Shared repo, two machines. Pull before starting; claim in `HANDOVER.md` §9; commit + push
per feature; don't rewrite unrelated files.
