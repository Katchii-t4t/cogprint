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

**Still open for the other bot / next session:** create GitHub repo ✅ (done),
deploy the research frontend, move rebuild to a real task queue (Celery) if load
grows, add per-participant tokens (current auth only guards bulk-data endpoints),
wire retention reminders/notifications, and resolve the retention-schedule
decision above. Postgres + Alembic when leaving SQLite.

---

*End of handover. Everything above reflects the actual state of the repo as of the last
commit. When in doubt, read the code — the docstrings are detailed and the math is explained
inline.*
