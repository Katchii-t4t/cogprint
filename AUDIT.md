# CogPrint — Full Codebase Audit & Commercialisation Roadmap

> **Audience: an AI agent or engineer picking up this codebase cold.**
> Every finding is written to be actionable without re-deriving the analysis:
> location, observed evidence, impact, concrete fix, and a testable acceptance
> criterion. Findings are ordered by severity, not by area.
>
> Audited at commit `8e51a9a`, 2026-08-09. State at audit time: 186 backend
> tests + 128 frontend tests green, `tsc -b` and `vite build` clean,
> `npm run lint` **failing** (4 pre-existing errors).
>
> Claims marked **VERIFIED** were reproduced against a running instance during
> this audit. Claims marked **READ** come from source inspection only.

---

## 0. Executive summary

The intelligence layer is genuinely good and now measurably so: the Bayesian
posterior is calibrated (92–96% coverage against a nominal 95%), it is robust
to the forgetting curve being the wrong shape (ranking survives power-law
misspecification), and after this session's changes the planner acts on
personal evidence instead of overruling it.

**The product is not commercialisable today, and the reason is not the
science.** It is that every per-user endpoint is anonymously readable and
writable by counting integers. That is one blocker, it is narrow, and it is
fixable in roughly a day.

Ranked by what actually stands between here and charging money:

| # | Blocker | Effort |
|---|---|---|
| 1 | **SEC-001** — anonymous read/write of any user's data by id | 1 day |
| 2 | **SEC-004** — unbounded input sizes (DoS + unbounded cost) | 2 h |
| 3 | **LEGAL-001** — no privacy policy / ToS / DPA, while processing health-adjacent data | Katchi, not code |
| 4 | **OPS-001** — never deployed; zero real users; validation 0% | 1 h + recruiting |
| 5 | **SEC-002/003** — API key optional by default, rate limiter per-process | 3 h |

Everything else is quality, polish, or future work.

---

## 1. Severity definitions

- **BLOCKER** — must be fixed before any real user touches the product.
- **HIGH** — must be fixed before charging money or scaling past a pilot.
- **MEDIUM** — degrades quality, trust, or velocity; fix in the next arc.
- **LOW** — polish. Batch these.

---

## 2. Security & privacy

### SEC-001 — Every per-user endpoint is anonymously readable and writable
- **Severity**: BLOCKER
- **Area**: security / privacy / GDPR
- **Location**: `main.py` — endpoints at lines 579, 594, 636, 682, 716, 988, 1138, 1156, 1226, 1326, 1427
- **Status**: **VERIFIED** against a running instance

User ids are sequential integers. `GET /users/{user_id}` was correctly placed
behind `require_api_key` with a comment explaining exactly this risk. **The
other eleven user-addressed endpoints were not.** The `SESSION_HANDOFF.md`
claim that the enumeration hole "is now closed" is true only of
`POST /auth/recover`.

Observed, with no API key and no token, against a freshly created user:

```
GET   /users/18/materials            200  [{"title": "Oncology exam notes - relapse risk", ...}]
GET   /users/18/sessions             200  [{"technique": "re_reading", "quiz_score": 1.0, ...}]
GET   /users/18/fingerprint          200  full profile
GET   /users/18/review-suggestions   200
GET   /users/18/pending-checks       200
POST  /users/18/study-plan           200
POST  /users/18/share-code           200  {"share_code": "YEUBYS"}
POST  /users/18/fingerprint/rebuild  200  (also unbounded CPU)
PATCH /users/18/post-test            200  post_test_score overwritten
POST  /sessions {"user_id": 18, ...}  201  session injected into another user's fingerprint
```

- **Impact**:
  1. **Privacy breach.** Material titles reveal what a named-by-id person is
     studying. The probe above used a plausible medical title and read it back
     anonymously — that is a health-adjacent inference about an identifiable
     individual under GDPR Art. 9 reasoning. Not a theoretical risk for a
     product whose first cohort is medical students.
  2. **Research integrity.** `PATCH /post-test` and `POST /sessions` let anyone
     corrupt the RCT's outcome variable and poison any user's fingerprint.
  3. **Compute DoS.** `POST /fingerprint/rebuild` runs MCMC synchronously, is
     unauthenticated, and is not rate limited.
- **Fix**: introduce one dependency, `require_user_token`, that resolves the
  caller from a recovery token (SHA-256 lookup, already implemented for
  `/auth/recover`) supplied in an `Authorization: Bearer` header, and apply it
  to every route addressed by `user_id`. Reject any request whose resolved
  user id does not match the path/body id. Keep `require_api_key` for the
  researcher routes. The client already persists `recoveryKey` in
  `app/src/store.ts`, so the frontend change is to attach one header in
  `app/src/api.ts:req`.
- **Done when**: a test in `tests/test_authz.py` creates users A and B, and
  asserts that every route in the list above returns 401/403 when called with
  B's token against A's id, and 200 with A's own token. Model it on the
  existing enumeration-attack test in `tests/test_recovery.py`.

### SEC-002 — Authentication is opt-in and silently disabled by default
- **Severity**: HIGH
- **Location**: `auth.py:39-55`
- **Status**: READ

`require_api_key` returns early when `COGPRINT_API_KEY` is unset. A deploy that
forgets the variable exposes `/users/all`, `/export/study-data`,
`/analytics/funnel` and `/admin/send-reminders` to the internet, with no
warning and a green `/health`.

- **Fix**: fail closed in production. Read an explicit `COGPRINT_ENV`
  (`dev|prod`); in `prod`, refuse to start when `COGPRINT_API_KEY` is unset.
  Keep the zero-config behaviour for `dev` only.
- **Done when**: a test asserts the app raises at startup with
  `COGPRINT_ENV=prod` and no key, and starts normally in `dev`.

### SEC-003 — Rate limiting is per-process and collapses on scale-out
- **Severity**: HIGH
- **Location**: `auth.py:73-122` (documented as a known limitation)
- **Status**: READ

The limiter's state is an in-process dict. Render's starter plan is a single
instance today, so this is currently correct — but the first time the service
scales to two instances or more than one uvicorn worker, every budget silently
multiplies, and the OCR spend ceiling multiplies with it.

- **Fix**: move buckets behind a small interface with two implementations
  (in-memory, Redis). Select by `REDIS_URL` presence. Alternatively enforce at
  the edge (Cloudflare / Render), but then the OCR *spend* limit still needs an
  application-level counter because it is a cost control, not an abuse control.
- **Done when**: `WEB_CONCURRENCY=2` no longer doubles the observed allowance in
  an integration test.

### SEC-004 — No size limits on any user-supplied input
- **Severity**: BLOCKER (cost) / HIGH (availability)
- **Location**: `schemas/session.py:43-51` (`MaterialCreate`, `OcrRequest`), `main.py:1462` (`ClientEvent`)
- **Status**: VERIFIED by inspection of the schemas

`MaterialCreate.raw_text`, `MaterialCreate.title`, `OcrRequest.image_base64` and
`ClientEvent.properties` are unbounded. `POST /materials/analyze` is
unauthenticated and feeds `raw_text` straight into TF-IDF → SVD → TextRank,
whose cost grows superlinearly in sentence count, then stores the text forever.

- **Impact**: a single unauthenticated request can pin a CPU and grow the
  database without limit. On a metered Postgres plan that is a direct bill.
- **Fix**: `raw_text: str = Field(min_length=1, max_length=200_000)`,
  `title: str = Field(min_length=1, max_length=200)`,
  `image_base64: str = Field(max_length=8_000_000)` (~6 MB decoded),
  and cap `properties` by serialising and rejecting above ~4 KB. Add a
  `Content-Length` guard in middleware as a second layer.
- **Done when**: a test posts oversized payloads to each endpoint and asserts
  422, and a test asserts a 200 for a realistically long chapter (~50k chars).

### SEC-005 — `POST /events` accepts arbitrary `user_id` and unbounded properties
- **Severity**: MEDIUM
- **Location**: `main.py:1468`
- **Status**: READ

Analytics is the instrument the beta exists to read (`SESSION_HANDOFF.md` §4).
Anyone can write events attributed to any user, so D1/D7 retention — the number
that will decide whether the product is working — is trivially forgeable.

- **Fix**: derive `user_id` from the auth token introduced in SEC-001; ignore
  any client-supplied value. Rate limit per client.
- **Done when**: an event posted with a mismatched `user_id` is stored against
  the authenticated user, or rejected.

### SEC-006 — Share codes are mintable for any user and never expire
- **Severity**: MEDIUM
- **Location**: `main.py:1427`, `database.py:111`
- **Status**: VERIFIED (minted a code for an arbitrary id anonymously)

`POST /users/{user_id}/share-code` is unauthenticated, so an attacker can mint
and then read a stranger's buddy forecast. The code has no expiry and no
revocation.

- **Fix**: covered by SEC-001 for minting. Separately add `expires_at` and a
  revoke endpoint. Note `share_code` is `String(12)` — confirm the generator's
  entropy is at least 48 bits and drawn from `secrets`.
- **Done when**: codes expire, can be revoked, and only the owner can mint.

### SEC-007 — CORS defaults to localhost but `allow_credentials=True` with `allow_methods=["*"]`
- **Severity**: LOW (currently), MEDIUM (once cookies are ever used)
- **Location**: `main.py:119-132`
- **Status**: READ

Safe today because auth is header-based, not cookie-based. It becomes a real
CSRF surface the moment a cookie is introduced. `CORS_ORIGINS` is `sync: false`
in `render.yaml`, so a deploy that forgets it falls back to localhost and the
frontend breaks loudly — which is the right failure direction.

- **Fix**: set `allow_credentials=False` while auth is header-based, and add a
  comment stating the coupling.

### SEC-008 — Docker image runs as root
- **Severity**: MEDIUM
- **Location**: `Dockerfile`
- **Status**: READ

- **Fix**: add a non-root user, `USER app`, and `--chown` on the copy. Add
  `HEALTHCHECK`. Pin the base image by digest.

### SEC-009 — No dependency pinning or lockfile on the Python side
- **Severity**: HIGH
- **Location**: `requirements.txt`
- **Status**: READ

Everything is `>=`. Two builds a week apart can install different code, and a
compromised upstream release lands automatically in production.

- **Fix**: `pip-compile` (or `uv pip compile`) to a hash-pinned
  `requirements.lock`, install from it in the Dockerfile, and keep
  `requirements.in` for humans. Add Dependabot or Renovate.
- **Done when**: the Docker build installs from a hash-pinned file and CI
  verifies the lock is current.

### SEC-010 — 5 high-severity npm advisories, unaddressed
- **Severity**: MEDIUM
- **Location**: `app/package.json`
- **Status**: VERIFIED (`npm audit`)

`brace-expansion`, `fast-uri`, `postcss` (path traversal via
`sourceMappingURL`), and `react-router` (RSC-mode CSRF bypass, affects
7.12.0–8.2.0; the app is on 7.18.0). Most are build-time only, but the
react-router one is runtime.

- **Fix**: `npm audit fix`, then re-run `tsc -b`, `npm test`, `npm run build`.
  Evaluate the react-router major bump separately.
- **Done when**: `npm audit --audit-level=high` is clean and CI enforces it.

---

## 3. Correctness

### COR-001 — `_build_general_advice` still hardcodes claims elsewhere in the string
- **Severity**: MEDIUM
- **Location**: `agents/study_planner.py:_build_general_advice`
- **Status**: READ

The "evidence-based defaults" phrase was fixed this session to name the
techniques actually used, but the surrounding sentences ("Research favours
spaced repetition for this kind of content") are still generated independently
of the plan. Same class of defect: two surfaces, two answers.

- **Fix**: derive every claim in the advice paragraph from the generated plan
  and the fingerprint, or delete the claim.
- **Done when**: a test asserts no technique is named in the advice that does
  not appear in `plan.days`.

### COR-002 — Two estimators presented as one claim on the fingerprint screen
- **Severity**: HIGH (trust)
- **Location**: `app/src/pages/Grow.tsx:retentionBand` + the retention grid
- **Status**: VERIFIED in the browser — observed "26% at 7 days · likely 0–10%"

The headline percentage comes from the Ebbinghaus OLS fit (`memory_profiles`);
the interval comes from the Bayesian posterior (`technique_stability`). They
are different estimators and can disagree enough that the interval excludes
its own point estimate. The posterior itself is **not** at fault — measured
coverage is 92–96% against a nominal 95%.

- **Fix**: choose one estimator for both numbers. Recommendation: the Bayesian
  posterior (`posterior_median_days` → `R(7)`), because it is
  population-informed, shrinks correctly at low N, and already carries the
  interval. Then delete the OLS path from the UI, or keep it only as an input
  to the posterior.
- **Done when**: a property test asserts `lo <= point <= hi` for every rendered
  retention card across a large fixture sweep.

### COR-003 — `eff_map` carries point estimates with no sample size
- **Severity**: MEDIUM
- **Location**: `agents/study_planner.py:_technique_effectiveness_map`, `_UNMEASURED_DISCOUNT`
- **Status**: READ (documented in-code as a limitation)

The planner cannot distinguish a retention measured over two sessions from one
measured over twenty. `_UNMEASURED_DISCOUNT = 0.6` is a flat stand-in for
proper uncertainty weighting.

- **Fix**: pass `BayesianStabilityStats` into the planner instead of a float,
  and weight by posterior width (or sample the posterior — Thompson sampling
  would also subsume the optimism bonus added this session).
- **Done when**: `evaluation/monte_carlo.py --loop` shows equal or better
  retention with fewer wasted exploration sessions.

### COR-004 — Fingerprint rebuild is non-deterministic
- **Severity**: LOW
- **Location**: `personalization/hierarchical_memory.py:_run_mcmc` (`default_rng()` unseeded)
- **Status**: READ; `tests/test_pipeline.py` deliberately asserts only counts

Two rebuilds on identical data give different numbers. Users who tap "Rebuild"
see values move for no reason.

- **Fix**: seed the chain deterministically from `user_id` (and a schema
  version), so results are reproducible per user but not correlated across
  users. Document that this makes the posterior a deterministic function of
  the data, which is what a user expects from "your" number.
- **Done when**: a test asserts two consecutive rebuilds produce identical
  `technique_stability`.

### COR-005 — `@app.on_event("startup")` is deprecated
- **Severity**: LOW
- **Location**: `main.py:135`
- **Fix**: migrate to the `lifespan` context manager.

### COR-006 — 4 lint errors, and lint is not in CI
- **Severity**: MEDIUM (velocity)
- **Location**: `app/src/pages/Grow.tsx` ×3, `app/src/pages/Verify.tsx` ×1
- **Status**: VERIFIED (`npm run lint` exits 1)

`react-hooks/purity` and `set-state-in-effect`. At least one
(`setStreak(getStreak())` reading localStorage on mount) is arguably a false
positive deserving a rule exception rather than a refactor. A script that
always fails trains everyone to skip it.

- **Fix**: fix or explicitly exempt each, then add `npm run lint` to CI.
- **Done when**: `npm run lint` exits 0 and CI runs it.

---

## 4. Science & product logic

### SCI-001 — `_CANDIDATES_BY_CONTEXT` is the most expensive assumption in the brain and the weakest-evidenced
- **Severity**: HIGH (product value)
- **Location**: `agents/study_planner.py:_CANDIDATES_BY_CONTEXT`, `_BETA`
- **Status**: VERIFIED by simulation

The table extrapolates from Dunlosky's *main effects* to technique ×
material-type *interactions*, which the literature supports far less strongly.
Closed-loop Monte Carlo, 120 learners × 60 sessions, mean true 7-day retention
achieved and share of later sessions on the learner's genuinely best technique:

| τ | with table | with β=0 | DUNLOSKY | ORACLE |
|---|---|---|---|---|
| 0.0 | 0.728 (4%) | **0.827 (85%)** | 0.843 | 0.843 |
| 0.3 | 0.755 (22%) | **0.833 (80%)** | 0.835 | 0.845 |
| 0.6 | 0.798 (37%) | **0.854 (82%)** | 0.814 | 0.870 |

At τ=0.6, personalisation beats generic advice only with the table off.

- **Caveat that must travel with this table**: the simulation *builds in* that
  the interaction does not exist. This measures what the table costs **if** it
  is wrong, not that it is wrong.
- **Fix**: reduce `_BETA` so the table is a tie-breaker rather than a gate, and
  settle it empirically once there is data —
  `evaluation/predictive_baseline.py` can compare held-out prediction with and
  without the material term.
- **Decision owner**: Katchi. This is a scientific position, not a constant.

### SCI-002 — Technique is self-selected, so no claim here is causal
- **Severity**: HIGH (validity)
- **Location**: product design; `app/src/pages/Plan.tsx` ModePicker
- **Status**: READ

"Re-reading works for me" and "I re-read material I already half-know" are
indistinguishable in the collected data. The LinUCB bandit has exploration but
only shapes what is *recommended*; the user still overrides freely.

- **Fix**: assign the technique on a fraction of sessions (~20%), labelled
  honestly to the user ("today's session is testing something for you"). This
  is the only mechanism that makes a causal claim possible.
- **Done when**: assigned sessions are flagged in `study_sessions` and
  `predictive_baseline.py` can filter to them.

### SCI-003 — Validation is 0%
- **Severity**: BLOCKER (for the *claim*, not the code)
- **Status**: READ

No real user has ever used the product. The instrument is ready:
`evaluation/predictive_baseline.py` answers whether per-technique
personalisation predicts better, and the power table says **10 users × 12
sessions per technique** settles a moderate-or-larger effect (τ ≥ 0.4). A small
effect (τ = 0.2) is undetectable at any reachable scale.

- **Fix**: deploy, recruit 10 committed users, run a semester.

### SCI-004 — The RCT blind is asymmetric
- **Severity**: MEDIUM (deprioritised by Katchi, 2026-08-06)
- **Location**: `app/src/pages/Grow.tsx`
- **Status**: VERIFIED in the browser

Treatment gets a forecast card and archetype badge; control has no equivalent.
The two screens remain distinguishable side by side even after this session's
confidence fix.

- **Fix**: sham forecast and sham archetype, deterministic and seeded by user
  id, exactly as the sham insights already work.

### SCI-005 — Blinded payload names the arm
- **Severity**: LOW
- **Location**: `personalization/fingerprint_builder.py` control branch
- **Status**: READ

`data_gaps: ["Personalisation not enabled for this study group."]` is shipped to
the client. Nothing renders it (pinned by a test), but it is in the network tab.

- **Fix**: drop the string, or replace it with a neutral one.

---

## 5. Frontend

### FE-001 — Zero render tests on the front door and four other routes
- **Severity**: MEDIUM
- **Location**: `app/src/pages/Paste.tsx` (510 lines), `Plan.tsx`, `Library.tsx`, `Checks.tsx`, `Study.tsx`, `Verify.tsx`, `App.tsx`
- **Fix**: `Paste.tsx` first — every user passes through it. Cover: paste →
  analyse → navigate, the sample-material path, the OCR path, the error path,
  and the recovery-key save prompt.

### FE-002 — `Grow.tsx` is 905 lines with ~12 components in one file
- **Severity**: MEDIUM (maintainability)
- **Fix**: extract `ForecastCard`, `ArchetypeBadge`, `StreakBadge`,
  `BossSection`, `SaveProgress`, `RebuildBanner`, `BuddySection` into
  `app/src/components/grow/`. Each becomes independently testable.

### FE-003 — No error boundary; a render throw is a white screen
- **Severity**: HIGH (retention)
- **Location**: `app/src/App.tsx`
- **Fix**: wrap `<Routes>` in an error boundary that offers "reload" and
  "start over" and reports to Sentry. A white screen on a PWA whose identity
  lives in localStorage reads as total data loss to the user.
- **Done when**: a test renders a component that throws and asserts the
  fallback appears with the recovery-key still intact.

### FE-004 — No i18n; first cohort is Norwegian
- **Severity**: HIGH (adoption)
- **Fix**: extract strings, `nb`/`nn`/`en`, browser-locale default. Pass the
  material's language through to card generation — currently a Norwegian text
  produces English cloze scaffolding.

### FE-005 — No a11y audit
- **Severity**: MEDIUM (and a legal requirement for Norwegian public-sector or
  education sales — WCAG 2.1 AA under *forskrift om universell utforming av IKT*)
- **Fix**: contrast audit on the dark theme, ARIA for the SVG fingerprint and
  icon-only buttons, keyboard nav, visible focus. `prefers-reduced-motion` is
  already handled.

### FE-006 — A bad flashcard can only be flagged, never corrected
- **Severity**: MEDIUM
- **Fix**: inline edit, store the correction, prefer it on re-render.

### FE-007 — No PWA install prompt
- **Severity**: HIGH (silent user loss)
- **Location**: `app/vite.config.ts` PWA config exists; no prompt
- **Status**: READ

iOS evicts localStorage for non-installed PWAs after ~7 days of inactivity.
Identity lives in localStorage. This silently loses anonymous users.

- **Fix**: `beforeinstallprompt` handling on Android, an iOS-specific
  instruction card, triggered after the first completed round (value delivered
  first). Pair with pushing users to save a recovery key.

### FE-008 — `raw_text` is held in localStorage indefinitely
- **Severity**: MEDIUM (privacy)
- **Location**: `app/src/store.ts:lastMaterialText`
- **Fix**: purge after cards are derived, or after N days. Mirror the
  server-side retention rule (see OPS-004).

### FE-009 — Strict mode is not enabled in `tsconfig.app.json`
- **Severity**: MEDIUM
- **Location**: `app/tsconfig.app.json` — no `"strict": true`
- **Status**: VERIFIED

`strictNullChecks` off means the null-safety of the whole app is unverified.
- **Fix**: enable `strict`, fix the fallout incrementally with
  `// @ts-expect-error` markers as a work list.

---

## 6. Data & operations

### OPS-001 — Never deployed
- **Severity**: BLOCKER
- **Fix**: `DEPLOY.md` has the click path. Needs a Render account, a domain,
  ~1 hour.

### OPS-002 — No indexes on the columns every query filters by
- **Severity**: HIGH (at scale)
- **Location**: `database.py` — `study_sessions.user_id`, `study_sessions.material_id`, `retention_checks.user_id`, `retention_checks.session_id`, `analytics_events.user_id`
- **Status**: VERIFIED by inspection — `index=True` appears on primary keys and
  the token/email/share-code lookups, but not on these foreign keys.

Every per-user query is a full table scan. Fine at 20 users; a cliff at 10,000.
- **Fix**: add indexes plus an Alembic migration. `tests/test_migrations.py`
  will fail on drift until the migration exists, by design.
- **Done when**: `EXPLAIN` on `/users/{id}/sessions` shows an index scan.

### OPS-003 — Concurrent instances race on `alembic upgrade head`
- **Severity**: MEDIUM
- **Location**: `Dockerfile` CMD
- **Fix**: run migrations as a release/pre-deploy step, not in the web CMD.
  Render supports a `preDeployCommand`.

### OPS-004 — No content retention policy
- **Severity**: MEDIUM (GDPR data minimisation)
- **Location**: `database.py:Material.raw_text`
- **Fix**: purge `raw_text` once cards and the knowledge map are derived, or
  after N days. Note the deliberate boundary already documented: `Material` rows
  are shared between users, so deletion must not cascade.

### OPS-005 — No backups documented, no restore drill
- **Severity**: HIGH
- **Fix**: enable Render's Postgres backups, document the restore procedure,
  and actually run a restore once. An untested backup is not a backup.

### OPS-006 — No structured logging, no request ids, no metrics
- **Severity**: MEDIUM
- **Fix**: JSON logs with a request id, latency and status per request. Sentry
  is wired but only for errors. Without this, the first production incident is
  debugged blind.

### OPS-007 — No staging environment
- **Severity**: MEDIUM
- **Fix**: a second Render service from the same blueprint on a `staging`
  branch, with its own database.

### OPS-008 — `/health` does not check the database
- **Severity**: MEDIUM
- **Location**: `main.py:1601`
- **Fix**: execute `SELECT 1`. A health check that passes while the database is
  unreachable causes the platform to route traffic into a broken instance.

---

## 7. Testing & CI

### TEST-001 — CI does not run lint, `npm audit`, or the migration-drift check on PRs from forks
- **Severity**: MEDIUM
- **Fix**: add `npm run lint` and `npm audit --audit-level=high`.

### TEST-002 — No end-to-end test of the actual user journey
- **Severity**: HIGH
- **Status**: READ. Two real bugs in this codebase's history escaped 148 green
  tests; two more escaped 170 this session and were caught only by browsing.
- **Fix**: one Playwright spec: paste → knowledge map → plan → mode picker →
  round → grade → fingerprint → retention check. Run against a real backend in
  CI. This is the single highest-value test remaining.

### TEST-003 — No load test
- **Severity**: MEDIUM
- **Fix**: `locust` or `k6` against `/materials/analyze` and
  `/users/{id}/fingerprint`. Needed to size the Render plan honestly, and to
  quantify SEC-004 before it is exploited rather than after.

### TEST-004 — No property-based tests on the maths
- **Severity**: LOW
- **Fix**: `hypothesis` over `forgetting_curve` and `hierarchical_memory`:
  R monotone decreasing in t, R ∈ (0,1], posterior median inside the CI,
  stability positive and finite for all valid inputs.

---

## 8. Documentation & code health

### DOC-001 — `SESSION_HANDOFF.md` contained a false security claim
- **Severity**: MEDIUM (it caused this hole to persist)
- **Status**: The "never enumerate" guardrail is stated correctly but was
  described as satisfied. It was satisfied for one endpoint.
- **Fix**: correct it, and add a rule: guardrail claims must name the test that
  enforces them.

### DOC-002 — `COGPRINT_PROBLEMS.md` and `_2.md` are stale
- **Fix**: fold anything still live into this file, delete the rest. Two
  inventories that disagree with the code are worse than none.

### DOC-003 — `frontend/` and `extension/` are unowned surfaces
- **Severity**: MEDIUM
- **Location**: `frontend/` (research UI, ~1,400 lines), `extension/` (~156 lines)
- **Status**: READ — no tests, not in CI, not in the audit trail.
- **Fix**: decide explicitly: maintain, archive, or delete. If the consumer app
  is the product, these are liabilities that still ship code and still read the
  same API.

### DOC-004 — No `CONTRIBUTING.md`, no ADR trail
- **Severity**: LOW
- **Note**: the commit messages *are* the design record and are unusually good.
  An `docs/decisions/` index pointing at the relevant commits would make that
  legible to a newcomer without reading the whole log.

---

## 9. Commercialisation gate

The product may be sold when all of the following are true. This is the
definition of done for "commercialisable".

- [ ] SEC-001 fixed and covered by `tests/test_authz.py`
- [ ] SEC-004 fixed and covered
- [ ] SEC-002 fails closed in production
- [ ] SEC-009 dependencies pinned; SEC-010 npm advisories cleared
- [ ] OPS-001 deployed; OPS-002 indexes; OPS-005 backups with a tested restore
- [ ] OPS-008 health check verifies the database
- [ ] FE-003 error boundary; FE-007 install prompt
- [ ] TEST-002 one end-to-end journey test in CI
- [ ] COR-002 one estimator, so no interval excludes its own point estimate
- [ ] LEGAL-001 privacy policy, ToS, and a DPA route — **Katchi, not code**
- [ ] At least 10 real users have completed 20+ sessions each

Estimated engineering effort to clear every code item: **6–9 working days.**
The non-code items (legal text, deploy accounts, recruiting) are the longer
pole.

---

## 10. The future — beyond the gate

Ordered by expected value, with the reasoning that produced the ordering.

### F1. Settle the personalisation question (highest value, lowest cost)
Run `evaluation/predictive_baseline.py --db` once 10 users have 12+ sessions
per technique. Three outcomes, each of which changes the company:
- **PERSONAL > PERSON** — the thesis holds; personalised technique choice is
  the moat, and the marketing writes itself.
- **PERSONAL ≈ PERSON** — people differ in memory strength but not in which
  technique suits them. Pivot the pitch to personalised *scheduling*, which is
  still valuable and still differentiated from Anki. Drop the technique claim.
- **PERSON ≈ PRIOR** — not enough data yet. Keep collecting.

Nothing else on this list should be built before this is answered.

### F2. Assigned-technique sessions (SCI-002)
The only route to a causal claim, and a prerequisite for any published result.

### F3. Institutional distribution, not consumer subscription
"€0 runtime, offline-capable, self-hostable, no data leaves your server" is a
far stronger pitch to a school or a university department than to an individual
student, and it needs less marketing muscle — which matters given the founder's
time is the binding constraint. Concretely: a per-institution deployment, SSO,
a teacher dashboard over the *aggregate* fingerprint, and a data-processing
agreement. The zero-LLM architecture is what makes this saleable; protect it.

### F4. Capture extension
The existing `extension/` is research tooling and explicitly not this. A
"capture what I'm reading" surface attacks the product's real friction —
pasting requires a context switch away from studying. This is the more
interesting of the two future surfaces, but not before F1.

### F5. Native app via Capacitor
The PWA is installable and complete. The only real gaps are iOS push and
app-store presence. Capacitor wraps the existing React app with no rewrite.
Do it when app-store presence is a distribution requirement, not before.

### F6. Web push
Deliberately deferred. Requires moving the Vite PWA plugin from `generateSW` to
`injectManifest` so the service worker can own `push`/`notificationclick`, and
iOS only delivers push to home-screen-installed PWAs. Email reminders reach the
same goal today. Do it against a real device, not blind.

### F7. Model improvements, in order of expected gain
1. Thompson sampling from the existing posterior — subsumes the hand-tuned
   optimism bonus and the `_UNMEASURED_DISCOUNT`, and is better founded.
2. Item-level (per-concept) stability rather than per-technique only. The
   scheduler currently treats every concept in a material as equally durable.
   This is what FSRS does and it is where most of the remaining scheduling gain
   is.
3. Replace the exponential curve with a power law. Study 2 shows ranking
   survives misspecification, so this is a refinement, not a fix — but the
   power law is better supported empirically.
4. Cross-user archetype clustering. Needs a population and a backend job.

### F8. Content pipeline
The knowledge map's quality caps everything downstream. A concept extractor
that understands headings, definitions and worked examples would lift card
quality more than any model change. Still doable with zero LLM calls.

---

## 11. What is genuinely good — do not "improve" these

Recorded so a future agent does not refactor away the parts that are working.

- **The zero-LLM core.** Analysis, fingerprint, matching and planning are pure
  NumPy and run offline for €0. It is simultaneously the moat, the margin and
  the privacy story. Never move core intelligence behind an LLM.
- **The Bayesian layer is calibrated and robust.** 92–96% coverage against a
  nominal 95%; ranking survives power-law misspecification. Measured, not
  assumed.
- **Comments that state limitations instead of hiding them.** The rate limiter
  documents that it is per-process. `_UNMEASURED_DISCOUNT` documents that it is
  a stand-in. This is why the audit above could be written quickly.
- **Tests that encode the attack.** `tests/test_recovery.py` performs the old
  enumeration attack and asserts it fails. `tests/test_analytics.py` pins D1/D7
  against a hand-built timeline. Keep writing them this way.
- **Commit messages as design notes.** They name the rejected alternative. This
  is the single most useful artefact in the repository for a new contributor.
- **The evaluation harnesses are tested.** Both `predictive_baseline` and
  `monte_carlo` have calibration tests, because the first version of the former
  declared personalisation a 100% winner on data generated with the effect set
  to exactly zero. An untested evaluator is worse than none.
