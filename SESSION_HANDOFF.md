# CogPrint — Session Handoff

> **Read this first, then `git log --oneline -25`, then start.** This is written
> to be the only thing a new session needs. It covers who you're working with,
> what the product is, what is built, what is left, the conventions that made
> the code good, and the specific traps in this environment that will otherwise
> cost you an hour rediscovering.
>
> Written 2026-08-06 at commit `9173cb5`, updated at `022a29a`. When this file
> and the code disagree, **the code wins** — update this file.

---

## 1. Who you're working with

**Katchi** (she/her — *hun/henne*). Git author "Katchi", GitHub `Katchii-t4t`.

- 19, doing a **triple degree at UiO simultaneously**: Medicine (MD), Honours
  Math/Data Science (BSc), Economics & Finance (BSc). Her free time is close to
  zero, and that is the binding constraint on this project — not the code.
- She writes Norwegian, nynorsk-leaning. **Reply in Norwegian.** Code, comments
  and commit messages stay in English.
- She thinks carefully about the *science* and will notice hand-waving. She has
  explicitly asked, more than once, for honesty over enthusiasm: what the model
  can and cannot do, what is proven versus assumed. **Never oversell.** Telling
  her a number is unproven has consistently been more useful to her than telling
  her it is good.
- She owns the project alone (dropped a UiO affiliation deliberately, 2026-06-18
  — do not reference advisors or ethics boards).
- She has said she'll handle the non-code work herself: legal, business,
  validation, and the accounts needed to deploy.

**Working style that has worked:** do the work, verify it, commit it, tell her
plainly what landed and what did not. She responds well to "here is the honest
tradeoff" and to being given a recommendation rather than a menu.

---

## 2. What CogPrint is

A study app that turns pasted material into a personalised, science-grounded
study plan, then **learns how that individual's memory actually works** and
adapts. Two halves in one repo:

- **Consumer app** — `app/`, a mobile-first React + TypeScript + Vite PWA
  (installable, offline-capable). Dark "neural" theme. 9 routes.
- **Research platform** — `frontend/` (research UI), `extension/` (RCT session
  logging), and an RCT harness in the backend: control/treatment groups, real
  vs. sham insights, for testing whether personalisation actually improves
  retention.

Backend is FastAPI + SQLAlchemy, 32 endpoints, SQLite locally / Postgres in
production via Alembic.

### The crown jewel: the zero-LLM brain

**All the intelligence is pure NumPy. No API calls.**

- `agents/material_analyzer.py` — TF-IDF → LSA (SVD) → TextRank → heuristic
  concept typing (`factual|conceptual|procedural` × `foundational|intermediate|advanced`)
- `personalization/` — Ebbinghaus forgetting-curve fits, hierarchical Bayesian
  MCMC for per-technique memory stability, LinUCB contextual bandit, trend
  detection, insight generation
- `personalization/priors.py` — research-derived priors (Dunlosky 2013 ranking)
  so the brain is useful from session zero
- `agents/study_planner.py` — DP/Ebbinghaus scheduler with material-aware
  matching: `score(technique) = material_fit × learner_effectiveness`

Only **three optional** touchpoints use an LLM, all with working free fallbacks:
`question_generator.py` (falls back to local cloze cards),
`material_ocr.py` (photo→text), `performance_optimizer.py` (advice text).

**The product runs completely with no API keys.** That is the moat, the margin
and the privacy story at once. **Protect it. Never move core intelligence
behind an LLM.**

---

## 3. Non-negotiable guardrails

Violating any of these breaks the product:

1. **No LLM in the core pipeline.** Analysis, fingerprint, matching, planning
   stay pure-math and offline.
2. **Preserve the RCT blind.** Control users must never receive personalised
   surfaces (forecast, archetype, real insights, confidence bands). Gate on
   `group === "treatment"` and give control a neutral equivalent so the screen
   isn't obviously emptier.
3. **Never over-claim the science.** Surface uncertainty. At low N say "early
   estimate". Material-type effects are a *modulation* on the strong general
   finding (testing & spacing win broadly). Honest calibration is the brand.
4. **Don't lose users.** Every change must keep or improve identity persistence.
5. **Never enumerate.** Ids are sequential. Any endpoint addressed by `user_id`
   that returns or mutates user data is a hole — this product already shipped
   that bug once (restore-by-ID) and it is now closed. Authenticate with a
   recovery token in the body instead.

---

## 4. What is built (state at `022a29a`)

**182 backend tests + 128 frontend tests green. 3 migrations. tsc + build clean.**
(`npm run lint` does *not* pass — 4 pre-existing errors, see §7.)

### The full loop works
paste (or photo, or sample) → knowledge map → 14-day adaptive plan → study mode
picker → focus/reading screen → graded round → fingerprint → retention checks →
library.

### Recently landed (this arc, 24 commits)
| Area | What |
|---|---|
| **Honest technique logging** | The round logs the technique the user *chose* (Plan ModePicker → `?mode=` → Study → Cards), not a hardcoded `active_recall`. This closed the learning loop — the fingerprint can finally learn what works. |
| **Material-aware matching** | Plans vary technique by text type (vocab→spaced repetition, proofs→interleaving, essays→elaborative interrogation) instead of collapsing to one. |
| **Cold-start priors** | `personalization/priors.py` — Dunlosky-derived per-technique priors feed the planner and the Bayesian model, so day-1 users get differentiated, research-defensible recommendations. |
| **API-free flashcards** | `agents/question_generator_local.py` — cloze cards from the concept graph. The `/questions` endpoint **never 503s** for a missing key. `COGPRINT_MODE=free` forces local even with a key. |
| **Material library** | `GET /users/{id}/materials` + `app/src/pages/Library.tsx` — the returning-user home, with retention rings and due counts. |
| **Observable rebuild** | Fingerprint rebuild failures are logged and stamped (`last_rebuild_status`), surfaced in the UI with a one-tap "Rebuild". No more silent staleness. |
| **RESEARCH.md + backtest** | Every algorithmic choice mapped to its citation, plus `tests/test_science_backtest.py` which seeds synthetic learners from the literature and asserts the pipeline recovers the known ranking. This is the regression test for the *intelligence itself*. |
| **Adaptive re-planning** | Plans resume from today after a gap instead of restarting; optional exam-date horizon. |
| **Recovery tokens** | Replaced enumerable id-based restore. 192-bit token, stored as SHA-256, returned once. `/auth/recover`, `/auth/recover/rotate`. |
| **Alembic + Postgres** | Real migrations, drift test, `psycopg`. Docker runs `alembic upgrade head` before uvicorn. |
| **Magic-link email auth** | Additive to tokens. Unverified addresses never accepted; request endpoint is non-enumerating. Pluggable sender — logs the email when no `RESEND_API_KEY`. |
| **GDPR** | `POST /users/me/export`, `POST /users/me/delete` (requires `confirm: true`). |
| **First-party analytics** | `analytics_events` table, `track_event`, `POST /events`, and `GET /analytics/funnel` with D1/D7 return rates. **This is the instrument the beta exists to read.** |
| **Review reminders** | `POST /admin/send-reminders` — emails users with due reviews. 20h per-user cooldown. Driven by external cron (Render Cron), not self-scheduling. |
| **Onboarding** | "Try a sample" on first run (real pipeline, nothing seeded) + first-round celebration copy. |
| **Spend ceilings** | Daily budgets on OCR and LLM cards, counted from analytics events. Over budget, cards **degrade to cloze** rather than failing. |
| **Prompt-injection boundary** | Material wrapped in `<study_material>` tags; the closing tag is stripped from user input so the delimiter can't be forged. |
| **CI** | `.github/workflows/ci.yml` — pytest, tsc, build, bundle budget, standalone `alembic upgrade head`. No secrets needed. |
| **Concept quality** | Verb-detection heuristic — a noun phrase doesn't span a finite verb. Killed "Chlorophyll Absorbs", "Fixes Carbon", "Bastille Became". |

---

## 5. What is left

### Tier 4 — polish (~10h, nothing blocking) — **this is the next code work**
1. ~~**Frontend tests**~~ — **done** (`11eb3c3`, `022a29a`). Vitest + jsdom +
   React Testing Library, 128 tests. `cd app && npm test`. It found five real
   bugs; see §7. **Not covered:** `Paste.tsx` (510 lines, the front door),
   `Plan.tsx`, `Library.tsx`, `Checks.tsx`, `Study.tsx`, `Verify.tsx` and the
   router in `App.tsx` all still have zero render tests. Paste is the one worth
   doing next — it is the only screen every user must pass through.
2. **i18n Norwegian** (~3h) — extract UI strings, nb/nn + en, browser-locale default. Pass material language through to card generation. Her first beta cohort is Norwegian.
3. **a11y audit** (~2h) — WCAG-AA contrast on the dark theme, ARIA for the SVG fingerprint and icon-only buttons, keyboard nav + visible focus. (`prefers-reduced-motion` is already done.)
4. **Edit a flashcard** (~2h) — currently a bad card can only be flagged, not corrected. Store the correction and prefer it.
5. **PWA install prompt** (~1h) — iOS evicts localStorage for non-installed PWAs after ~7 days of inactivity, which silently loses anonymous users.
6. **Content retention** (~1h) — purge `raw_text` after cards are derived, or after N days.
7. **Perf budget** (~1h) — CI has a bundle budget; a Lighthouse-mobile gate would be the next step.

### Blocked on Katchi (not code)
- **Deploy** — the actual bottleneck. `DEPLOY.md` has the click-path. Needs a Render account, a domain, and ~1 hour of hers.
- Privacy policy + ToS text (the *endpoints* exist).
- Resend account for real email; Sentry DSN. Both optional — the app works without.
- Recruiting 10–20 beta users.

### Open findings — decisions for Katchi, not defects
1. **The blind is still not symmetric.** Treatment gets a memory-forecast card
   and an archetype badge; control has no equivalent for either, so the two
   screens are still distinguishable side by side. The consistent fix is a
   *sham* forecast and archetype — fabricated, deterministic, seeded by user
   id, exactly as the sham insights already work. ~2h. Recommended before any
   participant is recruited. (Deprioritised 2026-08-06: the near-term focus is
   the consumer product, not the trial.)
2. **Two estimators are shown as one claim.** On the treatment fingerprint,
   re-reading reads "26% at 7 days" with "likely 0–10%" underneath. The
   headline is the Ebbinghaus OLS fit (`memory_profiles`); the band is the
   Bayesian posterior (`technique_stability`). They are different estimators,
   and here they disagree enough that the interval excludes the point estimate.
   Whichever is canonical, **both numbers must come from it** — a visible
   interval that does not contain its own point estimate reads as a bug and
   costs exactly the calibration trust the brand is built on.
4. **How much authority does `_CANDIDATES_BY_CONTEXT` deserve?** The scoring
   ceiling is fixed (Monte Carlo study 1 above), but the underlying question is
   not settled: that table extrapolates from Dunlosky's *main effects* to
   technique × material-type *interactions*, which the literature supports far
   less strongly. It currently ships as a strong prior worth a 3× evidence
   bar. If the interaction cannot be validated, the honest position is to drop
   the table and let priors plus measured data decide. Cheap to test once
   there is data: compare predicted retention with and without the material
   term in `evaluation/predictive_baseline.py`.

5. **The loop never explores, and that is now the binding constraint.**
   `_technique_for_concept` is deterministic; the LinUCB bandit has
   exploration but only shapes what is *recommended*, and the ModePicker lets
   the user override freely. The Monte Carlo prices it: at τ=0.6, exploration
   is worth +0.037 retention and 3× the rate of finding the learner's best
   technique — and without it the scoring fix contributes nothing, because the
   planner samples 1 technique of 7 and has nothing to compare. **This is the
   highest-value remaining change to the brain.** It is also open finding 6:
   the same mechanism is what makes any causal claim possible.

6. **Technique is self-selected, so nothing here is causal.** The app offers a
   technique and the learner picks. "Re-reading works for me" and "I re-read
   material I already half-know" are indistinguishable in the data. The only
   fix is assigning the technique on some fraction of sessions — the LinUCB
   bandit has exploration built in, but it only shapes what is *recommended*;
   the ModePicker still lets the user override freely. If personalisation is
   the product, roughly 20% of sessions need to be assigned. Real friction,
   real decision.

### The plan now follows the fingerprint (2026-08-06)
An A/B probe — two learners, same material, opposite measured histories — found
the fingerprint personalising correctly while the plan barely did. Reproduce it
any time; the decisive comparison is whether the two learners' 14-day plans
differ, and whether either differs from a cold-start plan.

What was wrong, and what changed:

| symptom | cause | fix |
|---|---|---|
| A learner measured at 0.90 on re-reading was told it was their best technique, while the plan scheduled it 0/14 days | `_CANDIDATES_BY_CONTEXT` lists re_reading in **no** context, so it was pinned at the material floor 0.45 while ranked techniques scored up to 1.0 — a hard gate no evidence could pass | floor 0.45 → **0.62**, ranks `[1.0, .72, .55]` → **`[1.0, .85, .72]`**. Material now spans 1.6×, measured effectiveness up to 2.3×, so evidence can win |
| A learner with 20 sessions got a plan byte-identical to a brand-new user's | plan collapsed to argmax of a deterministic score | rotate across days among techniques within **85%** of the day's best (`_ROTATION_BAND`) — variety only where the model is indifferent |
| Cold-start "recommended techniques" put mind_maps and re_reading at positions 2–3 | at n=0 every bandit arm ties and `sorted` is stable, so the order was set iteration order; `priors.py` fed the planner but never this field | blend toward the research prior as n→0, and use the prior as final tie-break |
| Fluency illusion could drive technique choice | `avg_retention_7d or avg_retention_24h or avg_immediate_score` — immediate score measures encoding, not forgetting, and flatters exactly the techniques the literature warns about. The `or` chain also treated a genuine 0.0 retention as missing | `_delayed_retention()`: delayed checks only, explicit `is not None` |
| Advice text named "active recall + spaced repetition" regardless of the plan below it | hardcoded string that survived the move to material-aware matching | names the techniques the plan actually contains |

One knob is a deliberate stand-in: `_UNMEASURED_DISCOUNT = 0.9` on techniques
still scored by prior. Widening the floor let an *unmeasured* high-prior
technique beat one the learner had been measured on, which is wrong — a
population average and a personal measurement are different claims. The proper
fix is passing the posterior into the planner instead of a bare float, so
sample size counts; `eff_map` currently cannot tell two sessions from twenty.

### Monte Carlo studies (`evaluation/monte_carlo.py`)
```bash
python -m evaluation.monte_carlo --loop           # study 1, ~1 min
python -m evaluation.monte_carlo --misspecified   # study 2, ~2 min
```

**Study 2 — misspecification — is reassuring.** Generate forgetting as a power
law (Wixted & Ebbesen: forgetting is power-law, not exponential), fit with the
app's exponential anyway, matched at t=7:

| world | CI coverage | rank agreement | picks best | bias |
|---|---|---|---|---|
| exponential (control) | 91% | 0.95 | 80% | −0.009 |
| power law | 83% | 0.95 | 77% | −0.026 |

The numbers go slightly biased and the intervals slightly overconfident, but
**the ordering is untouched** — and ordering is what the recommendation
consumes. The Bayesian layer is robust to the curve being wrong. Separately,
the 95% credible interval covers at 92–96% across 2–16 sessions, so the
interval itself is honest; the "26% · likely 0–10%" contradiction is purely
the two-estimator problem in open finding 2, not a broken posterior.

**Study 1 — the closed loop — is not reassuring.** 150 learners × 60 sessions,
scored on true 7-day retention achieved:

| τ | ORACLE | DUNLOSKY | PLANNER | EXPLORER |
|---|---|---|---|---|
| 0.0 | 0.843 | 0.843 | **0.719** | 0.710 |
| 0.3 | 0.843 | 0.834 | **0.715** | 0.715 |
| 0.6 | 0.867 | 0.812 | **0.742** | 0.739 |

The planner tries **1.2–1.4 of 7 techniques** and lands on the learner's truly
best one 0–13% of the time. It loses to always-do-practice-testing. Random
exploration does not rescue it (EXPLORER samples 6 techniques and still
loses), which locates the fault precisely: not too little data, but a scoring
rule that cannot act on the data it has.

**Fixed since, with an honest result.** Scoring moved to log space —
`log(S) + β·log(material_weight)` — with β derived from a stated criterion
rather than tuned: a floor-weight technique overturns a rank-1 material fit
exactly when the learner's measured stability is 3× higher, giving
β = log 3 / −log(floor) ≈ 2.3. Re-running the loop after that change:

| τ | PLANNER before | PLANNER after | EXPLORER before | EXPLORER after |
|---|---|---|---|---|
| 0.0 | 0.719 | 0.720 | 0.710 | 0.713 |
| 0.3 | 0.715 | 0.710 | 0.715 | **0.723** |
| 0.6 | 0.742 | 0.712 | 0.739 | **0.749** |

PLANNER did not improve. EXPLORER now *does* — it rises with τ (0.713 → 0.723
→ 0.749) and reaches the best technique 5% → 15% → 30% of the time, where
before it was flat. That is the change working exactly as designed: evidence
is now actionable. PLANNER cannot benefit because it still samples **1.0–1.2
of 7 techniques** — it has no evidence to act on.

So the two defects are separable, and only one is fixed:
- *scoring could not act on evidence* — fixed, and EXPLORER is the proof;
- *the loop never gathers evidence* — *not* fixed. This is open finding 5,
  and the Monte Carlo now prices it: at τ=0.6 exploration is worth **+0.037
  retention and 3× the hit rate**. Without it the scoring fix is inert.

**The cause of the ceiling, and it is assumption-free arithmetic.**
`score = material_weight × effectiveness`, where effectiveness is 7-day
retention — bounded above by 1.0. A rank-1 technique scores `1.0 × a`; a
floor technique scores `0.62 × e ≤ 0.62`. So once the ranked technique
measures above 0.62, *no possible evidence* can overturn it. Demonstrated: a
learner whose practice testing is genuinely 3.3× more durable (S=40d vs 12d)
is still told to use active recall. Widening the floor from 0.45 to 0.62
raised the ceiling; it did not remove it.

Scoring on **stability** (unbounded) fixes it, which is what now ships. Two
knobs carry the judgement, both stated as rules rather than magic numbers:
`_EVIDENCE_OVERRIDE_RATIO = 3.0` (how much measured advantage overturns the
material table) and `_UNMEASURED_DISCOUNT = 0.6` (an untried technique must be
~1.7× more durable *in the literature* than what you have measured before the
plan switches you to it). Change those two if the material table's authority
should change; nothing else needs touching.

**New consequence, not yet addressed:** on the stability scale a confident
learner's best technique now sits far above the rotation margin, so the band
collapses to one and the 14-day plan goes monotonous again for exactly the
users who have earned personalisation. That is the rule behaving correctly —
there is no indifference to exploit — so the fix is *not* a wider band, which
would just resurrect the ceiling. Varied practice has its own evidence base,
so the honest fix is an explicit interleaving term in the objective rather
than variety smuggled in through an indifference threshold.

Caveat that limits all of study 1: the simulation sets true stability from the
*global* prior plus a person term, i.e. it assumes technique × material-type
interactions do not exist. If they do exist as `_CANDIDATES_BY_CONTEXT`
assumes, the planner's material-first choice is less wrong than this table
suggests. The ceiling finding does not depend on that assumption; the size of
the retention gap does.

### The validation harness (`evaluation/predictive_baseline.py`)
Answers "does personalisation actually predict better?" offline, from the
retention checks the app already collects — no RCT, no control arm, no extra
participants. Three predictors on identical held-out points:

| | S comes from | claims |
|---|---|---|
| `PRIOR` | research prior per technique | nothing personal |
| `PERSON` | `prior[technique] × m_user` | you forget slower; technique ranking is everyone's |
| `PERSONAL` | posterior per (person, technique) | **which technique suits you is personal** |

`PERSONAL` beating `PERSON` is the whole product thesis. `PERSONAL` beating
`PRIOR` is not — that can come entirely from the person level and be misread.

```bash
python -m evaluation.predictive_baseline --db        # once there are users
python -m evaluation.predictive_baseline --simulate  # power table, ~3.5 min
```

**Power, from the simulation** (how often `PERSONAL` beat `PERSON`; τ is the
between-person spread in per-technique stability, log units):

| τ | 10u × 3s | 10u × 6s | 10u × 12s | 20u × 12s |
|---|---|---|---|---|
| 0.0 | 16% | 3% | 2% | 0% |
| 0.2 | 58% | 24% | 70% | 69% |
| 0.4 | 93% | 90% | **100%** | 100% |
| 0.6 | 100% | 100% | 100% | 100% |

Read: **10 users × 12 sessions per technique settles a moderate-or-larger
effect.** A small effect (τ=0.2) is not detectable at any scale she can reach —
and is probably too small to build a differentiator on anyway. The τ=0 row is
the false-positive check, not a result; it must stay low.

Two honest limits: the simulation generates data under the model's own
assumptions, so real-world power is *lower* than this table, and technique is
self-selected in the app, so a win is predictive association, not a causal
technique effect. The fix for the second is assigning technique on some
fraction of sessions.

**The harness is tested (`tests/test_predictive_baseline.py`), because a broken
evaluator is worse than none.** Its first version declared personalisation a
100% winner on data generated with the effect set to exactly zero — its
baseline could not represent population-level technique differences either, so
`PERSONAL` beat it for a reason unrelated to personalisation. That is why
`PERSON` fits a *multiplier on the per-technique prior*, not one pooled S.

### Deliberate future work, with reasoning recorded
- **Web Push** — chosen against for now. Real push needs the Vite PWA plugin moved from `generateSW` to `injectManifest` so the service worker can own `push`/`notificationclick`. Worth doing against a real device, not blind. iOS only delivers push to home-screen-installed PWAs. Email reminders reach the same goal today. (Noted in `DEPLOY.md`.)
- **Native app** — she already has a PWA (installable, standalone, all icons). The gap is iOS push and app-store presence. **Capacitor wraps the existing React app** — no rewrite. The cheap path when the time comes.
- **Capture extension** — the existing `extension/` is *research tooling* (session logging), explicitly not this. A "capture what I'm reading" extension would attack the product's real friction (paste requires context-switching), and is the more interesting of the two future surfaces — but not before validation.

---

## 6. Conventions that made this code good — keep them

These are not style preferences; they are why the codebase reads as deliberate.

**Comments explain *why*, and state limitations rather than hiding them.**
Example: the rate limiter documents that it is per-process and won't survive
multiple workers, and that `X-Forwarded-For` is only trusted behind
`TRUST_PROXY_HEADER`. Say the uncomfortable thing in the code.

**Commit messages explain the reasoning and name what is NOT covered.**
Look at `git log` — they read as short design notes. Include the tradeoff you
made and why the alternative was rejected. End with:
`Co-Authored-By: Claude <model> <noreply@anthropic.com>`

**Tests test the attack, not the happy path.** `tests/test_recovery.py` contains
a test that literally performs the old enumeration attack and asserts it fails.
`tests/test_analytics.py` pins the D1/D7 arithmetic against a hand-built
timeline where the right answer is exactly 0.5. Write the test that would have
caught the bug.

**Match the file you're editing.** Comment density, naming, import style. The
backend uses `List`/`Optional` from `typing` in `schemas/`, modern generics
elsewhere. Follow what's there.

**Frontend stays inside the design system.** Tokens in `app/tailwind.config.js`:
`ink-950..400`, `neural` (DEFAULT/dim/glow/muted). Rounded-2xl cards,
`neural-border`, `animate-fade-up`, `focus-visible` rings, 8pt spacing. See
`app/src/pages/Library.tsx` for the target quality bar. **No colours outside the
palette.**

**Verify before claiming.** Run tsc, build, pytest. For anything observable,
check it in the browser. Two real bugs in this arc were found by smoke-testing,
**not** by the 148-test suite (see §7).

---

## 7. Hard-won lessons — do not relearn these

### Frontend tests: how they are set up, and what they caught
`app/vitest.config.ts` is deliberately **separate** from `vite.config.ts` — the
PWA plugin has no role in a jsdom run. Two settings there are load-bearing:

- **`env: { TZ: "Europe/Oslo" }`.** The streak is computed in local calendar
  days, so under CI's default UTC the daylight-saving cases cannot fail no
  matter what the code does. One test asserts the pin took effect.
- **Component tests need `vi.useFakeTimers({ shouldAdvanceTime: true })`.**
  Testing Library's `findBy*`/`waitFor` poll on real timers; under plain fake
  timers every async query hangs until the test times out.

Use `blindedFingerprint()` from `src/test/fixtures.ts` for any control-arm
test. Using the measured fixture asserts against a payload the server will
never send — that is exactly how the gating bug below stayed hidden.

Five real bugs came out of writing these, none of which the 148 green backend
tests could see:
1. **The RCT blind was broken in production.** `fingerprint_builder` pinned
   control users to `confidence=LOW` forever, and the client gates its whole
   fingerprint screen on `confidence !== "low"` — so control saw "your
   fingerprint is growing" permanently while treatment saw a full screen.
   `buildShamView` still *ran* — its session count and confidence reached the
   header — but its technique bars, memory grid, insights and top technique
   never rendered, because every one of those sits inside the
   `confidence !== "low"` branch. Confidence is now derived from the session
   count for both arms (it discloses nothing measured; the count is already
   sent). **This is the one to remember: the sham screen is only reachable
   because of that one line.**
   Note it is served from cache: `GET /fingerprint` returns the stored
   `profile_json`, so an existing control user keeps the old confidence until
   their next session triggers a rebuild.
2. `retentionBand()` read `technique_stability` off the raw API response rather
   than the sham view — a leak by construction. Now gated on treatment.
3. `store.ts` spread a module-level `EMPTY`, so every `getState()` handed out
   the *same* `recents` array; one push poisoned the default session-wide.
4. `streak.ts` tested "is b the next day" with an exact 86,400,000 ms diff
   between local midnights — a DST day is 23 or 25 hours, so the longest streak
   reset every March and October for every Norwegian user.
5. `currentHour()` bucketed 00:00–04:59 as "morning". The client is the only
   place `time_of_day` is decided, so 2am sessions were dragging night owls'
   `best_time_of_day` the wrong way.

**`npm run lint` fails with 4 pre-existing errors** (`react-hooks/purity` and
`set-state-in-effect`, in `Grow.tsx` ×3 and `Verify.tsx` ×1). None come from the
test arc, and CI does not run lint — which is why they accumulated unnoticed.
Either fix them or add lint to CI with those rules downgraded; leaving a script
that always fails just trains everyone to skip it.

Also: **`npx tsc --noEmit` in `app/` was a no-op.** `tsconfig.json` is a
solution file (`files: []` + references), so without `-b` it resolves zero
inputs and exits 0. CI's type check was checking nothing; types were only ever
verified as a side effect of `npm run build`. Now `npx tsc -b`.

### The test suite is not sufficient
Two genuine bugs got through green tests:
1. **`init_db` stamped a pre-Alembic database at `head`**, asserting a currency
   it didn't have — so `git pull` + run server crashed at the first query. The
   fix: stamp the *baseline revision* (not `head`, which lies; not `base`, which
   tries to re-create existing tables). Now covered by a test.
2. **Sentry probes for optional libraries by name** and one probe hits this
   project's own top-level `agents` package (it expects OpenAI's), logging an
   AttributeError every boot. Fixed with `auto_enabling_integrations=False`.

**Always smoke-test observable changes against a running app.**

### Environment traps (Windows)
- `mktemp -d` in Git Bash returns a POSIX path (`/tmp/...`) that **SQLite cannot
  open**. Use the scratchpad directory with a `C:/...` style path instead.
- Killing a process on a port: `pkill -f uvicorn` does **not** work. Use
  PowerShell `Get-NetTCPConnection -LocalPort 8000 | Stop-Process -Force`.
- The **browser screenshot tool times out** consistently in this environment.
  Use `read_page` / `get_page_text` — they work fine and are better for
  verifying text anyway.
- The full pytest suite takes **~2 minutes**. Bump the Bash timeout to 300000 or
  it will be cut off. Don't chain it after a slow npm build in one call.

### Code traps
- Endpoints import some things **at call time** (`from agents.question_generator
  import generate_flashcards` inside the function). To monkeypatch, patch the
  **source module** (`qg.generate_flashcards`), not `main.generate_flashcards`.
- Pydantic `model_validate(obj)` fails if a subclass adds a required field the
  ORM object lacks. Construct explicitly:
  `Child(**Parent.model_validate(obj).model_dump(), extra=value)`.
- `migrations/env.py` accepts a live connection via `config.attributes["connection"]`
  and resolves the URL from the app's `DATABASE_URL` unless the caller sets one.
  `alembic.ini` ships with `sqlalchemy.url` **blank on purpose**.
- **`email_validator` is not installed**, so pydantic's `EmailStr` will fail.
  Email is normalised and sanity-checked by hand instead — deliberately, since
  the magic link is the real validator.
- **Any new column or table needs an Alembic migration.**
  `tests/test_migrations.py` fails the build on drift, by design.

### Decisions with reasoning — don't silently undo these
- **SHA-256, not bcrypt, for tokens.** Slow hashes exist to resist brute force
  on low-entropy human passwords. These are 192 bits of CSPRNG output; there is
  nothing to brute-force, and a fast hash keeps lookup a single indexed query.
- **First-party analytics, not PostHog/Plausible.** The events *are* the
  research data, and shipping them to a third party contradicts the privacy
  posture that is part of the moat.
- **Materials are NOT deleted on account erasure.** A `Material` row is shared
  (the shared-deck feature), so cascading would destroy another user's history.
  Documented in the endpoint docstring as a deliberate boundary.
- **Over budget, card generation degrades to cloze rather than failing.**
  Denying someone a study round over a spend limit they can't see is the wrong
  trade when the free path is right there.
- **The verb filter is precision-biased.** It will occasionally drop a real
  concept. A missing concept costs a card; a nonsense one costs trust.

---

## 8. The strategic picture (so you can advise, not just build)

**Honest completion: ~55%.** The brain is ~90% done and proven. Production
readiness improved a lot this arc. Legal, business and **validation are ~0%**.

**The one question that decides everything:** does personalisation actually
help? The literature strongly supports that *technique* matters (testing and
spacing win broadly). It does **not** clearly establish that *per-person*
technique personalisation beats a good generic plan. If people don't vary
meaningfully in which technique works for them, the core differentiator is
worth much less.

**That is testable cheaply, and it is the recommended next move**, ahead of any
new feature:
- A between-subjects RCT needs ~128 users for a medium effect — she won't get
  that, and she knows it.
- A **within-subject design** (each user compared against themselves across
  techniques, 10–20 users × 20+ sessions, mixed-effects model) can answer
  whether the *between-person variance* in technique effect is real. That's the
  actual crux, and it mirrors what the product already does.
- Public spaced-repetition datasets (Duolingo half-life regression, Anki/FSRS
  review logs) can validate the **forgetting-curve half** but not the
  technique-comparison half — they have no technique labels. Worth saying if
  she asks about training data. (She should verify licensing herself.)

**Also worth knowing:** the strongest commercial wedge may be institutional
rather than consumer. "$0 runtime, offline, self-hostable, no data leaves your
server" is far more compelling to a school than to a student, and it needs less
marketing muscle than a consumer subscription — which matters given her time.

---

## 9. Reference

**Key docs:** `HANDOVER.md` (project history + work log), `RESEARCH.md`
(citations for every algorithm), `COGPRINT_MEGAPROMPT.md` (full strategy),
`COGPRINT_PROBLEMS.md` + `_2.md` (problem inventories — partly stale now, many
items are done), `DEPLOY.md` (click-path).

**Run it:**
```bash
python -m uvicorn main:app --port 8000     # backend (repo root)
cd app && npm run dev                       # app on :5173
python -m pytest -q                         # 182 tests, ~2.5 min
python -m pytest -q -m "not slow"           # skip the MCMC calibration tests
cd app && npm test                          # 128 frontend tests, ~8s
cd app && npx tsc -b && npm run build       # NOT `tsc --noEmit` — see §7
```

**Env vars, all optional:** `ANTHROPIC_API_KEY` (better cards + OCR),
`RESEND_API_KEY` + `EMAIL_FROM` + `FRONTEND_URL` (real email),
`COGPRINT_API_KEY` (guards research endpoints — **set before public traffic**),
`SENTRY_DSN`, `DATABASE_URL`, `COGPRINT_MODE=free|hybrid`,
`COGPRINT_OCR_DAILY_LIMIT`, `COGPRINT_LLM_DAILY_LIMIT`, `TRUST_PROXY_HEADER`.

**Do not touch:** `batteryswap/`, `eeg_project/`, `event_camera/`, `meso_pong/`
in the repo root — unrelated projects sharing the folder, untracked. Not yours
to move or delete.

---

## 10. If you do one thing

Frontend tests are done. The next-most-valuable code work is **finishing the
blind** (§5, open finding 1): a sham forecast and archetype, so the two arms'
screens are actually indistinguishable. Everything else in Tier 4 is polish;
that one decides whether the study can be run at all.

But the honest answer has not changed: **deploy is still the thing standing
between her and knowing whether any of this is true.** No amount of test
coverage moves validation off 0%.
