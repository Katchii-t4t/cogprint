# CogPrint — Engineering Handover & Collaboration Guide

**Last updated:** 2026-06-07
**Audience:** Any AI agent (Claude Code) or human engineer continuing this project,
including a **second Claude Code instance running on a different machine** that needs to
collaborate on this same codebase.

> If you are the "other" Claude Code bot reading this for the first time: welcome. This
> document is your complete context. Read §0 (collaboration workflow) first, then §1–§8.

---

## 0. Two-machine collaboration workflow (READ FIRST)

Two Claude Code instances are working on this project from **different PCs**. You share
state **only through this GitHub repo** — there is no other channel between you. Follow
these rules so you never clobber each other's work:

### Golden rules
1. **`git pull` before you start any work.** Always begin a session by syncing:
   ```bash
   git checkout master
   git pull origin master
   ```
2. **`git push` after every logical unit of work.** Don't sit on uncommitted changes —
   the other machine can't see them. Small, frequent commits > big rare ones.
3. **Use feature branches for anything non-trivial**, then merge to `master`:
   ```bash
   git checkout -b feature/<short-name>
   # ... work ...
   git push -u origin feature/<short-name>
   # open a PR, or merge to master once green
   ```
4. **Communicate intent through this file.** Update the **§9 "Work log / coordination"**
   section at the bottom when you start or finish a chunk of work, so the other bot knows
   who owns what. Commit that change first, before touching code, to "claim" an area.
5. **Never commit secrets or the database.** `.gitignore` already excludes `.env`,
   `*.db`, `*.sqlite3`, `__pycache__/`, and `node_modules/`. Keep it that way.

### Avoiding merge conflicts
- The two big "hot" files are `main.py` and `personalization/fingerprint_builder.py`.
  If both bots need to edit the same file, coordinate via §9 and pull frequently.
- Prefer adding **new functions/files** over rewriting existing ones when possible.
- If you hit a conflict: `git pull` shows it; resolve by keeping both intents, run the
  syntax check (`python -m py_compile <file>`), then push.

### Default branch
- **This backend repo:** default branch is **`master`**.
- The separate marketing-site repo (`cogprint-site`) uses **`main`**. Don't confuse them.

---

## 1. The two-repo landscape

| Repo | What it is | Branch | Hosting |
|---|---|---|---|
| **`cogprint`** (this repo) | Research-platform backend + participant-facing frontend | `master` | GitHub only (run locally) |
| **`cogprint-site`** | Public marketing/landing website | `main` | GitHub → auto-deploys to Vercel |

`github.com/Katchii-t4t/cogprint` ← you are here
`github.com/Katchii-t4t/cogprint-site` ← marketing site (separate)

**Do not mix them up.** The `frontend/` folder *inside this repo* is the **research platform**
(where study participants onboard, log sessions, do retention checks, view their
fingerprint). The marketing site is a totally separate project.

---

## 2. System overview

CogPrint runs a **randomised controlled trial (RCT)** on personalised learning.

**Data flow:**
```
Participant logs StudySession ──▶ POST /sessions ──▶ rebuild_fingerprint()
                                                          │
Participant does RetentionCheck ─▶ POST /retention-checks ┘
   (24h, then 7d)                                          │
                                                           ▼
                              CognitiveFingerprint (profile_json + bandit_state_json)
                                                           │
                              GET /users/{id}/fingerprint ◀┘
                                                           │
Material text ─▶ POST /materials/analyze ─▶ KnowledgeMap  │
                                              │            │
                              POST /study-plan│◀───────────┘
                                              ▼
                                        StudyPlanResponse (14-day schedule)
```

**RCT blinding:** `control` participants receive a generic profile (no personalisation
shown) to preserve the experimental blind; `treatment` participants get the full pipeline.
This split lives in `rebuild_fingerprint()` (`personalization/fingerprint_builder.py`).

**Primary outcome metric:** retention, in priority order **7-day > 24-hour > immediate
quiz score**. This ordering is hard-coded throughout (reward extraction, technique ranking,
insight generation).

---

## 3. The big architectural decision: zero LLM API calls

The original design used the Claude API for all three agents. **That has been completely
removed.** Every agent is now a from-scratch classical-ML / statistics implementation using
only NumPy. This was a deliberate goal: full transparency, reproducibility, zero per-request
cost, and no external dependency at runtime.

> ⚠️ **Do not reintroduce LLM API calls into the runtime pipeline** without explicit
> instruction. The one legacy file (`agents/performance_optimizer.py`) that still imports
> `anthropic` is dead code kept only for reference — see §6.

`requirements.txt` still lists `anthropic>=0.40.0` and `.env.example` still has
`ANTHROPIC_API_KEY`, but these are **only** for the legacy file. The active pipeline never
touches them. (Leaving the dep in is harmless; remove only if you also delete the legacy file.)

---

## 4. Component deep-dive

### 4.1 Agent 1 — Material Analyzer (`agents/material_analyzer.py`)

Turns raw study text into a structured `KnowledgeMap` (concepts + difficulty + type +
relations + suggested study order).

**Pipeline:**
1. **Sentence segmentation** (`_sentences`): split on `\n\n` paragraph breaks *first*, then
   on `.!?` followed by a capital. (Paragraph-first split prevents the title bleeding into
   the first sentence.)
2. **Tokenise + stop-word removal + `_stem`** — `_stem` is a lightweight hand-rolled suffix
   stripper (no NLTK/external lib).
3. **TF-IDF** (`_compute_tfidf`): sklearn-style smooth IDF, L2-normalised document columns.
   Returns `(tfidf_vectors, vocab, M)` where `M` is the term×doc matrix.
4. **LSA** (`_lsa`): truncated SVD via `numpy.linalg.svd`, `k = min(20, rank-1)`.
5. **TextRank** (`_textrank`): PageRank power iteration (damping 0.85, ≤100 iters) on the
   cosine-similarity graph of concept embeddings → centrality scores.
6. **Surface-form recovery** (`_build_stem_surface_map`): maps each stem back to the most
   frequent original word, so concepts display as real English ("active recall") not stems
   ("activ recal").
7. **Concept extraction** (`_extract_concepts`): per-sentence bigrams + unigrams, filtered
   by `_CONCEPT_BLACKLIST` and min length. **Bigrams are extracted per-sentence, never on
   the full text** — this prevents cross-sentence garbage like "Stability Active".
8. **Difficulty** (`_difficulty_score`): doc position + TF-IDF percentile + token length →
   foundational / intermediate / advanced.
9. **Type** (`_classify_type`): regex over surrounding sentences → factual / conceptual /
   procedural.
10. **Related concepts**: top-3 cosine neighbours in LSA space.
11. **Study order** (`_study_order`): sort by difficulty tier, tie-break by PageRank.

**Known footguns fixed (don't regress these):**
- Cross-sentence bigrams → fixed by per-sentence extraction.
- Stemmed display names → fixed by surface-form map.
- Noise words ("process", "level", "memory") → fixed by `_CONCEPT_BLACKLIST` + min length > 4.

### 4.2 Agent 2 — Fingerprint Builder (`personalization/fingerprint_builder.py`)

The heart of the system. A 10-step pure-Python pipeline. Entry point:
**`rebuild_fingerprint(db, user_id)`**.

| Step | Function | Output |
|---|---|---|
| 2 | `_compute_technique_stats` | Per-technique mean immediate/24h/7d + percentile `relative_effectiveness` |
| 3 | `_compute_optimal_conditions` | Pearson r (sleep/stress/duration vs score), best time-of-day, duration bucket analysis, threshold recommendations |
| 4 | `compute_memory_profiles` (from `forgetting_curve.py`) | Ebbinghaus **OLS** S-fit per technique |
| 5 | `_get_population_estimates` + `HierarchicalMemoryModel.fit_population` | Empirical-Bayes population prior (MLE over **all** users' S estimates) |
| 6 | `_compute_bayesian_stability` | Per-technique **MCMC posterior** over S (mean/median/std/95% CI) |
| 7 | LinUCB `fit_from_history` + `expected_rewards` | `bandit_expected_rewards` per technique |
| 8 | `_compute_trend` | OLS slope on weekly quiz averages → `improving_over_time` |
| 9 | `_generate_insights` | Rule-based insights (≤6) + data gaps (≤4) |
| 10 | assemble + persist | `FingerprintProfile` JSON + bandit state → DB |

**Confidence levels** (`_confidence_from_count`): `low` <5 sessions, `medium` 5–15, `high` 16+.

**Persistence:** writes `profile_json` *and* `bandit_state_json` to the
`cognitive_fingerprints` row, then commits.

### 4.3 Agent 3 — Study Planner (`agents/study_planner.py`)

A dynamic-programming spaced-repetition scheduler. Entry point:
**`StudyPlanner.generate_plan(user_id, knowledge_map, fingerprint, total_days=14)`**.

- **Ebbinghaus retention:** `R(lag, S) = exp(-lag / S)`.
- **Next-review rule:** `Δt = S · ln(1 / 0.85)` — review when predicted retention hits 85%.
- **Daily greedy/DP loop:** each day, collect due reviews → score by
  `priority = (1 - R) × technique_effectiveness` → fill remaining slots (max 3/day) with new
  concepts in study order.
- **Technique selection per concept** (`_technique_for_concept`): (1) if the user's overall
  best technique is contextually appropriate, use it; (2) else pick best from measured
  effectiveness; (3) else fall back to evidence-based defaults (Dunlosky et al. 2013).
- **S source:** Bayesian posterior median → OLS fallback → default 10 days.

### 4.4 LinUCB bandit (`personalization/linucb.py`)

Disjoint LinUCB (Li et al. 2010) for technique recommendation.

- **Context vector (9-dim):** `[intercept, sleep_norm, stress_norm(inverted), morning,
  afternoon, evening, night, duration_norm, session_norm]`.
- **Per-arm ridge model:** `A_k = I + Σxxᵀ`, `b_k = Σrx`, `θ̂ = A⁻¹b`.
- **UCB:** `θ̂ᵀx + α·√(xᵀA⁻¹x)`, default `α = 1.2`.
- **Reward (retention-priority):** 7d → 24h×0.85 → quiz×0.70 (`best_available_reward`).
- **Serialisation:** `to_json()`/`from_json()` store `A_k`,`b_k` as nested lists →
  `bandit_state_json` column. `fit_from_history()` replays all sessions chronologically.

### 4.5 Hierarchical memory model (`personalization/hierarchical_memory.py`)

Empirical-Bayes approximation to full hierarchical Bayes (chosen for pilot-scale tractability).

- **Population prior:** `log(S) ~ Normal(μ_pop, σ_pop)`, hyperparams via MLE over the cohort.
- **Likelihood:** `R(t) = exp(-t/S)` with Gaussian noise `σ=0.08`.
- **Inference:** Metropolis-Hastings, log-normal random-walk proposal (symmetric → no
  Jacobian). 2000 kept samples, 600 burn-in, proposal std 0.28, S∈[0.5, 365].
- **Benefit:** shrinks sparse individual S-estimates toward the cohort mean (Bayesian
  shrinkage) — a user with 2 observations gets a sensible posterior.

---

## 5. Database & schemas

### Models (`database.py`, SQLite via SQLAlchemy)
- **`User`**: `group` (control/treatment), `pre_test_score`, `post_test_score`.
- **`StudySession`**: `technique` (enum of 7), `duration_minutes`, `time_of_day`,
  `sleep_hours`, `stress_level` (1–5), `quiz_score` (0–1).
- **`RetentionCheck`**: `session_id`, `check_type` ("24h"/"7d"), `score` (0–1).
- **`Material`**: `title`, `raw_text`, `knowledge_map_json`.
- **`CognitiveFingerprint`**: `session_count`, `profile_json`, **`bandit_state_json`**
  (added for LinUCB persistence).

The 7 techniques: `spaced_repetition, active_recall, re_reading, mind_maps, interleaving,
elaborative_interrogation, practice_testing`.

### Schemas (`schemas/`)
- `fingerprint.py`: `ConfidenceLevel`, `TechniqueStats`, `OptimalConditions`,
  `TechniqueMemoryProfile`, `BayesianStabilityStats`, `FingerprintProfile`.
- `session.py`: session/material/plan/user request+response models, `KnowledgeMap`, etc.

`frontend/src/types.ts` mirrors these — **keep them in sync** when you change a schema.

---

## 6. ✅ Done / ❌ Pending / ⚠️ Known issues

### ✅ Complete
- All 3 agents rewritten from scratch, **zero LLM API calls**.
- LinUCB bandit: full implementation + JSON persistence + batch refit.
- Hierarchical Bayesian MCMC: complete.
- Fingerprint pipeline: 10-step, control/treatment RCT split.
- Material analyzer: TF-IDF→LSA→TextRank with all footguns fixed (§4.1).
- Study planner: DP + Ebbinghaus + technique-selection heuristic.
- All Pydantic schemas + matching `frontend/src/types.ts`.
- `database.py`: `bandit_state_json` column added.
- Backend **is pushed to GitHub** and in sync (this repo).
- Research-platform frontend tracked (`frontend/`, 20 files, 7 pages).

### ❌ Pending / not done
1. **Research-platform frontend never deployed.** `frontend/` runs locally only. No hosting
   decided (Vercel? Render? alongside the API?).
2. **CORS locked to localhost.** `main.py` only allows `localhost:5173` / `:4173`. Must add
   the real deployed frontend origin before going live.
3. **No authentication.** The API is open. `VITE_RESEARCHER_PASSWORD` is a soft client-side
   gate only. Fine for a closed pilot, not for public exposure.
4. **No automated tests.** Zero test suite. High-value next step.
5. **No DB migrations (Alembic).** Schema changes need manual `ALTER TABLE` or drop+recreate.
   (The `bandit_state_json` column may need a manual add on any pre-existing DB.)
6. **Retention-check reminders not automated.** `/users/{id}/pending-checks` exists but
   there's no notification/scheduling — participants must check manually.
7. **`forgetting_curve.py` and `serializer.py` not audited** in the last rewrite pass —
   assumed-correct dependencies. Worth a review.

### ⚠️ Known issues / footguns
- **`main.py:382`** has a dead placeholder class
  `class PendingCheck(BaseModel if False else object): pass` — safe to delete.
- **`agents/performance_optimizer.py`** is LEGACY. Its `__init__` calls
  `anthropic.Anthropic()` unconditionally → it will crash if instantiated without an API key.
  It's never instantiated by the active pipeline. Keep as reference or delete; don't wire it in.
- **Fingerprint rebuild is synchronous** inside `POST /sessions` and `POST /retention-checks`,
  wrapped in `try/except: pass` (a rebuild failure never breaks the request, but also fails
  silently). For production, move to a background task queue and add logging.
- **MCMC cost:** ~2600 iterations × N techniques per rebuild. Fast in practice (ms) but it's
  synchronous — watch it if the cohort or technique set grows a lot.
- **`.value` on enums:** stats functions assume ORM enum instances (`s.technique.value`).
  Feeding raw dicts/strings would break them.

---

## 7. Running & developing

```bash
# Backend
pip install -r requirements.txt
uvicorn main:app --reload          # http://localhost:8000/docs

# Research frontend
cd frontend && npm install && npm run dev   # http://localhost:5173

# Sanity check before pushing — these must pass:
python -m py_compile main.py database.py schemas/*.py personalization/*.py agents/*.py
cd frontend && npx tsc --noEmit
```

`cogprint.db` is created on first run and is git-ignored (per-machine local data).

---

## 8. Conventions

- **Python:** type hints everywhere, `from __future__ import annotations`, docstrings explain
  the *math/algorithm* not just the code. Pure functions where possible.
- **No LLM calls in the runtime path** (see §3).
- **Retention priority 7d > 24h > immediate** is sacred — preserve it in any new logic.
- **Commit messages:** imperative mood, explain *why*. Co-author trailer is used on commits.
- **Keep `frontend/src/types.ts` in sync with `schemas/`.**

---

## 9. Work log / coordination (update this when you start/finish work)

> Two bots share this repo. Add a dated line when you claim or finish an area, so the other
> machine knows what's in flight. Commit this section *before* starting big work to "claim" it.

| Date | Machine / who | Area | Status |
|---|---|---|---|
| 2026-06-07 | Bot A (Karthik's PC) | Initial handover docs (README + HANDOVER) committed | ✅ done |
| 2026-06-07 | Bot B (sgkar's PC) | Production-hardening pass (see below) | ✅ done |
| 2026-06-07 | Bot B (sgkar's PC) | Consumer-app build STARTED: Agent 4 question-gen (LLM, isolated) done. Full plan + API contract in **`CONSUMER_APP_BUILD.md`**. | ✅ handed off |
| 2026-06-07 | Bot B (sgkar's PC) | Step A backend done: bad-question flag (`POST /materials/{id}/questions/flag`), stable card ids, flagged-card exclusion. 24 tests passing. Next: Screens 1–4 (frontend). | ✅ done |
| 2026-07-04 | Bot B (sgkar, overnight) | Ideal-product polish on `app/`: generative FingerprintArt centrepiece; **sham made visually indistinguishable** (verified in browser vs real); question pre-gen on analyze; recents strip; forgetting-nudge (dismissible, ~6h). Build+PWA green. | ✅ done |
| 2026-07-05 | Bot B (sgkar) | Added `Study.tsx` (missing Focus-mode screen) + fullscreen timer; fixed 3 real eslint react-hooks bugs (1 mine, 2 pre-existing); found+fixed stale `cogprint.db` schema bug (no migrations — delete db to pick up new columns); wired `ANTHROPIC_API_KEY` into `cogprint/.env`, verified real flashcard generation live (Claude Opus 4.8, incl. Norwegian content). | ✅ done |
| 2026-07-05 | Bot B (sgkar) | **Quiz mode built + verified**: objectively-graded MC (answer + 3 distractors, deterministic grading) is the default and the only mode that logs sessions; flashcards demoted to unscored practice. Backend `Flashcard.distractors` (backward-compatible), prompt update, 2 new tests (26/26 green). Browser-verified: quiz round → 1 session, flashcard round → 0, practice banner OK. Bonus: fixed pre-existing stale-state bug that dropped the last card's answer from every score. Spec/design record: `QUIZ_MODE_BUILD.md`. | ✅ done |
| 2026-07-05 | (planning) | Spec'd 4 next features in **`NEXT_FEATURES_BUILD.md`**: (1) shareable fingerprint PNG, (2) photo→OCR (Claude vision), (3) smart per-topic forgetting nudges (Ebbinghaus), (4) save-progress name + restore-by-ID. Independent, recommended order 1→3→4→2. | ⏳ planned |
| 2026-06-18 | Bot A (Karthik's PC) | **Consumer app built (`app/`) — all 4 screens + retention checks, verified end-to-end against the live backend.** See "Bot A — consumer app" below. | ✅ done |

**Bot B pass — what landed (commits `0e0acd7`..`6501f8d`):**
- **Env-configurable CORS** (`CORS_ORIGINS`) — unblocks the deployed frontend.
- **Fingerprint rebuild → `BackgroundTasks`** — POST /sessions & /retention-checks
  no longer block on the MCMC pipeline.
- **Optional API-key auth** (`auth.py`, `COGPRINT_API_KEY`) on `/users/all` and
  `/export/study-data` — no-op unless the env var is set (local dev unaffected).
- **`config.py`** — single source of truth for the retention schedule (pending-checks
  + validation read it). **The 24h/7d ↔ day1/5/10/30 discrepancy is NOT resolved** —
  it is a scientific call left for the 19 June advisor meeting; see
  `RETENTION_SCHEDULE_DECISION.md`.
- **Audited** `forgetting_curve.py` (correct) and `serializer.py` (fixed a wrong
  return-type annotation on dormant legacy code).
- **`requirements.txt`** — added missing `numpy`; `pytest`+`httpx` for tests.
- **Test suite** (`tests/`, 19 tests) — was zero. `python -m pytest`.
- Removed dead `PendingCheck` no-op class in `main.py`.

**Bot B pass 2 — frontend now builds, runs, and is an installable PWA
(commits `a9d14d7`..`b495331`):**
- **Frontend builds cleanly** (`tsc && vite build`). Fixed two build-breakers:
  a duplicate `corr()` in `Fingerprint.tsx` (TS2393) and missing `import.meta.env`
  typings (added `src/vite-env.d.ts`).
- **API base is deploy-ready**: `api.ts`/`Researcher.tsx` read `VITE_API_BASE`
  (falls back to `/api` dev proxy).
- **Verified end-to-end at runtime**: uvicorn backend + `vite dev`, full flow
  (create user → log sessions → fingerprint → researcher list) works through
  the proxy. Note: fingerprint is now *eventually* consistent (rebuild moved to
  a BackgroundTask), so a GET right after a POST may lag one session.
- **Installable PWA** via `vite-plugin-pwa`: manifest + service worker +
  icon set (`public/pwa-*.png`, generated by `scripts/gen_icons.py`). App-shell
  cached offline; `/api/*` forced NetworkOnly so data is never stale.

**Bot A — consumer app build (2026-06-18, commit after `9785a7f`):**
The consumer product (Screens 1–4 from `CONSUMER_APP_BUILD.md`) is now built as a
**new `app/` folder** (Vite + React + TS + Tailwind v3), kept separate from the
research `frontend/` per §6 of that doc. Dark/neural theme (cyan on ink), mobile-first.

- **5 routes:** `/` Paste (analyse + auto-create anonymous user, random group),
  `/plan` (14-day plan + expandable rationale + Pomodoro focus timer),
  `/cards` (flashcard swipe loop, flip/answer/flag, logs a session on finish),
  `/grow` (fingerprint payoff — SVG bloom when low-confidence; technique bars +
  retention grid + actionable insights when data exists), `/checks` (24h/7d
  retention flow for returning users).
- **Real/sham split** (`app/src/insights.ts`): `buildView()` → `RealInsights` for
  treatment, `ShamInsights` (generic but plausible) for control. Identical UI.
- **Card round → study data**: fraction correct (excl. flagged) → `quiz_score`,
  technique `active_recall`, via `POST /sessions`; retention via `/checks`.
- **Two real bugs found + fixed during live testing:** `getQuestions` and
  `getStudyPlan` hit **POST** endpoints (the "get" names misled the first draft —
  they were defaulting to GET → 405). Also `study-plan` requires `material_id`;
  the app now remembers the last material in `localStorage` (`store.ts`) so
  `/plan`, `/cards`, `/grow` work even without it in the URL.
- **Verified end-to-end against a live uvicorn backend** (this machine now has the
  Python deps installed — see toolchain note): user create → analyse (20 concepts)
  → 14-day plan → flashcard round → session logged → fingerprint (low→medium as
  sessions seeded) → 24h+7d retention checks logged. Flashcards return 503 without
  `ANTHROPIC_API_KEY`; the app shows a clean "needs setup" screen and the rest
  still works. Tested the medium-confidence payoff screen with seeded data: bars,
  retention grid, and insights all render correctly.
- **Installable PWA** (`vite-plugin-pwa`): dark manifest + SW + cyan icon set
  (`app/scripts/gen_icons.py` → `app/public/pwa-*.png`). `/api/*` is NetworkOnly.
- **Verify:** `cd app && npx tsc --noEmit && npm run build` (both green; 24 backend
  tests still pass). Run: `cd app && npm run dev` → :5173 (proxies `/api` → :8000).

> ⚠️ **`technique` is hard-coded to `active_recall`** for every flashcard round.
> Fine for a flashcard-centric app (cards *are* active recall), but it means the
> "which technique works best for you" comparison only populates from the research
> `frontend/` path, not the consumer app. If the consumer app should drive
> technique comparison, the plan's per-day technique would need to flow into the
> round. Left as a product decision — not changed unilaterally.

**Toolchain note (important for the other machine):** the sgkar PC had no
Node.js — installed *portably* (no admin) at
`%LOCALAPPDATA%\node-portable\node-v24.16.0-win-x64`. Put that dir on PATH to
run `npm`. Python/uvicorn run the backend. **Karthik's PC (Bot A):** Node v24.16.0
+ Python 3.13 (Anaconda) with all `requirements.txt` deps installed as of
2026-06-18; backend tests run green here.

**Run the full stack locally:**
```
# terminal 1 — backend
uvicorn main:app --reload                       # :8000
# terminal 2 — frontend (Node on PATH)
cd frontend && npm install && npm run dev        # :5173  (proxies /api -> :8000)
# participant app:  http://localhost:5173
# researcher view:  http://localhost:5173/researcher
```

**Still open for the other bot / next session:** deploy the research frontend
(static host + set `VITE_API_BASE`) and the backend (set `CORS_ORIGINS` +
`COGPRINT_API_KEY`); move rebuild to a real task queue (Celery) if load grows;
add per-participant tokens (current auth only guards bulk-data endpoints); wire
retention reminders/notifications; resolve the retention-schedule decision
above; Postgres + Alembic when leaving SQLite. **Possible: a browser extension**
(MV3 popup reusing `api.ts`) for one-click session logging + retention-check
nudges — not started; confirm scope first.

---

# Appendix A — Complete State Snapshot (detailed, plain-language)

> A full backup of context as of commit `4cf43e1` (17 commits). If you are picking
> this up cold — or recovering after losing a session — this section alone should let
> you rebuild the whole mental model. Everything here is also true in the code; when
> the two disagree, the code wins and you should fix this doc.

## A.1 What CogPrint is, in one breath

A youth-led research project (owner: Katchi / Karthik) testing whether *individuals
respond differently and predictably to study techniques* — and, if so, building an app
that personalises study advice. **Two tracks:** the **research track** (a real RCT/study
that produces findings) runs first; the **product track** (the consumer app) is built in
parallel but must never hard-code a finding the study hasn't confirmed yet. This repo is
the **backend + research-platform frontend + (now) the start of the consumer app**. The
public marketing site is a *separate* repo (`cogprint-site`).

## A.2 Backup & where everything lives

- **GitHub (the backup):** `github.com/Katchii-t4t/cogprint`, default branch **`master`**.
  Everything important is committed and pushed. `git pull origin master` gives you 100%.
- **Local clone (this machine, user `sgkar`):**
  `C:\Users\sgkar\.claude\sessions\Proj Ciel\cogprint`.
- **Local-only, NOT on GitHub (all regenerable — safe to lose):** `cogprint.db` (SQLite
  data), `__pycache__/`, `.pytest_cache/`, `frontend/node_modules/`, `frontend/dist/`,
  and `.env` (does not exist yet — see A.7). `.gitignore` keeps these out on purpose.
- **Node.js:** not system-installed here; a **portable** copy lives at
  `%LOCALAPPDATA%\node-portable\node-v24.16.0-win-x64`. Put it on PATH to run `npm`.
- **Python:** Anaconda (`python`, `uvicorn`, `pytest`, `numpy`, `Pillow`, `anthropic`
  all available). The other machine (user `Karthik`) is the second collaborator.

## A.3 File inventory — what each thing is

**Backend (Python / FastAPI):**
- `main.py` — every REST route. Reads `CORS_ORIGINS`, mounts optional API-key auth,
  runs fingerprint rebuilds as BackgroundTasks. Hot file — coordinate edits.
- `database.py` — SQLAlchemy models: `User` (group control/treatment), `StudySession`,
  `RetentionCheck`, `Material` (now incl. `questions_json`), `CognitiveFingerprint`.
- `config.py` — single source of truth for the **retention schedule** (24h/7d). Honest
  about the limit: the t=1/t=7 day-coords are also baked into the math in 5 files.
- `auth.py` — optional API-key dependency (`COGPRINT_API_KEY`); no-op unless set.
- `schemas/` — Pydantic: `fingerprint.py`, `session.py`, and `question.py` (flashcards).
- `personalization/` — the API-free ML core: `fingerprint_builder.py` (10-step pipeline +
  RCT blinding), `linucb.py` (bandit), `hierarchical_memory.py` (Bayesian MCMC),
  `forgetting_curve.py` (Ebbinghaus OLS — audited, correct), `serializer.py` (legacy).
- `agents/` — `material_analyzer.py` (TF-IDF→LSA→TextRank, API-free),
  `study_planner.py` (DP spaced-repetition, API-free),
  `question_generator.py` (**Agent 4 — the ONLY LLM call**, isolated, optional),
  `performance_optimizer.py` (deprecated legacy; never instantiate).
- `tests/` — 24 pytest tests (conftest + test_api + test_auth + test_pipeline +
  test_questions). Run `python -m pytest`.

**Research-platform frontend (`frontend/`):** React 18 + Vite + Tailwind + react-router.
7 pages (Onboarding, Dashboard, LogSession, RetentionCheck, Fingerprint, StudyPlan,
Researcher). `src/types.ts` mirrors backend schemas — reuse it. Builds clean; is an
**installable PWA**; light/indigo theme.

**Browser extension (`extension/`):** MV3, vanilla JS, one-click session logging. Load
unpacked from `chrome://extensions`.

**Docs:** `README.md`, `HANDOVER.md` (this file), `CONSUMER_APP_BUILD.md` (the consumer
app plan + API contract), `RETENTION_SCHEDULE_DECISION.md` (the open scientific choice).

## A.4 Everything done so far (the 17 commits, grouped)

1. **Docs bootstrap** — README + HANDOVER so two machines can collaborate.
2. **Backend hardening (Bot B pass 1):** env-configurable CORS; fingerprint rebuild moved
   to BackgroundTasks; optional API-key auth on bulk-data endpoints; `config.py` retention
   source-of-truth + dead-code removal; audited `forgetting_curve.py`/`serializer.py`;
   added missing `numpy` to requirements; first pytest suite (was zero).
3. **Frontend made real (Bot B pass 2):** fixed 2 build-breakers (duplicate `corr`,
   missing `vite-env.d.ts`); `VITE_API_BASE` config; verified the full participant flow
   end-to-end through the Vite proxy against a live backend; added PWA (manifest + service
   worker + generated icons); installed Node portably.
4. **Browser extension** — MV3 quick-log popup.
5. **Consumer app foundation:** **Agent 4** (LLM flashcard generation, isolated, graceful
   503 without a key) + `CONSUMER_APP_BUILD.md` (vision, 4-screen plan, API contract,
   real/sham architecture) + **Step A backend** (bad-question flag, stable card ids,
   flagged-card exclusion).

## A.5 How the system works (data flow)

```
Participant pastes material ─▶ POST /materials/analyze ─▶ knowledge map (cached)
(optional, app)               POST /materials/{id}/questions ─▶ flashcards (Agent 4, LLM, cached)
Participant studies + tests ─▶ POST /sessions (quiz_score) ─▶ BackgroundTask rebuilds fingerprint
24h / 7d later ─────────────▶ POST /retention-checks ───────▶ BackgroundTask rebuilds fingerprint
                                                                     │
                              GET /users/{id}/fingerprint ◀──────────┘  (technique effectiveness,
                                                                          optimal conditions, MCMC
                                                                          stability, bandit, insights)
```
Control-group users get a **generic** fingerprint (RCT blinding); treatment users get the
full personalised pipeline. Confidence: <5 sessions = low, 5–15 = medium, 16+ = high.

## A.6 What works right now vs what's not built

**Works (verified):** the whole backend (24 tests green), the research frontend (builds +
runs + PWA), the extension, Agent 4 generation + the flag mechanism (mocked in tests; live
needs a key). **Not built:** the consumer app's 4 screens, the `InsightProvider` real/sham
frontend split, the dark redesign, the flashcard-round → session/retention frontend wiring
(Step A's frontend half). All of that is reduced to *frontend* work against a now-complete,
stable API contract (see `CONSUMER_APP_BUILD.md` §4).

## A.7 Security model (read before touching the LLM)

- The Anthropic API key is **never** in code, args, logs, commits, or chat. The owner
  puts `ANTHROPIC_API_KEY=sk-ant-...` in a local `.env` themselves. `.env` is gitignored.
- Without a key, `POST /materials/{id}/questions` returns **503** and everything else (all
  API-free) works normally — the UI should show a clean "needs setup" state, not crash.
- `COGPRINT_QGEN_MODEL` (default `claude-opus-4-8`) is the cost lever — switch to a cheaper
  model to save money. Question sets are cached per material; don't regenerate needlessly.
- `COGPRINT_API_KEY` (separate thing) gates the bulk-data researcher endpoints. Off by
  default (fine for local/closed pilot); set it before any public deploy.

## A.8 Open decisions (do NOT resolve unilaterally)

- **Retention schedule:** code uses 24h/7d; study materials use day 1/5/10/30. This is a
  *scientific* choice for the owner + UiO advisor (meeting ~19 Jun). See
  `RETENTION_SCHEDULE_DECISION.md`. The flashcard mapping must use whatever
  `config.CHECK_TYPE_KEYS` holds.
- **Consumer app: new `app/` folder vs restyle `frontend/`** — `CONSUMER_APP_BUILD.md` §6;
  recommended new folder so the research platform keeps working.

## A.9 Recover / run everything from scratch

```bash
# 1. Get the code (the backup IS GitHub)
git clone https://github.com/Katchii-t4t/cogprint.git && cd cogprint

# 2. Backend
pip install -r requirements.txt
python -m pytest                 # expect 24 passing
uvicorn main:app --reload        # http://localhost:8000/docs

# 3. Frontend (Node on PATH — portable copy at %LOCALAPPDATA%\node-portable\...)
cd frontend && npm install && npm run dev   # http://localhost:5173

# 4. (optional) enable flashcards: create cogprint/.env with ANTHROPIC_API_KEY=...
```
Sanity before pushing: `python -m py_compile main.py config.py auth.py database.py
schemas/*.py personalization/*.py agents/*.py` and `cd frontend && npx tsc --noEmit`.

## A.10 What's next

Frontend build of the consumer app, in order: **Step A frontend wiring** → **Screen 1**
(paste→analyze) → **Screen 2** (study plan + why + timer) → **Screen 3** (flashcard swipe
loop, using Agent 4 + the flag endpoint) → **Screen 4** (growing fingerprint) → **dark
redesign**. Build each end-to-end before the next. Confirm scope with the owner before
anything beyond these screens. Full detail: `CONSUMER_APP_BUILD.md`.

---

*End of handover. Everything above reflects the actual state of the repo as of the last
commit. When in doubt, read the code — the docstrings are detailed and the math is explained
inline.*
