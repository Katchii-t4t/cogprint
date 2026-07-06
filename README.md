# CogPrint — Research Platform Backend

> Personalised-learning RCT platform. FastAPI + SQLAlchemy + SQLite backend with a
> **100% API-free** machine-learning pipeline (no external LLM calls — all three
> "agents" are custom classical-ML/statistics implementations).

This repo is the **backend + research-platform frontend** for CogPrint, a youth-led
international study on how individuals learn best. The public **marketing website** is a
separate repo: [`cogprint-site`](https://github.com/Katchii-t4t/cogprint-site).

> ### 🧭 START HERE (cold-start map — owner away until ~Aug 2026)
> Everything important is in this repo; GitHub is the single source of truth.
> 1. **[`HANDOVER.md`](./HANDOVER.md)** — full technical state + two-machine workflow.
>    **Appendix A** is the complete plain-language snapshot: read that alone and you
>    have the whole mental model, including how to run everything from scratch.
> 2. **[`CONSUMER_APP_BUILD.md`](./CONSUMER_APP_BUILD.md)** — the product vision, the
>    frontend↔backend API contract, and the build-status box (what's shipped).
> 3. Design records of shipped work: [`QUIZ_MODE_BUILD.md`](./QUIZ_MODE_BUILD.md),
>    [`NEXT_FEATURES_BUILD.md`](./NEXT_FEATURES_BUILD.md).
> 4. The open scientific decision: [`RETENTION_SCHEDULE_DECISION.md`](./RETENTION_SCHEDULE_DECISION.md).
>
> **State in one line:** backend complete (34 tests green); consumer app (`app/`)
> feature-complete vs the ideal-product spec (quiz mode, fingerprint art, share-PNG,
> OCR, nudges, save/restore); research platform (`frontend/`) + browser extension live;
> **remaining: deploy + the retention-schedule decision.** The Anthropic API key lives
> only in the stationary PC's gitignored `.env` — other machines get a graceful 503 on
> flashcards/OCR until a key is added.

---

## What this system does

1. A learner logs **study sessions** (technique, duration, time-of-day, sleep, stress, quiz score).
2. They complete **retention checks** at 24 h and 7 d (the primary outcome — durable memory).
3. Three custom "agents" turn that data into personalised guidance:
   - **Agent 1 — Material Analyzer** (`agents/material_analyzer.py`): turns raw study text into a
     concept graph (TF-IDF → LSA → TextRank).
   - **Agent 2 — Fingerprint Builder** (`personalization/fingerprint_builder.py`): a 10-step
     statistical pipeline that produces the learner's "cognitive fingerprint"
     (Bayesian memory stability + LinUCB technique recommendations + rule-based insights).
   - **Agent 3 — Study Planner** (`agents/study_planner.py`): a dynamic-programming
     spaced-repetition scheduler based on the Ebbinghaus forgetting curve.
4. It's a **randomised controlled trial**: `control` users get generic guidance (blinded),
   `treatment` users get the full personalised pipeline.

**No Claude/OpenAI/any LLM API is called at runtime.** Everything is NumPy + classical stats.

---

## Quick start

```bash
# 1. Install backend deps
pip install -r requirements.txt

# 2. (Optional) create a .env — defaults work out of the box for local dev
cp .env.example .env

# 3. Run the API
uvicorn main:app --reload
#   → API:      http://localhost:8000
#   → Swagger:  http://localhost:8000/docs

# 4. Run the tests (19 tests, all API-free)
python -m pytest

# 5. Run the research-platform frontend (separate terminal)
cd frontend
npm install
npm run dev
#   → http://localhost:5173
```

The SQLite database (`cogprint.db`) is created automatically on first run. It is
**git-ignored** — each machine has its own local data.

### Configuration (env vars — all optional for local dev)

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./cogprint.db` | Swap to Postgres for a deploy |
| `CORS_ORIGINS` | `localhost:5173,4173` | Comma-separated allowed frontend origins |
| `COGPRINT_API_KEY` | _unset_ | If set, `/users/all` & `/export/study-data` require an `X-API-Key` header (bulk-data protection). Unset = open (fine for local/closed pilot). |

> ⚠️ **Retention schedule is an open decision** — see
> [`RETENTION_SCHEDULE_DECISION.md`](./RETENTION_SCHEDULE_DECISION.md). The code is
> built around 24h/7d; the study materials use day 1/5/10/30. Lock one before
> collecting data. `config.py` centralises the scheduling half.

---

## Project structure

```
.
├── main.py                          # FastAPI app — all REST routes
├── database.py                      # SQLAlchemy ORM models + DB setup
├── requirements.txt
├── .env.example
│
├── schemas/                         # Pydantic request/response models
│   ├── fingerprint.py               #   FingerprintProfile, BayesianStabilityStats, ...
│   └── session.py                   #   SessionCreate, KnowledgeMap, StudyPlan, ...
│
├── personalization/                 # The statistical core
│   ├── fingerprint_builder.py       # Agent 2 — main 10-step pipeline (API-free)
│   ├── linucb.py                    # LinUCB contextual bandit (Li et al. 2010)
│   ├── hierarchical_memory.py       # Empirical-Bayes MCMC over memory stability S
│   ├── forgetting_curve.py          # Ebbinghaus OLS curve fitting
│   └── serializer.py                # JSON helpers
│
├── agents/
│   ├── material_analyzer.py         # Agent 1 — TF-IDF→LSA→TextRank NLP (API-free)
│   ├── study_planner.py             # Agent 3 — DP spaced-repetition scheduler (API-free)
│   └── performance_optimizer.py     # LEGACY — old LLM-based Agent 2, kept for reference
│
└── frontend/                        # Research-platform UI (React + TS + Vite + Tailwind)
    └── src/pages/                    #   Onboarding, LogSession, RetentionCheck,
                                      #   Dashboard, Fingerprint, StudyPlan, Researcher
```

> **Note:** `frontend/` here is the **research platform** (where study participants log data).
> It is *not* the public marketing site — that lives in the separate `cogprint-site` repo.

---

## Key API routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/users` | Create a participant (assign `control`/`treatment` group) |
| `POST` | `/sessions` | Log a study session → triggers fingerprint rebuild |
| `POST` | `/retention-checks` | Log a 24 h / 7 d retention check → triggers rebuild |
| `GET`  | `/users/{id}/fingerprint` | Get the computed cognitive fingerprint |
| `POST` | `/materials/analyze` | Agent 1: text → concept knowledge map |
| `POST` | `/users/{id}/study-plan` | Agent 3: generate a day-by-day study plan |
| `GET`  | `/users/{id}/pending-checks` | List overdue retention checks |
| `GET`  | `/export/study-data` | CSV export of all sessions for statistical analysis |
| `GET`  | `/health` | Health check |

Full schemas and parameters: **http://localhost:8000/docs**.

---

## Branch

This backend repo's default branch is **`master`** (the marketing-site repo uses `main` —
don't mix them up).

---

*See [`HANDOVER.md`](./HANDOVER.md) for everything else.*
