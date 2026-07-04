# CogPrint — Consumer App Build Plan & Handover

**Audience:** the next Claude Code session (or engineer) building the
consumer-facing CogPrint app on top of the existing backend.
**Status:** ✅ **MVP built** — all 4 screens + retention checks live in `app/`,
verified end-to-end against the backend (Bot A, 2026-06-18). Remaining: real LLM
flashcards need `ANTHROPIC_API_KEY`; deploy; explicit sham-content polish. The
dark redesign is already done. See the build-status box below and `app/README.md`.
**Read order:** this file → `app/README.md` → `HANDOVER.md` (backend) → the code.

> ### Build status (2026-06-18)
> - ✅ **Screen 1 Paste** (`app/src/pages/Paste.tsx`) — analyse + anonymous user.
> - ✅ **Screen 2 Plan** (`Plan.tsx`) — 14-day plan, rationale, Pomodoro timer.
> - ✅ **Screen 3 Cards** (`Cards.tsx`) — swipe loop, flag, logs session on finish.
> - ✅ **Screen 4 Grow** (`Grow.tsx`) — growing fingerprint + bars/grid/insights.
> - ✅ **Checks** (`Checks.tsx`) — 24h/7d retention flow for returning users.
> - ✅ **Real/sham `InsightProvider`** (`insights.ts`), **dark theme**, **PWA**.
> - ✅ **(2026-07-04, Bot B)** Living generative fingerprint art
>   (`components/FingerprintArt.tsx`) — per-user, data-grown, the centrepiece;
>   **sham made visually indistinguishable** (deterministic per-user bars/grid/
>   insights — verified in-browser vs real); questions **pre-generated** after
>   analysis (no wait at Cards); **recents strip** + **forgetting-nudge**
>   (dismissible, ~6h rate-limit) on Paste.
> - ⏳ Real flashcards need the API key set; ⏳ deploy.
> - ⚠️ Built as a **new `app/` folder** (the recommended option in §6), NOT a
>   restyle of `frontend/` — the research platform is untouched.

> This is the *product track* (the AI study app). It sits on top of the existing
> *research track* backend. Do **not** rebuild the backend. Build the app on the
> API contract in §4.

---

## 0. TL;DR for a cold start

1. `git checkout master && git pull origin master`. Default branch is **`master`**.
2. Backend is complete, hardened, and tested (22 tests). Run it:
   `pip install -r requirements.txt && uvicorn main:app --reload` → http://localhost:8000/docs
3. Node is installed **portably** (no admin) at
   `%LOCALAPPDATA%\node-portable\node-v24.16.0-win-x64` — put it on PATH to run `npm`.
4. There are **two** frontends in play:
   - `frontend/` — the **research platform** (participant data-logging). Builds, runs,
     is an installable PWA. Light/indigo theme. **Do not delete it** — it serves the study.
   - The **consumer app** described here is **new** and not built yet. Decide whether to
     build it as a new top-level folder (e.g. `app/`) or restyle `frontend/`. See §6.
5. The one new backend capability — flashcard generation (Agent 4) — is **done**
   (`agents/question_generator.py`, `POST /materials/{id}/questions`). It needs
   `ANTHROPIC_API_KEY` in a local `.env` (the owner sets this; never commit it).
6. Build in the order in §5. Commit + push after each working piece; update the
   work-log table in `HANDOVER.md` §9 so the other machine doesn't collide.

---

## 1. The vision (the soul of the product)

CogPrint is **not** "an app that makes flashcards" — there are a thousand of those.
Its entire promise: **an app that understands *you* specifically and gets better the
more it learns you.** The "cognitive fingerprint" is the whole point. Every screen,
animation, and interaction should make the user feel: *this app sees me.*

**Design priority order (highest first):** (1) zero friction, (2) feels alive,
(3) honest, (4) beautiful.

**Hard requirements:**
1. **Mobile-first.** People study on their phone. The flashcard screen must feel
   native on mobile (swipe, not tap-tiny-button). Must also work on desktop.
2. **No login wall.** First screen is paste-material, never sign-up. Auto-create an
   anonymous user on first paste (assign `group` then); only ask to "save/name" later.
   Value first, commitment after.
3. **The sham layer must be invisible.** The app runs in **real** (full personalisation)
   or **sham** (identical UI, generic non-personalised insights) mode. The user must
   NEVER be able to tell which. Route all insight content through one `InsightProvider`
   interface with a real and a sham implementation (§7). This is core architecture for
   the Phase-5 RCT, not an add-on. The backend already exposes `control`/`treatment`
   via the user's group, and `control` users already get a generic fingerprint.
4. **Never freeze on an LLM/compute call.** Material analysis and question generation
   take time. Always show motion/progress; render structure immediately, fill in details
   as results arrive. No static spinner > ~2s without context.
5. **Cache everything expensive.** A material analysed once is never re-analysed; a
   generated question set is never regenerated. (Backend already caches both — see §4.)
6. **Isolate any LLM call behind one service module.** Already done for question-gen
   (`agents/question_generator.py`). Keep it that way so it can be swapped for a
   local/cheaper method without touching the UI.

**Framing constraint (non-negotiable, scientific integrity):** CogPrint is about
*measured response to study techniques*, NOT self-reported "learning styles" (visual/
auditory/kinesthetic — discredited). Every insight must be grounded in the user's own
measured data, never a general claim. Insights must end in an **action the user can
take** ("You remember 40% better in the mornings — schedule the hard stuff there?"),
never surveillance ("we logged that you studied at 11pm three nights running").

---

## 2. The four screens (the MVP — build in this order)

### Screen 1 — Paste material (the landing screen)
- Large inviting input: "Paste what you need to learn." Accept pasted text (and image →
  OCR is **not** supported by the backend yet; flag as TODO or do client-side OCR).
- On submit, show the material being "read" — a visual analysis animation (brain/roots/
  neural aesthetic). Never a dead screen. Calls `POST /materials/analyze`.
- On completion → Screen 2.

### Screen 2 — Study plan
- Show the AI-generated plan from `POST /users/{id}/study-plan` (returns day-by-day
  `days[]`, each with a `rationale` — surface the **why**). Include a simple study/break
  timer. Should feel like a gift, not an instruction.

### Screen 3 — Flashcard tab (THE CORE — passive data capture)
- A small CogPrint logo tab, quiet, that comes alive with a question when a study
  session ends. One question at a time, large, clean, **swipe/one-tap** to answer.
- Cards come from `POST /materials/{id}/questions` (Agent 4 — already built).
- A discreet **"this question was bad/confusing" flag** on every card. Flagged cards are
  excluded from modelling (see §5 Step A — needs a tiny backend addition).
- Every answer silently feeds the backend (see §5 Step A for how answers map onto
  `POST /sessions` / `POST /retention-checks`). The user thinks they're self-testing;
  they're drawing their own fingerprint.

### Screen 4 — The fingerprint / progress (the payoff)
- NOT dry numbers — something visual, personal, almost a unique artwork that **grows** as
  data comes in. From `GET /users/{id}/fingerprint`.
- **Day one, do NOT show empty graphs.** Show "Answer a few more and I'll start drawing
  your fingerprint." Let it visibly grow. (`confidence` is `low`/`medium`/`high`;
  `session_count` drives the growth.)
- When data exists, surface: best time of day, technique effectiveness (radar chart),
  retention curves per technique, optimal-condition heatmap, improving-over-time trend.
- **Every insight ends in an action**, never just something the app knows.

---

## 3. Current state (what exists, with commits)

**Backend — complete, API-free except Agent 4, 22 tests passing.**
- 3 original agents (material analyzer, fingerprint builder, study planner) — all NumPy,
  no external calls. RCT `control`/`treatment` split + blinding in `fingerprint_builder.py`.
- Hardening pass (commits `0e0acd7`..`6501f8d`): env CORS, BackgroundTasks rebuild,
  optional API-key auth on bulk endpoints (`COGPRINT_API_KEY`), `config.py` retention
  source-of-truth, pytest suite.
- **Agent 4 — question generation (commit `b3c22d9`)** — the only LLM call, isolated:
  `agents/question_generator.py`, `schemas/question.py`, `POST /materials/{id}/questions`,
  `questions_json` cache column on `Material`. Returns 503 when no key (UI degrades).

**Research frontend (`frontend/`) — builds, runs, PWA, browser extension** (commits
`a9d14d7`..`25670fb`). React 18 + Vite + Tailwind + react-router. `frontend/src/types.ts`
mirrors the backend schemas — **reuse it**. Light/indigo theme (the consumer app wants
the dark marketing-site look — see §6).

**Not built:** the consumer app (Screens 1–4), card-answer logging (§5 Step A), the
`InsightProvider` real/sham split, the dark redesign.

---

## 4. The API contract (build the frontend against THIS)

Base URL: `/api` via the Vite dev proxy → `http://localhost:8000`, or set
`VITE_API_BASE` to an absolute backend URL for a deploy. JSON in/out.
Enums: technique ∈ {spaced_repetition, active_recall, re_reading, mind_maps,
interleaving, elaborative_interrogation, practice_testing}; time_of_day ∈
{morning, afternoon, evening, night}; group ∈ {control, treatment};
check_type ∈ {24h, 7d} (from `config.CHECK_TYPE_KEYS`).

| Method | Path | Body / params | Returns |
|---|---|---|---|
| POST | `/users` | `{group, pre_test_score?}` | `User` |
| GET | `/users/{id}` | — | `User` |
| GET | `/users/all` | header `X-API-Key` if `COGPRINT_API_KEY` set | `[{id,group,...,session_count}]` |
| PATCH | `/users/{id}/post-test` | `{post_test_score}` | `User` |
| POST | `/sessions` | `{user_id, material_id?, technique, duration_minutes, time_of_day, sleep_hours?, stress_level?, quiz_score}` | `Session` (triggers bg fingerprint rebuild) |
| GET | `/users/{id}/sessions` | — | `[Session]` |
| POST | `/retention-checks` | `{session_id, user_id, check_type, score}` | `RetentionCheck` (triggers bg rebuild) |
| GET | `/users/{id}/pending-checks` | — | `[{session_id, check_type, session_date, due_date}]` |
| GET | `/users/{id}/fingerprint` | — | `FingerprintResponse` |
| POST | `/users/{id}/fingerprint/rebuild` | — | `FingerprintResponse` |
| POST | `/materials/analyze` | `{title, raw_text}` | `{material_id, knowledge_map}` (cached on material) |
| POST | `/materials/{id}/questions` | `?n=8&refresh=false&include_flagged=false` | `{material_id, title, cards:[{id,question,answer,concept,difficulty,flagged}], generated_by}` — flagged cards excluded by default; **503** if no API key |
| POST | `/materials/{id}/questions/flag` | `{card_id}` (stable index) | `{material_id, card_id, flagged_count}` — marks a card bad/confusing (excluded from study + modelling); idempotent |
| POST | `/users/{id}/study-plan` | `?material_id=&total_days=14` | `{user_id, total_days, days:[{day,technique,topic_focus,session_duration_minutes,time_of_day,rationale}], general_advice}` |
| GET | `/export/study-data` | `?group=`, `X-API-Key` if set | CSV |
| GET | `/health` | — | `{status, service}` |

`FingerprintResponse = {user_id, fingerprint, updated_at}`. `fingerprint` (see
`schemas/fingerprint.py` / `frontend/src/types.ts`): `session_count`, `confidence`
(low/medium/high), `technique_effectiveness[]`, `optimal_conditions`,
`recommended_techniques[]`, `recommended_session_duration_minutes`, `insights[]`,
`data_gaps[]`, `improving_over_time`, `avg_score_trend_per_week`, `memory_profiles[]`,
`technique_stability[]`, `bandit_expected_rewards{}`. **Control-group users get a
generic profile with empty `bandit_expected_rewards`** — this is the sham hook.

Confidence tiers: <5 sessions = low/generic, 5–15 = medium, 16+ = high.

---

## 5. Build sequence (each piece committed + pushed before the next)

### Step A — Card-answer logging
**Backend part: ✅ DONE (commit adds the flag mechanism).** A flashcard now has a
stable `id`, can be flagged via `POST /materials/{id}/questions/flag`, and flagged
cards are excluded from the study set by default. The remaining part of Step A is the
**frontend mapping** below (build it with Screen 3 in Step E):

The backend has no per-flashcard *answer* model — and doesn't need one. Map a flashcard
round onto the existing endpoints. **Recommended mapping (no heavy new tables):**
- A flashcard round over a material = one **study event**. The frontend aggregates the
  round's correctness into a 0–1 score and:
  - First round on a material → `POST /sessions` with `quiz_score` = fraction correct,
    `technique` = the technique studied, plus duration/time-of-day.
  - Later rounds (24h / 7d later) → `POST /retention-checks` with that session's id and
    `check_type`. (This reuses the whole fingerprint pipeline as-is.)
- **Bad-question flag: ✅ done.** `POST /materials/{id}/questions/flag {card_id}` stores
  flagged ids in `questions_json` (`StoredQuestions.flagged`); the questions endpoint hides
  them by default. The frontend should call this from the per-card flag affordance and
  drop flagged cards from any round-score it computes.

> ⚠️ The remaining frontend mapping is the only thing left for Step A. Per the owner's
> rules, confirm the round→session/retention mapping with the owner before wiring it if
> anything is ambiguous (especially once the retention-schedule decision is locked).

### Step B — Frontend scaffold + `InsightProvider` real/sham split (§7)
New app shell (mobile-first), routing, a typed API client (reuse `frontend/src/api.ts`
+ `types.ts` as the base; add `getQuestions`, `flagQuestion`, card-answer posting).
Anonymous-user bootstrap on first paste (random `group`, store id in normal persistence —
not localStorage if this will ever run as an artifact; for a standalone deploy, fine).

### Step C — Screen 1 (Paste → analyze, with the reading animation)
### Step D — Screen 2 (Study plan + why + timer)
### Step E — Screen 3 (Flashcard swipe loop + bad-question flag + silent logging)
### Step F — Screen 4 (Growing fingerprint visualisation)
### Step G — Dark redesign to match the marketing site (cyan/neural, dark base)

Build C→F each working end-to-end before moving on. G can be folded in as you go or done
as a polish pass. **Ask the owner before building anything beyond these screens.**

---

## 6. Consumer app vs research frontend — a decision to make

`frontend/` is the **research platform** (participant onboarding to control/treatment,
researcher dashboard, data logging) — it must keep working for the study. The consumer
app is a **different product** with a different (dark) look.

Two options — pick one and note it in the work-log:
- **(Recommended) New folder** (e.g. `app/`) — a separate Vite app for the consumer
  product, sharing types with the backend. Keeps the research platform untouched.
- Restyle `frontend/` into the consumer app — risks breaking the research flow; avoid
  unless the owner wants a single unified app.

Match the marketing site's visual language (the separate `cogprint-site` repo: dark base,
cyan/neural accents, brain+circuit+roots aesthetic) so product and site feel like one brand.

---

## 7. The `InsightProvider` real/sham architecture (required)

All insight-rendering goes behind one interface with two implementations; the user's
mode decides which is injected. No visible difference between them.

```ts
interface InsightProvider {
  getFingerprint(userId): Promise<FingerprintView>;   // technique effectiveness, optimal conditions, trend
  getRecommendations(userId): Promise<Action[]>;      // each insight ends in an action
}

// RealInsights  → reads GET /users/{id}/fingerprint (treatment users)
// ShamInsights  → returns generic, plausible-but-non-personalised content (control users)
```
- Decide which to inject from the user's `group` (`treatment` → Real, `control` → Sham).
  The backend already blinds control users (generic fingerprint, empty
  `bandit_expected_rewards`), so `RealInsights` on a control user would already look
  generic — but build `ShamInsights` explicitly so the sham is a deliberate, controllable
  active-placebo, not an accident of empty data. The convincing "looks personalised but
  is random" sham content is real work and is also flagged in `HANDOVER.md` (Phase-5 sham
  engine) — coordinate so the frontend sham and any backend sham engine stay consistent.
- The UI components must be identical regardless of which provider is behind them.

---

## 8. Constraints, security, and gotchas

- **API key boundary:** the owner sets `ANTHROPIC_API_KEY` in a local `.env` themselves —
  never put a key in code, args, logs, commits, or chat. `.env` is gitignored. Without a
  key, `/materials/{id}/questions` returns 503 and the UI must show a clean "needs setup"
  state, not crash.
- **Cost lever:** `COGPRINT_QGEN_MODEL` (default `claude-opus-4-8`) — switch to a cheaper
  model to cut cost. Question sets are cached on the material; don't regenerate needlessly.
- **Two-track rule:** don't hard-code or assume any study finding before the study
  confirms it. Personalisation infra is fine; baked-in conclusions are not.
- **Retention schedule is still an OPEN scientific decision** (`RETENTION_SCHEDULE_DECISION.md`)
  — 24h/7d (code) vs day1/5/10/30 (study materials). Don't silently change it; the
  flashcard-round mapping in Step A should use whatever `config.CHECK_TYPE_KEYS` holds.
- **Don't break the research frontend or the backend API** without flagging.
- Fingerprint is **eventually consistent** (rebuild runs in a BackgroundTask) — a GET
  right after a POST may lag one session. Fine for humans; account for it in any test.

---

## 9. Run / test / verify

```bash
# Backend
pip install -r requirements.txt
uvicorn main:app --reload                 # http://localhost:8000/docs
python -m pytest                          # 22 tests, all green

# Frontend (Node on PATH — see §0.3)
cd frontend && npm install && npm run dev # http://localhost:5173 (proxies /api -> :8000)

# Enable flashcards (owner does this once, locally):
#   create cogprint/.env with:  ANTHROPIC_API_KEY=sk-ant-...
```

Sanity before pushing: `python -m py_compile main.py *.py **/*.py` (or the explicit list
in `HANDOVER.md` §7) and `cd frontend && npx tsc --noEmit`.

---

## 10. Collaboration workflow (two machines share this repo)

`git pull origin master` before work; `git push origin master` after each logical unit;
update the **`HANDOVER.md` §9 work-log** when you start/finish an area so the other
machine doesn't collide. Hot files: `main.py`, `personalization/fingerprint_builder.py`.
Prefer adding new files/functions over rewriting. Never commit `.env`, `*.db`, or
`node_modules/`.

*End of consumer-app handover. The foundation (Agent 4) is in; Screens 1–4 are next,
starting with Step A.*
