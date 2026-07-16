# CogPrint — Master Problem Inventory & Execution Prompts

> **What this is:** an exhaustive, honest catalog of every gap between "impressive
> local MVP" and "commercial product people pay for." Written the night of
> 2026-07-10 as an autonomous brainstorm. Each problem has: **why it matters**, a
> **severity**, and a self-contained **execution prompt** a fresh Claude Code agent
> (or a human) can run cold. Read `HANDOVER.md` for the system model first.
>
> **Severity key:** 🔴 blocker (can't launch without it) · 🟠 major (needed before
> charging money) · 🟡 important (needed before scale) · 🟢 nice-to-have.
>
> **Honest verdict (see the readiness scorecard in chat 2026-07-10):** CogPrint is
> ~40% of the way to a sellable product. The gap is NOT more features — it's
> **deploy → real accounts → real users → validation.** Prioritize the 🔴s.

---

## 0. Priorities at a glance (do them in this order)

1. **P1 — Deploy something** (§1). Nothing exists for anyone until it's hosted.
2. **P2 — Real accounts + data persistence** (§2). localStorage loses users.
3. **P3 — Legal minimum** (§5). GDPR/ToS before a single real EU user.
4. **P4 — Validate with 20–50 real users** (§7). Free beta. Learn before building more.
5. **P5 — Only then: payments + freemium** (§6).

Everything else supports or follows these five.

---

## 1. Deployment & infrastructure 🔴

**Problem:** Nothing is deployed. Backend, consumer app (`app/`), and research
frontend (`frontend/`) all run only on localhost. There is no host, no domain, no
CI/CD, no container, no environment separation (dev/staging/prod).

**Why it matters:** This is the single biggest blocker. Without hosting, the product
does not exist for anyone but you.

**Sub-problems:**
- SQLite (`cogprint.db`) is a single local file — fine for dev/beta, wrong for prod
  (no concurrent writes at scale, no managed backups).
- No `Dockerfile` / container definition for the backend.
- No `vercel.json` / static-host config for the frontends.
- CORS is env-configurable (`CORS_ORIGINS`) — good — but nothing sets it in prod.
- No health-check wiring to a platform, no process manager, no restart policy.
- Secrets (`ANTHROPIC_API_KEY`, `COGPRINT_API_KEY`, `DATABASE_URL`) have no prod home.

**Execution prompt:**
> Stand up a minimal prod deployment. (1) Add a `Dockerfile` for the FastAPI backend
> (python:3.13-slim, install `requirements.txt`, run `uvicorn main:app --host 0.0.0.0
> --port $PORT`) plus a `.dockerignore`. (2) Add a `render.yaml` (or Railway config)
> that provisions the web service + a managed Postgres and sets `DATABASE_URL`,
> `CORS_ORIGINS`, `COGPRINT_API_KEY`. (3) Add `app/vercel.json` and
> `frontend/vercel.json` (SPA rewrite to index.html; set `VITE_API_BASE` to the
> backend URL at build). (4) Document the exact click-path to deploy in a new
> `DEPLOY.md`. Do NOT actually deploy or create accounts — leave that to the owner;
> just make it a one-command / few-click operation. Note: some scaffolding may
> already exist (added 2026-07-10) — check before duplicating.

---

## 2. Identity, accounts & data persistence 🔴

**Problem:** Users are anonymous, keyed only by a `userId` in `localStorage`
(`app/src/store.ts`). Clearing the browser, switching devices, or using private mode
= total loss of progress and fingerprint.

**Why it matters:** No one pays for a product that forgets them. This is the biggest
*architecture* change on the roadmap and gates everything about retention/LTV.

**Sub-problems:**
- No way to recover an account (the buddy `share_code` is the closest thing).
- No cross-device sync.
- No email → no lifecycle messaging, no retention nudges, no password reset.
- The anonymous model was a deliberate RCT choice; a real product needs a bridge
  from "anonymous first paste" → "claimed account" without losing the RCT blind.

**Execution prompt:**
> Add a lightweight, passwordless account layer that preserves the "no login wall"
> first-run. (1) Backend: add `email` (nullable, unique) to `User`; add magic-link
> auth (`POST /auth/request-link` emails a signed token; `GET /auth/verify?token=`
> returns a session). Use a signed JWT or a random session token table. (2) Let a
> user "claim" their existing anonymous `userId` by adding an email — migrate the
> anonymous row, don't create a new one, so the fingerprint carries over. (3)
> Frontend: keep the anonymous first paste; after the first real payoff (Grow
> screen), prompt "save your progress — enter your email." Store the session token
> in `localStorage` alongside `userId`. (4) Pick an email sender (Resend/Postmark)
> behind an env var; degrade gracefully to console-log in dev. Keep the RCT group
> assignment untouched during claim.

---

## 3. The "always active recall" problem — single study modality 🟠

**Problem:** Every flashcard round logs `technique: "active_recall"` (hardcoded in
`app/src/pages/Cards.tsx`). The technique-comparison engine (LinUCB bandit +
`technique_effectiveness`) is real and correct — proven 2026-07-10 by seeding varied
data and watching it rediscover the Dunlosky (2013) ranking — but the consumer app
only ever feeds it ONE technique, so "which technique works best for you" can never
populate from real consumer use.

**Why it matters:** The whole pitch is "the app that learns *how you* learn." With a
single modality that promise is structurally unfulfillable in the consumer product.

**Execution prompt (partially built 2026-07-10 — verify state first):**
> Make study multi-modal and log the honest technique. The study plan already
> recommends a research-backed technique per day (`StudyPlanDay.technique`). (1) Add
> a study-mode concept to the cards flow: pass a `technique` (or `mode`) into
> `/cards` (URL param + a picker defaulting to the plan's recommendation). (2)
> Implement 3–4 genuinely distinct, honest modes: **Active Recall** (current
> flashcards), **Practice Testing** (same items, graded "test" framing, no peeking),
> **Elaborative Interrogation** (show concept → "explain why, in your own words" →
> self-rate), **Re-reading** (show concept + source text → light check; the baseline).
> (3) Log the actual technique used, not a constant. (4) The scheduling-type
> techniques (spaced_repetition, interleaving) are properties of *when/what order*
> reviews happen, not session modes — surface them in the plan, don't fake them as
> modes. Never log a technique the user didn't actually do — honest data is the
> product's scientific spine.

---

## 4. Flashcard generation dependency & cost 🟡

**Problem:** Flashcards (Agent 4) are the only LLM call and need
`ANTHROPIC_API_KEY`. Without it, `/cards` shows a clean "needs setup" screen. Input
is capped at 24,000 chars (~6 pages of a 30-page PDF), so long material is silently
truncated.

**Why it matters:** Flashcards are the core loop; today they're off. And the input
cap means a 30-page upload only cards its first ~6 pages — a real content gap.

**Execution prompt:**
> (1) Document turning flashcards on: owner adds `ANTHROPIC_API_KEY` to backend
> `.env`; note `COGPRINT_QGEN_MODEL` as the cost lever (Haiku ≈ 5× cheaper than
> Opus). (2) Fix the truncation: instead of hard-cutting at 24k chars, chunk long
> material and generate cards per chunk (bounded total), or let the user pick which
> section to card. Keep a hard total-token ceiling so cost stays bounded. (3) Add a
> per-user daily generation cap to prevent runaway spend before pricing exists.

---

## 5. Legal, privacy & compliance 🔴 (for EU)

**Problem:** No privacy policy, no terms of service, no cookie/consent handling, no
GDPR data-subject flows (export/delete). CogPrint collects behavioral learning data
about identifiable people once accounts exist, and the owner is in the EU/EEA.

**Why it matters:** Legally required before real users. Also a trust signal.

**Execution prompt:**
> (1) Draft a plain-language Privacy Policy and Terms of Service tuned to CogPrint
> (what's collected: pasted study text, scores, retention checks, email; why; how
> long; processors: the hosting provider + Anthropic for flashcards). (2) Add
> `GET /users/{id}/export` (full personal-data export, JSON) and
> `DELETE /users/{id}` (hard-delete user + sessions + checks + fingerprint) behind
> the user's own auth. (3) Add a first-run consent line and a settings page linking
> both docs. (4) Since flashcard text is sent to Anthropic, disclose that
> sub-processor. Flag anything that needs a human lawyer's review rather than
> presenting drafts as legal advice.

---

## 6. Business model, pricing & payments 🟠

**Problem:** No monetization exists — no Stripe, no plans, no freemium gating, no
usage metering.

**Why it matters:** Needed to make money, but ONLY after §7 validation. Building it
before you know people value the product is premature.

**Execution prompt (do AFTER validation):**
> Implement freemium. (1) Backend: a `plan` field on `User` (`free`/`pro`) and a
> metered counter for monthly material analyses. Enforce the free cap (e.g. 3–5
> PDFs/month) server-side. (2) Stripe Checkout + a webhook that flips `plan` on
> successful subscription; Billing Portal for cancel. (3) Frontend: a paywall/upsell
> at the free cap and a "Pro" badge. Suggested price from the cost analysis: $6/mo
> or $48/yr (≈85–95% margin on Haiku-tier costs). (4) NEVER handle raw card data —
> Stripe hosts it. Keep secrets server-side.

---

## 7. Validation — zero real users 🔴

**Problem:** Everything has been tested by the owner with seeded/synthetic data. The
core value hypothesis ("the fingerprint feels valuable and changes how people
study") is completely unvalidated.

**Why it matters:** You cannot price, market, or prioritize correctly without it.
This is the highest-leverage non-code work in the whole project.

**Execution prompt (mostly non-code):**
> Design a 2–4 week free beta. (1) Define 2–3 success metrics up front: e.g. D7
> retention, % of users who complete ≥5 sessions (reach medium confidence), and a
> one-question "was the fingerprint useful?" survey. (2) Add minimal privacy-safe
> product analytics (self-hosted Plausible or a simple events table) — track funnel:
> paste → plan → cards → grow → return. (3) Recruit 20–50 students (owner's network).
> (4) Add an in-app feedback button. Instrument, don't guess. The code deliverable
> here is just the analytics events + feedback capture; the rest is running the beta.

---

## 8. Testing & quality 🟡

**Problem:** Backend has 24 tests (good). The consumer app (`app/`) has **zero**
automated tests. `datetime.utcnow()` is deprecated across the backend (warnings
today, breakage on a future Python). No end-to-end/integration test for the full
paste→plan→cards→grow→checks flow. No linting/formatting gate in CI (no CI at all).

**Execution prompt:**
> (1) Replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` (or a
> single helper) across `main.py`, `database.py`, `personalization/`, keeping stored
> values naive-UTC-compatible if columns are naive. (2) Add Vitest + React Testing
> Library to `app/`; unit-test `forecast.ts`, `streak.ts`, `insights.ts`, and the
> archetype logic (pure functions — easy wins). (3) Add a GitHub Actions workflow:
> backend `pytest`, app `tsc --noEmit && npm run build && vitest`. (4) Add
> ruff/black for Python and prettier/eslint for TS as a check. Note: datetime fix may
> already be done (2026-07-10) — verify.

---

## 9. Data & scientific integrity 🟠

**Problem:** Several open scientific/product decisions the owner must own (no longer
UiO-anchored as of 2026-06-18):
- **Retention schedule:** code uses 24h/7d; study materials referenced day 1/5/10/30.
  `RETENTION_SCHEDULE_DECISION.md` + `config.py` hold this. Still unresolved.
- **RCT blind in a commercial app:** control users get sham insights to preserve the
  experiment. In a *paid* product, deliberately giving paying users worse (sham)
  insights is ethically/commercially fraught. Decide whether the RCT continues once
  money is involved, or whether treatment becomes the default for everyone.
- **Technique honesty** (see §3) — don't log techniques not actually used.

**Execution prompt:**
> Surface these as explicit owner decisions with tradeoffs; do NOT resolve
> unilaterally. For the retention schedule, present the two schedules' pros/cons and
> implement whichever the owner picks via `config.CHECK_TYPE_KEYS` (single source of
> truth already exists). For the RCT-vs-commercial tension, write up options
> (A: drop the blind, everyone gets real insights; B: keep a research cohort,
> separate from paying users) and let the owner choose.

---

## 10. Security & abuse 🟡

**Problem:** `COGPRINT_API_KEY` guards only bulk-data endpoints and is off by
default. No per-user auth on user-scoped endpoints (anyone who guesses a `userId`
can read that user's fingerprint/plan). No rate limiting. No input size/abuse limits
beyond the flashcard char cap. Pasted text is stored verbatim (could be huge or
malicious).

**Execution prompt:**
> (1) Once accounts exist (§2), require the user's own session token on
> `/users/{id}/*` routes so users can only read their own data. (2) Add rate limiting
> (slowapi or a reverse-proxy limit), especially on `/materials/analyze` and the
> flashcard endpoint. (3) Cap stored `raw_text` length and reject oversized payloads
> with a clear error. (4) Turn on `COGPRINT_API_KEY` before any public deploy.

---

## 11. Observability 🟡

**Problem:** No structured logging, error tracking, uptime monitoring, or product
analytics. If prod breaks, you won't know; if users drop off, you won't see where.

**Execution prompt:**
> (1) Add structured logging (uvicorn access + app logs) and an error tracker
> (Sentry, free tier) on both backend and frontend behind env vars. (2) Add uptime
> monitoring on `/health`. (3) Product analytics per §7. All behind env vars so dev
> stays quiet.

---

## 12. Content & input methods 🟢

**Problem:** The only input is pasted text, capped at ~6 pages of effective content
(§4). No PDF upload, no photo/OCR, no lecture/YouTube import. Students live in PDFs
and lecture videos.

**Execution prompt:**
> (1) PDF upload → extract text server-side (pypdf) → existing analyze flow, with the
> section picker from §4 for long docs. (2) Photo → OCR (Tesseract, self-hosted =
> ~free) → flashcards; keep the input cap to bound LLM cost. (3) YouTube → transcript
> (youtube-transcript-api) → cards; long transcripts can be 3–5× normal cost, so keep
> the cap. These are the two paid-to-run ideas (#6/#7 in `COGPRINT_IDEAS.md`) — cheap
> if OCR is self-hosted and the cap holds.

---

## 13. Scalability 🟢 (only matters after traction)

**Problem:** Fingerprint rebuild runs as a FastAPI `BackgroundTask` (in-process) —
fine now, but a spike of writes could pile up MCMC work on the web dyno. SQLite
serializes writes. No caching of the (expensive) fingerprint computation beyond the
stored profile.

**Execution prompt:**
> Defer until load justifies it. When it does: move `rebuild_fingerprint` to a real
> task queue (Celery/RQ + Redis) so the web process stays responsive; move to
> Postgres (§1); add a rebuild debounce so N rapid sessions trigger one rebuild.

---

## 14. UX & product polish 🟢

**Problem / opportunities:**
- Onboarding is a cold paste box — no example, no "try a sample" affordance.
- The medium/high-confidence Grow payoff is only reachable after ≥5 sessions; the
  first-run "growing" state must carry motivation alone.
- No empty-states audit beyond flashcards' "needs setup."
- No settings screen (needed for §5 export/delete, §2 email).
- Accessibility unaudited (contrast, focus order, screen-reader labels).

**Execution prompt:**
> (1) Add a "try a sample" button on the paste screen that loads demo text. (2)
> Audit every screen's empty/loading/error state. (3) Add a settings screen (account,
> data export/delete, privacy links, buddy code). (4) Run an accessibility pass
> (labels, contrast, keyboard nav).

---

## 15. Repo & docs hygiene 🟢

**Problem:** Four related surfaces are easy to confuse: `app/` (consumer), `frontend/`
(research platform), the `cogprint-site` repo (marketing), and the backend. An
unrelated `event_camera/` project sits untracked in the repo root. Multiple large
handover/idea docs risk drifting from the code.

**Execution prompt:**
> (1) Add a top-level README section mapping the four surfaces in one table (partly in
> HANDOVER already). (2) Decide `event_camera/`'s fate — it's unrelated; move it out
> of this repo or explicitly `.gitignore` it (do not commit its large `.npy` files).
> (3) Keep `HANDOVER.md`, `COGPRINT_IDEAS.md`, this file, and
> `RETENTION_SCHEDULE_DECISION.md` cross-linked and dated.

---

## 16. Grab-bag / smaller issues 🟢

- `Checks.tsx` displays the technique as a hardcoded "Active Recall" label — tie it to
  the real session technique once §3 lands.
- Study plan is fixed at 14 days — could adapt to material size / user goal.
- No offline handling beyond the PWA app-shell (API is network-only by design).
- Buddy system (`#9`) has no way to remove/block a buddy beyond "unfollow", and one
  buddy max — fine for v1, note for later.
- The archetype (`#2`) is a single-user heuristic, not real clustering — upgrade to a
  nightly population k-means job once there's a population (noted in `COGPRINT_IDEAS.md`).
- No i18n — the owner is Norwegian; the app is English-only. Consider nb/nn locale.

---

## Appendix — the one-paragraph strategic read

CogPrint's engine is genuinely good and genuinely research-grounded — it rediscovers
the study-technique literature from data, which most "study app" startups can't
claim. The danger is **building more engine when the missing pieces are all
distribution and validation.** The disciplined path: stop adding features, ship the
🔴s (deploy, accounts, legal), run a free beta with 20–50 real students, and let their
behavior — not more code — decide what comes next. The features already built (forecast,
archetype, streak, boss battles, buddy, multi-modal study) are more than enough to
test the core hypothesis.

*Generated autonomously 2026-07-10. When this doc and the code disagree, the code wins
— update this doc.*
