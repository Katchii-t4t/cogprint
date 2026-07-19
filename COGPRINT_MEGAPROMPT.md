# CogPrint — The Mega Prompt

> **To the model reading this (Fable):** You are being handed a real, working
> product and asked to take it from "impressive MVP" to a **commercializable beast**.
> This document is your complete brief. Read all of it before touching code. It is
> deliberately ambitious — sky's the limit — but every ambition here is anchored to
> a real constraint of *this* codebase and to the learning science the product is
> built on. Your job is not to bolt on features. It is to **upgrade every layer of an
> already-coherent system** without breaking the two things that make it special:
> (1) a **100%-in-house, zero-LLM personalization brain**, and (2) **scientific honesty**.
> Owner: **Katchi** (she/her). She wants audacity *and* research integrity — never
> trade one for the other. When code and this doc disagree, the code wins; update
> the doc.

---

## 0. What CogPrint is (context you must internalize first)

CogPrint turns any study material into a personalized, science-grounded study plan,
then **learns how the individual's memory actually works** and adapts. It has two
halves living in one repo:

- **A research platform** (`frontend/`, browser extension, an RCT harness in the
  backend): control/treatment groups, real vs. sham insights, for running a proper
  randomized study on whether personalization improves retention.
- **A consumer app** (`app/`): a mobile-first React PWA — paste text → knowledge map
  → 14-day plan → study round → **cognitive fingerprint** that grows with use.

### The crown jewel — the zero-LLM brain
The intelligence is **pure NumPy math, no API calls**:
- `agents/material_analyzer.py` — TF-IDF → LSA (SVD) → TextRank → heuristic
  concept typing (`factual|conceptual|procedural` × `foundational|intermediate|advanced`).
- `personalization/` — Ebbinghaus forgetting-curve fits, **hierarchical Bayesian MCMC**
  for per-technique memory stability, a **LinUCB bandit** for technique recommendation,
  trend detection, insight generation.
- `agents/study_planner.py` — a DP/Ebbinghaus MDP scheduler with **material-aware
  technique matching**: `score(technique) = material_fit × learner_effectiveness`.

Only **three** touchpoints use the Anthropic API: `question_generator.py` (flashcards),
`material_ocr.py` (photo→text), `performance_optimizer.py` (advice text). Everything
that makes CogPrint *smart* runs offline for **$0 runtime**. **This is the moat, the
margin, and the privacy story all at once. Protect it. Never move core intelligence
behind an LLM.**

### Where the project is right now (as of the merge, commit `81c0de3`)
- Backend: 42 tests green. Consumer app: full paste→plan→study→round→fingerprint loop,
  quiz mode with objective grading, retention checks, forgetting nudges, share-card PNG,
  save/restore, photo→OCR.
- **Just landed:** 7 fingerprint-native features (memory-weather forecast, learner
  archetype, retention streak, boss battles, why-this-card, buddy share-code, shared
  decks); **material-aware matching** (plans no longer collapse to "always active
  recall" — technique varies by text type); and the **honest-technique-logging fix**
  (the round logs the technique the user actually chose, so the fingerprint can finally
  learn what works — the learning loop is *closed*).
- **Two problem inventories already exist**: `COGPRINT_PROBLEMS.md` (16 areas) and
  `COGPRINT_PROBLEMS_2.md` (18 more). Treat them as your backlog of known gaps; this
  mega-prompt is the *strategy* that orders and upgrades them.

### Non-negotiable guardrails (violating these breaks the product)
1. **Never put an LLM in the core pipeline.** Analysis, fingerprint, matching,
   planning stay pure-math and offline.
2. **Preserve the RCT blind.** Control users must never receive personalized surfaces
   (forecast, archetype, real insights). If you add a personalized feature, gate it on
   `group === "treatment"` and give control a neutral equivalent so the screen isn't
   obviously emptier.
3. **Never over-claim the science.** Surface uncertainty. At low N say "early estimate."
   Material-type effects are a *modulation* on top of the strong general finding
   (testing & spacing win broadly — Dunlosky 2013). Honest calibration *is* the brand.
4. **Don't lose users.** Every change must keep or improve identity persistence.

---

## 1. The vision — what "the beast" is

A student pastes a chapter at 11pm before an exam. Within **10 seconds** they see a
knowledge map, a plan built for *this* text, and a first study round. Within one
session they feel the app is learning *them*. Over days, timed nudges pull them back at
the exact moment they're about to forget — and it works, measurably. They share a
beautiful fingerprint that markets the app for free. They never pay for the core loop,
and it costs the company ~$0 to serve. Schools adopt it because it's private and
self-hostable. The retention data — grounded in 300+ studies and each user's own
curve — becomes a moat no LLM wrapper can copy.

**One-line positioning:** *"Not another flashcard app. CogPrint learns how your memory
works and studies you back."*

The rest of this document is how to build that, layer by layer.

---

## 2. THE BRAIN — upgrade the intelligence

### 2.1 Cold-start seeding (do this first — it's the single highest-leverage unlock)
**Problem:** the fingerprint needs ~5 sessions for "medium" confidence; most users
churn before the payoff. **Fix:** ship a **research-derived population prior** so the
brain is useful from session zero.

- Build `personalization/priors.py`: encode evidence-based per-technique retention
  distributions from **Dunlosky et al. 2013**, **Cepeda et al. 2006** (spacing),
  **Roediger & Karpicke** (testing effect), **Bjork** (desirable difficulties). Each
  technique gets `(mu_retention_7d, sigma)` and a material-context modifier.
- Feed these as the **Bayesian prior** the MCMC updates from. Day 1 → the posterior ≈
  the prior (material-driven, honest "early estimate"). As real retention checks arrive
  → the posterior sharpens into a true personal fingerprint. This is textbook
  hierarchical Bayes: population prior → individual posterior.
- **UX:** never a "come back after 5 sessions" wall. Show a provisional fingerprint
  labeled *"Early read — sharpening as you study,"* with a visible confidence band.
- **Payoff:** the wow-moment moves to session 1, and the trust story becomes *"grounded
  in 300+ studies **and** your own behavior."* This alone can transform D1→D7 retention.

### 2.2 Material-match v2
Current matching is a solid rank-weighted `material_fit × effectiveness`. Upgrade it:
- **Whole-material profile → soft distribution** over techniques (already returns
  `MaterialProfile`; make it drive a *blend*, not a single winner).
- **Concept-graph signals:** use `related_concepts` density → interconnected material
  favors interleaving/mind-maps; long/dense → wider spacing intervals.
- **Calibrate weights** against the priors so recommendations stay research-defensible.
- **Explain every pick** in one plain sentence tying text-shape + personal strength.

### 2.3 Richer fingerprint & honest uncertainty
- Surface the **Bayesian credible intervals** the backend already computes (posterior
  CIs) as "±" bands / confidence rings in the UI. False precision destroys trust;
  honest uncertainty builds it.
- Add **time-of-day / sleep / stress** conditioning to recommendations (data model
  already carries these) — "you retain 14% more studying before 11am."
- Add a **"how we know this"** one-tap explainer (method in plain language).

### 2.4 The 100%-API-free build (strategic weapon — build it as a first-class mode)
Make the whole product runnable with **zero API keys**:
- **Flashcards without an LLM:** generate **cloze-deletion cards** from the concept
  graph (`material_analyzer` already extracts key terms + types). Cloze is Anki's most
  popular, research-backed format — not a downgrade. Distractors = same-type concepts.
  Build `agents/question_generator_local.py` as a drop-in; keep the LLM path as optional
  "enhance."
- **OCR without an LLM:** Tesseract (`pytesseract`) as the default; LLM-vision optional.
- **Advice without an LLM:** the template-based insight generator already exists — use
  it when no key is set.
- Ship a config flag `COGPRINT_MODE = free | hybrid | premium`. **Free** = $0, offline,
  self-hostable, no data leaves the box (huge for schools + GDPR). **Hybrid** = free
  baseline + optional AI polish. This is a genuine market wedge; treat it as a headline
  capability, not a fallback.

---

## 3. THE LOOP — upgrade the product experience

### 3.1 Onboarding & the engineered "aha"
- First run currently is a cold paste box. Add a **"Try a sample"** path that loads a
  demo deck with a pre-seeded fingerprint so the payoff is felt in <60s.
- After the first real round, a micro-celebration that points at the fingerprint growing:
  *"You just taught CogPrint something about **you**."* Make the learning visible.

### 3.2 Re-engagement — the missing timed loop (this makes the science actually work)
Spaced repetition is inert if nothing brings the user back at the right time. Build the
channel:
- Backend scheduled worker: per user, compute due reviews (reuse forgetting-curve +
  pending-checks logic) → enqueue reminders.
- Channels cheapest-first: **email** (Resend/Postmark) once accounts exist; **Web Push**
  (VAPID + service-worker) for installed PWAs (note iOS requires home-screen install).
- Respect quiet hours, a per-user frequency cap, one-tap unsubscribe (legal).
- Content names the fading concept: *"'Calvin cycle' is about to slip — a 2-min review
  locks it in."* Measure reminder→return conversion; a wrong cadence kills trust faster
  than silence.

### 3.3 Adaptive plans & the material library
- **Adherence tracking + re-planning:** the 14-day plan must adapt when the user misses
  days. On return, regenerate from *today* given what's done and what's now due. Add an
  optional exam-date so horizon isn't hardcoded at 14.
- **Library:** `GET /users/{id}/materials` + a home screen to browse/search/rename/delete
  decks, each with a "next review" indicator. Make it the returning-user home; paste
  becomes "+ new."

### 3.4 Flashcard quality loop
- Let users **edit** a card's answer (store + prefer the correction).
- **Ground each generated card in a source sentence**; drop cards that can't be grounded.
- Turn the existing flag into a signal that regenerates/hides.

---

## 4. IDENTITY, DATA & TRUST

### 4.1 Real accounts (fixes the biggest leak)
- localStorage loses users across devices; the current "restore by numeric ID" is an
  **account-takeover hole** (sequential, guessable). Replace with **magic-link email
  auth** (passwordless) + an unguessable recovery token. Keep the no-login first paste;
  prompt to "save your progress" *after* value is delivered.
- Migrate anonymous → claimed accounts seamlessly (carry the fingerprint over).

### 4.2 Data model & durability
- Move SQLite → **Postgres** (Alembic migrations); nightly backups.
- Soft-delete + retention policy on raw pasted text (purge after cards are derived, or
  after N days) — privacy + storage hygiene.
- Make the fingerprint rebuild **observable**: log failures (Sentry), track
  `last_rebuild_status`, add retry + a user-triggered "rebuild now." Today failures are
  swallowed and the fingerprint can rot invisibly.

### 4.3 Trust & science surfaces
- Confidence bands everywhere personalized numbers appear.
- A public **"the science" page** citing the literature and explaining the method.
- Run the **validation study** the RCT harness was built for: 20–50 real users, measure
  D7 retention treatment vs control, and "was the fingerprint useful?" This is what turns
  claims into credibility — and is worth more than any feature.

---

## 5. GROWTH, MOAT & BUSINESS

### 5.1 Virality (build the loop, don't bolt it on)
- The shareable fingerprint PNG is already a growth surface — make **every share a
  referral**: deep-link back into a "compare fingerprints" or shared-deck flow.
- Study-buddy accountability (already scaffolded) → light social pressure that pulls
  people back (feeds §3.2).

### 5.2 The moat
- Not the features (copyable) — the **per-user retention curves + research-grounded
  priors** and the **$0-runtime, private, self-hostable** posture. An LLM-wrapper
  competitor cannot match the margin or the privacy story. Lean into it in positioning.

### 5.3 Pricing (protect the free core)
- **Free forever:** the full study loop, cloze cards, local OCR, the fingerprint. Costs
  ~$0 to serve, so give it away — it's the wedge.
- **Premium ($ / mo):** AI-polished cards & vision OCR, unlimited materials, advanced
  analytics, priority reminders, export.
- **Institutional/self-host:** schools pay for a private, GDPR-clean, offline deployment
  — the free-mode build (§2.4) *is* this product.
- Add abuse-resistant limits (IP + device-signal rate limiting on paid paths) so the
  anonymous-first flow can't be used as an infinite-cost faucet.

---

## 6. INFRA, QUALITY, COMPLIANCE

- **Deploy** (scaffolding exists: Dockerfile, render.yaml, vercel.json, DEPLOY.md):
  ship the API to Render + Postgres, the app to Vercel, wire a domain, smoke-test.
- **CI/CD:** GitHub Actions running tsc + vite build + pytest on every PR; fail on a
  bundle-size regression past budget. Enforce short-lived branches + PRs (the two-agent
  workflow just proved that ad-hoc pushes to master diverge painfully).
- **Observability:** Sentry (front + back), basic product analytics for the activation
  funnel (paste → plan → round → D1 → D7), per-user LLM/OCR spend tracking.
- **Performance:** lazy-load routes, keep the paste screen tiny, defer the generative-art
  code; Lighthouse-mobile as a gate.
- **Accessibility:** WCAG-AA contrast on the dark theme, `prefers-reduced-motion`, ARIA
  for the SVG fingerprint + icon buttons, keyboard nav.
- **Legal/GDPR:** privacy policy + ToS, data export/delete endpoints, sub-processor
  disclosure (or, in free mode, "no data leaves your server" — a selling point).
- **i18n:** extract UI strings; add **Norwegian (nb/nn)** + English; pass material
  language through to card generation. The first beta cohort is Norwegian.
- **Prompt-injection hardening** on the (optional) LLM paths: wrap user text as data,
  validate structured output, cap size + rate.

---

## 7. HARDEN THE SCIENCE (the thing competitors can't fake)

- Keep a **`RESEARCH.md`** mapping every algorithmic choice to a citation
  (Ebbinghaus, Dunlosky 2013, Cepeda 2006, Roediger & Karpicke, Bjork).
- Add **backtests**: seed synthetic learners from the literature (a `seed_demo.py`
  already proved the pipeline rediscovers Dunlosky's ranking) and assert the brain
  recovers known effects — this is your regression test for the intelligence itself.
- Expose an **honest "model card"** for the fingerprint: what it measures, its
  assumptions, where it's uncertain.

---

## 8. SUGGESTED SEQUENCING (don't do it all at once)

1. **Cold-start seeding (§2.1)** + **API-free flashcards (§2.4)** — makes the app useful
   from session 1 and free to run. Highest leverage, mostly backend, low risk.
2. **Deploy + real accounts (§6, §4.1)** — reachable, doesn't lose people.
3. **Re-engagement (§3.2)** — makes retention actually happen; the science needs it.
4. **Library + adaptive plans (§3.3)**, **onboarding aha (§3.1)** — depth for returning users.
5. **Validation study (§4.3)** — turn claims into evidence. Run it in parallel from step 2.
6. **Virality, pricing, institutional (§5)** — once retention is proven.
7. **Polish, a11y, i18n, perf, compliance (§6)** — continuous.

At each step: keep 42+ backend tests green, tsc clean, vite build green, and verify the
observable change live in the browser before moving on.

---

## 9. DEFINITION OF DONE (what "beast" means, measurably)

- A first-time user sees a **personalized, material-grounded** recommendation in
  **session 1** (not after 5).
- **$0-runtime free mode** runs with no API key, fully offline, self-hostable.
- Users are **pulled back at the right time** and **come back** (measurable D7 lift,
  treatment vs control, from the RCT).
- **No user is ever lost** to a cleared cache or a new device.
- Every personalized number carries **honest uncertainty**; the science page cites its
  sources; the backtest proves the brain recovers known effects.
- It is **deployed**, on a domain, with CI, observability, and a privacy story a school
  would sign.

---

## 10. Final instruction to Fable

Be bold in ambition and conservative in engineering. **Upgrade every layer, break
none.** Protect the zero-LLM brain, preserve the RCT blind, and never let the product
claim more than the data supports — because for CogPrint, *earned trust is the entire
moat.* Now go build the beast. 🧠⚡

*— Handed off by Katchi's autonomous build partner, 2026-07-19.*
