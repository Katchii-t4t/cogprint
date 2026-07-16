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
   - `COGPRINT_API_KEY` — a long random string (guards bulk-data endpoints). **Set this before any public traffic.**
   - `CORS_ORIGINS` — your frontend URL(s), e.g. `https://cogprint.vercel.app` (fill in after Step 2).
   - `ANTHROPIC_API_KEY` — optional; enables flashcards. Leave unset to launch without them.
4. Deploy. Confirm `https://<your-api>.onrender.com/health` returns `{"status":"ok"}`.

> The `Dockerfile` installs `psycopg[binary]` so Postgres works in prod; local dev
> still uses SQLite via the default `DATABASE_URL`. No code change needed —
> SQLAlchemy reads the URL.

## Step 2 — Consumer app on Vercel

1. Vercel → **New Project** → same repo → set **Root Directory** to `app`.
2. It auto-detects Vite and uses [`app/vercel.json`](app/vercel.json) (SPA rewrite).
3. Add env var **`VITE_API_BASE`** = your Render URL (e.g. `https://cogprint-api.onrender.com`).
4. Deploy. Then go back to Render and put this Vercel URL in `CORS_ORIGINS`.

Repeat for `frontend/` (the research UI) if you want it live too — same steps, Root
Directory `frontend`, add a `frontend/vercel.json` mirroring the app's if missing.

## Step 3 — Smoke test the live stack

- Open the Vercel URL, paste some text → should analyze and build a plan.
- `curl https://<api>/health` → ok.
- Flashcards will show the "needs setup" screen unless `ANTHROPIC_API_KEY` is set.

## Before charging money (not needed for a free beta)

- Real accounts / data persistence (§2 in `COGPRINT_PROBLEMS.md`) — localStorage
  loses users across devices.
- Privacy policy + ToS + data export/delete (§5) — required for EU users.
- Stripe + freemium gating (§6).

## Cost notes

- Vercel static hosting: **free** for this scale.
- Render starter web + basic Postgres: **~$7–14/mo**.
- Anthropic (flashcards only): **~$0.03–0.13 per generated set** on Opus,
  ~5× cheaper on Haiku (`COGPRINT_QGEN_MODEL=claude-haiku-4-5`, already the
  prod default in `render.yaml`). Everything else is free NumPy.
