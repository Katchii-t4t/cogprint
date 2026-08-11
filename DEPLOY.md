# CogPrint — Deployment Guide

> Scaffolding to take CogPrint from localhost to a live free-beta (§1 in
> `COGPRINT_PROBLEMS.md`). The files are ready; **this doc is the click-path.**
> Nothing here has been executed — the owner runs these steps (they create
> accounts and hold the secrets). Rough cost: **~$7–15/month** for a small beta.

## Architecture (recommended)

```
 consumer app (app/)  ──► Vercel (static, free)      ──┐
 research UI (frontend/) ─► Vercel (static, free)     ─┤──► calls VITE_API_BASE
 backend (FastAPI)   ──► Render (Docker web service) ──┘
 database            ──► Render managed Postgres
 flashcards (opt)    ──► Anthropic API (only paid runtime piece)
```

Why this split: the frontends are static (cheap/free on any CDN); the backend needs
a real server + database. Render reads `render.yaml` and provisions both.

## Step 1 — Backend + database on Render

1. Push this repo to GitHub (already at `github.com/Katchii-t4t/cogprint`).
2. Render → **New → Blueprint** → pick this repo. It reads [`render.yaml`](render.yaml)
   and creates `cogprint-api` (Docker) + `cogprint-db` (Postgres), wiring
   `DATABASE_URL` automatically.
3. In the service's **Environment**, set the secrets that are `sync: false`:
   - `COGPRINT_API_KEY` — a long random string (guards bulk-data endpoints and
     the research analytics view). **The service will refuse to boot without
     it**, because `render.yaml` sets `COGPRINT_ENV=prod`. If your first deploy
     crashes on startup with a message naming this variable, that is the
     safeguard working, not a broken build — set the value and redeploy.
     Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `CORS_ORIGINS` — your frontend URL(s), e.g. `https://cogprint.vercel.app` (fill in after Step 2).
   - `FRONTEND_URL` — same value; this is where emailed sign-in links point.
     Without it links point at `localhost` and won't work for anyone else.
   - `RESEND_API_KEY` — optional; enables real magic-link email. Without it the
     app still works (recovery keys) and links are written to the service logs
     instead of sent — fine for a private trial, not for real users.
   - `EMAIL_FROM` — e.g. `CogPrint <noreply@yourdomain.com>`. Resend requires a
     verified sending domain.
   - `ANTHROPIC_API_KEY` — optional; upgrades flashcards from local cloze cards
     to LLM-written ones, and enables photo OCR. Leave unset to launch without it.
4. Deploy. Confirm `https://<your-api>.onrender.com/health` returns
   `{"status":"ok","service":"CogPrint API","database":"ok"}`. The `database`
   field is the one that matters — the check runs a real query, so a 503 here
   means the app is up but cannot reach Postgres, which is a different problem
   from the app being down.

> The `Dockerfile` installs `psycopg[binary]` so Postgres works in prod; local dev
> still uses SQLite via the default `DATABASE_URL`. No code change needed —
> SQLAlchemy reads the URL. The container runs `alembic upgrade head` before
> starting uvicorn, so schema changes apply on deploy.

## Step 2 — Consumer app on Vercel

1. Vercel → **New Project** → same repo → set **Root Directory** to `app`.
2. It auto-detects Vite and uses [`app/vercel.json`](app/vercel.json) (SPA rewrite).
3. Add env var **`VITE_API_BASE`** = your Render URL (e.g. `https://cogprint-api.onrender.com`).
4. Deploy. Then go back to Render and put this Vercel URL in `CORS_ORIGINS`.

Repeat for `frontend/` (the research UI) if you want it live too — same steps, Root
Directory `frontend`, add a `frontend/vercel.json` mirroring the app's if missing.

## Step 3 — Smoke test the live stack

Do these in order. Each one fails differently, so a failure tells you which
step was wrong rather than just "it's broken".

1. `curl https://<api>/health` → `"database":"ok"`.
2. Open the Vercel URL and click **"Try a sample"** then **Analyse**. You should
   land on a 14-day plan. If this hangs, it is almost always `CORS_ORIGINS` not
   matching your Vercel URL exactly (scheme included, no trailing slash) — the
   browser console will say so plainly.
3. Finish one flashcard round. You should land on the fingerprint screen with a
   score. **If the plan loads but the fingerprint 401s**, the client is not
   sending its recovery token: check that the sign-up response was persisted
   (Application → Local Storage → `cogprint_app_v1` should contain
   `recoveryKey`).
4. Verify the enumeration guard is live in production — this is the one check
   worth doing by hand, because it is the difference between a private beta and
   a data breach:

   ```
   curl -i https://<api>/users/1/materials
   ```

   Must return **401**. If it returns 200 with data, stop and do not invite
   anyone.

- Flashcards will show local cloze cards unless `ANTHROPIC_API_KEY` is set;
  that is the intended free path, not a failure.

## Step 4 — Daily review reminders (recommended)

Spaced repetition only works if something brings people back at the right time.
`POST /admin/send-reminders` emails everyone with a verified address and reviews
due; it is intentionally not self-scheduling (there is no job runner in this
process), so drive it from outside:

Render → **New → Cron Job**, schedule `0 7 * * *` (07:00 UTC daily), command:

```
curl -fsS -X POST https://<your-api>.onrender.com/admin/send-reminders \
  -H "X-API-Key: $COGPRINT_API_KEY"
```

Users are capped at one reminder per 20 hours in the endpoint itself, so a
double-fired cron cannot spam anyone.

> **Web Push is a deliberate follow-up, not an oversight.** Real push needs the
> PWA's service worker to own `push`/`notificationclick` handlers, which means
> switching the Vite PWA plugin from `generateSW` to `injectManifest` — a build
> change worth making against a real device to test delivery on, rather than
> blind. Email reaches the same goal today; add push once there's a phone to
> verify it against. Note iOS only delivers push to home-screen-installed PWAs.

## Before charging money (not needed for a free beta)

- ~~Real accounts / data persistence~~ — done: recovery keys + magic-link email.
- ~~Data export/delete~~ — done: `POST /users/me/export`, `POST /users/me/delete`.
- Privacy policy + ToS — still required for EU users; the endpoints exist, the
  legal text does not.
- Stripe + freemium gating (§6 in `COGPRINT_PROBLEMS.md`).

## Cost notes

- Vercel static hosting: **free** for this scale.
- Render starter web + basic Postgres: **~$7–14/mo**.
- Anthropic (flashcards only): **~$0.03–0.13 per generated set** on Opus,
  ~5× cheaper on Haiku (`COGPRINT_QGEN_MODEL=claude-haiku-4-5`, already the
  prod default in `render.yaml`). Everything else is free NumPy.
