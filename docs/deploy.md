# Deploying Leadnius

> **Current plan: [go-live.md](go-live.md)** (2026-11-17). The web app now also runs the SEO / GEO / AEO job worker, so it
> deploys to Render with the API (`render.yaml`); the Vercel section below is out of date unless a separate Render
> worker runs `npm run seo:worker:prod`.

Two deployables: the API (`lead-gen-backend`, FastAPI + Postgres) and the web app (`lead-gen-frontend`, Next.js).

## API on Render (blueprint)

`render.yaml` at the repo root defines a Postgres database and a Docker web service built from
`lead-gen-backend/Dockerfile`. Render → New → Blueprint → pick the repo. After the first deploy set the env vars
marked `sync: false` in the dashboard (`FRONTEND_URL`, `RESEND_API_KEY`, `EMAIL_FROM`, `ANTHROPIC_API_KEY`, the
Google / Microsoft OAuth keys). Migrations run automatically at startup (`alembic upgrade head`).

Then update the OAuth redirect URIs to the Render URL:
- Google: `https://<api>.onrender.com/api/auth/google/callback` and `.../api/integrations/oauth/callback/google`
- Microsoft: `https://<api>.onrender.com/api/integrations/oauth/callback/outlook`
- Meta WhatsApp webhook: `https://<api>.onrender.com/api/webhooks/whatsapp`

`RENDER_EXTERNAL_URL` is set by Render and used as `BACKEND_URL` automatically. `TRUST_PROXY_HEADERS=true` makes the
auth rate limiter see real client IPs behind Render's proxy. `WEB_CONCURRENCY=2` runs two workers; the senders are
safe to run in several workers (`services/send_lock.py`).

## API anywhere else (Docker)

```bash
docker build -t leadnius-api -f lead-gen-backend/Dockerfile lead-gen-backend
docker run --env-file lead-gen-backend/.env -e DEV_MODE=false -p 8000:8000 leadnius-api
```

`DATABASE_URL` may be `postgres://…`; it is rewritten to the asyncpg driver. Set `SECRET_KEY` to a random string of
32+ characters before the first real user: rotating it later logs everyone out and invalidates the encrypted inbox
passwords / OAuth tokens (they have to reconnect).

## Web app on Vercel

Import `lead-gen-frontend` as a Vercel project (framework: Next.js). Env: `NEXT_PUBLIC_API_URL=https://<api>.onrender.com`.
CORS in `main.py` already allows `*.vercel.app`, `*.render.com` and `*.leadnius.in`; add the final domain to
`FRONTEND_URL` on the API so OAuth and email links point at it.

## Before going live checklist

- `DEV_MODE=false` (no demo seeding, real sends by default)
- `EMAIL_DRY_RUN=false`, `WHATSAPP_DRY_RUN=false` when you really want to send
- Transactional email configured (`RESEND_API_KEY` or SMTP) so signup verification and password reset work
- Google OAuth app moved from *Testing* to *Production* (restricted Gmail scope → Google verification) if customers
  other than your test users will connect Gmail
- Microsoft: SMTP AUTH enabled on connecting mailboxes
- Meta: WhatsApp business verification + an approved message template
- Run the test suite: `cd lead-gen-backend && venv/bin/python -m pytest`
