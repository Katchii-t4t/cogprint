# CogPrint — Consumer App

The **product-track** consumer app: a mobile-first, dark-themed study app that
builds a plan around how *you* learn and grows a "cognitive fingerprint" from
your own data. It sits on top of the existing CogPrint backend (FastAPI) — it
does **not** contain any ML itself; all intelligence comes from the API.

> This is a separate app from `../frontend/` (the research-platform UI for study
> participants) and from the `cogprint-site` repo (the marketing site). See
> `../CONSUMER_APP_BUILD.md` for the full product vision and `../HANDOVER.md` for
> the backend.

## Run it

```bash
# 1. Backend must be running (from the repo root):
pip install -r requirements.txt
uvicorn main:app --reload        # → http://localhost:8000

# 2. This app (from app/):
npm install
npm run dev                      # → http://localhost:5173 (proxies /api → :8000)
```

Flashcards (Screen 3) need the backend's `ANTHROPIC_API_KEY` set in a local
`.env` (the owner does this). Without it, `/cards` shows a clean "needs setup"
screen and the rest of the app still works.

## The five screens

| Route | Screen | What it does |
|---|---|---|
| `/` | **Paste** | Paste study material → analyse animation → auto-creates an anonymous user (random `control`/`treatment` group) and a material. |
| `/plan` | **Plan** | 14-day study plan with expandable rationale + a Pomodoro focus timer. |
| `/cards` | **Cards** | Flashcard swipe loop (tap to flip, swipe/tap to answer, flag bad cards). On finish, logs a `StudySession` with the round score. |
| `/grow` | **Grow** | The fingerprint payoff — an SVG bloom that grows with data; technique bars, retention grid, and actionable insights once enough sessions exist. |
| `/checks` | **Checks** | Retention-check flow (24h / 7d) for returning users → logs `RetentionCheck`s. |

## Architecture notes

- **No login wall.** The first paste creates an anonymous user; state lives in
  `localStorage` (`src/store.ts`).
- **Real vs. sham insights** (`src/insights.ts`): `buildView()` returns
  `RealInsights` for `treatment` users and `ShamInsights` (convincing but
  generic) for `control` users — the UI is identical either way. This preserves
  the RCT blind. The backend already blinds control users too.
- **Typed API client** (`src/api.ts`) wraps every backend endpoint. Note the two
  "get" calls that are actually **POST** on the backend (`getQuestions`,
  `getStudyPlan`) — they generate + cache server-side.
- **Card round → study data** (`src/pages/Cards.tsx`): a flashcard round = one
  study event. Fraction correct (excluding flagged cards) → `quiz_score`;
  technique is `active_recall`. Later rounds map onto retention checks via
  `/checks`.
- **Dark neural theme**: `ink-*` backgrounds + `neural` cyan accents
  (`tailwind.config.js`), mobile-first (`max-w-lg`, `min-h-dvh`).
- **PWA**: installable, offline app-shell caching; API calls are network-only so
  study data is never stale. Icons: `python scripts/gen_icons.py`.

## Verify

```bash
npx tsc --noEmit      # type check
npm run build         # production build
```
