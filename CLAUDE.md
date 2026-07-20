# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

CogPrint: a personalised-learning RCT platform. FastAPI + SQLAlchemy backend whose ML pipeline is **100% API-free** (custom classical ML/statistics, no LLM calls in the runtime path), plus three clients. The public marketing site is a **separate repo** (`cogprint-site`, default branch `main`); this repo's default branch is **`master`** — don't mix them up.

Deep context lives in `HANDOVER.md` (full technical state; Appendix A is a complete plain-language snapshot) and `CONSUMER_APP_BUILD.md` (product vision + frontend↔backend API contract). Update the work log in HANDOVER §9 when starting/finishing significant work — two machines coordinate through this repo only.

## Commands

```bash
# Backend (repo root)
pip install -r requirements.txt
uvicorn main:app --reload            # http://localhost:8000, Swagger at /docs
python -m pytest                     # full suite (all API-free, no network)
python -m pytest tests/test_api.py                       # one file
python -m pytest tests/test_api.py::test_name            # one test

# Consumer app (product track)
cd app && npm install && npm run dev # http://localhost:5173, proxies /api → :8000
npx tsc --noEmit                     # type check
npm run build                        # tsc -b && vite build
npm run lint                         # eslint (app/ only; frontend/ has no lint script)

# Research-platform UI
cd frontend && npm install && npm run dev

# Sanity check before pushing (from HANDOVER §7)
python -m py_compile main.py database.py schemas/*.py personalization/*.py agents/*.py
cd frontend && npx tsc --noEmit
```

The SQLite db `cogprint.db` is auto-created on first run and git-ignored. If the backend 500s with "table X has no column Y", the local db predates a schema change — delete it; `create_all` rebuilds it. There are no migrations.

The browser `extension/` has no build step — load unpacked via `chrome://extensions`.

## Architecture

Four "agents", all invoked from routes in `main.py` (single-file API, ~20 routes):

1. **Agent 1 — Material Analyzer** (`agents/material_analyzer.py`): study text → concept graph via TF-IDF → LSA → TextRank. API-free.
2. **Agent 2 — Fingerprint Builder** (`personalization/fingerprint_builder.py`): 10-step statistical pipeline producing the user's "cognitive fingerprint". Composes `hierarchical_memory.py` (empirical-Bayes MCMC over memory stability), `forgetting_curve.py` (Ebbinghaus OLS fit), `linucb.py` (contextual bandit for technique recommendation), `priors.py`. API-free.
3. **Agent 3 — Study Planner** (`agents/study_planner.py`): dynamic-programming spaced-repetition scheduler. API-free.
4. **Agent 4 — Question generation/OCR** (`agents/question_generator.py`, `agents/material_ocr.py`): the **only** LLM-backed features. Without `ANTHROPIC_API_KEY` they return 503 and everything else works; clients must show a clean "needs setup" state, not crash. `agents/question_generator_local.py` is the API-free fallback.

`agents/performance_optimizer.py` is **LEGACY** (old LLM-based Agent 2): its `__init__` calls `anthropic.Anthropic()` unconditionally and crashes without a key. Never wire it into the live pipeline.

**Data flow:** `POST /sessions` and `POST /retention-checks` synchronously trigger a fingerprint rebuild wrapped in `try/except` (a rebuild failure never breaks the request but records the failure — see `tests/test_rebuild_observability.py`). `POST /materials/{id}/questions` and `POST /users/{id}/study-plan` are POSTs that generate + cache server-side, even though clients treat them as "get" calls.

**The RCT blind:** users are randomised `control`/`treatment`. Control users get generic/sham guidance, treatment users get the real pipeline — blinded on the backend AND in the consumer app (`app/src/insights.ts` `buildView()` returns `RealInsights` vs `ShamInsights` with identical UI). Preserve this blind in any change.

**Clients:**
- `app/` — consumer product (React 19, Vite, Tailwind, PWA, dark "ink/neural" theme, mobile-first). No login: first paste creates an anonymous user; state in `localStorage` (`app/src/store.ts`). Typed API client in `app/src/api.ts` wraps every backend endpoint.
- `frontend/` — research-platform UI for study participants (React 18, light theme). Keep `frontend/src/types.ts` in sync with `schemas/`.
- `extension/` — Manifest V3 extension, plain JS, logs sessions via `POST /sessions`.

**Auth** (`auth.py`): `COGPRINT_API_KEY` env var gates only the bulk-data researcher endpoints (`/users/all`, `/export/study-data`) via `X-API-Key` header. Unset = open (fine locally; must be set before any public deploy).

**Deploy** (`DEPLOY.md`): frontends → Vercel (static), backend → Render via `render.yaml`/`Dockerfile` with managed Postgres (`DATABASE_URL` swap only; local dev stays SQLite).

## Critical constraints

- **⚠️ Retention schedule is an open decision owned by the project owner — do NOT resolve it unilaterally.** Code uses 24h/7d; study materials use day 1/5/10/30. `config.py` centralises the scheduling half, but the time coordinates are also baked into the math in five `personalization/` modules (listed in `config.py`'s docstring). Import `config.CHECK_TYPE_KEYS` / `RETENTION_SCHEDULE` instead of hard-coding "24h"/"7d". See `RETENTION_SCHEDULE_DECISION.md`.
- **No LLM calls in the numeric/runtime path.** Exactly two LLM service modules exist (question generation, OCR) and both produce content only; everything numeric stays deterministic NumPy. Keep it that way.
- **Retention priority 7d > 24h > immediate quiz is sacred** — preserve it in any new scoring/reward logic.
- The Anthropic API key exists only in the owner's gitignored `.env`; never in code, logs, or commits. `COGPRINT_QGEN_MODEL`/`COGPRINT_OCR_MODEL` are the cost levers; question sets are cached per material — don't regenerate needlessly.
- Stats functions expect ORM enum instances (`s.technique.value`); raw dicts/strings break them.
- Fingerprint rebuild (incl. MCMC, ~2600 iterations × N techniques) is synchronous inside request handlers — cheap now, but watch it if cohort/technique count grows.

## Conventions

- Python: type hints everywhere, `from __future__ import annotations`, docstrings explain the *math/algorithm*, pure functions where possible. Pydantic schemas in `schemas/`, ORM models in `database.py`.
- Commit messages: imperative mood, explain *why*.
- Git hygiene (two machines share this repo): pull before starting, push after every logical unit, feature branches for anything non-trivial. Hot files prone to conflicts: `main.py`, `personalization/fingerprint_builder.py` — prefer adding new functions/files over rewriting.
- Never commit secrets, `.env`, or `*.db`.
