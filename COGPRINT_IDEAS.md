# CogPrint — Creative Feature Specs (the 7 free ideas)

> Top-tier implementation prompts for each feature. Every idea here costs **$0 per
> user to run** — it surfaces or reframes data the backend already computes, or uses
> only local state. No new LLM calls, no third-party APIs. Written so a fresh Claude
> Code agent (or a human) can execute any one of these cold.
>
> Read `HANDOVER.md` first for the system model. The consumer app is `app/`
> (React + Vite + TS + Tailwind, dark neural theme). The fingerprint shape is in
> `app/src/types.ts` → `FingerprintProfile`. The API client is `app/src/api.ts`.
>
> **Status legend:** ✅ built · 🔨 spec only (not built yet)

---

## #1 — Memory weather forecast ✅

**Pitch:** A daily glanceable "decay radar" that turns the invisible forgetting-curve
math into something felt: *"3 concepts entering the forgetting zone today, 1 rock-solid."*

**Implementation prompt:**
> Add a `forecast.ts` module to `app/src/` that computes a memory forecast from a
> `FingerprintProfile` plus the pending-checks list (`api.getPendingChecks`). For each
> technique memory profile (`fp.memory_profiles`), use `predicted_retention_7d`,
> `avg_stability_days`, and `optimal_review_interval_days` to bucket the user's memory
> into `fading` (predicted retention < 0.5), `cooling` (0.5–0.8), and `solid` (> 0.8).
> Combine with the count of pending retention checks (those are literally concepts due
> for review). Render a compact "forecast" card at the top of the Grow screen (`Grow.tsx`)
> above the fingerprint header: an icon per bucket, counts, and a one-line summary.
> Weather metaphor in copy ("stormy / cloudy / clear"). Pure client-side; no new endpoint.

**Data source:** `FingerprintProfile.memory_profiles`, `getPendingChecks`. Free.

---

## #2 — Learner archetype ✅

**Pitch:** Give the user an identity: *"You learn like a 'Sprinter' — high early retention,
fast decay."* Social-proof + identity hook.

**Implementation prompt:**
> Add an `archetype()` function (in `forecast.ts` or its own `archetype.ts`) that maps a
> `FingerprintProfile` to one of ~5 named archetypes using a **heuristic on the user's own
> curve shape** (NOT cross-user clustering — that needs a population and a backend job;
> note this honestly in a tooltip as "based on your data so far"). Signal axes: mean
> `avg_stability_days` across `memory_profiles` (fast vs slow decay), the spread of
> `technique_effectiveness` (specialist vs generalist), and `improving_over_time` (trending
> vs plateaued). Archetypes e.g. Sprinter (fast learn, fast decay), Marathoner (slow, durable),
> Specialist (one dominant technique), Explorer (even across techniques), Climber (improving).
> Render as a labelled badge on Grow with a one-line description of what people like them do best.
> Only show at `medium`+ confidence.
>
> **Future upgrade (🔨, needs a population):** replace the heuristic with real k-means over
> all users' fingerprints via a nightly backend job + a `GET /users/{id}/archetype` endpoint.

**Data source:** `FingerprintProfile`. Free (heuristic). Real clustering later.

---

## #3 — "Why this card, why now" transparency ✅

**Pitch:** Every scheduled review shows its reasoning: *"Predicted retention dropped to 84%
— review threshold."* Builds trust that the app is smart *about you*.

**Implementation prompt:**
> The study plan already returns a per-day `rationale` and each `StudyPlanDay` has a
> `technique` + `topic_focus` (`StudyPlanResponse` in `types.ts`). On the Plan screen
> (`Plan.tsx`), for each expandable day card add a small "why" chip that surfaces the
> retention math: pull the matching technique's `predicted_retention_7d` and
> `optimal_review_interval_days` from the fingerprint (`memory_profiles`) and render a
> plain-language line ("Review now — predicted retention ~84%, past your 85% threshold").
> Also add a subtle "why this card" affordance on the Cards screen header. Reuse the
> existing `rationale` text; layer the numbers on top. No new endpoint.

**Data source:** `StudyPlanResponse.days[].rationale`, `memory_profiles`. Free.

---

## #4 — Retention streak (not a login streak) ✅

**Pitch:** A streak that rewards *memory*, not app-opening: consecutive days where recall
stayed above the personal curve.

**Implementation prompt:**
> Add a `streak.ts` module using `localStorage` (co-locate with `store.ts`). Record an
> activity entry each time the user finishes a flashcard round (`Cards.tsx` on finish) or
> completes a retention check (`Checks.tsx`), storing the date (YYYY-MM-DD) and whether the
> score beat a threshold (e.g. ≥ 70%, or ≥ the user's rolling average). Compute the current
> streak (consecutive calendar days with a qualifying activity) and the longest streak.
> Render a flame/streak badge on Grow and optionally on Plan. Keep it purely local; it's a
> motivator, not research data. Guard against timezone edge cases (use local date).

**Data source:** local activity log in `localStorage`. Free.

---

## #5 — Boss battles = retention checks ✅

**Pitch:** Reframe the 24h/7d checks as "memory boss fights." Weakest-decay concepts are
the bosses; beating them strengthens the fingerprint bloom.

**Implementation prompt:**
> Reframe the existing pending-checks flow (`Checks.tsx`, `getPendingChecks`) with a
> boss-battle skin — no new data. Each pending check becomes a "boss" with a difficulty
> derived from how overdue it is (`due_date` vs now) and the technique's stability. The
> weakest technique from the fingerprint (lowest `predicted_retention_7d` in
> `memory_profiles`) is the "final boss." On Grow, show a "Bosses" section listing due
> checks as beatable cards with HP-style bars; completing a check in `/checks` visibly
> "defeats" the boss. Keep all real scoring/logging unchanged underneath — this is a
> presentation layer over `RetentionCheck` logging.

**Data source:** `getPendingChecks`, `memory_profiles`. Free.

---

## #8 — Shared decks with *your* fingerprint applied 🔨

**Pitch:** A friend shares a deck; you study it, but *your* schedule/technique come from
*your* fingerprint. Same content, personalized delivery — sharing without leaking the moat.

**Implementation prompt:**
> Materials are already server-side by id (`POST /materials/analyze` → `material_id`;
> questions cached per material). Add a lightweight share flow: a "Share deck" button
> (Plan/Cards) that produces a link like `/?deck=<material_id>` (or a short code). Opening
> that link on another device imports the material id into local state and routes into the
> plan/cards for it — but the plan, technique choice, and fingerprint are computed for the
> *current* user, not the sharer (this already happens, since those endpoints are per-user).
> No accounts needed. **Backend touch (small):** confirm `POST /users/{id}/study-plan` and
> `POST /materials/{id}/questions` work for any user against a material another user created
> (they should — materials aren't user-scoped). Add a `GET /materials/{id}` if a title/preview
> is needed for the import screen.
>
> **Privacy:** share only the material id/content, never the sharer's fingerprint or sessions.

**Data source:** existing per-user endpoints + material id. Free. Needs a small import UI + maybe `GET /materials/{id}`.

---

## #9 — Study-buddy accountability 🔨

**Pitch:** Two users see each other's *forecast* (not content): *"your buddy has 4 concepts
fading."* Light social pressure, zero privacy leak.

**Implementation prompt:**
> Build the minimum identity layer that fits the anonymous, localStorage-first design — a
> **buddy share-code**, not full accounts.
> - **Backend:** add a short random `share_code` to the `User` model (`database.py`),
>   generated on user creation (or lazily via `POST /users/{id}/share-code`). Add
>   `GET /buddy/{share_code}/forecast` that returns a **privacy-safe summary only**:
>   confidence level, session count, streak-ish counts, and the memory-forecast buckets
>   from #1 — **never** raw sessions, material content, or the full fingerprint.
> - **Frontend:** a "Study buddy" card on Grow: show my code + a field to paste a buddy's
>   code (store buddy code in `localStorage`). Fetch and render the buddy's forecast summary
>   ("Alex: 4 concepts fading, 6-day streak"). One buddy is enough for v1.
> - **Note:** adding a column to `User` is a schema change; the dev SQLite DB is regenerable,
>   but if any real data exists, add a migration or a nullable column with lazy backfill.

**Data source:** new `share_code` column + one read-only summary endpoint. Free to run.

---

## Not in this doc (cost money — separate decision)

- **#6 Photo → flashcards** — OCR (Tesseract = ~free self-hosted; cloud OCR ~$1.50/1k imgs)
  then the existing Agent-4 flashcard call. Keep the 24k-char input cap to bound cost.
- **#7 YouTube → cards** — transcript pull (free-ish) + Agent-4 call, but long transcripts
  can be 3–5× a normal flashcard cost. Keep the input cap.

---

*Build order recommendation: #1 → #3 → #4 (cheapest, highest "felt intelligence"), then
#5 → #2, then the social pair #8 → #9. Ship each end-to-end before the next.*
